import threading
import time
import json
from typing import Optional
from .exporter import MediaWikiExporter

try:
    from rich.live import Live
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.text import Text
    from rich.align import Align
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

class Tui:
    """A Terminal User Interface for the exporter."""

    def __init__(self, exporter: MediaWikiExporter, root_category: str):
        self.exporter = exporter
        self.root_category = root_category
        self.worker_thread: Optional[threading.Thread] = None

    def _run_worker(self):
        """Target for the background worker thread."""
        self.exporter.run(self.root_category)

    def run(self):
        """Starts the TUI and the background exporter thread."""
        self.worker_thread = threading.Thread(target=self._run_worker, daemon=True)
        self.worker_thread.start()

        if RICH_AVAILABLE:
            self._run_rich_ui()
        else:
            self._run_fallback_ui()

        # Final report
        if RICH_AVAILABLE:
            console = Console()
            console.print("\n[bold green]Export complete.[/bold green]")
            console.print_json(data=self.exporter.report())
        else:
            print("\nExport complete.")
            print(json.dumps(self.exporter.report(), indent=2))

    def _run_rich_ui(self):
        layout = self._build_layout()
        with Live(layout, screen=True, auto_refresh=False) as live:
            try:
                while self.worker_thread and self.worker_thread.is_alive():
                    self._update_layout(layout)
                    live.update(layout, refresh=True)
                    time.sleep(0.5)
            except KeyboardInterrupt:
                self.exporter.request_stop()
                if self.worker_thread: self.worker_thread.join()

    def _run_fallback_ui(self):
        print("Rich library not found. Using simple progress output.")
        try:
            while self.worker_thread and self.worker_thread.is_alive():
                print(json.dumps(self.exporter.report(), indent=2))
                time.sleep(2)
        except KeyboardInterrupt:
            self.exporter.request_stop()
            if self.worker_thread: self.worker_thread.join()

    def _build_layout(self) -> "Layout":
        layout = Layout(name="root")
        layout.split(Layout(name="header", size=3), Layout(ratio=1, name="main"))
        layout["main"].split_row(Layout(name="side"), Layout(name="body", ratio=2))
        layout["side"].split(Layout(name="stats"), Layout(name="progress"))
        return layout

    def _update_layout(self, layout: "Layout"):
        layout["header"].update(Align.center(Text("MediaWiki Exporter", style="bold magenta"), vertical="middle"))
        stats = self.exporter.report()
        stats_text = Text("\n".join(f"[bold]{key}:[/bold] {value}" for key, value in stats.items()))
        layout["stats"].update(Panel(stats_text, title="[bold cyan]Export Stats[/bold cyan]", border_style="cyan"))
        layout["progress"].update(Panel("Running...", title="[bold]Status[/bold]"))
        logs = "\n".join(self.exporter.get_log_lines()[-50:])
        layout["body"].update(Panel(logs, title="[bold yellow]Logs[/bold yellow]", border_style="yellow"))