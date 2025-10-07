import os
import json
import time
import threading
from typing import Set, Dict, Any

class State:
    """Manages application state, focusing on image hashes for efficient updates."""

    def __init__(self, output_dir: str):
        self.state_path = os.path.join(output_dir, 'export_state.json')
        self._lock = threading.RLock()

        # Maps image titles (e.g., "File:MyImage.png") to their server-side SHA1 hash
        self.image_versions: Dict[str, str] = {}
        
        # Live counters for the TUI
        self.categories_traversed_count = 0
        self.count_pages_written = 0
        self.count_templates_written = 0
        self.count_images_downloaded = 0
        self.count_images_skipped = 0

    def load(self) -> None:
        if not os.path.exists(self.state_path): return
        try:
            with open(self.state_path, 'r', encoding='utf-8') as f: data = json.load(f)
            with self._lock: self.image_versions = data.get('image_versions', {})
        except (json.JSONDecodeError, IOError): pass

    def save(self) -> None:
        from .utils import atomic_write_text
        with self._lock: data = {'image_versions': self.image_versions, 'last_updated': time.time()}
        try: atomic_write_text(self.state_path, json.dumps(data, indent=2, ensure_ascii=False))
        except IOError: pass

    def get_report(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'Pages Written': self.count_pages_written,
                'Templates Written': self.count_templates_written,
                'Images Downloaded': self.count_images_downloaded,
                'Images Skipped (Cached)': self.count_images_skipped,
                'Categories Traversed': self.categories_traversed_count,
            }

    def needs_image_update(self, image_title: str, new_hash: str) -> bool:
        """Checks if an image needs to be re-downloaded based on its hash."""
        with self._lock:
            if self.image_versions.get(image_title) == new_hash:
                self.count_images_skipped += 1
                return False
            return True

    def update_image_hash(self, image_title: str, new_hash: str):
        """Updates the stored hash for an image and counts it as downloaded."""
        with self._lock:
            self.image_versions[image_title] = new_hash
            self.count_images_downloaded += 1
    
    def increment_written_counter(self, kind: str):
        with self._lock:
            if kind == 'page': self.count_pages_written += 1
            if kind == 'template': self.count_templates_written += 1