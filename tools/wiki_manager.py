"""
Wiki Manager - Track and manage multiple wiki instances
"""
import os
import shutil
import subprocess
import yaml
from datetime import datetime
from typing import List, Optional, Dict
from .config import ConfigManager

PORTABLE_WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'portable_wiki')
STATE_FILE = os.path.join(PORTABLE_WIKI_DIR, '.state')

class WikiManager:
    """Manages multiple wiki instances."""
    
    def __init__(self, config: ConfigManager):
        self.config = config

    def list(self) -> List[dict]:
        """List all wikis with their status."""
        wikis = []
        active = self.config.get_active_wiki()
        
        for name, info in self.config.list_wikis().items():
            wiki = {
                'name': name,
                'url': info.get('url', ''),
                'path': info.get('path', ''),
                'active': name == active
            }
            
            # Check if data exists
            data_path = os.path.join(info.get('path', ''), 'data')
            wiki['has_data'] = os.path.exists(data_path)
            
            wikis.append(wiki)
        
        return wikis

    def swap(self, name: str) -> bool:
        """Swap to a different wiki instance."""
        try:
            self.config.set_active_wiki(name)
            return True
        except ValueError:
            return False

    def create(self, name: str, url: str, username: str, password: str) -> str:
        """Create a new wiki instance and return its data path."""
        return self.config.add_wiki(name, url, username, password)

    def delete(self, name: str, keep_data: bool = False) -> bool:
        """Delete a wiki instance."""
        wiki = self.config.get_wiki(name)
        if not wiki:
            return False
        
        # Remove from config
        del self.config.config['wikis'][name]
        
        # Update active if needed
        if self.config.get_active_wiki() == name:
            remaining = list(self.config.config['wikis'].keys())
            self.config.config['active_wiki'] = remaining[0] if remaining else None
        
        self.config.save()
        
        # Remove data if requested
        if not keep_data and wiki.get('path'):
            path = wiki['path']
            if os.path.exists(path):
                shutil.rmtree(path)
        
        return True

    def get_active(self) -> Optional[dict]:
        """Get the active wiki info."""
        name = self.config.get_active_wiki()
        if not name:
            return None
        
        info = self.config.get_wiki(name)
        if info:
            info['name'] = name
        return info

    def get_status(self) -> Dict:
        """Get comprehensive status of wiki environment."""
        status = {
            'active_wiki': self.config.get_active_wiki(),
            'container_running': False,
            'synced_wiki': None,
            'synced_at': None,
            'mismatch': False,
            'needs_sync': False,
            'warnings': []
        }
        
        # Check container status
        try:
            result = subprocess.run(
                ['docker-compose', 'ps', '-q', 'mediawiki'],
                cwd=PORTABLE_WIKI_DIR,
                capture_output=True,
                text=True
            )
            status['container_running'] = bool(result.stdout.strip())
        except Exception:
            pass
        
        # Check sync state
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = yaml.safe_load(f) or {}
                status['synced_wiki'] = state.get('synced_wiki')
                status['synced_at'] = state.get('synced_at')
            except Exception:
                pass
        
        # Detect mismatches
        if status['container_running']:
            if status['synced_wiki'] and status['synced_wiki'] != status['active_wiki']:
                status['mismatch'] = True
                status['warnings'].append(
                    f"Container running '{status['synced_wiki']}' but active wiki is '{status['active_wiki']}'"
                )
        
        # Check if sync needed
        if status['active_wiki'] and not status['synced_wiki']:
            status['needs_sync'] = True
            status['warnings'].append("Wiki not synced yet. Run 'sync' to import data.")
        elif status['mismatch']:
            status['needs_sync'] = True
        
        # Check symlink
        data_link = os.path.join(PORTABLE_WIKI_DIR, 'data')
        if os.path.islink(data_link):
            link_target = os.path.realpath(data_link)
            active_wiki = self.get_active()
            if active_wiki:
                expected_target = os.path.join(active_wiki['path'], 'data')
                if os.path.realpath(expected_target) != link_target:
                    status['warnings'].append("Data symlink points to wrong wiki")
                    status['needs_sync'] = True
        
        return status

    def save_sync_state(self, wiki_name: str):
        """Save sync state after successful sync."""
        state = {
            'synced_wiki': wiki_name,
            'synced_at': datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            yaml.dump(state, f)
