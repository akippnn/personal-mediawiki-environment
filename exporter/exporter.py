import os
import re
import sys
import time
import threading
import traceback
from collections import deque
from typing import List, Deque, Dict, Set, Tuple

import mwparserfromhell
import requests
import yaml

from api import MediaWikiApi
from state import State
from utils import make_dir, sanitize_filename, atomic_write_text, atomic_write_bytes

BATCH_SIZE = 50
MAX_RECURSION_DEPTH = 10

class MediaWikiExporter:
    """Orchestrates a robust export using direct WikiText parsing or XML dump."""

    def __init__(self, api_url: str, output_dir: str, **kwargs):
        self.api = MediaWikiApi(api_url=api_url, **kwargs)
        self.state = State(output_dir)
        self._stop_event = threading.Event()
        self._log_lines: Deque[str] = deque(maxlen=2000)
        self.template_cache: Dict[str, str] = {}
        self.run_visited_categories: Set[str] = set()
        
        # Ensure output directory exists
        make_dir(output_dir)
        
        # --- FIX: Restore the persistent log file logic ---
        self.log_file_path = os.path.join(output_dir, 'debug.log')
        self.log_file = open(self.log_file_path, 'a', encoding='utf-8')

        self.pages_dir = os.path.join(output_dir, 'pages')
        self.media_dir = os.path.join(output_dir, 'media')
        self.templates_dir = os.path.join(output_dir, 'templates')
        self.xml_dir = os.path.join(output_dir, 'xml')

        # Create dirs if they don't exist
        for d in [self.pages_dir, self.media_dir, self.templates_dir, self.xml_dir]:
            make_dir(d)

        self.state.load()
        self.log(f"--- New Run Started ---")
        self.log(f"Resumed state with {len(self.state.image_versions)} images tracked.")

    # --- FIX: Restore the log method to write to file ---
    def log(self, *parts):
        log_entry = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {' '.join(str(p) for p in parts)}"
        self._log_lines.append(log_entry)
        # Print to console for real-time feedback
        print(log_entry)
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

    def run(self, root_category: str = None, scope: str = 'category', export_format: str = 'markdown'):
        """
        Runs the export process.
        scope: 'category' (default) or 'all'
        export_format: 'markdown' (default) or 'xml'
        """
        self.log(f"Starting export with scope={scope}, format={export_format}")
        
        # 1. Discover Pages
        all_pages = set()
        all_images = set()

        if scope == 'all':
            self.log("Discovering ALL pages in the wiki...")
            all_pages = self._discover_all_pages()
            self.log(f"Found {len(all_pages)} total pages.")
        else:
            if not root_category:
                raise ValueError("root_category is required when scope='category'")
            # Original discovery logic...
            # We'll adapt the original logic to just populate sets first, then process.
            # For backward compatibility with the 'live' queue processing, we can stick to the original flow
            # IF format is markdown. But for XML, we usually want to batch export everything.
            pass # We will use the queue system for category discovery below if needed.

        # 2. Extract Extensions (if 'all' scope or requested)
        if scope == 'all':
            self._export_extensions()

        # 3. Process Content
        if export_format == 'xml':
            if scope == 'category':
                 # Use the queue-based discovery for category, then export XML batches
                 self._run_category_discovery_and_xml_export(root_category)
            else:
                self._batch_export_xml(list(all_pages))
            
            # Also download images for XML export
            self.log("Discovering images...")
            all_images = self._discover_all_images()
            self.log(f"Found {len(all_images)} images to check.")
            if all_images:
                img_q = deque(all_images)
                while img_q and not self._stop_event.is_set():
                    self._process_image_batch(img_q)
                
        else:
            # Markdown export (Original logic)
            if scope == 'all':
                # Populate queues from discovery and process
                page_q = deque(p for p in all_pages if not p.startswith("File:") and not p.startswith("Template:"))
                tmpl_q = deque(p for p in all_pages if p.startswith("Template:"))
                img_q = deque(p for p in all_pages if p.startswith("File:"))
                self.log(f"Queued {len(page_q)} pages, {len(tmpl_q)} templates, {len(img_q)} images.")
                
                # Process sequentially as we already have the full list
                while page_q: self._process_content_batch('page', page_q)
                while tmpl_q: self._process_content_batch('template', tmpl_q)
                while img_q: self._process_image_batch(img_q)
            else:
                # Original category crawler
                self._run_original_category_loop(root_category)
        
        self.log("Worker finished. Saving final state."); self.state.save()

    def _run_original_category_loop(self, root_category):
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

    def _run_category_discovery_and_xml_export(self, root_category):
        # Discover all items in category first, then export
        self.log("Discovering category members for XML export...")
        # Re-using discovery logic but collecting titles
        visited = set()
        queue = deque([root_category])
        titles_to_export = set()
        
        while queue:
            cat = queue.popleft()
            if cat in visited: continue
            visited.add(cat)
            self.log(f"Scanning Category:{cat}")
            
            # Simple manual iteration logic reuse or new one? 
            # Let's perform a direct API walk similar to _discover but deeper
            cmcontinue = None
            while not self._stop_event.is_set():
                params = {'action': 'query', 'list': 'categorymembers', 'cmtitle': f'Category:{cat}', 'cmlimit': 'max'}
                if cmcontinue: params['cmcontinue'] = cmcontinue
                data = self.api.request(params, self._stop_event)
                if not data: break
                for m in data.get('query', {}).get('categorymembers', []):
                    t = m.get('title')
                    ns = m.get('ns')
                    if not t: continue
                    titles_to_export.add(t)
                    if ns == 14: # Category
                        c_name = t.split(':', 1)[-1]
                        if c_name not in visited: queue.append(c_name)
                
                if 'continue' not in data: break
                cmcontinue = data['continue'].get('cmcontinue')
        
        self.log(f"Discovery complete. Found {len(titles_to_export)} items. Starting XML export...")
        self._batch_export_xml(list(titles_to_export))

    def _discover_all_pages(self) -> Set[str]:
        """
        Discovers ALL pages in the wiki across all namespaces.
        MediaWiki namespaces: 0=Main, 1=Talk, 2=User, 3=User talk, 4=Project,
        6=File, 8=MediaWiki, 10=Template, 12=Help, 14=Category, 828=Module
        """
        pages = set()
        
        # First, get the list of all namespaces from the wiki
        self.log("Fetching namespace list...")
        ns_data = self.api.request({'action': 'query', 'meta': 'siteinfo', 'siprop': 'namespaces'}, self._stop_event)
        if not ns_data:
            self.log("Failed to fetch namespaces, using defaults")
            namespaces = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 828]
        else:
            namespaces = [int(ns) for ns in ns_data.get('query', {}).get('namespaces', {}).keys() if ns != '-1' and ns != '-2']
        
        self.log(f"Will query {len(namespaces)} namespaces: {namespaces[:10]}...")
        
        # Query each namespace
        for ns in namespaces:
            if self._stop_event.is_set(): break
            if ns < 0: continue  # Skip special namespaces
            
            apcontinue = None
            ns_count = 0
            while not self._stop_event.is_set():
                params = {
                    'action': 'query',
                    'list': 'allpages',
                    'aplimit': 'max',
                    'apnamespace': ns
                }
                if apcontinue: params['apcontinue'] = apcontinue
                data = self.api.request(params, self._stop_event)
                if not data: break
                
                for p in data.get('query', {}).get('allpages', []):
                    pages.add(p['title'])
                    ns_count += 1
                
                if 'continue' not in data: break
                apcontinue = data['continue'].get('apcontinue')
            
            if ns_count > 0:
                self.log(f"  Namespace {ns}: {ns_count} pages")
        
        return pages

    def _discover_all_images(self) -> Set[str]:
        """Discovers all images in the wiki using allimages API."""
        images = set()
        aicontinue = None
        while not self._stop_event.is_set():
            params = {'action': 'query', 'list': 'allimages', 'ailimit': 'max'}
            if aicontinue: params['aicontinue'] = aicontinue
            data = self.api.request(params, self._stop_event)
            if not data: break
            
            for img in data.get('query', {}).get('allimages', []):
                images.add(f"File:{img['name']}")
            
            if 'continue' not in data: break
            aicontinue = data['continue'].get('aicontinue')
        
        return images

    def _export_extensions(self):
        self.log("Fetching site info for extensions...")
        data = self.api.request({'action': 'query', 'meta': 'siteinfo', 'siprop': 'extensions'}, self._stop_event)
        if data and 'query' in data and 'extensions' in data['query']:
            exts = data['query']['extensions']
            self.log(f"Found {len(exts)} extensions.")
            atomic_write_text(os.path.join(self.state.output_dir, 'extensions.yaml'), yaml.dump(exts))
            
            # Write a simple list for shell scripts
            ext_names = [e['name'] for e in exts if 'name' in e]
            atomic_write_text(os.path.join(self.state.output_dir, 'extensions.txt'), '\n'.join(ext_names))
        else:
            self.log("Could not fetch extensions info.")

    def _batch_export_xml(self, titles: List[str]):
        """
        Exports pages to XML format with efficient revision-based diffing.
        Skips pages that haven't changed since last export.
        """
        # Step 1: Query revisions for all titles to determine what needs updating
        self.log(f"Checking {len(titles)} pages for changes...")
        titles_to_export = self._filter_changed_pages(titles)
        
        if not titles_to_export:
            self.log("No changes detected. All pages are up to date.")
            return
        
        self.log(f"Found {len(titles_to_export)} pages with changes (skipped {len(titles) - len(titles_to_export)} unchanged).")
        
        # Step 2: Export only changed pages in chunks
        chunk_size = 50
        for i in range(0, len(titles_to_export), chunk_size):
            if self._stop_event.is_set(): break
            batch = titles_to_export[i:i+chunk_size]
            self.log(f"Exporting XML batch {i//chunk_size + 1}/{len(titles_to_export)//chunk_size + 1} ({len(batch)} titles)...")
            
            params = {
                'action': 'query',
                'export': '1',
                'exportnowrap': '1',
                'titles': '|'.join(batch)
            }
            
            try:
                resp = self.api.session.post(self.api.api_url, data=params, timeout=60)
                resp.raise_for_status()
                filename = f"export_{i}.xml"
                atomic_write_text(os.path.join(self.xml_dir, filename), resp.text)
                self.log(f"Saved {filename}")
            except Exception as e:
                self.log(f"Failed to export XML batch: {e}")

    def _filter_changed_pages(self, titles: List[str]) -> List[str]:
        """
        Queries the API for current revision IDs and filters to only pages that have changed.
        Updates state with new revision IDs for exported pages.
        """
        changed = []
        chunk_size = 50  # API limit for titles
        
        for i in range(0, len(titles), chunk_size):
            if self._stop_event.is_set(): break
            batch = titles[i:i+chunk_size]
            
            params = {
                'action': 'query',
                'prop': 'revisions',
                'rvprop': 'ids',  # Only get revision IDs, not content
                'titles': '|'.join(batch)
            }
            
            data = self.api.request(params, self._stop_event)
            if not data: continue
            
            for page in data.get('query', {}).get('pages', []):
                title = page.get('title')
                if not title or 'missing' in page: continue
                
                revisions = page.get('revisions', [])
                if not revisions: continue
                
                revid = revisions[0].get('revid')
                if revid and self.state.needs_page_update(title, revid):
                    changed.append(title)
                    # Update state immediately so next run knows
                    self.state.update_page_revision(title, revid)
        
        return changed

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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        batch = [image_queue.popleft() for _ in range(min(BATCH_SIZE, len(image_queue)))]
        if not batch: return
        self.log(f"Checking for updates on {len(batch)} images...")
        params = {'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|sha1', 'titles': '|'.join(batch)}
        data = self.api.request(params, self._stop_event)
        if not data: return
        
        # Collect images that need downloading
        to_download = []
        for page in data.get('query', {}).get('pages', []):
            if 'imageinfo' not in page: continue
            info = page['imageinfo'][0]
            title, url, new_hash = page['title'], info.get('url'), info.get('sha1')
            if url and new_hash and self.state.needs_image_update(title, new_hash):
                to_download.append((url, title, new_hash))
        
        if not to_download:
            return
        
        self.log(f"Downloading {len(to_download)} images (parallel, 4 workers)...")
        
        # Download in parallel with 4 workers
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(self._download_media, url, title, new_hash): title 
                      for url, title, new_hash in to_download}
            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break
                try:
                    future.result()
                except Exception as e:
                    self.log(f"Download error: {e}")
        
        # Small delay between batches to be polite
        time.sleep(0.5)

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
                pages = data.get('query', {}).get('pages', {}) if data else {}
                if pages:
                    page_data = next(iter(pages.values()))
                    if 'revisions' in page_data:
                        content = page_data['revisions'][0].get('content', f"''Template:{t_name} not found''")
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
                    alt_text = link_text if node.text else filename
                    parsed.replace(node, f"![{alt_text}](../media/{sanitize_filename(filename)})")
                else:
                    parsed.replace(node, f"[{link_text}](./{sanitize_filename(link_title)}.md)")
        
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
        
        try:
            # Use a fresh request (not the API session) for CDN downloads
            resp = requests.get(url, stream=True, timeout=60, headers={
                'User-Agent': 'PortableMediaWikiEditor/1.0'
            })
            resp.raise_for_status()
            
            # Write directly to file
            with open(dest_path, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if self._stop_event.is_set():
                        break
                    if chunk:
                        f.write(chunk)
            
            # Verify file was written
            file_size = os.path.getsize(dest_path)
            if file_size > 0:
                self.state.update_image_hash(title, new_hash)
                self.log(f"  ✓ {title} ({file_size} bytes)")
            else:
                self.log(f"  ⚠ {title} - empty file")
                os.remove(dest_path)
                
        except Exception as e:
            self.log(f"Failed to download {title}: {e}")