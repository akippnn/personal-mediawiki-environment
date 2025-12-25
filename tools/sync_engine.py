"""
Sync Engine - Fetch/Pull logic with conflict resolution
"""
import os
import shutil
import subprocess
import yaml
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field

@dataclass
class PageState:
    """Tracks revision state for a single page."""
    base_revid: int = 0
    local_revid: int = 0
    remote_revid: int = 0
    status: str = "clean"  # clean, modified, conflict, new

@dataclass
class SyncState:
    """Tracks sync state for a wiki."""
    last_fetch: Optional[str] = None
    last_sync: Optional[str] = None  # When import completed
    pages: Dict[str, PageState] = field(default_factory=dict)
    
    def save(self, path: str):
        data = {
            'last_fetch': self.last_fetch,
            'last_sync': self.last_sync,
            'pages': {
                name: {
                    'base_revid': p.base_revid,
                    'local_revid': p.local_revid,
                    'remote_revid': p.remote_revid,
                    'status': p.status
                }
                for name, p in self.pages.items()
            }
        }
        with open(path, 'w') as f:
            yaml.dump(data, f)
    
    @classmethod
    def load(cls, path: str) -> 'SyncState':
        if not os.path.exists(path):
            return cls()
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        state = cls(
            last_fetch=data.get('last_fetch'),
            last_sync=data.get('last_sync')
        )
        for name, p in data.get('pages', {}).items():
            state.pages[name] = PageState(
                base_revid=p.get('base_revid', 0),
                local_revid=p.get('local_revid', 0),
                remote_revid=p.get('remote_revid', 0),
                status=p.get('status', 'clean')
            )
        return state


class SyncEngine:
    """Handles fetch/pull operations with conflict detection."""
    
    def __init__(self, wiki_path: str, api_url: str):
        self.wiki_path = wiki_path
        self.api_url = api_url
        self.data_dir = os.path.join(wiki_path, 'data')
        self.tmp_dir = os.path.join(wiki_path, '.tmp')
        self.conflict_dir = os.path.join(wiki_path, 'conflicts')
        self.state_file = os.path.join(wiki_path, 'sync_state.yaml')
        self.state = SyncState.load(self.state_file)

    def has_incomplete_fetch(self) -> bool:
        """Check if there's an incomplete fetch (orphaned .tmp dir)."""
        return os.path.exists(self.tmp_dir)

    def discard_incomplete_fetch(self):
        """Remove orphaned .tmp directory."""
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir)
            print("Discarded incomplete fetch data.")

    # =========================================================================
    # LOCAL CHANGE DETECTION
    # =========================================================================
    
    def get_local_revisions(self, local_api_url: str = 'http://localhost:8080/api.php') -> Dict[str, int]:
        """
        Query local wiki for current revision IDs of all pages.
        Returns dict: {page_title: revision_id}
        """
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core import MediaWikiClient
        
        client = MediaWikiClient(local_api_url)
        revisions = {}
        
        # Query all pages with their revision IDs
        continue_token = None
        while True:
            params = {
                'action': 'query',
                'generator': 'allpages',
                'gaplimit': 'max',
                'prop': 'revisions',
                'rvprop': 'ids'
            }
            if continue_token:
                params['gapcontinue'] = continue_token
            
            data = client.request(params)
            if not data:
                break
            
            pages = data.get('query', {}).get('pages', {})
            for page_id, page in pages.items():
                title = page.get('title')
                if title and 'revisions' in page:
                    revisions[title] = page['revisions'][0]['revid']
            
            # Check for continuation
            if 'continue' in data:
                continue_token = data['continue'].get('gapcontinue')
            else:
                break
        
        return revisions
    
    def update_local_revisions(self, local_api_url: str = 'http://localhost:8080/api.php'):
        """
        Query local wiki and update sync_state with current local revisions.
        Call this after sync/import completes.
        """
        print("Recording local wiki revision state...")
        revisions = self.get_local_revisions(local_api_url)
        
        for title, revid in revisions.items():
            if title not in self.state.pages:
                self.state.pages[title] = PageState()
            self.state.pages[title].local_revid = revid
            # On fresh sync, base_revid = local_revid
            if self.state.pages[title].base_revid == 0:
                self.state.pages[title].base_revid = revid
        
        self.state.last_sync = datetime.now().isoformat()
        self.state.save(self.state_file)
        print(f"Recorded {len(revisions)} page revisions.")
    
    def get_local_changes(self, local_api_url: str = 'http://localhost:8080/api.php') -> List[str]:
        """
        Detect pages modified locally since last sync.
        Returns list of modified page titles.
        """
        current_revs = self.get_local_revisions(local_api_url)
        modified = []
        
        for title, revid in current_revs.items():
            if title in self.state.pages:
                if revid != self.state.pages[title].local_revid:
                    modified.append(title)
            else:
                # New page created locally
                modified.append(title)
        
        return modified

    def fetch(self, exporter_func) -> Dict:
        """
        Fetch remote changes to .tmp directory.
        Returns summary of changes.
        """
        # Clean up any previous incomplete fetch
        self.discard_incomplete_fetch()
        
        # Create .tmp directory
        os.makedirs(self.tmp_dir, exist_ok=True)
        tmp_data = os.path.join(self.tmp_dir, 'data')
        
        print(f"Fetching from {self.api_url}...")
        
        # Run exporter to .tmp/data
        exporter_func(self.api_url, tmp_data)
        
        # Parse and compare
        local_pages = self._parse_all_xml(os.path.join(self.data_dir, 'xml'))
        remote_pages = self._parse_all_xml(os.path.join(tmp_data, 'xml'))
        
        summary = {
            'new': [],
            'modified': [],
            'conflicts': [],
            'deleted': []
        }
        
        # First fetch? (no existing state)
        is_first_fetch = len(self.state.pages) == 0
        
        # Check remote pages
        for title, remote_rev in remote_pages.items():
            local_rev = local_pages.get(title, 0)
            page_state = self.state.pages.get(title, PageState())
            
            if is_first_fetch:
                # First fetch: local is now our base, no conflicts possible
                page_state.base_revid = local_rev
                page_state.local_revid = local_rev
                page_state.remote_revid = remote_rev
                if remote_rev != local_rev:
                    summary['modified'].append(title)
                    page_state.status = 'modified'
                else:
                    page_state.status = 'clean'
            else:
                # Subsequent fetch: compare against base
                if local_rev == 0:
                    # New page from remote
                    summary['new'].append(title)
                    page_state.remote_revid = remote_rev
                    page_state.status = 'new'
                elif remote_rev != page_state.base_revid:
                    # Remote has changes since base
                    if local_rev != page_state.base_revid:
                        # Local also changed - CONFLICT
                        summary['conflicts'].append(title)
                        page_state.status = 'conflict'
                    else:
                        # Only remote modified
                        summary['modified'].append(title)
                        page_state.status = 'modified'
                    page_state.remote_revid = remote_rev
                else:
                    page_state.status = 'clean'
                
                page_state.local_revid = local_rev
            
            self.state.pages[title] = page_state
        
        # Check for deletions
        for title in local_pages:
            if title not in remote_pages:
                summary['deleted'].append(title)
        
        # Save state to .tmp
        self.state.last_fetch = datetime.now().isoformat()
        tmp_state_file = os.path.join(self.tmp_dir, 'sync_state.yaml')
        self.state.save(tmp_state_file)
        
        return summary

    def pull(self) -> Dict:
        """
        Pull fetched changes into local data.
        Creates conflict files for conflicts.
        Returns summary.
        """
        if not self.has_incomplete_fetch():
            print("No fetched data. Run 'fetch' first.")
            return {}
        
        tmp_data = os.path.join(self.tmp_dir, 'data')
        summary = {'merged': [], 'conflicts': []}
        
        # Load temp state
        tmp_state_file = os.path.join(self.tmp_dir, 'sync_state.yaml')
        tmp_state = SyncState.load(tmp_state_file)
        
        for title, page_state in tmp_state.pages.items():
            if page_state.status == 'new':
                # Copy new page
                self._copy_page_from_tmp(title)
                summary['merged'].append(title)
                page_state.base_revid = page_state.remote_revid
                page_state.status = 'clean'
                
            elif page_state.status == 'modified':
                # Simple update - remote wins
                self._copy_page_from_tmp(title)
                summary['merged'].append(title)
                page_state.base_revid = page_state.remote_revid
                page_state.status = 'clean'
                
            elif page_state.status == 'conflict':
                # Try three-way merge
                merged = self._try_merge(title)
                if merged:
                    summary['merged'].append(title)
                    page_state.base_revid = page_state.remote_revid
                    page_state.status = 'clean'
                else:
                    # Create conflict file
                    self._create_conflict_file(title)
                    summary['conflicts'].append(title)
        
        # Update state and clean up
        self.state = tmp_state
        self.state.save(self.state_file)
        shutil.rmtree(self.tmp_dir)
        
        return summary

    def _parse_all_xml(self, xml_dir: str) -> Dict[str, int]:
        """Parse all XML files and return {title: revid} mapping."""
        pages = {}
        if not os.path.exists(xml_dir):
            return pages
        
        for filename in os.listdir(xml_dir):
            if not filename.endswith('.xml'):
                continue
            filepath = os.path.join(xml_dir, filename)
            try:
                tree = ET.parse(filepath)
                root = tree.getroot()
                ns = {'mw': 'http://www.mediawiki.org/xml/export-0.11/'}
                
                for page in root.findall('.//mw:page', ns):
                    title_el = page.find('mw:title', ns)
                    rev_el = page.find('.//mw:revision/mw:id', ns)
                    if title_el is not None and rev_el is not None:
                        pages[title_el.text] = int(rev_el.text)
            except Exception as e:
                print(f"Warning: Could not parse {filename}: {e}")
        
        return pages

    def _copy_page_from_tmp(self, title: str):
        """Copy a page's content from .tmp to data."""
        # For now, this is a placeholder
        # Real implementation would extract specific page from XML
        pass

    def _try_merge(self, title: str) -> bool:
        """
        Attempt three-way merge using diff3.
        Returns True if merge succeeded, False if conflicts remain.
        """
        base_content = self._get_page_content(title, 'base')
        local_content = self._get_page_content(title, 'local')
        remote_content = self._get_page_content(title, 'remote')
        
        if not all([base_content, local_content, remote_content]):
            return False
        
        # Write temp files
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(local_content)
            local_file = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(base_content)
            base_file = f.name
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(remote_content)
            remote_file = f.name
        
        try:
            # Run diff3
            result = subprocess.run(
                ['diff3', '-m', local_file, base_file, remote_file],
                capture_output=True,
                text=True
            )
            
            # Clean up temp files
            os.unlink(local_file)
            os.unlink(base_file)
            os.unlink(remote_file)
            
            if result.returncode == 0:
                # Clean merge - save result
                self._save_page_content(title, result.stdout)
                return True
            else:
                # Conflicts in merge
                return False
                
        except FileNotFoundError:
            # diff3 not available
            os.unlink(local_file)
            os.unlink(base_file)
            os.unlink(remote_file)
            return False

    def _create_conflict_file(self, title: str):
        """Create a conflict file with all three versions."""
        os.makedirs(self.conflict_dir, exist_ok=True)
        
        base = self._get_page_content(title, 'base') or ''
        local = self._get_page_content(title, 'local') or ''
        remote = self._get_page_content(title, 'remote') or ''
        
        base_rev = self.state.pages.get(title, PageState()).base_revid
        remote_rev = self.state.pages.get(title, PageState()).remote_revid
        
        safe_title = title.replace('/', '_').replace(':', '_')
        conflict_path = os.path.join(self.conflict_dir, f"{safe_title}.conflict")
        
        with open(conflict_path, 'w') as f:
            f.write(f"<<<<<<< LOCAL\n")
            f.write(local)
            f.write(f"\n=======\n")
            f.write(f">>>>>>> BASE (rev {base_rev})\n")
            f.write(base)
            f.write(f"\n=======\n")
            f.write(f">>>>>>> REMOTE (rev {remote_rev})\n")
            f.write(remote)
        
        print(f"  Created conflict file: {conflict_path}")

    def _get_page_content(self, title: str, version: str) -> Optional[str]:
        """Get page content for a specific version (base/local/remote)."""
        # Placeholder - real implementation would extract from XML
        return None

    def _save_page_content(self, title: str, content: str):
        """Save merged page content."""
        # Placeholder - real implementation would update XML
        pass
