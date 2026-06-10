"""AI output screen (S6.2+) — shows an AI review/explanation/narrative.

A plain scrollable text panel reused by the AI actions (semantic validation
now; failure explanation and narrative reports in S6.3). The text is model
output, so it's rendered as escaped plain text — never interpreted as markup.
"""

from __future__ import annotations

from rich.markup import escape

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static


class AIReviewScreen(Screen[None]):
    TITLE = "WiseQL — AI"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    AIReviewScreen #ai-output {
        border: round $primary 50%;
        border-title-color: $accent;
        height: 1fr;
        padding: 1 2;
        margin: 1 2;
    }
    """

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._panel_title = title
        self._text = text or "(no response)"

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll():
            yield Static(escape(self._text), id="ai-output")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ai-output").border_title = self._panel_title
