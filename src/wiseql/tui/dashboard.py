"""Project dashboard — the main per-project workspace.

A tabbed view of everything in a project folder:
- Overview: the project.toml manifest, parsed and laid out, plus counts.
- Recipes: pick a recipe → its recipe.toml and its *resolved* SQL (external
  sql_file contents inlined, not the filename).
- Runs: the run history; Enter on a run opens its result.

Actions are scoped to this project: F2 runs the selected recipe, F3 connections,
Ctrl+T syncs the schema, Ctrl+N a new project. Esc returns to the project picker.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from rich.markup import escape
from rich.syntax import Syntax
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    ListItem,
    ListView,
    Static,
    TabbedContent,
    TabPane,
)

from wiseql.recipes import load_recipe
from wiseql.report import (
    REPORT_NAME,
    checkpoint_steps,
    list_reports,
    load_report,
    read_manifest,
    report_info,
)


@dataclass
class _RunRow:
    """One row in the Runs tab: a finished run (report) or an interrupted one (manifest)."""

    run_dir: Path
    report_path: Path | None  # None → interrupted (no report written)
    recipe: str
    started_at: str
    result_markup: str
    steps_text: str
    resumable: bool
    has_checkpoints: bool


def _collect_runs(runs_dir: Path) -> list[_RunRow]:
    """All run dirs newest first: finished (report.json) and interrupted (run.json only)."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    rows: list[_RunRow] = []
    for d in sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True):
        report = d / REPORT_NAME
        manifest = read_manifest(d)
        done = checkpoint_steps(d)
        status = (manifest or {}).get("status")
        total = len((manifest or {}).get("step_sql") or {})
        # Resumable only if a step still remains to run — a fully-checkpointed
        # failed run (e.g. terminal report_samples) has nothing to resume.
        has_work = bool(done) and total > 0 and len(done) < total
        if report.is_file():
            info = report_info(report)
            result = "[green]✓ ok[/]" if info.ok else "[bold red]✗ failed[/]"
            resumable = (not info.ok) and has_work and status in ("failed", "running")
            rows.append(_RunRow(d, report, info.recipe, info.started_at, result, str(info.step_count), resumable, bool(done)))
        elif manifest is not None:
            rows.append(_RunRow(
                d, None, manifest.get("recipe", "?"), manifest.get("started_at", "?"),
                "[yellow]⚠ interrupted[/]", f"{len(done)} ✓",
                has_work and status in ("running", "failed"), bool(done),
            ))
    return rows


class ProjectDashboardScreen(Screen[None]):
    _TABS = ("overview", "recipes", "runs")

    BINDINGS = [
        Binding("escape", "back", "Projects"),
        # priority so tab nav works even when a tab's list/table has focus.
        Binding("1", "switch('overview')", "Overview", priority=True),
        Binding("2", "switch('recipes')", "Recipes", priority=True),
        Binding("3", "switch('runs')", "Runs", priority=True),
        Binding("left", "prev_tab", "Prev tab", priority=True, show=False),
        Binding("right", "next_tab", "Next tab", priority=True, show=False),
        Binding("f2", "run", "Run"),
        Binding("ctrl+r", "resume", "Resume"),
        Binding("ctrl+d", "diff", "Diff vs prev"),
        Binding("ctrl+e", "explore", "Explore data"),
        Binding("f3", "connections", "Connections"),
        Binding("ctrl+t", "sync", "Sync schema"),
        Binding("ctrl+n", "new_project", "New project"),
        Binding("f1", "help", "Help"),
    ]

    DEFAULT_CSS = """
    ProjectDashboardScreen TabPane { padding: 0; }
    ProjectDashboardScreen #overview-pane { border: round $primary 50%; height: 1fr; padding: 1 2; }
    ProjectDashboardScreen #recipe-list { width: 32; border: round $primary 50%; height: 1fr; }
    ProjectDashboardScreen #recipe-detail { border: round $primary 50%; height: 1fr; padding: 0 1; }
    ProjectDashboardScreen #runs-table { border: round $primary 50%; height: 1fr; margin: 0; }
    ProjectDashboardScreen .pane-label { color: $text-muted; padding-top: 1; }

    /* The focused pane lights up (brighter accent border + title) so it's
       obvious where the keys go. */
    ProjectDashboardScreen #overview-pane:focus,
    ProjectDashboardScreen #recipe-list:focus,
    ProjectDashboardScreen #recipe-detail:focus,
    ProjectDashboardScreen #runs-table:focus {
        border: round $accent;
        border-title-color: $accent;
    }
    """

    def __init__(self, project: Path, config_path: Path | None = None) -> None:
        super().__init__()
        self._project = Path(project)
        self._config_path = config_path
        self._recipe_paths: list[Path] = []
        self._current = None  # LoadResult of the selected recipe
        self._run_rows: list[_RunRow] = []
        # Rendered text mirrors, exposed for tests (the panes hold Syntax objects).
        self.overview_text = ""
        self.recipe_toml_text = ""
        self.recipe_sql_text = ""

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Overview", id="overview"):
                with VerticalScroll(id="overview-pane"):
                    yield Static("", id="overview-body")
            with TabPane("Recipes", id="recipes"):
                with Horizontal():
                    yield ListView(id="recipe-list")
                    with VerticalScroll(id="recipe-detail"):
                        yield Static("", id="recipe-meta")
                        yield Static("recipe.toml", classes="pane-label")
                        yield Static("", id="recipe-toml")
                        yield Static("sql (resolved)", classes="pane-label")
                        yield Static("", id="recipe-sql")
            with TabPane("Runs", id="runs"):
                yield DataTable(id="runs-table", cursor_type="row", zebra_stripes=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "WiseQL"
        self.sub_title = f"project · {self._project.name}"
        # Bordered, titled panes for a consistent framed look across tabs.
        for sel, label in (
            ("#overview-pane", "Project"),
            ("#recipe-list", "Recipes"),
            ("#recipe-detail", "Recipe"),
            ("#runs-table", "Runs"),
        ):
            self.query_one(sel).border_title = label
        # Discoverable hints for the Recipes-tab focus flow.
        self.query_one("#recipe-list").border_subtitle = "enter → scroll"
        self.query_one("#recipe-detail").border_subtitle = "esc → list"
        self.query_one("#runs-table").border_subtitle = "enter → detail · ctrl+r resume · ctrl+d diff · ctrl+e explore"
        self._render_overview()
        self._load_recipes()
        self._load_runs()
        self._focus_active_tab()

    def on_screen_resume(self) -> None:
        # A run may have just written a report; refresh the history.
        self._load_runs()

    # --- tab navigation / focus --------------------------------------------

    def on_tabbed_content_tab_activated(self, event) -> None:
        # Any tab switch (digits, ←/→, click) lands focus in the content, so
        # ↑/↓/Enter work immediately — no mouse needed.
        self._focus_active_tab()

    def _focus_active_tab(self) -> None:
        active = self.query_one("#tabs", TabbedContent).active
        sel = {"overview": "#overview-pane", "recipes": "#recipe-list", "runs": "#runs-table"}.get(active)
        if sel:
            try:
                self.query_one(sel).focus()
            except Exception:  # noqa: BLE001
                pass

    def action_prev_tab(self) -> None:
        self._step_tab(-1)

    def action_next_tab(self) -> None:
        self._step_tab(1)

    def _step_tab(self, delta: int) -> None:
        tabs = self.query_one("#tabs", TabbedContent)
        i = self._TABS.index(tabs.active)
        tabs.active = self._TABS[(i + delta) % len(self._TABS)]

    # --- overview -----------------------------------------------------------

    def _render_overview(self) -> None:
        manifest = self._project / "project.toml"
        lines: list[str] = []
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            self.query_one("#overview-body", Static).update(f"[red]cannot read project.toml: {escape(str(exc))}[/]")
            return

        proj = data.get("project", {})
        lines.append(f"[b]{escape(str(proj.get('name', self._project.name)))}[/b]")
        if proj.get("description"):
            lines.append(f"[i]{escape(str(proj['description']))}[/i]")
        lines.append("")
        for key in ("owner", "tags"):
            if key in proj:
                lines.append(f"[dim]{key}:[/] {escape(str(proj[key]))}")

        defaults = data.get("defaults", {})
        if defaults.get("connection"):
            lines.append(f"[dim]default connection:[/] {escape(str(defaults['connection']))}")

        conns = data.get("connections", {})
        if conns:
            lines.append("")
            lines.append("[b]Connections[/b]")
            for name, c in conns.items():
                target = c.get("dsn") or f"{c.get('host', '?')}:{c.get('port', 1521)}/{c.get('service', '?')}"
                lines.append(f"  [b]{escape(name)}[/] [dim]{escape(target)}  user={escape(str(c.get('user', '—')))}  auth={escape(str(c.get('auth', '—')))}[/]")

        lines.append("")
        lines.append(f"[dim]recipes:[/] {len(list((self._project / 'recipes').glob('*.toml')))}    "
                     f"[dim]runs:[/] {len(list_reports(self._project / 'runs'))}")
        ctx = self._project / "context"
        present = [f.name for f in (ctx / "tables.md", ctx / "domain.md") if f.exists()]
        lines.append(f"[dim]context:[/] {', '.join(present) if present else '—'}")
        lines.append("")
        lines.append("[dim]2 Recipes · 3 Runs · F2 run · F3 connections · Ctrl+T sync · Esc projects[/]")

        self.overview_text = "\n".join(lines)
        self.query_one("#overview-body", Static).update(self.overview_text)

    # --- recipes ------------------------------------------------------------

    def _load_recipes(self) -> None:
        list_view = self.query_one("#recipe-list", ListView)
        list_view.clear()
        recipes_dir = self._project / "recipes"
        self._recipe_paths = sorted(recipes_dir.glob("*.toml")) if recipes_dir.is_dir() else []
        for path in self._recipe_paths:
            list_view.append(ListItem(Static(path.stem, markup=False)))
        if self._recipe_paths:
            list_view.index = 0
            self._show_recipe(self._recipe_paths[0])
        else:
            self.query_one("#recipe-meta", Static).update("[dim]no recipes in this project[/]")

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        lv = self.query_one("#recipe-list", ListView)
        if lv.index is not None and self._recipe_paths:
            self._show_recipe(self._recipe_paths[lv.index])

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        # Enter on a recipe → focus the detail pane so ↑/↓ scroll its TOML/SQL.
        self.query_one("#recipe-detail").focus()

    def _show_recipe(self, path: Path) -> None:
        self._current = load_recipe(path)
        recipe = self._current.recipe

        meta: list[str] = [f"[b]{escape(path.stem)}[/b]"]
        if recipe is not None:
            r = recipe.recipe
            if r.description:
                meta.append(f"[i]{escape(r.description)}[/i]")
            params = ", ".join(r.params) if r.params else "—"
            meta.append(f"[dim]params:[/] {escape(params)}    [dim]steps:[/] {len(recipe.steps)}")
        ok = self._current.ok
        meta.append("[green]✓ valid[/]" if ok else "[bold red]✗ invalid[/]")
        for issue in self._current.errors:
            meta.append(f"  [red]{escape(str(issue))}[/]")
        self.query_one("#recipe-meta", Static).update("\n".join(meta))

        raw = path.read_text(encoding="utf-8")
        self.recipe_toml_text = raw
        self.query_one("#recipe-toml", Static).update(
            Syntax(raw, "toml", theme="ansi_dark", word_wrap=True)
        )

        # Resolved SQL: external sql_file contents inlined, per step.
        parts = []
        for name, sql in self._current.resolved_sql.items():
            parts.append(f"-- step: {name}\n{sql.strip()}")
        self.recipe_sql_text = "\n\n".join(parts) if parts else "(no SQL)"
        self.query_one("#recipe-sql", Static).update(
            Syntax(self.recipe_sql_text, "sql", theme="ansi_dark", word_wrap=True)
        )
        # New recipe → start the detail pane at the top.
        self.query_one("#recipe-detail").scroll_home(animate=False)

    # --- runs ---------------------------------------------------------------

    def _load_runs(self) -> None:
        table = self.query_one("#runs-table", DataTable)
        table.clear(columns=True)
        for col in ("when", "recipe", "result", "steps"):
            table.add_column(col, key=col)
        # One row per run dir, newest first. A finished run has report.json; an
        # interrupted run (killed before the report) has only its run.json
        # manifest + checkpoints — still listed, so it can be resumed.
        self._run_rows = _collect_runs(self._project / "runs")
        for i, row in enumerate(self._run_rows):
            table.add_row(row.started_at, row.recipe, row.result_markup, row.steps_text, key=str(i))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        idx = int(event.row_key.value)
        if not (0 <= idx < len(self._run_rows)):
            return
        row = self._run_rows[idx]
        if row.report_path is None:
            self.notify("interrupted run — press Ctrl+R to resume it", severity="information")
            return
        from wiseql.tui.reports import ReportDetailScreen

        self.app.push_screen(ReportDetailScreen(load_report(row.report_path)))

    # --- actions ------------------------------------------------------------

    def action_switch(self, tab: str) -> None:
        # Setting active fires TabActivated → _focus_active_tab moves focus in.
        self.query_one("#tabs", TabbedContent).active = tab

    def action_back(self) -> None:
        # In the Recipes tab, Esc from the detail pane returns to the list;
        # otherwise Esc leaves the project for the picker.
        if self.app.focused is self.query_one("#recipe-detail"):
            self.query_one("#recipe-list").focus()
        else:
            self.app.show_picker()

    def _config(self):
        from wiseql.config import load_active_config

        return load_active_config(self._config_path, project_path=self._project / "project.toml").config

    def action_run(self) -> None:
        if self._current is None or self._current.recipe is None or not self._current.ok:
            self.notify("select a valid recipe first (Recipes tab)", severity="warning")
            return
        config = self._config()
        declared = self._current.recipe.recipe.params
        if declared:
            from wiseql.tui.params import ParamModal

            def _got(values: dict | None) -> None:
                if values is not None:
                    self._launch_run(config, values)

            self.app.push_screen(ParamModal(self._current.recipe.recipe.name, declared), _got)
        else:
            self._launch_run(config, {})

    def _launch_run(self, config, params: dict) -> None:
        from wiseql.tui.run import RunScreen

        self.app.push_screen(
            RunScreen(
                self._current, config, params, self._current.recipe.recipe.name,
                runs_dir=self._project / "runs",
            )
        )

    def action_resume(self) -> None:
        """Resume the selected run from its checkpoints (Runs tab)."""
        table = self.query_one("#runs-table", DataTable)
        idx = table.cursor_row
        if not (0 <= idx < len(self._run_rows)):
            self.notify("select a run first (Runs tab)", severity="warning")
            return
        row = self._run_rows[idx]
        if not row.resumable:
            self.notify("this run has nothing to resume", severity="warning")
            return
        loaded = self._find_recipe_by_name(row.recipe)
        if loaded is None or loaded.recipe is None or not loaded.ok:
            self.notify(f"recipe '{row.recipe}' not found or invalid in this project", severity="error")
            return
        from wiseql.tui.run import RunScreen

        params = (read_manifest(row.run_dir) or {}).get("params") or {}
        self.app.push_screen(
            RunScreen(
                loaded, self._config(), params, row.recipe,
                runs_dir=self._project / "runs", resume_from=row.run_dir,
            )
        )

    def action_diff(self) -> None:
        """Diff the selected run against the previous run of the same recipe."""
        table = self.query_one("#runs-table", DataTable)
        idx = table.cursor_row
        if not (0 <= idx < len(self._run_rows)):
            self.notify("select a run first (Runs tab)", severity="warning")
            return
        newer = self._run_rows[idx]
        if newer.report_path is None:
            self.notify("interrupted run has no report to diff", severity="warning")
            return
        # _run_rows is newest-first, so older runs sit at higher indices.
        older = next(
            (r for r in self._run_rows[idx + 1:] if r.report_path is not None and r.recipe == newer.recipe),
            None,
        )
        if older is None:
            self.notify(f"no earlier run of '{newer.recipe}' to diff against", severity="information")
            return
        from wiseql.engine import diff_runs
        from wiseql.tui.diff import DiffScreen

        d = diff_runs(
            load_report(older.report_path), load_report(newer.report_path),
            a_label=older.run_dir.name, b_label=newer.run_dir.name,
        )
        self.app.push_screen(DiffScreen(d))

    def action_explore(self) -> None:
        """Open the Data Explorer over the selected run's checkpoints."""
        table = self.query_one("#runs-table", DataTable)
        idx = table.cursor_row
        if not (0 <= idx < len(self._run_rows)):
            self.notify("select a run first (Runs tab)", severity="warning")
            return
        row = self._run_rows[idx]
        if not row.has_checkpoints:
            self.notify("this run has no checkpoints to explore", severity="warning")
            return
        from wiseql.tui.explorer import ExplorerScreen

        self.app.push_screen(ExplorerScreen(row.run_dir, row.recipe))

    def _find_recipe_by_name(self, name: str):
        """Find the LoadResult whose [recipe].name matches (manifests store the name)."""
        for path in self._recipe_paths:
            loaded = load_recipe(path)
            if loaded.recipe is not None and loaded.recipe.recipe.name == name:
                return loaded
        return None

    def action_connections(self) -> None:
        from wiseql.tui.connections import ConnectionsScreen

        self.app.push_screen(
            ConnectionsScreen(config_path=self._config_path, project_path=self._project / "project.toml")
        )

    def action_new_project(self) -> None:
        self.app.action_new_project()

    def action_help(self) -> None:
        from wiseql.tui.app import HelpScreen

        self.app.push_screen(HelpScreen())

    def action_sync(self) -> None:
        config = self._config()
        name = config.defaults.connection
        conn = config.connections.get(name) if name else None
        if conn is None:
            self.notify("no default connection configured (F3)", severity="error")
            return
        self.notify(f"Syncing schema from {name} …")
        self._sync_worker(name, conn)

    @work(thread=True)
    def _sync_worker(self, name, conn) -> None:
        from wiseql.config import open_connection
        from wiseql.context import introspect_tables, write_tables_md

        try:
            connection = open_connection(name, conn)
            try:
                tables = introspect_tables(connection)
            finally:
                connection.close()
            write_tables_md(self._project / "context" / "tables.md", tables, project_name=self._project.name)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self.notify, f"sync failed: {str(exc).strip()}", severity="error")
            return
        self.app.call_from_thread(self.notify, f"Synced {len(tables)} tables → context/tables.md")
