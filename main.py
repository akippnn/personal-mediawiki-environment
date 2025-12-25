#!/usr/bin/env python3
"""
Local MediaWiki Tools - Unified CLI

Commands:
    clone     Clone a remote wiki
    fetch     Fetch remote changes (compare)
    pull      Pull and merge changes
    push      Push local changes to remote
    list      Show all cloned wikis
    swap      Switch active wiki
    status    Show environment status
    start     Start portable wiki
    sync      Sync data to portable wiki
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

def run_exporter(api_url: str, output_dir: str, mode: str = 'all', skip_media: bool = False):
    """Run the exporter subprocess."""
    print(f"Starting Exporter (scope={mode}, skip_media={skip_media})...")
    cmd = [
        sys.executable, os.path.join(EXPORTER_DIR, 'main.py'),
        '--api-url', api_url,
        '--scope', mode,
        '--format', 'xml',
        '--output-dir', output_dir,
        '--no-tui'
    ]
    if skip_media:
        cmd.append('--skip-media')
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
    from tools.sync_engine import SyncEngine
    
    config = ConfigManager(ROOT_DIR)
    manager = WikiManager(config)
    
    active = config.get_active_wiki()
    if not active:
        print("No active wiki. Run 'clone' first.")
        return
    
    wiki = config.get_wiki_config(active)
    
    print(f"Syncing '{active}'...")
    subprocess.run([sys.executable, 'manager.py', 'install'], cwd=PORTABLE_DIR, check=True)
    subprocess.run([sys.executable, 'manager.py', 'import'], cwd=PORTABLE_DIR, check=True)
    
    # Record local wiki state for change detection
    engine = SyncEngine(wiki['path'], wiki['url'])
    engine.update_local_revisions()
    
    # Save sync state
    manager.save_sync_state(active)
    print(f"✓ Synced '{active}'")

def cmd_clone(args):
    """Clone a remote wiki with extension resolution."""
    import threading
    from tools.config import ConfigManager
    from tools.extension_resolver import ExtensionResolver
    from tools.extension_installer import install_extensions
    
    config = ConfigManager(ROOT_DIR)
    
    # --- Phase 0: Gather user input FIRST (good UX) ---
    url = args.url or input("Remote Wiki API URL: ").strip()
    user = args.user or input("Bot Username (optional): ").strip()
    pw = getpass("Bot Password (optional): ") if user else ""
    
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
    extensions_dir = os.path.join(wiki_path, 'extensions')
    
    # --- Phase 1: Export in background ---
    print("\n--- Phase 1: Exporting Remote Wiki ---")
    export_done = threading.Event()
    export_error = [None]
    
    def export_thread():
        try:
            run_exporter(url, data_dir, mode='all')
        except Exception as e:
            export_error[0] = e
        finally:
            export_done.set()
    
    thread = threading.Thread(target=export_thread)
    thread.start()
    
    # Wait for export to complete
    export_done.wait()
    thread.join()
    
    if export_error[0]:
        print(f"Export failed: {export_error[0]}")
        return
    
    # --- Phase 2: Resolve Extensions ---
    print("\n--- Phase 2: Resolving Extensions ---")
    resolver = ExtensionResolver(wiki_path)
    exported_exts = resolver.load_exported_extensions()
    
    if exported_exts:
        print(f"Found {len(exported_exts)} extensions to check...")
        ext_info = resolver.resolve_all(exported_exts, callback=print)
        
        # Prompt for archived extensions
        archived = resolver.get_unresolved_archived(ext_info)
        for ext in archived:
            resolver.prompt_archived(ext)
        
        # Save lock
        resolver.lock.extensions = ext_info
        resolver.save()
        
        # Install extensions
        print("\n--- Phase 3: Installing Extensions ---")
        to_install = resolver.get_extensions_to_install()
        if to_install:
            install_extensions(to_install, extensions_dir, callback=print)
    else:
        print("No extensions found in export.")
    
    # --- Phase 4: Setup Portable Wiki ---
    print("\n--- Phase 4: Starting Portable Wiki ---")
    
    # Symlink data to portable_wiki
    portable_data = os.path.join(PORTABLE_DIR, 'data')
    if os.path.islink(portable_data):
        os.unlink(portable_data)
    elif os.path.exists(portable_data):
        import shutil
        shutil.rmtree(portable_data)
    os.symlink(data_dir, portable_data)
    
    # Symlink extensions
    portable_ext = os.path.join(PORTABLE_DIR, 'extensions')
    if os.path.islink(portable_ext):
        os.unlink(portable_ext)
    elif os.path.exists(portable_ext):
        import shutil
        shutil.rmtree(portable_ext)
    if os.path.exists(extensions_dir):
        os.symlink(extensions_dir, portable_ext)
    
    start_docker()
    run_sync()
    
    print(f"\n✓ Clone Complete! Wiki '{name}' running at http://localhost:8080")

def cmd_push(args):
    """Push local changes to remote wiki."""
    from tools.config import ConfigManager
    from tools.sync_engine import SyncEngine
    from core import MediaWikiClient
    import getpass
    
    config = ConfigManager(ROOT_DIR)
    wiki = config.get_active_wiki_config()
    
    if not wiki:
        print("No active wiki. Run 'clone' first.")
        return
    
    wiki_name = config.get_active_wiki()
    print(f"Checking for local changes in '{wiki_name}'...")
    
    # Detect local changes
    engine = SyncEngine(wiki['path'], wiki['url'])
    modified = engine.get_local_changes()
    
    if not modified:
        print("No local changes to push.")
        return
    
    print(f"\nFound {len(modified)} modified page(s):")
    for title in modified[:10]:
        print(f"  • {title}")
    if len(modified) > 10:
        print(f"  ... and {len(modified) - 10} more")
    
    # Confirm
    if not args.yes:
        response = input(f"\nPush {len(modified)} page(s) to remote? [y/N]: ").strip().lower()
        if response != 'y':
            print("Cancelled.")
            return
    
    # Get credentials if needed
    username = wiki.get('username')
    password = wiki.get('password')
    if not password and username:
        password = getpass.getpass(f"Password for {username}: ")
    
    # Connect to remote
    remote = MediaWikiClient(wiki['url'], username, password)
    if username:
        if not remote.login():
            print("Login failed. Check credentials.")
            return
    
    # Connect to local
    local = MediaWikiClient('http://localhost:8080/api.php')
    
    # Push each modified page
    success = 0
    failed = 0
    for i, title in enumerate(modified, 1):
        print(f"[{i}/{len(modified)}] Pushing '{title}'...")
        
        # Get content from local wiki
        content = local.get_page_content(title)
        if content is None:
            print(f"  ⚠ Could not get content, skipping")
            failed += 1
            continue
        
        # Push to remote
        if remote.edit_page(title, content, f"Pushed from local wiki"):
            success += 1
            # Update local_revid in state
            current_revs = engine.get_local_revisions()
            if title in current_revs:
                engine.state.pages[title].local_revid = current_revs[title]
        else:
            failed += 1
    
    # Save state
    engine.state.save(engine.state_file)
    
    print(f"\n✓ Push complete: {success} succeeded, {failed} failed")

def cmd_fetch(args):
    """Fetch remote changes (download to .tmp, compare)."""
    from tools.config import ConfigManager
    from tools.sync_engine import SyncEngine
    
    config = ConfigManager(ROOT_DIR)
    wiki = config.get_active_wiki_config()
    
    if not wiki:
        print("No active wiki. Run 'clone' first.")
        return
    
    engine = SyncEngine(wiki['path'], wiki['url'])
    
    # Check for incomplete previous fetch
    if engine.has_incomplete_fetch():
        print("Found incomplete fetch data.")
        if args.discard:
            engine.discard_incomplete_fetch()
        else:
            print("Use --discard to remove, or run 'pull' to complete.")
            return
    
    # Use skip_media=True for fetch (only download metadata, not images)
    fetch_exporter = lambda url, output: run_exporter(url, output, skip_media=True)
    summary = engine.fetch(fetch_exporter)
    
    print("\n" + "=" * 50)
    print("Fetch Summary")
    print("=" * 50)
    print(f"  New pages:      {len(summary.get('new', []))}")
    print(f"  Modified:       {len(summary.get('modified', []))}")
    print(f"  Conflicts:      {len(summary.get('conflicts', []))}")
    print(f"  Deleted:        {len(summary.get('deleted', []))}")
    print("=" * 50)
    
    if summary.get('conflicts'):
        print("\n⚠️  Conflicts detected:")
        for title in summary['conflicts'][:10]:
            print(f"   • {title}")
        if len(summary['conflicts']) > 10:
            print(f"   ... and {len(summary['conflicts']) - 10} more")
    
    print("\n→ Run 'pull' to apply changes")

def cmd_pull(args):
    """Pull fetched changes into local data."""
    from tools.config import ConfigManager
    from tools.sync_engine import SyncEngine
    from tools.extension_resolver import ExtensionResolver, ExtensionLock
    from tools.extension_installer import install_extensions
    
    config = ConfigManager(ROOT_DIR)
    wiki = config.get_active_wiki_config()
    
    if not wiki:
        print("No active wiki. Run 'clone' first.")
        return
    
    engine = SyncEngine(wiki['path'], wiki['url'])
    
    if not engine.has_incomplete_fetch():
        print("No fetched data. Run 'fetch' first.")
        return
    
    # --- Resolve extensions if needed ---
    extensions_dir = os.path.join(wiki['path'], 'extensions')
    lock_path = os.path.join(wiki['path'], 'extensions.lock')
    lock = ExtensionLock.load(lock_path)
    
    if len(lock.extensions) == 0:
        print("\n--- Resolving Extensions (first pull) ---")
        resolver = ExtensionResolver(wiki['path'])
        exported_exts = resolver.load_exported_extensions()
        
        if exported_exts:
            print(f"Found {len(exported_exts)} extensions to check...")
            ext_info = resolver.resolve_all(exported_exts, callback=print)
            
            # Prompt for archived
            archived = resolver.get_unresolved_archived(ext_info)
            for ext in archived:
                resolver.prompt_archived(ext)
            
            resolver.lock.extensions = ext_info
            resolver.save()
            
            # Install
            print("\n--- Installing Extensions ---")
            to_install = resolver.get_extensions_to_install()
            if to_install:
                install_extensions(to_install, extensions_dir, callback=print)
    
    # --- Pull data ---
    summary = engine.pull()
    
    print("\n" + "=" * 50)
    print("Pull Summary")
    print("=" * 50)
    print(f"  Merged:         {len(summary.get('merged', []))}")
    print(f"  Conflicts:      {len(summary.get('conflicts', []))}")
    print("=" * 50)
    
    if summary.get('conflicts'):
        conflict_dir = os.path.join(wiki['path'], 'conflicts')
        print(f"\n⚠️  {len(summary['conflicts'])} conflict files created in:")
        print(f"   {conflict_dir}")
        print("\nResolve conflicts manually, then run 'sync' to update portable wiki.")

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
    from tools.extension_resolver import ExtensionLock
    
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
    
    # Extension status
    wiki = config.get_active_wiki_config()
    if wiki:
        lock_path = os.path.join(wiki['path'], 'extensions.lock')
        lock = ExtensionLock.load(lock_path)
        ext_count = len(lock.extensions)
        if ext_count > 0:
            resolved = sum(1 for e in lock.extensions.values() if e.status != 'unknown')
            print(f"Extensions:      {resolved}/{ext_count} resolved")
        else:
            status['warnings'].append("No extensions.lock - run 'clone' or 'pull' to resolve extensions")
        
        # Check for pending fetch
        tmp_dir = os.path.join(wiki['path'], '.tmp')
        if os.path.exists(tmp_dir):
            tmp_state_file = os.path.join(tmp_dir, 'sync_state.yaml')
            if os.path.exists(tmp_state_file):
                from tools.sync_engine import SyncState
                tmp_state = SyncState.load(tmp_state_file)
                conflicts = sum(1 for p in tmp_state.pages.values() if p.status == 'conflict')
                modified = sum(1 for p in tmp_state.pages.values() if p.status == 'modified')
                new = sum(1 for p in tmp_state.pages.values() if p.status == 'new')
                print(f"Pending Fetch:   {new} new, {modified} modified, {conflicts} conflicts")
                if conflicts > 0:
                    status['warnings'].append(f"{conflicts} conflicts detected - run 'pull' to resolve")
                else:
                    status['warnings'].append("Fetch pending - run 'pull' to apply changes")
        
        # Check for conflict files
        conflict_dir = os.path.join(wiki['path'], 'conflicts')
        if os.path.exists(conflict_dir):
            conflict_files = [f for f in os.listdir(conflict_dir) if f.endswith('.conflict')]
            if conflict_files:
                print(f"Conflicts:       {len(conflict_files)} unresolved")
                status['warnings'].append(f"{len(conflict_files)} conflict files need manual resolution")
        
        # Check for local changes (only if container running)
        if status['container_running']:
            try:
                from tools.sync_engine import SyncEngine
                engine = SyncEngine(wiki['path'], wiki['url'])
                local_changes = engine.get_local_changes()
                if local_changes:
                    print(f"Local Changes:   {len(local_changes)} pages modified")
                    status['warnings'].append(f"{len(local_changes)} pages modified locally - run 'push' to upload")
                    # Show details if --local flag
                    if args.local:
                        print("\n  Modified pages:")
                        for title in local_changes:
                            print(f"    • {title}")
                else:
                    print(f"Local Changes:   none")
            except Exception:
                print(f"Local Changes:   (container not ready)")
    
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

def cmd_optimize(args):
    """Optimize media files with ffmpeg."""
    from tools.config import ConfigManager
    from tools.media_optimizer import MediaOptimizer
    
    config = ConfigManager(ROOT_DIR)
    wiki = config.get_active_wiki_config()
    
    if not wiki:
        print("No active wiki. Run 'clone' first.")
        return
    
    media_dir = os.path.join(wiki['path'], 'data', 'media')
    state_path = os.path.join(wiki['path'], 'media_state.yaml')
    
    if not os.path.exists(media_dir):
        print(f"No media directory found: {media_dir}")
        return
    
    optimizer = MediaOptimizer(media_dir, state_path)
    
    print(f"Optimizing media in {media_dir}...")
    print(f"Quality: {args.quality}, Skip video: {args.skip_video}")
    print(f"Local only: {not args.include_in_push}")
    print()
    
    summary = optimizer.optimize_all(
        quality=args.quality,
        skip_video=args.skip_video,
        local_only=not args.include_in_push,
        callback=print
    )
    
    print("\n" + "=" * 50)
    print("Optimization Summary")
    print("=" * 50)
    print(f"  Optimized:   {summary.get('optimized', 0)}")
    print(f"  Skipped:     {summary.get('skipped', 0)}")
    print(f"  Failed:      {summary.get('failed', 0)}")
    
    if summary.get('saved_bytes', 0) > 0:
        saved = summary['saved_bytes']
        for unit in ['B', 'KB', 'MB', 'GB']:
            if saved < 1024:
                print(f"  Saved:       {saved:.1f} {unit}")
                break
            saved /= 1024
    print("=" * 50)

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
    p.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompt')
    p.set_defaults(func=cmd_push)
    
    # Fetch
    p = subparsers.add_parser('fetch', help='Fetch remote changes (compare)')
    p.add_argument('--discard', action='store_true', help='Discard incomplete previous fetch')
    p.set_defaults(func=cmd_fetch)
    
    # Pull
    p = subparsers.add_parser('pull', help='Pull and merge fetched changes')
    p.set_defaults(func=cmd_pull)
    
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
    p.add_argument('--local', '-l', action='store_true', help='List locally modified pages')
    p.set_defaults(func=cmd_status)
    
    # Cleanup
    p = subparsers.add_parser('cleanup', help='Stop containers and clean up')
    p.add_argument('--volumes', '-v', action='store_true', help='Also remove Docker volumes')
    p.add_argument('--data', '-d', action='store_true', help='Also remove exported data')
    p.set_defaults(func=cmd_cleanup)
    
    # Optimize
    p = subparsers.add_parser('optimize', help='Optimize media files with ffmpeg')
    p.add_argument('--quality', '-q', type=int, default=80, help='Quality 1-100 (default: 80)')
    p.add_argument('--skip-video', action='store_true', help='Skip video files')
    p.add_argument('--include-in-push', action='store_true', help='Allow optimized files in push')
    p.set_defaults(func=cmd_optimize)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
