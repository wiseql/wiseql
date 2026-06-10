"""Settings screen (S6.1) — currently the optional AI add-on status.

Shows whether AI is enabled/reachable and, when it isn't, the
visible-but-disabled hint required by the architecture rule (AI features never
fail; they only ever *add* information). Enabling pulls a model, so it's done
from a terminal (`wiseql ai setup`); this screen reports state and points there.

The live probe (`describe_status`) is network I/O when AI is enabled, so it runs
in a thread worker — never on the render path.
"""

from __future__ import annotations

from rich.markup import escape

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class SettingsScreen(Screen[None]):
    TITLE = "WiseQL — Settings"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    SettingsScreen #ai-panel {
        border: round $primary 50%;
        border-title-color: $accent;
        height: auto;
        padding: 1 2;
        margin: 1 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self.status = None  # AIStatus, exposed for tests once probed

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static("", id="ai-panel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ai-panel").border_title = "AI add-on (optional)"
        self.query_one("#ai-panel", Static).update("[dim]checking AI status…[/]")
        self._probe()

    @work(thread=True)
    def _probe(self) -> None:
        from wiseql.ai import describe_status

        status = describe_status()  # network I/O when enabled — hence a worker
        self.app.call_from_thread(self._show_status, status)

    def _show_status(self, status) -> None:
        self.status = status
        lines: list[str] = []
        if status.ready:
            lines.append("[green]✓ ready[/] — AI features are active")
        elif not status.enabled:
            lines.append("[yellow]· off[/] — AI features are disabled")
        else:
            lines.append("[bold red]✗ unavailable[/] — AI is enabled but not usable yet")
        lines.append("")
        lines.append(f"[dim]model:[/] {escape(status.model)}    [dim]host:[/] {escape(status.host)}")
        if status.enabled:
            lines.append(
                f"[dim]installed:[/] {status.installed}   "
                f"[dim]reachable:[/] {status.reachable}   "
                f"[dim]model pulled:[/] {status.model_present}"
            )
        lines.append("")
        lines.append(f"{escape(status.detail)}")
        if not status.ready:
            lines.append("")
            lines.append("[dim]Enable from a terminal:[/]  [b]wiseql ai setup[/]")
        self.query_one("#ai-panel", Static).update("\n".join(lines))
