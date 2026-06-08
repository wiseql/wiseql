"""Parameter prompt modal (S3.2).

When F2 runs a recipe that declares ``params``, this collects a value for each
before execution. Values are returned as a dict and bound safely as SQL bind
variables downstream — never string-interpolated.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class ParamModal(ModalScreen[dict | None]):
    """Prompt for each recipe parameter. Dismisses with a {name: value} dict,
    or None if cancelled."""

    DEFAULT_CSS = """
    ParamModal { align: center middle; }
    ParamModal > Vertical {
        width: 64; height: auto; padding: 1 2;
        background: $surface; border: round $primary;
    }
    ParamModal Static { padding-bottom: 1; }
    ParamModal Input { margin-bottom: 1; }
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel", show=False)]

    def __init__(self, recipe_name: str, params: list[str]) -> None:
        super().__init__()
        self._recipe_name = recipe_name
        self._params = params

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(f"Parameters for [b]{self._recipe_name}[/b]")
            for name in self._params:
                yield Input(placeholder=name, id=f"param-{name}")
            yield Static("[dim]Enter to run · Esc to cancel[/]")

    def on_mount(self) -> None:
        self.query_one(f"#param-{self._params[0]}", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(
            {name: self.query_one(f"#param-{name}", Input).value for name in self._params}
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
