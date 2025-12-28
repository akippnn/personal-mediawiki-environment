import argparse
import signal
import sys
import threading
import time
import traceback
from exporter import MediaWikiExporter
from tui import Tui

def run_without_tui(exporter: MediaWikiExporter, category: str, scope: str, export_format: str, skip_media: bool = False, with_history: bool = False):
    """A simple runner for non-interactive environments."""
    print("TUI disabled. Logging directly to console and to debug.log file.")
    
    worker = threading.Thread(target=exporter.run, args=(category, scope, export_format, skip_media, with_history), daemon=True)
    worker.start()
    
    try:
        # Wait for the worker to finish, checking for Ctrl+C periodically
        while worker.is_alive():
            worker.join(timeout=0.5)
    except KeyboardInterrupt:
        print("\nSignal received, requesting graceful stop...", file=sys.stderr)
        exporter.request_stop()
        worker.join() # Wait for the worker to finish shutting down
    
    print("\nExport complete.")
    print(exporter.report())

def main():
    """Main function to parse arguments and start the exporter."""
    p = argparse.ArgumentParser(description="Export a MediaWiki category to Markdown and media files (resumable, safe).")
    p.add_argument('--api-url', required=True, help='MediaWiki API endpoint')
    p.add_argument('--category', help='Root category name (required if scope is category)')
    p.add_argument('--scope', choices=['category', 'all'], default='category', help='Export scope: category (recursive) or all (entire wiki)')
    p.add_argument('--format', choices=['markdown', 'xml'], default='markdown', help='Export format: markdown (for static site) or xml (for import)')
    p.add_argument('--output-dir', default='./export', help='Output directory')
    p.add_argument('--sleep', type=float, default=0.5, help='Seconds to sleep between API requests')
    p.add_argument('--user-agent', default='mediawiki-exporter/2.0', help='User-Agent header')
    p.add_argument('--maxlag', type=int, default=5, help='maxlag value sent to MediaWiki API')
    p.add_argument('--no-tui', action='store_true', help='Disable the rich TUI and print logs directly to the console.')
    p.add_argument('--skip-media', action='store_true', help='Skip downloading media files (metadata only)')
    p.add_argument('--with-history', action='store_true', help='Include full revision history in XML export')
    args = p.parse_args()

    # Validate args
    if args.scope == 'category' and not args.category:
        p.error("--category is required when --scope is 'category'")

    exporter = None
    try:
        exporter = MediaWikiExporter(api_url=args.api_url, output_dir=args.output_dir, sleep=args.sleep, user_agent=args.user_agent, maxlag=args.maxlag)

        def signal_handler(sig, frame):
            print("\nSignal received, requesting graceful stop...", file=sys.stderr)
            if exporter: exporter.request_stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        if args.no_tui:
            run_without_tui(exporter, args.category, args.scope, args.format, args.skip_media, args.with_history)
        else:
            # TUI might need updates to support new args, but for now let's assume TUI only works with category/markdown
            # or we disable TUI for XML/All for simplicity if needed.
            if args.format == 'xml' or args.scope == 'all':
                print("TUI not supported for XML export or 'all' scope yet. Running in console mode.")
                run_without_tui(exporter, args.category, args.scope, args.format, args.skip_media, args.with_history)
            else:
                tui = Tui(exporter, args.category)
                tui.run()

    except Exception as e:
        print(f"A fatal error occurred: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
    finally:
        if exporter:
            exporter.close_log() # Ensure the log file is always closed

if __name__ == "__main__":
    main()