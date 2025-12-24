"""
Extension Resolver - Detect and resolve MediaWiki extensions

Handles:
- Bundled extensions (skip)
- Archived extensions (prompt for alternatives)
- Available extensions (install from Gerrit)
"""
import os
import re
import yaml
import requests
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

MEDIAWIKI_API = "https://www.mediawiki.org/w/api.php"
GERRIT_BASE = "https://gerrit.wikimedia.org/r/mediawiki/extensions"

@dataclass
class ExtensionInfo:
    name: str
    status: str = "unknown"  # bundled, archived, available, unknown
    bundled_since: Optional[str] = None
    alternatives: List[str] = field(default_factory=list)
    chosen: Optional[str] = None
    source: Optional[str] = None  # gerrit, github, skip

@dataclass
class ExtensionLock:
    resolved_at: Optional[str] = None
    extensions: Dict[str, ExtensionInfo] = field(default_factory=dict)
    
    def save(self, path: str):
        data = {
            'resolved_at': self.resolved_at,
            'extensions': {
                name: {
                    'status': ext.status,
                    'bundled_since': ext.bundled_since,
                    'alternatives': ext.alternatives,
                    'chosen': ext.chosen,
                    'source': ext.source
                }
                for name, ext in self.extensions.items()
            }
        }
        with open(path, 'w') as f:
            yaml.dump(data, f)
    
    @classmethod
    def load(cls, path: str) -> 'ExtensionLock':
        if not os.path.exists(path):
            return cls()
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        lock = cls(resolved_at=data.get('resolved_at'))
        for name, ext_data in data.get('extensions', {}).items():
            lock.extensions[name] = ExtensionInfo(
                name=name,
                status=ext_data.get('status', 'unknown'),
                bundled_since=ext_data.get('bundled_since'),
                alternatives=ext_data.get('alternatives', []),
                chosen=ext_data.get('chosen'),
                source=ext_data.get('source')
            )
        return lock


class ExtensionResolver:
    """Resolves extensions from exported list."""
    
    def __init__(self, wiki_path: str):
        self.wiki_path = wiki_path
        self.lock_file = os.path.join(wiki_path, 'extensions.lock')
        self.lock = ExtensionLock.load(self.lock_file)
        self.session = requests.Session()
        self.session.headers['User-Agent'] = 'LocalMediaWikiTools/1.0'

    def load_exported_extensions(self) -> List[str]:
        """Load extension names from exported data."""
        yaml_path = os.path.join(self.wiki_path, 'data', 'extensions.yaml')
        txt_path = os.path.join(self.wiki_path, 'data', 'extensions.txt')
        
        if os.path.exists(yaml_path):
            with open(yaml_path, 'r') as f:
                data = yaml.safe_load(f) or {}
            return list(data.keys()) if isinstance(data, dict) else []
        elif os.path.exists(txt_path):
            with open(txt_path, 'r') as f:
                return [line.strip() for line in f if line.strip()]
        return []

    def check_extension(self, name: str, callback=None) -> ExtensionInfo:
        """Check extension status on mediawiki.org."""
        info = ExtensionInfo(name=name)
        
        # Query mediawiki.org for extension page content
        params = {
            'action': 'query',
            'titles': f'Extension:{name}',
            'prop': 'revisions',
            'rvprop': 'content',
            'format': 'json'
        }
        
        try:
            resp = self.session.get(MEDIAWIKI_API, params=params, timeout=10)
            data = resp.json()
            pages = data.get('query', {}).get('pages', {})
            
            for page in pages.values():
                if 'missing' in page:
                    info.status = 'unknown'
                    break
                
                content = ''
                revs = page.get('revisions', [])
                if revs:
                    content = revs[0].get('*', '') or revs[0].get('content', '')
                
                # Check for Bundled template
                bundled_match = re.search(r'\{\{Bundled\|([^}]+)\}\}', content, re.IGNORECASE)
                if bundled_match:
                    info.status = 'bundled'
                    info.bundled_since = bundled_match.group(1)
                    info.source = 'skip'
                    if callback:
                        callback(f"  ✓ {name} (bundled since {info.bundled_since})")
                    return info
                
                # Check for Archived extension template
                archived_match = re.search(
                    r'\{\{Archived extension\|[^|]*\|([^}]+)\}\}',
                    content, re.IGNORECASE
                )
                if archived_match:
                    info.status = 'archived'
                    # Parse alternatives (pipe-separated after first param)
                    alt_str = archived_match.group(1)
                    info.alternatives = [a.strip() for a in alt_str.split('|') 
                                        if a.strip() and not a.startswith('task=') 
                                        and not a.startswith('reason=')]
                    if callback:
                        callback(f"  ⚠ {name} (archived)")
                    return info
                
                # Extension exists, check if on Gerrit
                info.status = 'available'
                info.source = 'gerrit'
                if callback:
                    callback(f"  ✓ {name}")
                    
        except Exception as e:
            info.status = 'unknown'
            if callback:
                callback(f"  ? {name} (check failed: {e})")
        
        return info

    def resolve_all(self, extensions: List[str], callback=None) -> Dict[str, ExtensionInfo]:
        """Check all extensions, return info dict."""
        results = {}
        for name in extensions:
            # Skip if already resolved
            if name in self.lock.extensions and self.lock.extensions[name].status != 'unknown':
                results[name] = self.lock.extensions[name]
                if callback:
                    callback(f"  ✓ {name} (cached)")
            else:
                results[name] = self.check_extension(name, callback)
        return results

    def get_unresolved_archived(self, extensions: Dict[str, ExtensionInfo]) -> List[ExtensionInfo]:
        """Get archived extensions that need user choice."""
        return [ext for ext in extensions.values() 
                if ext.status == 'archived' and not ext.chosen]

    def prompt_archived(self, ext: ExtensionInfo) -> str:
        """Prompt user for archived extension choice."""
        print(f"\nExtension '{ext.name}' is archived.")
        print("Alternatives:")
        for i, alt in enumerate(ext.alternatives, 1):
            rec = " (recommended)" if i == 1 else ""
            print(f"  {i}. {alt}{rec}")
        print(f"  s. Skip this extension")
        
        while True:
            choice = input(f"Choose [1-{len(ext.alternatives)}, s=skip]: ").strip().lower()
            if choice == 's':
                ext.chosen = None
                ext.source = 'skip'
                return 'skip'
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(ext.alternatives):
                    ext.chosen = ext.alternatives[idx]
                    ext.source = 'gerrit'
                    return ext.chosen
            except ValueError:
                pass
            print("Invalid choice. Try again.")

    def save(self):
        """Save lock file."""
        self.lock.resolved_at = datetime.now().isoformat()
        self.lock.save(self.lock_file)

    def get_extensions_to_install(self) -> List[Tuple[str, str]]:
        """Get list of (name, source) for extensions to install."""
        to_install = []
        for name, ext in self.lock.extensions.items():
            if ext.source == 'skip' or ext.status == 'bundled':
                continue
            install_name = ext.chosen if ext.chosen else name
            to_install.append((install_name, ext.source or 'gerrit'))
        return to_install
