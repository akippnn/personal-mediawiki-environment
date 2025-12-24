import os
from datetime import datetime
from .api import SyncApi

class Syncer:
    """
    Handles the 'Push' logic:
    1. Gets all pages from Local (Portable Wiki).
    2. Gets corresponding pages from Remote.
    3. Compares timestamps/content.
    4. Pushes changes.
    """
    def __init__(self, local_api: SyncApi, remote_api: SyncApi):
        self.local = local_api
        self.remote = remote_api

    def push(self):
        """Performs the push operation."""
        print("Analyizing local changes...")
        
        # 1. Get all local pages
        # We assume local is small enough to get all pages. 
        # For larger wikis, generators/iterators would be better.
        params = {'action': 'query', 'list': 'allpages', 'aplimit': 'max'}
        data = self.local.request(params)
        local_pages = data.get('query', {}).get('allpages', [])
        
        print(f"Found {len(local_pages)} local pages to check.")
        
        for page in local_pages:
            title = page['title']
            self._sync_page(title)

    def _sync_page(self, title):
        # Get Local Content & Time
        local_info = self._get_page_info(self.local, title)
        if not local_info: return # Should not happen if discovered via allpages
        
        # Get Remote Content & Time
        # Only fetch metadata first to save bandwidth if possible? 
        # We need timestamp.
        remote_info = self._get_page_info(self.remote, title)
        
        should_push = False
        reason = ""
        
        if not remote_info:
            should_push = True
            reason = "New Page"
        else:
            # Compare Timestamps
            # ISO format: 2025-12-23T12:00:00Z
            l_ts = local_info['timestamp']
            r_ts = remote_info['timestamp']
            
            if l_ts > r_ts:
                # Local is newer. But is content different?
                if local_info['content'] != remote_info['content']:
                    should_push = True
                    reason = f"Local newer ({l_ts} > {r_ts})"
                else:
                    # Timestamps differ but content same? No push needed.
                    pass
            elif l_ts < r_ts:
                print(f"[SKIP] Remote is newer for '{title}' ({r_ts} > {l_ts}). Pull required.")
                return
            else:
                # Same timestamp
                pass

        if should_push:
            print(f"[PUSH] '{title}': {reason}")
            success = self.remote.edit_page(
                title=title,
                text=local_info['content'],
                summary=f"Sync Manager Push: {reason}"
            )
            if success:
                print(f"[SUCCESS] Pushed '{title}'.")
            else:
                print(f"[FAILED] Could not push '{title}'.")

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
            if not pages: return None
            
            page = pages[0]
            if 'missing' in page: return None
            
            rev = page.get('revisions', [])[0]
            return {
                'timestamp': rev.get('timestamp'),
                'content': rev.get('content')
            }
        except Exception as e:
            # If local/remote fails, we log and return None
            print(f"Error fetching info for '{title}': {e}")
            return None
