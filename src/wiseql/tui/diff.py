"""Run diff view (S5.2): two runs side by side, step by step.

Opened from the dashboard's Runs tab (Ctrl+D) comparing the selected run
against the previous run of the same recipe. Read-only; renders the ``RunDiff``
from ``engine.diff`` as a per-step table with row deltas and status/assertion
changes — the row delta is the spine (the signal that moves when the data
changes but the recipe doesn't).
"""

from __future__ import annotations

from rich.markup import escape

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static


def _delta_cell(step) -> str:
    if not step.in_a:
        return "[green]new[/]"
    if not step.in_b:
        return "[red]gone[/]"
    delta = step.row_delta
    if delta is None:
        return "—"
    if delta == 0:
        return "[dim]0[/]"
    return f"[b cyan]{'+' if delta > 0 else ''}{delta}[/]"


def _status_cell(step) -> str:
    if not step.in_a:
        return "[green]added[/]"
    if not step.in_b:
        return "[red]removed[/]"
    a, b = ("ok" if step.a_ok else "err"), ("ok" if step.b_ok else "err")
    if step.ok_changed:
        return f"[bold yellow]{a}→{b}[/]"
    return "[dim]ok[/]" if step.a_ok else "[red]err[/]"


def _notes_cell(step) -> str:
    parts: list[str] = []
    for a in step.assertions:
        if not a.changed:
            continue
        if a.a_passed != a.b_passed:
            ap = "—" if a.a_passed is None else ("✓" if a.a_passed else "✗")
            bp = "—" if a.b_passed is None else ("✓" if a.b_passed else "✗")
            parts.append(f"{escape(a.check)}: {ap}→{bp}")
        else:
            parts.append(f"{escape(a.check)}: {escape(a.a_detail)} → {escape(a.b_detail)}")
    return "; ".join(parts)


class DiffScreen(Screen[None]):
    """Two runs, step by step (A older → B newer)."""

    TITLE = "WiseQL — Diff"
    BINDINGS = [Binding("escape", "app.pop_screen", "Back")]

    DEFAULT_CSS = """
    DiffScreen #diff-status { padding: 0 1; height: auto; }
    DiffScreen #diff-table { height: 1fr; }
    """

    def __init__(self, diff) -> None:
        super().__init__()
        self._diff = diff

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="diff-status")
        yield DataTable(id="diff-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        d = self._diff
        table = self.query_one("#diff-table", DataTable)
        for col in ("step", "A rows", "B rows", "Δ", "status", "notes"):
            table.add_column(col, key=col)
        for s in d.steps:
            a_rows = "—" if s.a_rows is None else str(s.a_rows)
            b_rows = "—" if s.b_rows is None else str(s.b_rows)
            name = f"[yellow]{escape(s.name)}[/]" if s.changed else escape(s.name)
            table.add_row(name, a_rows, b_rows, _delta_cell(s), _status_cell(s), _notes_cell(s), key=s.name)

        recipe = (
            f"[b]{escape(d.recipe_a)}[/]" if d.same_recipe
            else f"[bold yellow]⚠ {escape(d.recipe_a)} ≠ {escape(d.recipe_b)}[/]"
        )
        av, bv = ("ok" if d.a_ok else "failed"), ("ok" if d.b_ok else "failed")
        verdict = f"A {av} → B {bv}"
        verdict = f"[bold yellow]{verdict}[/]" if d.verdict_changed else f"[dim]{verdict}[/]"
        warn = "  [yellow]· params differ[/]" if d.params_differ else ""
        self.query_one("#diff-status", Static).update(
            f"{recipe}  [dim]A=[/]{escape(d.a_label)} [dim]B=[/]{escape(d.b_label)}  {verdict}{warn}"
            f"  [dim]· {len(d.changed_steps)} changed · Esc = back[/]"
        )
        table.focus()
