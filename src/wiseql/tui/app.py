"""The WiseQL Textual application (Sprint 1: recipe browser).

Norton Commander spirit: recipe list on the left, detail + DAG plan on the
right, everything reachable via the F-key bar.
"""

from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, ListItem, ListView, Static, Tree

from wiseql import __version__
from wiseql.ai import get_provider
from wiseql.recipes import LoadResult, build_plan, load_recipe
from wiseql.recipes.dag import describe_step
from wiseql.tui.theme import THEME

HELP_TEXT = f"""\
[b]WiseQL v{__version__} — Help[/b]

[b]Keys[/b]
  F1  or ?       This help
  F2             Run selected recipe (live DAG view; Enter on a step = detail)
  F3             Connections (list · test · login)
  F4             Re-validate selected recipe
  F5             Rebuild plan for selected recipe
  F6             Reports (past runs · Enter to open)
  F7             Projects (switch / list projects)
  F10 or q       Quit (also Ctrl+Q)
  Ctrl+N         New project (in your projects folder)
  Ctrl+T         Sync DB schema → context/tables.md
  ↑/↓            Select recipe

[dim]macOS: F-keys are media keys by default — press Fn+F10, or enable
"Use F1, F2, etc. keys as standard function keys" in Keyboard settings.[/dim]

[b]What is WiseQL?[/b]
A terminal app that runs SQL [i]recipes[/i] — complex database reads broken
into a DAG of small steps — with live run views, per-step reports, and
assertions that catch data issues automatically.

[dim]Docs: https://wiseql.dev   ·   Press any key to close[/dim]
"""

NO_RECIPES = """\
[b]No recipes found.[/b]

Press [b]F7[/b] to pick a project, or [b]Ctrl+N[/b] to create one.
"""

NO_RECIPES_IN_PROJECT = """\
[b]This project has no recipes yet.[/b]

Add [i]*.toml[/i] recipe files to the project's [b]recipes/[/b] folder
(see RECIPE_SPEC.md), then they'll appear here.

[dim]F7 switch project · Ctrl+N new project · Ctrl+T sync schema[/dim]
"""


class HelpScreen(ModalScreen[None]):
    """F1 help, closes on any key."""

    DEFAULT_CSS = """
    HelpScreen { align: center middle; }
    HelpScreen > Static {
        width: 74; max-width: 90%; padding: 1 2;
        background: $surface; border: round $primary;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)

    def on_key(self) -> None:
        self.dismiss()


class WiseQLApp(App[None]):
    """Recipe browser: list pane + detail/plan pane."""

    TITLE = "WiseQL"
    SUB_TITLE = "the wise data browser"

    # Shared spacing/structure theme, cascaded to every screen.
    CSS = THEME

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f2", "run", "Run"),
        Binding("f3", "connections", "Connections"),
        Binding("f4", "validate", "Validate"),
        Binding("f5", "plan", "Plan"),
        Binding("f6", "reports", "Reports"),
        Binding("f7", "projects", "Projects"),
        Binding("f10", "quit", "Quit"),
        Binding("ctrl+n", "new_project", "New project"),
        Binding("ctrl+t", "sync_context", "Sync schema"),
        # macOS fallbacks: F-keys are media keys by default (F10 = mute),
        # so always provide plain-key alternatives.
        Binding("q", "quit", "Quit", show=False),
        Binding("question_mark", "help", "Help", show=False),
    ]

    DEFAULT_CSS = """
    #recipe-list { width: 32; border-right: solid $primary; }
    #detail-pane { padding: 0 1; }
    #detail-text { padding: 1 1; }
    #dag-tree { height: auto; }
    """

    def __init__(
        self,
        recipes_dir: Path | None = None,
        config_path: Path | None = None,
        projects_dir: Path | None = None,
    ) -> None:
        super().__init__()
        self.ai = get_provider()  # NullProvider until the [ai] add-on (Sprint 6)
        self.config_path = config_path  # None → $WISEQL_CONFIG / standard location
        # recipes_dir is a direct/legacy override (tests, ad-hoc): when set, the
        # app shows that folder's recipes and skips the projects model entirely.
        self._recipes_dir_override = recipes_dir
        self._projects_dir_override = projects_dir
        self.active_project: Path | None = None
        self._recipes_dir: Path | None = recipes_dir
        self._current: LoadResult | None = None
        self._paths: list[Path] = []

    @property
    def projects_dir(self) -> Path:
        """The configured projects folder — independent of the working directory."""
        if self._projects_dir_override is not None:
            return Path(self._projects_dir_override)
        from wiseql.config import load_active_config

        return load_active_config(self.config_path).config.projects_root

    # --- layout -------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ListView(id="recipe-list")
            with VerticalScroll(id="detail-pane"):
                yield Static(NO_RECIPES, id="detail-text")
                yield Tree("plan", id="dag-tree")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#dag-tree", Tree).display = False
        if self._recipes_dir_override is not None:
            self._load_recipes(self._recipes_dir_override)
            return
        # Projects model: list projects from the configured folder (not cwd).
        from wiseql.project import list_projects

        projects = list_projects(self.projects_dir)
        if len(projects) == 1:
            self.set_active_project(projects[0])
        else:  # 0 → empty picker with Ctrl+N hint; 2+ → choose
            self._open_projects()

    def _open_projects(self) -> None:
        from wiseql.tui.projects import ProjectsScreen

        self.push_screen(ProjectsScreen(self.projects_dir))

    def set_active_project(self, project: Path) -> None:
        """Make ``project`` active: scope recipes, reports, sync, and config to it."""
        self.active_project = Path(project)
        self.sub_title = f"project · {self.active_project.name}"
        self._load_recipes(self.active_project / "recipes")

    def _project_path(self) -> Path | None:
        return (self.active_project / "project.toml") if self.active_project else None

    def _config(self):
        """Config scoped to the active project's project.toml (its connections/defaults)."""
        from wiseql.config import load_active_config

        return load_active_config(self.config_path, project_path=self._project_path()).config

    def _load_recipes(self, recipes_dir: Path) -> None:
        self._recipes_dir = Path(recipes_dir)
        list_view = self.query_one("#recipe-list", ListView)
        list_view.clear()
        self._paths = sorted(self._recipes_dir.glob("*.toml")) if self._recipes_dir.is_dir() else []
        for path in self._paths:
            list_view.append(ListItem(Static(path.stem, markup=False)))
        if self._paths:
            list_view.index = 0
            self._show(self._paths[0])
        else:
            self._current = None
            self.query_one("#detail-text", Static).update(NO_RECIPES_IN_PROJECT)
            self.query_one("#dag-tree", Tree).display = False

    # --- selection ------------------------------------------------------------

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        list_view = self.query_one("#recipe-list", ListView)
        if list_view.index is not None and self._paths:
            self._show(self._paths[list_view.index])

    # --- rendering ------------------------------------------------------------

    def _show(self, path: Path) -> None:
        result = load_recipe(path)
        self._current = result

        lines: list[str] = []
        if result.recipe is not None:
            meta = result.recipe.recipe
            lines.append(f"[b]{meta.name}[/b]")
            if meta.description:
                lines.append(f"[i]{meta.description}[/i]")
            if meta.params:
                lines.append(f"params: [cyan]{', '.join(meta.params)}[/cyan]")
            lines.append(f"steps: {len(result.recipe.steps)}")
        else:
            lines.append(f"[b]{path.name}[/b]")

        issues = list(result.issues)
        if result.recipe is not None:
            issues += build_plan(result.recipe).issues
        errors = [i for i in issues if i.severity == "error"]

        lines.append("")
        lines.append("[bold red]✗ INVALID[/]" if errors else "[bold green]✓ valid[/]")
        for issue in issues:
            style = "red" if issue.severity == "error" else "yellow"
            lines.append(f"  [{style}]{issue.severity}[/] [dim]{issue.where}[/] — {issue.message}")

        self.detail_text = "\n".join(lines)  # also exposed for tests
        self.query_one("#detail-text", Static).update(self.detail_text)
        self._render_plan()

    def _render_plan(self) -> None:
        tree = self.query_one("#dag-tree", Tree)
        result = self._current
        if result is None or result.recipe is None or result.errors:
            tree.display = False
            return

        recipe = result.recipe
        plan = build_plan(recipe)
        tree.display = True
        tree.clear()
        tree.root.set_label(f"execution plan — {recipe.recipe.name}")
        tree.root.expand()
        if not plan.ok:
            tree.root.add_leaf("✗ cannot plan (cycle)")
            return
        for i, wave in enumerate(plan.waves, start=1):
            node = tree.root.add(f"wave {i}", expand=True)
            for name in wave:
                node.add_leaf(f"{name}  ·  {describe_step(recipe, name)}")

    # --- actions ----------------------------------------------------------------

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_projects(self) -> None:
        self._open_projects()

    def action_connections(self) -> None:
        from wiseql.tui.connections import ConnectionsScreen

        self.push_screen(
            ConnectionsScreen(config_path=self.config_path, project_path=self._project_path())
        )

    def action_reports(self) -> None:
        from wiseql.tui.reports import ReportsScreen

        runs_dir = (self.active_project / "runs") if self.active_project else None
        self.push_screen(ReportsScreen(runs_dir=runs_dir))

    def action_sync_context(self) -> None:
        if self.active_project is None:
            self.notify("no active project — F7 to pick one, Ctrl+N to create", severity="warning")
            return
        config = self._config()
        name = config.defaults.connection
        conn = config.connections.get(name) if name else None
        if conn is None:
            self.notify("no default connection configured (F3)", severity="error")
            return
        self.notify(f"Syncing schema from {name} …")
        self._sync_worker(self.active_project, name, conn)

    @work(thread=True)
    def _sync_worker(self, root, name, conn) -> None:
        from wiseql.config import open_connection
        from wiseql.context import introspect_tables, write_tables_md

        try:
            connection = open_connection(name, conn)
            try:
                tables = introspect_tables(connection)
            finally:
                connection.close()
            write_tables_md(root / "context" / "tables.md", tables, project_name=root.name)
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(
                self.notify, f"sync failed: {str(exc).strip()}", severity="error"
            )
            return
        self.app.call_from_thread(
            self.notify, f"Synced {len(tables)} tables → context/tables.md"
        )

    def action_new_project(self) -> None:
        from wiseql.project import scaffold_project
        from wiseql.tui.projects import ProjectsScreen
        from wiseql.tui.wizard import ProjectWizard

        def _create(values: dict | None) -> None:
            if values is None:
                return
            dest = self.projects_dir / values["name"]
            try:
                self.projects_dir.mkdir(parents=True, exist_ok=True)
                scaffold_project(dest, values["name"], description=values["description"])
            except (FileExistsError, OSError) as exc:
                self.notify(str(exc), severity="error")
                return
            self.notify(f"Created project '{values['name']}'")
            self.set_active_project(dest)
            # If launched from the projects picker, drop back to the browser.
            if isinstance(self.screen, ProjectsScreen):
                self.pop_screen()

        self.push_screen(ProjectWizard(), _create)

    def action_run(self) -> None:
        if self._current is None or self._current.recipe is None:
            self.notify("no valid recipe selected", severity="warning")
            return
        if not self._current.ok:
            self.notify("recipe has errors — F4 to see them", severity="warning")
            return

        config = self._config()
        declared = self._current.recipe.recipe.params
        if declared:
            from wiseql.tui.params import ParamModal

            def _got(values: dict | None) -> None:
                if values is not None:
                    self._launch_run(config, values)

            self.push_screen(ParamModal(self._current.recipe.recipe.name, declared), _got)
        else:
            self._launch_run(config, {})

    def _launch_run(self, config, params: dict) -> None:
        from wiseql.tui.run import RunScreen

        runs_dir = (self.active_project / "runs") if self.active_project else None
        self.push_screen(
            RunScreen(
                self._current, config, params, self._current.recipe.recipe.name, runs_dir=runs_dir
            )
        )

    def action_validate(self) -> None:
        list_view = self.query_one("#recipe-list", ListView)
        if list_view.index is not None and self._paths:
            self._show(self._paths[list_view.index])
            ok = self._current is not None and self._current.ok
            self.notify("Recipe is valid ✓" if ok else "Recipe has errors ✗",
                        severity="information" if ok else "error")

    def action_plan(self) -> None:
        self._render_plan()
        self.query_one("#dag-tree", Tree).focus()
