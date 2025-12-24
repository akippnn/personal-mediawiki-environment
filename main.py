#!/usr/bin/env python3
"""
Portable MediaWiki Editor - Unified CLI Orchestrator

Commands:
    clone     Clone a remote wiki (export + setup local)
    push      Push local changes to remote
    export    Run standalone exporter
    start     Start portable wiki (Docker)
    setup     Run setup script
    cleanup   Stop containers, remove volumes
"""
import argparse
import subprocess
import sys
import os
from getpass import getpass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTER_DIR = os.path.join(ROOT_DIR, 'exporter')
PORTABLE_DIR = os.path.join(ROOT_DIR, 'portable_wiki')

# Add paths for imports
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, EXPORTER_DIR)

def run_exporter(api_url: str, output_dir: str, mode: str = 'all'):
    """Run the exporter subprocess."""
    print(f"Starting Exporter (scope={mode})...")
    cmd = [
        sys.executable, os.path.join(EXPORTER_DIR, 'main.py'),
        '--api-url', api_url,
        '--scope', mode,
        '--format', 'xml',
        '--output-dir', output_dir,
        '--no-tui'
    ]
    subprocess.run(cmd, check=True)
    print("Export completed successfully.")

def start_docker():
    """Start Docker containers."""
    print("Starting Portable Wiki (Docker)...")
    subprocess.run(['docker-compose', 'up', '-d'], cwd=PORTABLE_DIR, check=True)
    print("Docker services started.")

def run_setup():
    """Run the setup script."""
    print("Running Portable Wiki Setup...")
    subprocess.run(['./setup.sh'], cwd=PORTABLE_DIR, check=True)

def cmd_clone(args):
    """Clone a remote wiki."""
    from tools.config import ConfigManager
    
    config = ConfigManager(ROOT_DIR)
    
    url = args.url or input("Remote Wiki API URL: ").strip()
    user = args.user or input("Bot Username: ").strip()
    pw = args.password or getpass("Bot Password: ")
    
    config.set_remote(url, user, pw)
    
    print("\n--- Phase 1: Exporting Remote Wiki ---")
    data_dir = os.path.join(PORTABLE_DIR, 'data')
    run_exporter(url, data_dir, mode='all')
    
    print("\n--- Phase 2: Starting Portable Wiki ---")
    start_docker()
    run_setup()
    
    print("\n✓ Clone Complete! Wiki running at http://localhost:8080")

def cmd_push(args):
    """Push local changes to remote wiki."""
    from tools.config import ConfigManager
    from tools.api import SyncApi
    from tools.syncer import Syncer
    
    config = ConfigManager(ROOT_DIR)
    
    if not config.is_configured():
        print("Not configured. Run 'clone' first.")
        return
    
    remote_cfg = config.get_remote()
    local_api = SyncApi('http://localhost:8080/api.php')
    remote_api = SyncApi(remote_cfg['url'], remote_cfg['username'], remote_cfg['password'])
    
    syncer = Syncer(local_api, remote_api)
    syncer.push()

def cmd_export(args):
    """Run the standalone exporter."""
    cmd = [sys.executable, os.path.join(EXPORTER_DIR, 'main.py')] + args.exporter_args
    subprocess.run(cmd)

def cmd_start(args):
    """Start the portable wiki Docker environment."""
    start_docker()
    print("Portable Wiki started at http://localhost:8080")

def cmd_setup(args):
    """Run the portable wiki setup script."""
    run_setup()

def cmd_cleanup(args):
    """Stop containers and optionally remove volumes and data."""
    print("Stopping Docker containers...")
    subprocess.run(['docker-compose', 'down'], cwd=PORTABLE_DIR, check=True)
    
    if args.volumes:
        print("Removing Docker volumes...")
        subprocess.run(['docker-compose', 'down', '-v'], cwd=PORTABLE_DIR, check=True)
    
    if args.data:
        import shutil
        data_dir = os.path.join(PORTABLE_DIR, 'data')
        if os.path.exists(data_dir):
            print(f"Removing {data_dir}...")
            shutil.rmtree(data_dir)
    
    print("✓ Cleanup complete.")

def main():
    parser = argparse.ArgumentParser(
        prog='portable-mediawiki-editor',
        description='Clone, edit, and sync MediaWiki sites locally.'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Clone
    p = subparsers.add_parser('clone', help='Clone a remote wiki')
    p.add_argument('--url', help='Remote API URL')
    p.add_argument('--user', help='Bot username')
    p.add_argument('--password', help='Bot password')
    p.set_defaults(func=cmd_clone)
    
    # Push
    p = subparsers.add_parser('push', help='Push local changes to remote')
    p.set_defaults(func=cmd_push)
    
    # Export (pass-through)
    p = subparsers.add_parser('export', help='Run standalone exporter')
    p.add_argument('exporter_args', nargs='*', help='Arguments for exporter')
    p.set_defaults(func=cmd_export)
    
    # Start
    p = subparsers.add_parser('start', help='Start portable wiki (Docker)')
    p.set_defaults(func=cmd_start)
    
    # Setup
    p = subparsers.add_parser('setup', help='Run portable wiki setup')
    p.set_defaults(func=cmd_setup)
    
    # Cleanup
    p = subparsers.add_parser('cleanup', help='Stop containers and clean up')
    p.add_argument('--volumes', '-v', action='store_true', help='Also remove Docker volumes')
    p.add_argument('--data', '-d', action='store_true', help='Also remove exported data')
    p.set_defaults(func=cmd_cleanup)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
