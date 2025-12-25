"""
Syncer - Push changes from local to remote wiki

Optimized for large wikis (10k+ pages):
- Batched page enumeration (generators)
- Parallel page comparison
- Progress logging
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import from core
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import MediaWikiClient, get_logger

BATCH_SIZE = 50
MAX_WORKERS = 4

class Syncer:
    """
    Handles the 'Push' logic:
    1. Enumerate local pages with generators (batched)
    2. Compare with remote in parallel
    3. Push changes
    """
    def __init__(self, local_api: MediaWikiClient, remote_api: MediaWikiClient):
        self.local = local_api
        self.remote = remote_api
        self.logger = get_logger('syncer')
        self.stats = {'checked': 0, 'pushed': 0, 'skipped': 0, 'failed': 0}

    def push(self):
        """Performs the push operation with batching and parallelism."""
        print("Analyzing local changes...")
        
        total = 0
        for batch in self._enumerate_pages_batched():
            total += len(batch)
            print(f"Checking batch of {len(batch)} pages (total: {total})...")
            self._process_batch(batch)
        
        self._print_summary()

    def _enumerate_pages_batched(self):
        """Generator that yields batches of page titles."""
        apcontinue = None
        while True:
            params = {
                'action': 'query',
                'list': 'allpages',
                'aplimit': BATCH_SIZE
            }
            if apcontinue:
                params['apcontinue'] = apcontinue
            
            data = self.local.request(params)
            if not data:
                break
            
            pages = data.get('query', {}).get('allpages', [])
            if pages:
                yield [p['title'] for p in pages]
            
            if 'continue' not in data:
                break
            apcontinue = data['continue'].get('apcontinue')

    def _process_batch(self, titles: list):
        """Process a batch of pages in parallel."""
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(self._sync_page, title): title for title in titles}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    title = futures[future]
                    print(f"[ERROR] Exception for '{title}': {e}")
                    self.stats['failed'] += 1

    def _sync_page(self, title: str):
        """Sync a single page."""
        self.stats['checked'] += 1
        
        # Get Local Content & Time
        local_info = self._get_page_info(self.local, title)
        if not local_info:
            return
        
        # Get Remote Content & Time
        remote_info = self._get_page_info(self.remote, title)
        
        should_push = False
        reason = ""
        
        if not remote_info:
            should_push = True
            reason = "New Page"
        else:
            l_ts = local_info['timestamp']
            r_ts = remote_info['timestamp']
            
            if l_ts > r_ts:
                if local_info['content'] != remote_info['content']:
                    should_push = True
                    reason = f"Local newer"
            elif l_ts < r_ts:
                self.stats['skipped'] += 1
                return

        if should_push:
            print(f"[PUSH] '{title}': {reason}")
            success = self.remote.edit_page(
                title=title,
                text=local_info['content'],
                summary=f"Sync Manager Push: {reason}"
            )
            if success:
                self.stats['pushed'] += 1
            else:
                self.stats['failed'] += 1
        else:
            self.stats['skipped'] += 1

    def _get_page_info(self, api, title):
        """Helper to get content and timestamp of a page."""
        params = {
            'action': 'query',
            'prop': 'revisions',
            'rvprop': 'content|timestamp',
            'titles': title
        }
        try:
            data = api.request(params)
            pages = data.get('query', {}).get('pages', [])
            if not pages:
                return None
            
            page = pages[0]
            if 'missing' in page:
                return None
            
            rev = page.get('revisions', [])[0]
            return {
                'timestamp': rev.get('timestamp'),
                'content': rev.get('content')
            }
        except Exception as e:
            return None

    def _print_summary(self):
        """Print push summary."""
        print("\n" + "=" * 40)
        print("Push Summary")
        print("=" * 40)
        print(f"  Checked:  {self.stats['checked']}")
        print(f"  Pushed:   {self.stats['pushed']}")
        print(f"  Skipped:  {self.stats['skipped']}")
        print(f"  Failed:   {self.stats['failed']}")
        print("=" * 40)
