"""Live run view (S3.4) — the executor, in the TUI.

F2 runs the whole recipe through ``run_recipe`` in a thread worker. Each step's
row lights up pending → running → ok/failed/assert-failed as the executor's
``on_step`` callback fires (marshalled to the UI thread via ``call_from_thread``).
Enter on a step opens its output grid, assertion results, and — for a failed
assertion — the offending rows.
"""

from __future__ import annotations

from rich.markup import escape

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

from wiseql.engine import RunResult, StepRun, run_recipe
from wiseql.recipes import build_plan

_RUN_COLUMNS = ("step", "kind", "status", "rows", "ms")


def _status_markup(s: StepRun) -> str:
    if not s.ok:
        return "[bold red]✗ error[/]"
    if s.assert_failed:
        return f"[yellow]⚠ assert ✗[/] [dim]({s.on_fail})[/]"
    return "[green]✓ ok[/]"


class StepDetailScreen(Screen[None]):
    """One step's output grid, assertion results, and offending rows."""

    TITLE = "WiseQL — Step"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    StepDetailScreen #detail-grid { height: auto; max-height: 18; }
    StepDetailScreen Static { padding: 0 2; }
    """

    def __init__(self, step: StepRun) -> None:
        super().__init__()
        self._step = step

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="detail-scroll"):
            yield Static("", id="detail-summary")
        yield Footer()

    def on_mount(self) -> None:
        s = self._step
        src = s.source or "duckdb"
        if s.ok:
            head = f"[b]{s.name}[/] [dim]({s.kind} · {src})[/] — [green]{s.row_count} row(s)[/] in {s.elapsed_ms} ms"
        else:
            head = f"[b]{s.name}[/] [dim]({s.kind} · {src})[/] — [bold red]✗ {escape(s.error)}[/]"
        self.query_one("#detail-summary", Static).update(head)

        scroll = self.query_one("#detail-scroll", VerticalScroll)

        if s.ok and s.columns:
            scroll.mount(Static("\n[b]Output[/]"))
            grid = DataTable(id="detail-grid", zebra_stripes=True)
            scroll.mount(grid)
            grid.add_columns(*s.columns)
            for row in s.sample:
                grid.add_row(*_cells(row))

        if s.assertions:
            lines = []
            for a in s.assertions:
                mark = "[green]✓[/]" if a.passed else f"[bold red]✗[/] [dim]({s.on_fail})[/]"
                lines.append(f"  {mark} {escape(a.check)}: {escape(a.detail)}")
            scroll.mount(Static("\n[b]Assertions[/]\n" + "\n".join(lines)))

        for a in s.assertions:
            if not a.passed and a.samples:
                scroll.mount(Static(f"\n[b]Offending rows[/] [dim]({escape(a.check)})[/]"))
                g = DataTable(zebra_stripes=True)
                scroll.mount(g)
                g.add_columns(*a.sample_columns)
                for row in a.samples:
                    g.add_row(*_cells(row))


class RunScreen(Screen[None]):
    """Live DAG run: a row per step, lighting up as the executor progresses."""

    TITLE = "WiseQL — Run"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    RunScreen #run-status { padding: 0 1; height: auto; }
    RunScreen #run-table { height: 1fr; }
    """

    def __init__(self, loaded, config, params: dict | None = None, recipe_name: str = "recipe") -> None:
        super().__init__()
        self._loaded = loaded
        self._config = config
        self._params = params or {}
        self._recipe_name = recipe_name
        self._names: list[str] = []
        self._result: RunResult | None = None
        self.status_text = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="run-status")
        yield DataTable(id="run-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#run-table", DataTable)
        for col in _RUN_COLUMNS:
            table.add_column(col, key=col)
        plan = build_plan(self._loaded.recipe)
        for name in plan.order:
            step = self._loaded.recipe.steps[name]
            table.add_row(name, "db" if step.source else "local", "· pending", "", "", key=name)
            self._names.append(name)
        self._set_status(f"Running [b]{self._recipe_name}[/] …")
        table.focus()
        self._run_worker()

    def _set_status(self, markup: str) -> None:
        self.status_text = markup
        self.query_one("#run-status", Static).update(markup)

    @work(thread=True)
    def _run_worker(self) -> None:
        def on_step(name, step_run) -> None:
            self.app.call_from_thread(self._update_step, name, step_run)

        result = run_recipe(
            self._loaded, self._config, params=self._params, on_step=on_step
        )
        self.app.call_from_thread(self._on_done, result)

    def _update_step(self, name: str, step_run: StepRun | None) -> None:
        table = self.query_one("#run-table", DataTable)
        # update_width=True so columns grow to fit values set after the rows were
        # added empty — otherwise "127"/"12.3 ms" get clipped to the header width.
        if step_run is None:
            table.update_cell(name, "status", "[cyan]running…[/]", update_width=True)
            return
        table.update_cell(name, "status", _status_markup(step_run), update_width=True)
        table.update_cell(name, "rows", str(step_run.row_count) if step_run.ok else "—", update_width=True)
        table.update_cell(name, "ms", f"{step_run.elapsed_ms} ms", update_width=True)

    def _on_done(self, result: RunResult) -> None:
        self._result = result
        verdict = "[green]✓ ok[/]" if result.ok else "[bold red]✗ failed[/]"
        extra = f" — {escape(result.error)}" if result.error else ""
        self._set_status(
            f"[b]{self._recipe_name}[/] · run {verdict} in {result.elapsed_ms} ms{extra}"
            "  [dim](Enter = step detail · Esc = back)[/]"
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        # Enter on a step row → its detail (DataTable consumes Enter as RowSelected).
        if self._result is None:
            return
        step = self._result.step(event.row_key.value)
        if step is not None:
            self.app.push_screen(StepDetailScreen(step))


def _cells(row) -> list[str]:
    return ["∅" if v is None else str(v) for v in row]
