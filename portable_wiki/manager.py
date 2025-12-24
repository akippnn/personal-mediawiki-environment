#!/usr/bin/env python3
"""
Portable Wiki Manager - Standalone instance management

Usage:
    python manager.py start       Start the wiki
    python manager.py stop        Stop the wiki
    python manager.py status      Show container status
    python manager.py install     Run MediaWiki install
    python manager.py import      Import XML dumps
    python manager.py extensions  Install extensions
"""
import argparse
import subprocess
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def docker_compose(*args):
    """Run docker-compose command."""
    cmd = ['docker-compose'] + list(args)
    return subprocess.run(cmd, cwd=SCRIPT_DIR)

def exec_mediawiki(*args):
    """Execute command in mediawiki container."""
    cmd = ['docker-compose', 'exec', '-T', 'mediawiki'] + list(args)
    return subprocess.run(cmd, cwd=SCRIPT_DIR, capture_output=True, text=True)

def cmd_start(args):
    """Start the wiki containers."""
    print("Starting Portable Wiki...")
    docker_compose('up', '-d')
    print("\nWiki available at http://localhost:8080")

def cmd_stop(args):
    """Stop the wiki containers."""
    print("Stopping Portable Wiki...")
    docker_compose('down')

def cmd_status(args):
    """Show container status."""
    docker_compose('ps')

def cmd_install(args):
    """Run MediaWiki installation."""
    print("Installing MediaWiki...")
    result = exec_mediawiki(
        'php', 'maintenance/install.php',
        '--dbserver', 'database',
        '--dbname', 'my_wiki',
        '--dbuser', 'wikiuser',
        '--dbpass', 'wikipass',
        '--server', 'http://localhost:8080',
        '--scriptpath', '',
        '--pass', 'adminpassword',
        'PortableWiki', 'admin'
    )
    if result.returncode == 0:
        # Enable uploads and extensions
        exec_mediawiki('bash', '-c', '''cat >> LocalSettings.php << 'EOF'
$wgEnableUploads = true;
$wgPFEnableStringFunctions = true;
$wgScribuntoDefaultEngine = "luastandalone";

# Load installed extensions
wfLoadExtension( 'Scribunto' );
wfLoadExtension( 'ParserFunctions' );
wfLoadExtension( 'TemplateStyles' );
wfLoadExtension( 'Cite' );
wfLoadExtension( 'WikiEditor' );
wfLoadExtension( 'CodeEditor' );
wfLoadExtension( 'InputBox' );
wfLoadExtension( 'CategoryTree' );
wfLoadExtension( 'Gadgets' );
wfLoadExtension( 'PageImages' );
wfLoadExtension( 'TextExtracts' );
wfLoadExtension( 'Poem' );
EOF''')
        print("✓ MediaWiki installed")
    else:
        print(f"Installation failed: {result.stderr}")

def cmd_import(args):
    """Import XML dumps."""
    data_dir = os.path.join(SCRIPT_DIR, 'data', 'xml')
    if not os.path.exists(data_dir):
        print("No XML data directory found")
        return
    
    xml_files = sorted([f for f in os.listdir(data_dir) if f.endswith('.xml')])
    print(f"Importing {len(xml_files)} XML files...")
    
    # Import in parallel batches
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    def import_file(filename):
        container_path = f"/var/www/data/xml/{filename}"
        result = exec_mediawiki('php', 'maintenance/importDump.php', container_path, '--username-prefix=')
        return filename, result.returncode == 0
    
    success = 0
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(import_file, f): f for f in xml_files}
        for future in as_completed(futures):
            filename, ok = future.result()
            if ok:
                success += 1
                print(f"  ✓ {filename}")
            else:
                print(f"  ✗ {filename}")
    
    print(f"\nImported {success}/{len(xml_files)} files")
    
    # Import images
    media_dir = os.path.join(SCRIPT_DIR, 'data', 'media')
    if os.path.exists(media_dir) and os.listdir(media_dir):
        img_count = len(os.listdir(media_dir))
        print(f"\nImporting {img_count} images...")
        result = exec_mediawiki('php', 'maintenance/importImages.php', '/var/www/data/media', '--overwrite')
        if result.returncode == 0:
            print("✓ Images imported")
        else:
            print(f"⚠ Image import issues: {result.stderr[:200]}")
    else:
        print("\nNo images to import")
    
    # Rebuild indexes
    print("\nRebuilding database...")
    exec_mediawiki('php', 'maintenance/rebuildrecentchanges.php')
    exec_mediawiki('php', 'maintenance/initSiteStats.php', '--update')

def cmd_extensions(args):
    """Install or list extensions."""
    if args.list:
        result = exec_mediawiki('ls', '/var/www/html/extensions')
        print("Installed extensions:")
        print(result.stdout)
    else:
        print("Extensions are installed via setup container")

def main():
    parser = argparse.ArgumentParser(
        description='Portable Wiki Instance Manager'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    subparsers.add_parser('start', help='Start wiki').set_defaults(func=cmd_start)
    subparsers.add_parser('stop', help='Stop wiki').set_defaults(func=cmd_stop)
    subparsers.add_parser('status', help='Show status').set_defaults(func=cmd_status)
    subparsers.add_parser('install', help='Run MediaWiki install').set_defaults(func=cmd_install)
    subparsers.add_parser('import', help='Import XML dumps').set_defaults(func=cmd_import)
    
    p = subparsers.add_parser('extensions', help='Manage extensions')
    p.add_argument('--list', '-l', action='store_true', help='List installed')
    p.set_defaults(func=cmd_extensions)
    
    args = parser.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
