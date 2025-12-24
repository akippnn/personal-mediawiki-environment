"""
Wiki Manager - Track and manage multiple wiki instances
"""
import os
import shutil
from typing import List, Optional
from .config import ConfigManager

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
