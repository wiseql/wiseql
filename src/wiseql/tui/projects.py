"""Projects screen (project model): list and switch projects.

Lists every project in the configured projects folder (independent of the
working directory). Enter activates one — scoping recipes, reports, and schema
sync to it; Ctrl+N (the app-level binding) creates a new one in the same folder.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from wiseql.project import list_projects, project_stats


class ProjectsScreen(Screen[None]):
    TITLE = "WiseQL — Projects"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    ProjectsScreen #projects-table { height: 1fr; }
    ProjectsScreen #projects-hint { padding: 0 1; color: $text-muted; }
    """

    def __init__(self, projects_dir: Path) -> None:
        super().__init__()
        self._projects_dir = Path(projects_dir)
        self._paths: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="projects-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="projects-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#projects-table", DataTable)
        for col in ("project", "recipes", "runs"):
            table.add_column(col, key=col)
        self._paths = list_projects(self._projects_dir)
        for i, path in enumerate(self._paths):
            recipes, runs = project_stats(path)
            table.add_row(path.name, str(recipes), str(runs), key=str(i))

        hint = self.query_one("#projects-hint", Static)
        if not self._paths:
            hint.update(f"No projects in {self._projects_dir} — Ctrl+N to create one.")
        else:
            hint.update(f"{len(self._paths)} project(s) · Enter = open · Ctrl+N = new")
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value)
        if 0 <= idx < len(self._paths):
            self.app.set_active_project(self._paths[idx])
            self.app.pop_screen()
