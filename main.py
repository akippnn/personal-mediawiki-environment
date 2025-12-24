#!/usr/bin/env python3
"""
Portable MediaWiki Editor - Unified CLI Orchestrator

Commands:
    clone     Clone a remote wiki
    push      Push local changes to remote
    list      Show all cloned wikis
    swap      Switch active wiki
    export    Run standalone exporter
    start     Start portable wiki
    setup     Run setup script
    cleanup   Stop and clean up
"""
import argparse
import subprocess
import sys
import os
from getpass import getpass

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPORTER_DIR = os.path.join(ROOT_DIR, 'exporter')
PORTABLE_DIR = os.path.join(ROOT_DIR, 'portable_wiki')

sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, EXPORTER_DIR)

def slugify(name: str) -> str:
    """Create a filesystem-safe name."""
    return name.lower().replace(' ', '_').replace('/', '_').replace(':', '_')

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

def run_sync():
    """Run sync via manager.py and save state."""
    from tools.config import ConfigManager
    from tools.wiki_manager import WikiManager
    
    config = ConfigManager(ROOT_DIR)
    manager = WikiManager(config)
    
    active = config.get_active_wiki()
    if not active:
        print("No active wiki. Run 'clone' first.")
        return
    
    print(f"Syncing '{active}'...")
    subprocess.run([sys.executable, 'manager.py', 'install'], cwd=PORTABLE_DIR, check=True)
    subprocess.run([sys.executable, 'manager.py', 'import'], cwd=PORTABLE_DIR, check=True)
    
    # Save sync state
    manager.save_sync_state(active)
    print(f"✓ Synced '{active}'")

def cmd_clone(args):
    """Clone a remote wiki."""
    from tools.config import ConfigManager
    
    config = ConfigManager(ROOT_DIR)
    
    url = args.url or input("Remote Wiki API URL: ").strip()
    user = args.user or input("Bot Username (optional): ").strip()
    pw = getpass("Bot Password (optional): ") if user else ""
    
    # Generate name from URL if not provided
    if args.name:
        name = slugify(args.name)
    else:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        name = slugify(parsed.netloc.split('.')[0])
    
    print(f"\nCloning wiki as '{name}'...")
    
    # Create wiki entry
    wiki_path = config.add_wiki(name, url, user, pw)
    data_dir = os.path.join(wiki_path, 'data')
    
    print("\n--- Phase 1: Exporting Remote Wiki ---")
    run_exporter(url, data_dir, mode='all')
    
    # Symlink data to portable_wiki
    portable_data = os.path.join(PORTABLE_DIR, 'data')
    if os.path.islink(portable_data):
        os.unlink(portable_data)
    elif os.path.exists(portable_data):
        import shutil
        shutil.rmtree(portable_data)
    os.symlink(data_dir, portable_data)
    
    print("\n--- Phase 2: Starting Portable Wiki ---")
    start_docker()
    run_setup()
    
    print(f"\n✓ Clone Complete! Wiki '{name}' running at http://localhost:8080")

def cmd_push(args):
    """Push local changes to remote wiki."""
    from tools.config import ConfigManager
    from tools.api import SyncApi
    from tools.syncer import Syncer
    
    config = ConfigManager(ROOT_DIR)
    wiki = config.get_active_wiki_config()
    
    if not wiki:
        print("No active wiki. Run 'clone' first.")
        return
    
    print(f"Pushing changes from '{config.get_active_wiki()}'...")
    
    local_api = SyncApi('http://localhost:8080/api.php')
    remote_api = SyncApi(wiki['url'], wiki.get('username'), wiki.get('password'))
    
    syncer = Syncer(local_api, remote_api)
    syncer.push()

def cmd_list(args):
    """List all cloned wikis."""
    from tools.config import ConfigManager
    from tools.wiki_manager import WikiManager
    
    config = ConfigManager(ROOT_DIR)
    manager = WikiManager(config)
    
    wikis = manager.list()
    
    if not wikis:
        print("No wikis cloned yet. Use 'clone' to add one.")
        return
    
    print("\nCloned Wikis:")
    print("-" * 60)
    for wiki in wikis:
        status = "→ " if wiki['active'] else "  "
        data = "✓" if wiki['has_data'] else "✗"
        print(f"{status}{wiki['name']:20} {wiki['url']:30} [{data}]")
    print("-" * 60)
    print(f"Active: {config.get_active_wiki() or 'none'}")

def cmd_swap(args):
    """Swap to a different wiki."""
    from tools.config import ConfigManager
    from tools.wiki_manager import WikiManager
    import shutil
    
    config = ConfigManager(ROOT_DIR)
    manager = WikiManager(config)
    
    if not manager.swap(args.name):
        print(f"Wiki '{args.name}' not found")
        return
    
    # Update symlink
    wiki = config.get_active_wiki_config()
    data_dir = os.path.join(wiki['path'], 'data')
    portable_data = os.path.join(PORTABLE_DIR, 'data')
    
    if os.path.islink(portable_data):
        os.unlink(portable_data)
    elif os.path.exists(portable_data):
        shutil.rmtree(portable_data)
    os.symlink(data_dir, portable_data)
    
    print(f"✓ Switched to '{args.name}'")
    print("  Run 'start' to launch or 'setup' to reimport data")

def cmd_export(args):
    """Run the standalone exporter."""
    cmd = [sys.executable, os.path.join(EXPORTER_DIR, 'main.py')] + args.exporter_args
    subprocess.run(cmd)

def cmd_start(args):
    """Start the portable wiki Docker environment."""
    start_docker()
    print("Portable Wiki started at http://localhost:8080")

def cmd_sync(args):
    """Sync data to portable wiki."""
    run_sync()

def cmd_status(args):
    """Show status of wiki environment."""
    from tools.config import ConfigManager
    from tools.wiki_manager import WikiManager
    
    config = ConfigManager(ROOT_DIR)
    manager = WikiManager(config)
    status = manager.get_status()
    
    print("\n" + "=" * 50)
    print("Wiki Environment Status")
    print("=" * 50)
    
    # Active wiki
    active = status['active_wiki'] or 'none'
    print(f"Active Wiki:     {active}")
    
    # Container status
    container = "running" if status['container_running'] else "stopped"
    if status['synced_wiki'] and status['container_running']:
        container += f" (synced: {status['synced_wiki']})"
    print(f"Container:       {container}")
    
    # Sync status
    if status['synced_at']:
        print(f"Last Sync:       {status['synced_at']}")
    else:
        print(f"Last Sync:       never")
    
    # Warnings
    if status['warnings']:
        print("\n⚠️  Warnings:")
        for warning in status['warnings']:
            print(f"   • {warning}")
    
    # Recommendations
    if status['needs_sync']:
        print("\n→ Run 'sync' to update the portable wiki")
    elif not status['container_running']:
        print("\n→ Run 'start' to start the wiki")
    else:
        print("\n✓ Everything looks good")
    
    print("=" * 50)

def cmd_cleanup(args):
    """Stop containers and optionally remove volumes and data."""
    print("Stopping Docker containers...")
    subprocess.run(['docker-compose', 'down'], cwd=PORTABLE_DIR, check=True)
    
    if args.volumes:
        print("Removing Docker volumes...")
        subprocess.run(['docker-compose', 'down', '-v'], cwd=PORTABLE_DIR, check=True)
    
    if args.data:
        from tools.config import ConfigManager
        config = ConfigManager(ROOT_DIR)
        wiki = config.get_active_wiki_config()
        if wiki:
            import shutil
            data_path = os.path.join(wiki['path'], 'data')
            if os.path.exists(data_path):
                print(f"Removing {data_path}...")
                shutil.rmtree(data_path)
    
    print("✓ Cleanup complete.")

def main():
    parser = argparse.ArgumentParser(
        prog='lmt',
        description='Clone MediaWiki sites locally, edit offline, push changes back.'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Clone
    p = subparsers.add_parser('clone', help='Clone a remote wiki')
    p.add_argument('--url', help='Remote API URL')
    p.add_argument('--name', '-n', help='Name for this wiki instance')
    p.add_argument('--user', help='Bot username')
    p.add_argument('--password', help='Bot password')
    p.set_defaults(func=cmd_clone)
    
    # Push
    p = subparsers.add_parser('push', help='Push local changes to remote')
    p.set_defaults(func=cmd_push)
    
    # List
    p = subparsers.add_parser('list', help='List all cloned wikis')
    p.set_defaults(func=cmd_list)
    
    # Swap
    p = subparsers.add_parser('swap', help='Switch to a different wiki')
    p.add_argument('name', help='Wiki name to switch to')
    p.set_defaults(func=cmd_swap)
    
    # Export
    p = subparsers.add_parser('export', help='Run standalone exporter')
    p.add_argument('exporter_args', nargs='*', help='Arguments for exporter')
    p.set_defaults(func=cmd_export)
    
    # Start
    p = subparsers.add_parser('start', help='Start portable wiki (Docker)')
    p.set_defaults(func=cmd_start)
    
    # Sync (was: setup)
    p = subparsers.add_parser('sync', help='Sync data to portable wiki')
    p.set_defaults(func=cmd_sync)
    
    # Status
    p = subparsers.add_parser('status', help='Show wiki environment status')
    p.set_defaults(func=cmd_status)
    
    # Cleanup
    p = subparsers.add_parser('cleanup', help='Stop containers and clean up')
    p.add_argument('--volumes', '-v', action='store_true', help='Also remove Docker volumes')
    p.add_argument('--data', '-d', action='store_true', help='Also remove exported data')
    p.set_defaults(func=cmd_cleanup)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
