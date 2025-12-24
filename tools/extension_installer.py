"""
Extension Installer - Install extensions using transient Docker container
"""
import os
import subprocess
from typing import List, Tuple

PORTABLE_WIKI_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'portable_wiki')

def install_extensions(extensions: List[Tuple[str, str]], output_dir: str, callback=None):
    """
    Install extensions to output directory using Docker.
    
    Args:
        extensions: List of (name, source) tuples
        output_dir: Directory to install extensions to
        callback: Optional status callback
    """
    os.makedirs(output_dir, exist_ok=True)
    
    if callback:
        callback(f"Installing {len(extensions)} extensions...")
    
    for name, source in extensions:
        if source == 'skip':
            continue
        
        dest = os.path.join(output_dir, name)
        if os.path.exists(dest):
            if callback:
                callback(f"  ✓ {name} (cached)")
            continue
        
        if callback:
            callback(f"  Installing {name}...")
        
        success = False
        
        # Try Gerrit branches
        if source == 'gerrit':
            for branch in ['REL1_45', 'REL1_44', 'REL1_43', 'master']:
                result = subprocess.run([
                    'docker', 'run', '--rm',
                    '-v', f'{output_dir}:/out',
                    'alpine/git',
                    'clone', '--depth', '1', '--branch', branch,
                    f'https://gerrit.wikimedia.org/r/mediawiki/extensions/{name}',
                    f'/out/{name}'
                ], capture_output=True, text=True)
                
                if result.returncode == 0:
                    success = True
                    if callback:
                        callback(f"  ✓ {name}")
                    break
        
        if not success:
            if callback:
                callback(f"  ✗ {name} (not found)")


def get_installed_extensions(extensions_dir: str) -> List[str]:
    """Get list of installed extension names."""
    if not os.path.exists(extensions_dir):
        return []
    return [d for d in os.listdir(extensions_dir) 
            if os.path.isdir(os.path.join(extensions_dir, d))]
