"""The WiseQL Textual application (Sprint 1: recipe browser).

Norton Commander spirit: recipe list on the left, detail + DAG plan on the
right, everything reachable via the F-key bar.
"""

from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, ListItem, ListView, Static, Tree

from wiseql import __version__
from wiseql.ai import get_provider
from wiseql.recipes import LoadResult, build_plan, load_recipe
from wiseql.recipes.dag import describe_step

HELP_TEXT = f"""\
[b]WiseQL v{__version__} — Help[/b]

[b]Keys[/b]
  F1  or ?       This help
  F2             Run selected recipe's database step (results grid)
  F3             Connections (list · test · login)
  F4             Re-validate selected recipe
  F5             Rebuild plan for selected recipe
  F10 or q       Quit (also Ctrl+Q)
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

WiseQL looked for [i]*.toml[/i] recipes in [b]./recipes[/b], [b]./examples[/b],
then the current directory.

Create one (see RECIPE_SPEC.md) or start the app inside a project folder.
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


def find_recipes_dir(base: Path) -> Path:
    """First existing of ./recipes, ./examples, else the base dir itself."""
    for candidate in ("recipes", "examples"):
        d = base / candidate
        if d.is_dir():
            return d
    return base


class WiseQLApp(App[None]):
    """Recipe browser: list pane + detail/plan pane."""

    TITLE = "WiseQL"
    SUB_TITLE = "the wise data browser"

    BINDINGS = [
        Binding("f1", "help", "Help"),
        Binding("f2", "run", "Run"),
        Binding("f3", "connections", "Connections"),
        Binding("f4", "validate", "Validate"),
        Binding("f5", "plan", "Plan"),
        Binding("f10", "quit", "Quit"),
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
        self, recipes_dir: Path | None = None, config_path: Path | None = None
    ) -> None:
        super().__init__()
        self.ai = get_provider()  # NullProvider until the [ai] add-on (Sprint 6)
        self.recipes_dir = recipes_dir or find_recipes_dir(Path.cwd())
        self.config_path = config_path  # None → $WISEQL_CONFIG / standard location
        self._current: LoadResult | None = None

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
        list_view = self.query_one("#recipe-list", ListView)
        self._paths = sorted(self.recipes_dir.glob("*.toml"))
        for path in self._paths:
            list_view.append(ListItem(Static(path.stem, markup=False)))
        self.query_one("#dag-tree", Tree).display = False
        if self._paths:
            list_view.index = 0
            self._show(self._paths[0])

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

    def action_connections(self) -> None:
        from wiseql.tui.connections import ConnectionsScreen

        self.push_screen(ConnectionsScreen(config_path=self.config_path))

    def action_run(self) -> None:
        from wiseql.config import load_active_config
        from wiseql.engine import choose_step

        if self._current is None or self._current.recipe is None:
            return
        choice, why = choose_step(self._current)
        if choice is None:
            self.notify(why or "cannot run", severity="warning")
            return
        config = load_active_config(self.config_path).config
        conn = config.connections.get(choice.source)
        if conn is None:
            self.notify(
                f"connection '{choice.source}' is not configured (F3 to manage)",
                severity="error",
            )
            return

        declared = self._current.recipe.recipe.params
        if declared:
            from wiseql.tui.params import ParamModal

            def _got(values: dict | None) -> None:
                if values is not None:
                    self._launch_results(choice, conn, values)

            self.push_screen(ParamModal(self._current.recipe.recipe.name, declared), _got)
        else:
            self._launch_results(choice, conn, {})

    def _launch_results(self, choice, conn, params: dict) -> None:
        from wiseql.tui.results import ResultsScreen

        self.push_screen(ResultsScreen(choice, conn, params))

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
