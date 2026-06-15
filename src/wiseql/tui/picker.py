"""Project picker — the app's entry screen (centered dialog).

Lists every project in the configured projects folder, on an empty background.
The user selects one (Enter), creates one (n), or quits (Esc). This is the
entry: its Esc quits the app, while the dashboard's Esc returns here.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Static

from wiseql.project import list_projects, project_stats


class ProjectPickerScreen(Screen[None]):
    TITLE = "WiseQL"

    BINDINGS = [
        Binding("escape", "quit_app", "Quit"),
        Binding("n", "new_project", "New project"),
    ]

    DEFAULT_CSS = """
    ProjectPickerScreen { align: center middle; }
    ProjectPickerScreen #picker-box {
        width: 72; max-width: 90%; height: auto; max-height: 80%;
        border: round $primary; background: $surface; padding: 1 2;
    }
    ProjectPickerScreen #picker-title { padding-bottom: 1; }
    ProjectPickerScreen #picker-table { height: auto; max-height: 18; }
    ProjectPickerScreen #picker-hint { padding-top: 1; color: $text-muted; }
    """

    def __init__(self, projects_dir: Path) -> None:
        super().__init__()
        self._projects_dir = Path(projects_dir)
        self._paths: list[Path] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="picker-box"):
            yield Static("[b]Open a Project[/b]", id="picker-title")
            yield DataTable(id="picker-table", cursor_type="row", zebra_stripes=True)
            yield Static("", id="picker-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#picker-table", DataTable)
        for col in ("project", "recipes", "runs"):
            table.add_column(col, key=col)
        self._paths = list_projects(self._projects_dir)
        for i, path in enumerate(self._paths):
            recipes, runs = project_stats(path)
            table.add_row(path.name, str(recipes), str(runs), key=str(i))

        hint = self.query_one("#picker-hint", Static)
        loc = f"[dim]projects in {self._projects_dir}[/]"
        if self._paths:
            hint.update(f"{loc}\n[dim]↑/↓ select · enter open · n new · esc quit[/]")
        else:
            hint.update(f"{loc}\n[dim]none yet — n new · esc quit[/]")
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value)
        if 0 <= idx < len(self._paths):
            self.app.open_project(self._paths[idx])

    def action_quit_app(self) -> None:
        self.app.exit()

    def action_new_project(self) -> None:
        self.app.action_new_project()
