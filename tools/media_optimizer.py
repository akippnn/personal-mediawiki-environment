"""
Media Optimizer - Compress images and videos with ffmpeg
"""
import os
import subprocess
import yaml
import shutil
from typing import Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime

# Supported formats
IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp'}
VIDEO_EXTS = {'.mp4', '.webm', '.ogg', '.ogv', '.avi', '.mov', '.mkv'}
SKIP_EXTS = {'.svg', '.pdf'}  # Don't optimize these

@dataclass
class MediaState:
    """Tracks optimization state for media files."""
    files: Dict[str, dict] = field(default_factory=dict)
    
    def save(self, path: str):
        with open(path, 'w') as f:
            yaml.dump({'files': self.files}, f)
    
    @classmethod
    def load(cls, path: str) -> 'MediaState':
        if not os.path.exists(path):
            return cls()
        with open(path, 'r') as f:
            data = yaml.safe_load(f) or {}
        return cls(files=data.get('files', {}))
    
    def mark_optimized(self, filename: str, original_hash: str, local_only: bool = True):
        self.files[filename] = {
            'original_hash': original_hash,
            'optimized': True,
            'optimized_at': datetime.now().isoformat(),
            'local_only': local_only
        }
    
    def is_local_only(self, filename: str) -> bool:
        return self.files.get(filename, {}).get('local_only', False)


class MediaOptimizer:
    """Optimizes media files using ffmpeg."""
    
    def __init__(self, media_dir: str, state_path: str):
        self.media_dir = media_dir
        self.state_path = state_path
        self.state = MediaState.load(state_path)
    
    def check_ffmpeg(self) -> bool:
        """Check if ffmpeg is available."""
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False
    
    def optimize_all(self, quality: int = 80, skip_video: bool = False, 
                     local_only: bool = True, callback=None) -> Dict:
        """Optimize all media in directory."""
        if not self.check_ffmpeg():
            print("Error: ffmpeg not found. Install with: brew install ffmpeg")
            return {'error': 'ffmpeg not found'}
        
        summary = {'optimized': 0, 'skipped': 0, 'failed': 0, 'saved_bytes': 0}
        
        if not os.path.exists(self.media_dir):
            return summary
        
        for filename in os.listdir(self.media_dir):
            filepath = os.path.join(self.media_dir, filename)
            if not os.path.isfile(filepath):
                continue
            
            ext = os.path.splitext(filename)[1].lower()
            
            # Skip already optimized
            if filename in self.state.files and self.state.files[filename].get('optimized'):
                summary['skipped'] += 1
                continue
            
            # Skip unsupported
            if ext in SKIP_EXTS:
                summary['skipped'] += 1
                continue
            
            original_size = os.path.getsize(filepath)
            original_hash = self._get_hash(filepath)
            
            try:
                if ext in IMAGE_EXTS:
                    saved = self._optimize_image(filepath, quality, callback)
                elif ext in VIDEO_EXTS and not skip_video:
                    saved = self._optimize_video(filepath, quality, callback)
                else:
                    summary['skipped'] += 1
                    continue
                
                if saved > 0:
                    summary['optimized'] += 1
                    summary['saved_bytes'] += saved
                    self.state.mark_optimized(filename, original_hash, local_only)
                else:
                    summary['skipped'] += 1
                    
            except Exception as e:
                if callback:
                    callback(f"  ✗ {filename}: {e}")
                summary['failed'] += 1
        
        self.state.save(self.state_path)
        return summary
    
    def _optimize_image(self, filepath: str, quality: int, callback=None) -> int:
        """Optimize an image, return bytes saved."""
        original_size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        
        # Create temp output
        temp_path = filepath + '.optimized.webp'
        
        # Convert to WebP
        result = subprocess.run([
            'ffmpeg', '-y', '-i', filepath,
            '-quality', str(quality),
            temp_path
        ], capture_output=True)
        
        if result.returncode != 0:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise Exception(f"ffmpeg failed: {result.stderr.decode()[:100]}")
        
        new_size = os.path.getsize(temp_path)
        
        if new_size < original_size:
            # Replace original with optimized
            shutil.move(temp_path, filepath)
            saved = original_size - new_size
            if callback:
                callback(f"  ✓ {filename}: {self._format_size(saved)} saved")
            return saved
        else:
            # Keep original
            os.remove(temp_path)
            if callback:
                callback(f"  - {filename}: already optimal")
            return 0
    
    def _optimize_video(self, filepath: str, quality: int, callback=None) -> int:
        """Optimize a video, return bytes saved."""
        original_size = os.path.getsize(filepath)
        filename = os.path.basename(filepath)
        
        # Create temp output
        ext = os.path.splitext(filepath)[1]
        temp_path = filepath + '.optimized' + ext
        
        # CRF value (lower = better quality)
        crf = max(18, min(35, 51 - (quality * 33 // 100)))
        
        if callback:
            callback(f"  Optimizing {filename}...")
        
        result = subprocess.run([
            'ffmpeg', '-y', '-i', filepath,
            '-c:v', 'libx264', '-crf', str(crf),
            '-c:a', 'aac', '-b:a', '128k',
            '-movflags', '+faststart',
            temp_path
        ], capture_output=True)
        
        if result.returncode != 0:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise Exception(f"ffmpeg failed")
        
        new_size = os.path.getsize(temp_path)
        
        if new_size < original_size * 0.9:  # At least 10% smaller
            shutil.move(temp_path, filepath)
            saved = original_size - new_size
            if callback:
                callback(f"  ✓ {filename}: {self._format_size(saved)} saved")
            return saved
        else:
            os.remove(temp_path)
            if callback:
                callback(f"  - {filename}: already optimal")
            return 0
    
    def _get_hash(self, filepath: str) -> str:
        """Get file hash for tracking."""
        import hashlib
        with open(filepath, 'rb') as f:
            return hashlib.md5(f.read(8192)).hexdigest()
    
    def _format_size(self, size: int) -> str:
        """Format bytes to human readable."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"
    
    def get_local_only_files(self) -> list:
        """Get list of files marked as local-only."""
        return [f for f, info in self.state.files.items() if info.get('local_only')]
    
    def clear_local_only(self, filename: str):
        """Remove local-only marker from a file."""
        if filename in self.state.files:
            self.state.files[filename]['local_only'] = False
            self.state.save(self.state_path)
