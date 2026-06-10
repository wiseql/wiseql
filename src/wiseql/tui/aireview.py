"""Streaming AI output screen (S6.2+).

Opened immediately by an AI action (F4 review now; failure-explain / narrative
in S6.3), then fills in as the model streams — so the user reads as soon as the
first tokens land instead of staring at the underlying screen while a worker
runs invisibly.

Given a provider + a built prompt, it streams ``provider.stream(prompt)`` on a
worker (the model is slow; never the render path). NullProvider yields nothing →
shown as the off hint. Model text is escaped — never interpreted as markup.
"""

from __future__ import annotations

from rich.markup import escape

from textual import work
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

    def __init__(self, title: str, provider, prompt: str) -> None:
        super().__init__()
        self._panel_title = title
        self._provider = provider
        self._prompt = prompt
        self.buffer = ""  # accumulated streamed text (exposed for tests)
        self.done = False

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="ai-scroll"):
            yield Static("", id="ai-output")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#ai-output").border_title = self._panel_title
        self.query_one("#ai-output", Static).update("[dim]Running AI review … (streaming)[/]")
        self._stream_worker()

    @work(thread=True)
    def _stream_worker(self) -> None:
        if getattr(self._provider, "name", "") == "null":
            self.app.call_from_thread(self._finish, "AI is off — enable it in Settings (F9).")
            return
        any_chunk = False
        try:
            for chunk in self._provider.stream(self._prompt):
                any_chunk = True
                self.app.call_from_thread(self._append, chunk)
        except ModuleNotFoundError:
            # AI is enabled but the [ai] extra isn't in this process.
            self.app.call_from_thread(
                self._finish,
                "The [ai] add-on isn't installed in this session.\n"
                "Relaunch with:  make run-ai   (or:  uv run --extra ai wiseql)\n"
                "For an installed copy:  uv tool install 'wiseql[ai]'",
            )
            return
        except Exception as exc:  # noqa: BLE001 — degrade to a readable message
            self.app.call_from_thread(self._finish, f"AI unavailable: {str(exc).strip()}")
            return
        if not any_chunk:
            self.app.call_from_thread(self._finish, "AI is unavailable right now.")
        else:
            self.app.call_from_thread(self._mark_done)

    def _append(self, chunk: str) -> None:
        self.buffer += chunk
        self.query_one("#ai-output", Static).update(escape(self.buffer))
        self.query_one("#ai-scroll", VerticalScroll).scroll_end(animate=False)

    def _finish(self, message: str) -> None:
        self.buffer = message
        self.query_one("#ai-output", Static).update(escape(message))
        self.done = True

    def _mark_done(self) -> None:
        self.done = True
