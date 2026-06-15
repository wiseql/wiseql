"""In-app text editor (S8) — edit recipe/SQL files without leaving the TUI.

WiseQL's vision is one app for the whole workflow; the missing piece was
authoring. This is a plain text editor over Textual's ``TextArea``: open a
file, edit, Ctrl+S to save, Esc to leave (with an unsaved-changes guard).

No syntax-highlighting dependency is pulled in — ``code_editor`` gives line
numbers and editor key bindings, which is the valuable part; highlighting can
be layered on later via the optional ``textual[syntax]`` extra.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Input, Static, TextArea


class NameModal(ModalScreen[str | None]):
    """Prompt for a single name (e.g. a new recipe's file stem)."""

    DEFAULT_CSS = """
    NameModal { align: center middle; }
    NameModal > Vertical {
        width: 60; height: auto; padding: 1 2;
        background: $surface; border: round $primary;
    }
    NameModal Static { padding-bottom: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, title: str, placeholder: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"[b]{self._title}[/b]")
            yield Input(placeholder=self._placeholder, id="name-input")
            yield Static("[dim]Enter to confirm · Esc to cancel[/]")

    def on_mount(self) -> None:
        self.query_one("#name-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class EditorScreen(Screen[bool]):
    """Edit one file. Dismisses True if the file was saved, else False."""

    TITLE = "WiseQL — Editor"
    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("escape", "close", "Back"),
    ]

    DEFAULT_CSS = """
    EditorScreen #editor {
        border: round $primary 50%;
        border-title-color: $accent;
        height: 1fr;
        margin: 1 2 0 2;
    }
    EditorScreen #editor:focus { border: round $accent; }
    EditorScreen #editor-status { padding: 0 2 1 2; height: auto; }
    """

    def __init__(self, path: Path, on_saved=None) -> None:
        super().__init__()
        self._path = Path(path)
        self._on_saved = on_saved
        self._dirty = False
        self._confirm_discard = False
        self._saved_any = False

    def compose(self) -> ComposeResult:
        yield Header()
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError:
            text = ""
        yield TextArea.code_editor(text, id="editor")
        yield Static("", id="editor-status")
        yield Footer()

    def on_mount(self) -> None:
        editor = self.query_one("#editor", TextArea)
        editor.border_title = str(self._path)
        editor.border_subtitle = "Ctrl+S save · Esc back"
        editor.focus()
        self._set_status("[dim]editing[/]")

    def _set_status(self, markup: str) -> None:
        self.query_one("#editor-status", Static).update(markup)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._dirty = True
        self._confirm_discard = False
        self._set_status("[yellow]● unsaved[/]  [dim](Ctrl+S to save)[/]")

    def action_save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(self.query_one("#editor", TextArea).text, encoding="utf-8")
        except OSError as exc:
            self._set_status(f"[bold red]save failed:[/] {exc}")
            return
        self._dirty = False
        self._saved_any = True
        self._set_status("[green]✓ saved[/]")
        self.notify(f"Saved {self._path.name}")
        if self._on_saved is not None:
            self._on_saved()

    def action_close(self) -> None:
        if self._dirty and not self._confirm_discard:
            self._confirm_discard = True
            self._set_status("[yellow]unsaved changes[/] — Ctrl+S to save, or Esc again to discard")
            return
        self.dismiss(self._saved_any)
