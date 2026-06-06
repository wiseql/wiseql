"""The WiseQL Textual application shell (Sprint 0).

Norton Commander spirit: everything reachable via the F-key bar at the
bottom. Sprint 1 adds the recipe browser; this shell establishes the frame.
"""

from __future__ import annotations

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Middle
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Static

from wiseql import __version__
from wiseql.ai import get_provider

WELCOME = f"""\
[b]WiseQL[/b] [dim]v{__version__}[/dim]

[i]The wise data browser.[/i]

Run SQL recipes as small, observable, debuggable steps.

[dim]Sprint 0 shell — the recipe browser arrives in Sprint 1.
Press F1 for help, F10 to quit.[/dim]
"""

HELP_TEXT = f"""\
[b]WiseQL v{__version__} — Help[/b]

[b]Keys[/b]
  F1   This help
  F10  Quit

[b]What is WiseQL?[/b]
A terminal app that runs SQL [i]recipes[/i] — complex database reads broken
into a DAG of small steps — with live run views, per-step reports, and
assertions that catch data issues automatically.

[b]AI[/b]
AI features are an optional add-on (not installed). When enabled, WiseQL
can explain failed runs and validate recipes semantically.

[dim]Docs: https://wiseql.dev   ·   Press any key to close[/dim]
"""


class HelpScreen(ModalScreen[None]):
    """F1 help, closes on any key."""

    DEFAULT_CSS = """
    HelpScreen {
        align: center middle;
    }
    HelpScreen > Static {
        width: 70;
        max-width: 90%;
        padding: 1 2;
        background: $surface;
        border: round $primary;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)

    def on_key(self) -> None:
        self.dismiss()


class WiseQLApp(App[None]):
    """Application shell: header, welcome pane, F-key footer."""

    TITLE = "WiseQL"
    SUB_TITLE = "the wise data browser"

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f10", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    #welcome {
        text-align: center;
        padding: 1 2;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        # The AI seam exists from day one; NullProvider until Sprint 6.
        self.ai = get_provider()

    def compose(self) -> ComposeResult:
        yield Header()
        with Middle():
            with Center():
                yield Static(WELCOME, id="welcome")
        yield Footer()

    def action_help(self) -> None:
        self.push_screen(HelpScreen())
