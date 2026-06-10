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
    DiffScreen #diff-summary {
        border: round $primary 50%;
        height: auto;
        padding: 0 1;
        margin: 1 1 0 1;
    }
    DiffScreen #diff-table {
        border: round $primary 50%;
        height: 1fr;
        margin: 0 1 1 1;
    }
    /* Titles render as a filled accent chip so they read as labels, not as
       part of the content row. */
    DiffScreen #diff-summary, DiffScreen #diff-table {
        border-title-color: $background;
        border-title-background: $accent;
        border-title-style: bold;
        border-subtitle-color: $text-muted;
    }
    """

    def __init__(self, diff) -> None:
        super().__init__()
        self._diff = diff

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="diff-summary")
        yield DataTable(id="diff-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        d = self._diff
        self.title = "WiseQL — Diff"
        self.sub_title = d.recipe_a if d.same_recipe else f"{d.recipe_a} ≠ {d.recipe_b}"

        # Summary panel — framed + titled, so it reads as a labelled window.
        summary = self.query_one("#diff-summary", Static)
        summary.border_title = " Diff — comparing two runs "
        av = "[green]ok[/]" if d.a_ok else "[red]failed[/]"
        bv = "[green]ok[/]" if d.b_ok else "[red]failed[/]"
        lines: list[str] = []
        if d.same_recipe:
            lines.append(f"recipe  [b]{escape(d.recipe_a)}[/]")
        else:
            lines.append(f"[bold yellow]⚠ different recipes[/]  A=[b]{escape(d.recipe_a)}[/]  B=[b]{escape(d.recipe_b)}[/]")
        lines.append(f"[dim]A (older):[/]  {escape(d.a_label)}   {av}")
        lines.append(f"[dim]B (newer):[/]  {escape(d.b_label)}   {bv}")
        flags: list[str] = []
        if d.verdict_changed:
            flags.append("[bold yellow]verdict changed[/]")
        if d.params_differ:
            flags.append(f"[yellow]params differ[/] [dim](A={d.params_a}  B={d.params_b})[/]")
        if flags:
            lines.append("  ·  ".join(flags))
        n = len(d.changed_steps)
        verdict_word = "identical" if n == 0 else f"{n} of {len(d.steps)} step(s) changed"
        lines.append(f"[b]{verdict_word}[/]")
        summary.update("\n".join(lines))

        # Results table — framed + titled.
        table = self.query_one("#diff-table", DataTable)
        table.border_title = " per-step changes "
        table.border_subtitle = "Δ = B − A  ·  changed rows in yellow  ·  Esc = back"
        for col in ("step", "A rows", "B rows", "Δ", "status", "notes"):
            table.add_column(col, key=col)
        for s in d.steps:
            a_rows = "—" if s.a_rows is None else str(s.a_rows)
            b_rows = "—" if s.b_rows is None else str(s.b_rows)
            name = f"[yellow]{escape(s.name)}[/]" if s.changed else escape(s.name)
            table.add_row(name, a_rows, b_rows, _delta_cell(s), _status_cell(s), _notes_cell(s), key=s.name)
        table.focus()
