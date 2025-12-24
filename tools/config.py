import yaml
import os

CONFIG_FILE = 'sync_config.yaml'

class ConfigManager:
    """Manages the sync configuration (remote URL, credentials, etc)."""
    
    def __init__(self, output_dir='.'):
        self.config_path = os.path.join(output_dir, CONFIG_FILE)
        self.config = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f) or {}

    def save(self):
        with open(self.config_path, 'w') as f:
            yaml.dump(self.config, f)

    def set_remote(self, url, username, password):
        self.config['remote'] = {
            'url': url,
            'username': username,
            'password': password
        }
        self.save()

    def get_remote(self):
        return self.config.get('remote', {})

    def is_configured(self):
        return 'remote' in self.config
