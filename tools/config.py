import os
import yaml

CONFIG_FILE = 'wikis.yaml'

class ConfigManager:
    """Manages multi-wiki configuration."""
    
    def __init__(self, root_dir: str):
        self.root_dir = root_dir
        self.config_path = os.path.join(root_dir, CONFIG_FILE)
        self.config = {
            'active_wiki': None,
            'wikis': {}
        }
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                loaded = yaml.safe_load(f) or {}
                self.config.update(loaded)

    def save(self):
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    # --- Wiki Management ---
    
    def add_wiki(self, name: str, url: str, username: str, password: str):
        """Add a new wiki to the config."""
        wiki_path = os.path.join(self.root_dir, 'wikis', name)
        os.makedirs(wiki_path, exist_ok=True)
        os.makedirs(os.path.join(wiki_path, 'data'), exist_ok=True)
        
        self.config['wikis'][name] = {
            'url': url,
            'username': username,
            'password': password,
            'path': wiki_path
        }
        
        # Set as active if first wiki
        if not self.config['active_wiki']:
            self.config['active_wiki'] = name
        
        self.save()
        return wiki_path

    def get_wiki(self, name: str) -> dict:
        """Get wiki config by name."""
        return self.config['wikis'].get(name)

    def list_wikis(self) -> dict:
        """List all configured wikis."""
        return self.config['wikis']

    def get_active_wiki(self) -> str:
        """Get the name of the active wiki."""
        return self.config.get('active_wiki')

    def set_active_wiki(self, name: str):
        """Set the active wiki."""
        if name not in self.config['wikis']:
            raise ValueError(f"Wiki '{name}' not found")
        self.config['active_wiki'] = name
        self.save()

    def get_active_wiki_config(self) -> dict:
        """Get the config for the currently active wiki."""
        active = self.get_active_wiki()
        if not active:
            return None
        return self.get_wiki(active)

    def get_active_data_dir(self) -> str:
        """Get the data directory for the active wiki."""
        config = self.get_active_wiki_config()
        if not config:
            return None
        return os.path.join(config['path'], 'data')

    # --- Legacy compatibility ---
    
    def set_remote(self, url: str, username: str, password: str):
        """Legacy method - creates a 'default' wiki."""
        self.add_wiki('default', url, username, password)

    def get_remote(self) -> dict:
        """Legacy method - get active wiki as remote."""
        return self.get_active_wiki_config()

    def is_configured(self) -> bool:
        """Check if any wiki is configured."""
        return len(self.config['wikis']) > 0
