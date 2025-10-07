import os
import re
import sys
import time
import threading
import traceback
from collections import deque
from typing import List, Deque, Dict, Set, Tuple

import mwparserfromhell
from markdownify import markdownify
import yaml

from .api import MediaWikiApi
from .state import State
from .utils import make_dir, sanitize_filename, atomic_write_text, atomic_write_bytes

BATCH_SIZE = 50
MAX_RECURSION_DEPTH = 10

class MediaWikiExporter:
    """Orchestrates a robust export using a powerful, direct WikiText parsing engine."""

    def __init__(self, api_url: str, output_dir: str, **kwargs):
        self.api = MediaWikiApi(api_url=api_url, **kwargs)
        self.state = State(output_dir)
        self._stop_event = threading.Event()
        self._log_lines: Deque[str] = deque(maxlen=2000)
        self.template_cache: Dict[str, str] = {}
        self.run_visited_categories: Set[str] = set()
        
        # --- FIX: Restore the persistent log file logic ---
        self.log_file_path = os.path.join(output_dir, 'debug.log')
        self.log_file = open(self.log_file_path, 'a', encoding='utf-8')

        self.pages_dir = os.path.join(output_dir, 'pages'); make_dir(self.pages_dir)
        self.media_dir = os.path.join(output_dir, 'media'); make_dir(self.media_dir)
        self.templates_dir = os.path.join(output_dir, 'templates'); make_dir(self.templates_dir)
        self.state.load()
        self.log(f"--- New Run Started ---")
        self.log(f"Resumed state with {len(self.state.image_versions)} images tracked.")

    # --- FIX: Restore the log method to write to file ---
    def log(self, *parts):
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {' '.join(str(p) for p in parts)}"
        self._log_lines.append(log_entry)
        if self.log_file:
            self.log_file.write(log_entry + '\n')
            self.log_file.flush()

    # --- FIX: Restore the close_log method ---
    def close_log(self):
        """Closes the persistent log file."""
        self.log(f"--- Run Finished ---")
        if self.log_file:
            self.log_file.close()
            self.log_file = None
            
    def get_log_lines(self) -> List[str]: return list(self._log_lines)
    def report(self): return self.state.get_report()
    def request_stop(self): self.log("Stop requested..."); self._stop_event.set()

    def run(self, root_category: str):
        page_q, tmpl_q, img_q, cat_q = deque(), deque(), deque(), deque([root_category])
        queued_p, queued_t = set(), set()
        try:
            while cat_q or page_q or tmpl_q or img_q:
                if self._stop_event.is_set(): break
                if cat_q: self._discover(cat_q, page_q, tmpl_q, img_q, queued_p, queued_t)
                if page_q: self._process_content_batch('page', page_q)
                if tmpl_q: self._process_content_batch('template', tmpl_q)
                if img_q: self._process_image_batch(img_q)
                if not any([cat_q, page_q, tmpl_q, img_q]): time.sleep(0.1)
        except Exception as e:
            self.log(f"FATAL WORKER ERROR: {type(e).__name__}: {e}")
            self.log("--- TRACEBACK ---"); [self.log(line) for line in traceback.format_exc().splitlines()]; self.log("--- END TRACEBACK ---")
        finally:
            self.log("Worker finished. Saving final state."); self.state.save()

    def _discover(self, cat_q, page_q, tmpl_q, img_q, queued_p, queued_t):
        category = cat_q.popleft()
        if category in self.run_visited_categories: return
        self.run_visited_categories.add(category)
        with self.state._lock: self.state.categories_traversed_count += 1
        self.log(f"Traversing category: {category}")
        cmcontinue = None
        while not self._stop_event.is_set():
            params = {'action': 'query', 'list': 'categorymembers', 'cmtitle': f'Category:{category}', 'cmlimit': 'max'}
            if cmcontinue: params['cmcontinue'] = cmcontinue
            data = self.api.request(params, self._stop_event)
            if not data: break
            for member in data.get('query', {}).get('categorymembers', []):
                title, ns = member.get('title'), member.get('ns')
                if not title: continue
                if ns == 14: cat_q.append(title.split(':', 1)[-1])
                elif ns == 6: img_q.append(title)
                elif ns == 10:
                    if title not in queued_t: tmpl_q.append(title); queued_t.add(title)
                else:
                    if title not in queued_p: page_q.append(title); queued_p.add(title)
            cont = data.get('continue'); cmcontinue = cont.get('cmcontinue') if cont else None
            if not cmcontinue: break
    
    def _process_content_batch(self, kind: str, queue: Deque[str]):
        batch = [queue.popleft() for _ in range(min(BATCH_SIZE, len(queue)))]
        if not batch: return
        self.log(f"Processing batch of {len(batch)} {kind}s...")
        params = {'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'titles': '|'.join(batch)}
        data = self.api.request(params, self._stop_event)
        if not data: return
        for page_data in data.get('query', {}).get('pages', []):
            if 'revisions' not in page_data: continue
            title, wikitext = page_data['title'], page_data['revisions'][0].get('content', '')
            self._save_markdown_file(title, wikitext, kind)
        self.state.save()

    def _process_image_batch(self, image_queue: Deque[str]):
        batch = [image_queue.popleft() for _ in range(min(BATCH_SIZE, len(image_queue)))]
        if not batch: return
        self.log(f"Checking for updates on {len(batch)} images...")
        params = {'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|sha1', 'titles': '|'.join(batch)}
        data = self.api.request(params, self._stop_event)
        if not data: return
        for page in data.get('query', {}).get('pages', []):
            if 'imageinfo' not in page: continue
            info = page['imageinfo'][0]
            title, url, new_hash = page['title'], info.get('url'), info.get('sha1')
            if url and new_hash and self.state.needs_image_update(title, new_hash):
                self._download_media(url, title, new_hash)

    def _render_wikitext(self, wikitext: str, depth=0) -> Tuple[str, List[str], List[Dict]]:
        if depth > MAX_RECURSION_DEPTH: return "[[TEMPLATE RECURSION LIMIT EXCEEDED]]", [], []
        
        parsed = mwparserfromhell.parse(wikitext)
        categories, images = [], []

        for T in parsed.filter_templates():
            t_name = str(T.name).strip()
            if t_name not in self.template_cache:
                params = {'action': 'query', 'prop': 'revisions', 'rvprop': 'content', 'titles': f"Template:{t_name}"}
                data = self.api.request(params, self._stop_event)
                content = ""
                if data and 'query' in data and (page := next(iter(data['query'].get('pages', [])), None)) and 'revisions' in page:
                    content = page['revisions'][0].get('content', f"''Template:{t_name} not found''")
                self.template_cache[t_name] = content
            
            expanded_template, _, _ = self._render_wikitext(self.template_cache.get(t_name, ''), depth + 1)
            parsed.replace(T, expanded_template)

        for node in parsed.nodes:
            if isinstance(node, mwparserfromhell.nodes.Heading):
                parsed.replace(node, f"{'#' * node.level} {str(node.title).strip()}")
            elif isinstance(node, mwparserfromhell.nodes.Tag) and node.tag == 'i':
                parsed.replace(node, f"*{str(node.contents).strip()}*")
            elif isinstance(node, mwparserfromhell.nodes.Wikilink):
                link_title, link_text = str(node.title).strip(), str(node.text or node.title).strip()
                if link_title.startswith("Category:"):
                    categories.append(link_title.split(":", 1)[-1].strip())
                    parsed.remove(node)
                elif link_title.startswith(("File:", "Image:")):
                    filename = link_title.split(":", 1)[-1].strip()
                    images.append({'name': filename, 'path': f"../media/{sanitize_filename(filename)}"})
                    parsed.replace(node, f"![{link_text}](../media/{sanitize_filename(filename)})")
                else:
                    parsed.replace(node, f"[{link_text}](./{sanitize_filename(link_title)}.md)")
        
        final_text = str(parsed)
        final_text = re.sub(r"'''(.*?)'''", r'**\1**', final_text)
        final_text = re.sub(r"''(.*?)''", r'*\1*', final_text)
        
        final_text = str(parsed)
        final_text = re.sub(r"'''(.*?)'''", r'**\1**', final_text)
        final_text = re.sub(r"''(.*?)''", r'*\1*', final_text)

        return final_text.strip(), categories, images

    def _save_markdown_file(self, title: str, wikitext: str, kind: str):
        try:
            markdown_body, categories, images = self._render_wikitext(wikitext)
            frontmatter = {'title': title, 'kind': kind, 'categories': sorted(list(set(categories))), 'images': images}
            full_content = f"---\n{yaml.dump(frontmatter, allow_unicode=True, sort_keys=False)}---\n\n{markdown_body}\n\n```mediawiki\n{wikitext}\n```"
            outdir = self.templates_dir if kind == 'template' else self.pages_dir
            atomic_write_text(os.path.join(outdir, sanitize_filename(title) + '.md'), full_content)
            self.state.increment_written_counter(kind)
            self.log('Wrote', kind, title)
        except Exception as e:
            self.log(f"ERROR processing content for '{title}': {e}"); traceback.print_exc()

    def _download_media(self, url: str, title: str, new_hash: str):
        self.log(f"Downloading media: {title}")
        dest_path = os.path.join(self.media_dir, sanitize_filename(title.split(':', 1)[-1]))
        def streamer():
            with self.api.session.get(url, stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(8192):
                    if self._stop_event.is_set(): break; yield chunk
        try:
            atomic_write_bytes(dest_path, streamer)
            self.state.update_image_hash(title, new_hash)
        except Exception as e:
            self.log(f"Failed to download {url}: {e}")