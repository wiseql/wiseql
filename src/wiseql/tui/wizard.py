"""Project wizard modal (S4.1).

Ctrl+N from the recipe browser opens this: name + description → a scaffolded
project in the current directory, no docs required.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class ProjectWizard(ModalScreen[dict | None]):
    """Collect a project name + description. Dismisses with the dict, or None."""

    DEFAULT_CSS = """
    ProjectWizard { align: center middle; }
    ProjectWizard > Vertical {
        width: 64; height: auto; padding: 1 2;
        background: $surface; border: round $primary;
    }
    ProjectWizard Static { padding-bottom: 1; }
    ProjectWizard Input { margin-bottom: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]New project[/b]")
            yield Input(placeholder="project name (e.g. returns-monitoring)", id="proj-name")
            yield Input(placeholder="description (optional)", id="proj-desc")
            yield Static("[dim]Enter to create · Esc to cancel[/]")

    def on_mount(self) -> None:
        self.query_one("#proj-name", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        name = self.query_one("#proj-name", Input).value.strip()
        if not name:
            self.query_one("#proj-name", Input).focus()
            return
        self.dismiss(
            {"name": name, "description": self.query_one("#proj-desc", Input).value.strip()}
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
