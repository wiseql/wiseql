"""Run report viewer (S4.2): browse past runs and drill into them.

F6 lists persisted runs from the project's ``runs/`` (newest first); Enter opens
a report, rendered with the same step table and step-detail screens as a live
run — the report is rebuilt into a RunResult so nothing about the rendering is
duplicated.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from wiseql.project import find_project_root
from wiseql.report import list_reports, load_report, report_info, report_to_runresult
from wiseql.tui.run import StepDetailScreen, _status_markup


class ReportDetailScreen(Screen[None]):
    """One past run, rendered like the live run view (static)."""

    TITLE = "WiseQL — Report"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    ReportDetailScreen #rep-status { padding: 0 1; height: auto; }
    ReportDetailScreen #rep-table { height: 1fr; }
    """

    def __init__(self, report: dict) -> None:
        super().__init__()
        self._report = report
        self._result = report_to_runresult(report)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="rep-status")
        yield DataTable(id="rep-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#rep-table", DataTable)
        for col in ("step", "kind", "status", "rows", "ms"):
            table.add_column(col, key=col)
        for s in self._result.steps:
            table.add_row(
                s.name, s.kind, _status_markup(s),
                str(s.row_count) if s.ok else "—", f"{s.elapsed_ms} ms", key=s.name,
            )
        verdict = "[green]✓ ok[/]" if self._result.ok else "[bold red]✗ failed[/]"
        self.query_one("#rep-status", Static).update(
            f"[b]{self._report.get('recipe', '?')}[/] · {self._report.get('started_at', '')} · "
            f"{verdict}  [dim](Enter = step detail · Esc = back)[/]"
        )
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        step = self._result.step(event.row_key.value)
        if step is not None:
            self.app.push_screen(StepDetailScreen(step))


class ReportsScreen(Screen[None]):
    """History of persisted runs."""

    TITLE = "WiseQL — Reports"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    ReportsScreen #reports-table { height: 1fr; }
    ReportsScreen #reports-hint { padding: 0 1; color: $text-muted; }
    """

    def __init__(self, runs_dir: Path | None = None) -> None:
        super().__init__()
        self._runs_dir = runs_dir
        self._paths: list[Path] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="reports-table", cursor_type="row", zebra_stripes=True)
        yield Static("", id="reports-hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#reports-table", DataTable)
        for col in ("when", "recipe", "result", "steps"):
            table.add_column(col, key=col)
        runs_dir = self._runs_dir or ((find_project_root() or Path.cwd()) / "runs")
        self._paths = list_reports(runs_dir)
        for i, path in enumerate(self._paths):
            info = report_info(path)
            result = "[green]✓ ok[/]" if info.ok else "[bold red]✗ failed[/]"
            table.add_row(info.started_at, info.recipe, result, str(info.step_count), key=str(i))

        hint = self.query_one("#reports-hint", Static)
        if not self._paths:
            hint.update(f"No runs yet in {runs_dir} — run a recipe (F2) to create one.")
        else:
            hint.update(f"{len(self._paths)} run(s) · Enter = open")
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value)
        if 0 <= idx < len(self._paths):
            self.app.push_screen(ReportDetailScreen(load_report(self._paths[idx])))
