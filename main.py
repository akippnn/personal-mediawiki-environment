import argparse
import signal
import sys
import threading
import time
import traceback
from mediawiki_exporter.exporter import MediaWikiExporter
from mediawiki_exporter.tui import Tui

def run_without_tui(exporter: MediaWikiExporter, category: str):
    """A simple runner for non-interactive environments."""
    print("TUI disabled. Logging directly to console and to debug.log file.")
    
    worker = threading.Thread(target=exporter.run, args=(category,), daemon=True)
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
    p.add_argument('--category', required=True, help='Root category name')
    p.add_argument('--output-dir', default='./export', help='Output directory')
    p.add_argument('--sleep', type=float, default=0.5, help='Seconds to sleep between API requests')
    p.add_argument('--user-agent', default='mediawiki-exporter/2.0', help='User-Agent header')
    p.add_argument('--maxlag', type=int, default=5, help='maxlag value sent to MediaWiki API')
    p.add_argument('--no-tui', action='store_true', help='Disable the rich TUI and print logs directly to the console.')
    args = p.parse_args()

    exporter = None
    try:
        exporter = MediaWikiExporter(api_url=args.api_url, output_dir=args.output_dir, sleep=args.sleep, user_agent=args.user_agent, maxlag=args.maxlag)

        def signal_handler(sig, frame):
            print("\nSignal received, requesting graceful stop...", file=sys.stderr)
            if exporter: exporter.request_stop()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        if args.no_tui:
            run_without_tui(exporter, args.category)
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