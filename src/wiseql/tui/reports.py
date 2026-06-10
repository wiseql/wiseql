"""Run report detail (S4.2): render one past run like the live run view.

The run history list lives in the dashboard's Runs tab; selecting a run opens
this screen, which rebuilds the report into a RunResult so it reuses the live
run-view rendering (step table + step detail) with no duplication.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from wiseql.report import report_to_runresult
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
