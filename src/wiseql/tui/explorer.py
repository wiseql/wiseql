"""Data Explorer screen (S5.3) — ad-hoc SQL over a run's checkpoints, in-app.

Opened from the dashboard's Runs tab on a run that has checkpoints. The run's
``checkpoints/<step>.parquet`` mount as DuckDB views named after each step
(shown in the left panel); type SQL, Enter runs it, results land in the grid.
Every query joins the history list — Enter on a past query recalls and reruns
it. This is the built-in replacement for reaching for an external SQL IDE:
explore the exact frozen data a run produced, no re-run, no second tool.

Queries run synchronously — the data is local Parquet over an in-memory DuckDB,
and results are capped — so no thread worker is needed.
"""

from __future__ import annotations

from pathlib import Path

from rich.markup import escape

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Input, ListItem, ListView, Static

from wiseql.engine.explorer import CheckpointExplorer


def _cells(row) -> list[str]:
    return ["∅" if v is None else str(v) for v in row]


class ExplorerScreen(Screen[None]):
    """Ad-hoc DuckDB SQL over one run's frozen checkpoints."""

    TITLE = "WiseQL — Data Explorer"
    BINDINGS = [Binding("escape", "close", "Back")]

    DEFAULT_CSS = """
    ExplorerScreen #explorer-body { height: 1fr; }
    ExplorerScreen #explorer-side { width: 34; border: round $primary 50%; height: 1fr; padding: 0 1; }
    ExplorerScreen #explorer-main { height: 1fr; }
    ExplorerScreen #sql-input { border: round $primary 50%; }
    ExplorerScreen #sql-input:focus { border: round $accent; }
    ExplorerScreen #explorer-status { padding: 0 1; height: auto; }
    ExplorerScreen #explorer-results { height: 1fr; border: round $primary 50%; }
    ExplorerScreen #history { height: auto; max-height: 50%; }
    """

    def __init__(self, run_dir: Path, recipe: str = "") -> None:
        super().__init__()
        self._run_dir = Path(run_dir)
        self._recipe = recipe
        self._explorer: CheckpointExplorer | None = None
        self.history: list[str] = []  # newest last
        self.last_result = None  # exposed for tests

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="explorer-body"):
            with VerticalScroll(id="explorer-side"):
                yield Static("", id="tables")
                yield Static("[dim]history[/]", classes="pane-label")
                yield ListView(id="history")
            with Vertical(id="explorer-main"):
                yield Input(placeholder="SELECT … over the steps on the left — Enter to run", id="sql-input")
                yield Static("", id="explorer-status")
                yield DataTable(id="explorer-results", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"{self._recipe} · {self._run_dir.name}" if self._recipe else self._run_dir.name
        self._explorer = CheckpointExplorer(self._run_dir)
        self.query_one("#explorer-side").border_title = "tables"

        infos = self._explorer.table_info()
        if infos:
            lines = ["[b]steps mounted[/]"]
            for t in infos:
                lines.append(f"[cyan]{escape(t.name)}[/] [dim]{t.row_count} rows[/]")
                lines.append(f"  [dim]{escape(', '.join(t.columns))}[/]")
            self.query_one("#tables", Static).update("\n".join(lines))
            # A useful starter query over the first mounted step.
            first = infos[0].name
            self.query_one("#sql-input", Input).value = f'SELECT * FROM "{first}" LIMIT 20'
            self._set_status(f"[dim]{len(infos)} step(s) mounted — Enter to run[/]")
        else:
            self.query_one("#tables", Static).update("[yellow]no checkpoints in this run[/]")
            self._set_status("[yellow]this run has no checkpoints to explore[/]")
        self.query_one("#sql-input", Input).focus()

    def _set_status(self, markup: str) -> None:
        self.query_one("#explorer-status", Static).update(markup)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._run_query(event.value)

    def _run_query(self, sql: str) -> None:
        if self._explorer is None:
            return
        result = self._explorer.query(sql)
        self.last_result = result
        if not result.ok:
            self._set_status(f"[bold red]✗ {escape(result.error)}[/]")
            return

        self._record_history(sql)
        table = self.query_one("#explorer-results", DataTable)
        table.clear(columns=True)
        table.add_columns(*(result.columns or ["(no columns)"]))
        for row in result.rows:
            table.add_row(*_cells(row))
        more = "  [yellow](capped)[/]" if result.truncated else ""
        self._set_status(f"[green]✓[/] {result.row_count} row(s){more}")

    def _record_history(self, sql: str) -> None:
        sql = sql.strip()
        if not sql or (self.history and self.history[-1] == sql):
            return
        self.history.append(sql)
        hist = self.query_one("#history", ListView)
        hist.insert(0, [ListItem(Static(sql, markup=False))])  # newest on top

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Enter on a history entry → recall it into the input and rerun.
        idx = event.list_view.index
        if idx is None:
            return
        sql = list(reversed(self.history))[idx]  # list shows newest-first
        self.query_one("#sql-input", Input).value = sql
        self.query_one("#sql-input", Input).focus()
        self._run_query(sql)

    def action_close(self) -> None:
        if self._explorer is not None:
            self._explorer.close()
        self.app.pop_screen()
