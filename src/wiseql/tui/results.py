"""Results screen (S2.3): run one database step and show its rows in a grid.

The query runs in a thread worker so the UI stays responsive during the
round-trip; the grid and summary populate via ``call_from_thread``.

The grid is Textual's built-in ``DataTable``, which is plenty for a single
step's capped result set. Swapping in ``textual-fastdatatable`` (Arrow-backed,
1M-row scrolling) is an isolated upgrade for later, when result size demands it
— see BACKLOG S2.3 note.
"""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from wiseql.config.model import Connection
from wiseql.engine import StepChoice, StepResult, run_step


class ResultsScreen(Screen[None]):
    """Run a single step and display its rows."""

    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    ResultsScreen #result-status { padding: 0 1; height: auto; }
    ResultsScreen #result-grid { height: 1fr; }
    """

    def __init__(self, choice: StepChoice, conn: Connection) -> None:
        super().__init__()
        self._choice = choice
        self._conn = conn
        self.status_text = ""  # mirror of the status line, exposed for tests

    def _status(self, markup: str) -> None:
        self.status_text = markup
        self.query_one("#result-status", Static).update(markup)

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="result-status")
        yield DataTable(id="result-grid", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self._status(
            f"Running step [b]{self._choice.name}[/] on [b]{self._choice.source}[/] "
            f"[dim]{self._conn.target}[/dim] …"
        )
        self._run_worker()

    @work(thread=True)
    def _run_worker(self) -> None:
        result = run_step(self._choice.source, self._conn, self._choice.sql)
        self.app.call_from_thread(self._show, result)

    def _show(self, result: StepResult) -> None:
        if not result.ok:
            self._status(f"[bold red]✗ {result.error}[/]")
            return

        table = self.query_one("#result-grid", DataTable)
        table.clear(columns=True)
        table.add_columns(*result.columns)
        for row in result.rows:
            table.add_row(*["∅" if v is None else str(v) for v in row])

        suffix = "+" if result.truncated else ""
        more = "  [yellow](truncated — more rows exist)[/]" if result.truncated else ""
        self._status(
            f"[b]{self._choice.name}[/] — [green]{result.row_count}{suffix} row(s)[/] "
            f"in {result.elapsed_ms} ms{more}"
        )
        table.focus()
