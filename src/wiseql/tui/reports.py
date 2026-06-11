"""Run report detail (S4.2) — render one past run like the live run view.

The run history list lives in the dashboard's Runs tab; selecting a run opens
this screen, which rebuilds the report into a RunResult so it reuses the live
run-view rendering (step table + step detail) with no duplication.

F4 runs an AI review of the run (S6.3) — what it did, what's correct, what's
wrong and where to look — streamed into the AI screen.
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

    TITLE = "WiseQL — Run report"
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("f4", "ai_explain", "AI explain"),
    ]

    DEFAULT_CSS = """
    ReportDetailScreen #rep-status {
        border: round $primary 50%;
        border-title-color: $accent;
        height: auto;
        padding: 0 1;
        margin: 1 2 0 2;
    }
    ReportDetailScreen #rep-table {
        border: round $primary 50%;
        border-title-color: $accent;
        height: 1fr;
        margin: 0 2 1 2;
    }
    """

    def __init__(self, report: dict, project=None) -> None:
        super().__init__()
        self._report = report
        self._project = project  # project root → AI grounding (recipe + context)
        self._result = report_to_runresult(report)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="rep-status")
        yield DataTable(id="rep-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        status = self.query_one("#rep-status", Static)
        status.border_title = "run report"
        table = self.query_one("#rep-table", DataTable)
        table.border_title = "steps"
        table.border_subtitle = "Enter = step detail · F4 = AI explain · Esc = back"
        for col in ("step", "kind", "status", "rows", "ms"):
            table.add_column(col, key=col)
        for s in self._result.steps:
            table.add_row(
                s.name, s.kind, _status_markup(s),
                str(s.row_count) if s.ok else "—", f"{s.elapsed_ms} ms", key=s.name,
            )
        verdict = "[green]✓ ok[/]" if self._result.ok else "[bold red]✗ failed[/]"
        status.update(
            f"[b]{self._report.get('recipe', '?')}[/]  [dim]{self._report.get('started_at', '')}[/]  {verdict}"
        )
        table.focus()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        step = self._result.step(event.row_key.value)
        if step is not None:
            self.app.push_screen(StepDetailScreen(step))

    def action_ai_explain(self) -> None:
        from wiseql.tui.aireview import push_run_review

        push_run_review(self.app, self._report, self._project)
