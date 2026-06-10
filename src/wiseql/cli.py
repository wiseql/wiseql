"""WiseQL command-line entry point.

Running ``wiseql`` with no arguments opens the TUI (the primary interface).
Subcommands exist for headless automation (cron, CI).
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.tree import Tree

from wiseql import __version__

app = typer.Typer(
    name="wiseql",
    help="WiseQL — the wise data browser. Run with no arguments to open the TUI.",
    no_args_is_help=False,
    add_completion=False,
)

conn_app = typer.Typer(help="Manage database connections (list, login, test).")
app.add_typer(conn_app, name="conn")

context_app = typer.Typer(help="Project context (schema sync).")
app.add_typer(context_app, name="context")

console = Console()
_SEVERITY_STYLE = {"error": "bold red", "warning": "yellow"}


@app.callback(invoke_without_command=True)
def _root(ctx: typer.Context) -> None:
    """Open the TUI when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        from wiseql.tui.app import WiseQLApp

        WiseQLApp().run()


@app.command()
def version() -> None:
    """Print the WiseQL version and exit."""
    typer.echo(f"WiseQL {__version__}")


@app.command()
def init(
    name: str,
    connection: str = typer.Option(None, "--connection", "-c", help="Default connection name."),
    description: str = typer.Option("", "--description", "-d"),
) -> None:
    """Create a new project in the configured projects folder."""
    from wiseql.project import scaffold_project

    root = _load_config().config.projects_root
    dest = root / name
    try:
        root.mkdir(parents=True, exist_ok=True)
        scaffold_project(dest, name, description=description, connection=connection)
    except (FileExistsError, OSError) as exc:
        console.print(f"[bold red]cannot create project:[/] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[green]✓[/] created project [b]{name}[/] at [dim]{dest}[/]")
    console.print(
        f"\nNext: add recipes to [b]{dest}/recipes/[/]  ·  "
        "open the TUI with [b]wiseql[/] (F7 to pick it)  ·  [b]wiseql context sync " + name + "[/]"
    )


@app.command()
def projects() -> None:
    """List projects in the configured projects folder."""
    from rich.table import Table

    from wiseql.project import list_projects, project_stats

    root = _load_config().config.projects_root
    found = list_projects(root)
    if not found:
        console.print(f"No projects in [b]{root}[/]. Create one: [b]wiseql init <name>[/]")
        return
    table = Table(title=f"Projects in {root}")
    table.add_column("project", style="bold")
    table.add_column("recipes", justify="right")
    table.add_column("runs", justify="right")
    for path in found:
        recipes, runs = project_stats(path)
        table.add_row(path.name, str(recipes), str(runs))
    console.print(table)


@app.command()
def validate(paths: list[Path]) -> None:
    """Validate one or more recipe files. Exit code 1 if any has errors."""
    from wiseql.recipes import build_plan, load_recipe

    failed = False
    for path in paths:
        result = load_recipe(path)
        issues = list(result.issues)
        if result.recipe is not None:
            issues += build_plan(result.recipe).issues

        errors = [i for i in issues if i.severity == "error"]
        status = "[bold red]INVALID[/]" if errors else "[bold green]OK[/]"
        console.print(f"{status}  {path}")
        for issue in issues:
            console.print(
                f"    [{_SEVERITY_STYLE[issue.severity]}]{issue.severity}[/] "
                f"[dim]{issue.where}[/] — {issue.message}"
            )
        failed |= bool(errors)

    raise typer.Exit(code=1 if failed else 0)


@app.command()
def plan(path: Path) -> None:
    """Show the execution plan (DAG waves) for a recipe."""
    from wiseql.recipes import build_plan, load_recipe
    from wiseql.recipes.dag import describe_step

    result = load_recipe(path)
    if result.recipe is None or result.errors:
        console.print(f"[bold red]Cannot plan — recipe is invalid:[/] {path}")
        for issue in result.errors:
            console.print(f"    [red]{issue}[/]")
        raise typer.Exit(code=1)

    recipe = result.recipe
    exec_plan = build_plan(recipe)
    if not exec_plan.ok:
        for issue in exec_plan.issues:
            console.print(f"    [red]{issue}[/]")
        raise typer.Exit(code=1)

    tree = Tree(f"[b]{recipe.recipe.name}[/b] [dim]{recipe.recipe.description}[/dim]")
    for i, wave in enumerate(exec_plan.waves, start=1):
        node = tree.add(f"[cyan]wave {i}[/cyan]")
        for name in wave:
            node.add(f"[b]{name}[/b]  [dim]{describe_step(recipe, name)}[/dim]")
    console.print(tree)

    for issue in exec_plan.issues:
        console.print(
            f"[{_SEVERITY_STYLE[issue.severity]}]{issue.severity}[/] {issue.message}"
        )


def _parse_params(pairs: list[str] | None) -> dict[str, str]:
    """Turn ``--param k=v`` options into a bind dict."""
    params: dict[str, str] = {}
    for pair in pairs or []:
        if "=" not in pair:
            console.print(f"[bold red]bad --param '{pair}'[/] — expected key=value")
            raise typer.Exit(code=2)
        key, value = pair.split("=", 1)
        params[key.strip()] = value
    return params


def _print_rows(columns: list[str], rows: list) -> None:
    from rich.table import Table

    table = Table(show_lines=False)
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*["" if v is None else str(v) for v in row])
    console.print(table)


@app.command()
def run(
    recipe: Path,
    step: str = typer.Option(None, "--step", "-s", help="Run only this one database step."),
    param: list[str] = typer.Option(None, "--param", "-p", help="Bind value, key=value."),
    max_rows: int = typer.Option(1000, help="Cap on rows fetched (single-step mode)."),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="No output; just exit code + report (cron)."),
    no_report: bool = typer.Option(False, "--no-report", help="Don't persist a run report."),
    resume: str = typer.Option(
        None, "--resume",
        help="Resume a prior run by id, or 'last' for the most recent resumable run.",
    ),
) -> None:
    """Run a recipe end-to-end through DuckDB (or one step with --step)."""
    from wiseql.recipes import load_recipe

    loaded = load_recipe(recipe)
    if not loaded.ok:
        if not quiet:
            console.print(f"[bold red]invalid recipe:[/] {recipe}")
            for issue in loaded.errors:
                console.print(f"    [red]{issue}[/]")
        raise typer.Exit(code=1)

    params = _parse_params(param)
    config = _load_config().config
    if step is not None:
        if resume is not None:
            console.print("[bold red]--resume cannot be combined with --step.[/]")
            raise typer.Exit(code=2)
        _run_single_step(loaded, config, step, params, max_rows)
        return

    # Reports go to the project that CONTAINS the recipe (cwd-independent).
    runs_dir = None
    if not no_report or resume is not None:
        from wiseql.project import find_project_root

        root = find_project_root(recipe.resolve().parent)
        runs_dir = (root / "runs") if root is not None else None

    if resume is not None:
        resume_dir = _resolve_resume_dir(runs_dir, resume, loaded.recipe.recipe.name)
        # No params on the CLI → inherit the original run's params (must match anyway).
        if not params:
            from wiseql.report import read_manifest

            params = (read_manifest(resume_dir) or {}).get("params") or {}
        _run_full_recipe(loaded, config, params, quiet=quiet, runs_dir=runs_dir, resume_from=resume_dir)
        return

    _run_full_recipe(loaded, config, params, quiet=quiet, runs_dir=runs_dir)


def _resolve_resume_dir(runs_dir, resume: str, recipe_name: str) -> Path:
    """Resolve --resume (a run id or 'last') to a run dir, or exit with a clear error."""
    if runs_dir is None:
        console.print("[bold red]--resume needs a project[/] — the recipe isn't inside one (no runs/).")
        raise typer.Exit(code=1)

    if resume == "last":
        from wiseql.report import list_resumable_runs

        candidates = list_resumable_runs(runs_dir, recipe_name)
        if not candidates:
            console.print(f"[bold red]no resumable run[/] for [b]{recipe_name}[/] in {runs_dir}.")
            raise typer.Exit(code=1)
        return candidates[0].path

    resume_dir = Path(runs_dir) / resume
    if not resume_dir.is_dir():
        console.print(f"[bold red]no such run:[/] {resume} (in {runs_dir})")
        raise typer.Exit(code=1)
    return resume_dir


def _run_single_step(loaded, config, step, params, max_rows) -> None:
    from wiseql.engine import choose_step, run_step

    choice, why = choose_step(loaded, step)
    if choice is None:
        console.print(f"[bold red]cannot run:[/] {why}")
        raise typer.Exit(code=1)
    conn = config.connections.get(choice.source)
    if conn is None:
        console.print(
            f"[bold red]step '{choice.name}' uses connection '{choice.source}'[/] "
            "which is not configured — add it or run `wiseql conn list`."
        )
        raise typer.Exit(code=1)

    console.print(f"Running step [b]{choice.name}[/] on [b]{choice.source}[/] [dim]{conn.target}[/dim] …")
    # The auth backend keys off the *connection* name (choice.source), not the step.
    result = run_step(choice.source, conn, choice.sql, params=params, max_rows=max_rows)
    if not result.ok:
        console.print(f"[bold red]✗ {result.error}[/]")
        raise typer.Exit(code=1)
    _print_rows(result.columns, result.rows)
    suffix = "+" if result.truncated else ""
    console.print(
        f"[green]✓[/] {result.row_count}{suffix} row(s) in {result.elapsed_ms} ms"
        + ("  [yellow](truncated — more rows exist)[/]" if result.truncated else "")
    )


def _run_full_recipe(loaded, config, params, *, quiet=False, runs_dir=None, resume_from=None) -> None:
    from wiseql.engine import run_recipe

    result = run_recipe(loaded, config, params=params, runs_dir=runs_dir, resume_from=resume_from)
    if result.error:
        if not quiet:
            console.print(f"[bold red]cannot run:[/] {result.error}")
        raise typer.Exit(code=1)

    if not quiet:
        from rich.markup import escape

        for s in result.steps:
            where = s.source or "duckdb"
            if s.restored:
                console.print(
                    f"[cyan]↻[/] [b]{s.name}[/] [dim]({s.kind} · {where})[/] — "
                    f"restored from checkpoint, {s.row_count} row(s)"
                )
            elif s.ok:
                console.print(
                    f"[green]✓[/] [b]{s.name}[/] [dim]({s.kind} · {where})[/] — "
                    f"{s.row_count} row(s) in {s.elapsed_ms} ms"
                )
            else:
                console.print(f"[bold red]✗ {s.name}[/] [dim]({s.kind} · {where})[/] — {s.error}")
            for a in s.assertions:
                mark = "[green]✓[/]" if a.passed else f"[bold red]✗[/] [dim]({s.on_fail})[/]"
                console.print(f"      {mark} assert {escape(a.check)}: {escape(a.detail)}")
                if not a.passed and a.samples:
                    _print_rows(a.sample_columns, a.samples)

        for name in result.terminals:
            s = result.step(name)
            if s is not None and s.ok:
                console.print(f"\n[b]{name}[/] [dim](result)[/]:")
                _print_rows(s.columns, s.sample)
                if s.row_count > len(s.sample):
                    console.print(f"[dim]… {s.row_count - len(s.sample)} more row(s)[/]")

        verdict = "[green]✓ ok" if result.ok else "[bold red]✗ failed"
        console.print(f"\n[b]run {verdict}[/][/] in {result.elapsed_ms} ms")
        if result.report_path:
            console.print(f"[dim]report: {result.report_path}[/]")
        elif runs_dir is None:
            console.print("[dim](recipe not in a project — no report written)[/]")

    if not result.ok:
        raise typer.Exit(code=1)


def _load_config():
    """Load layered config, printing any errors. Returns the ConfigResult.

    ``$WISEQL_CONFIG`` overrides the global config file path (handy for CI and
    for pointing at an alternate config without touching ``~/.config``).
    """
    from wiseql.config import load_active_config

    result = load_active_config()
    for err in result.errors:
        console.print(f"[bold red]config error[/] {err}")
    return result


@conn_app.command("list")
def conn_list() -> None:
    """List configured connections (metadata only — no database contact)."""
    from rich.table import Table

    from wiseql.config import get_backend

    result = _load_config()
    config = result.config
    if not config.connections:
        console.print(
            "[yellow]No connections configured.[/]\n"
            "Add a [b][connections.<name>][/b] table to "
            "[b]~/.config/wiseql/config.toml[/b] or your project's [b]project.toml[/b], "
            "then [b]wiseql conn login <name>[/b]."
        )
        raise typer.Exit(code=1 if result.errors else 0)

    default = config.defaults.connection
    table = Table(title="WiseQL connections")
    table.add_column("name", style="bold")
    table.add_column("driver")
    table.add_column("target")
    table.add_column("user")
    table.add_column("secret from")
    for name, conn in sorted(config.connections.items()):
        marker = " [cyan](default)[/]" if name == default else ""
        backend = get_backend(conn)
        table.add_row(
            f"{name}{marker}",
            conn.driver,
            conn.target,
            conn.user or "[dim]—[/]",
            backend.describe(name),
        )
    console.print(table)


@conn_app.command("login")
def conn_login(name: str) -> None:
    """Store the password for a connection in its auth backend."""
    from wiseql.config import get_backend

    result = _load_config()
    conn = result.config.connections.get(name)
    if conn is None:
        console.print(f"[bold red]unknown connection:[/] {name}")
        raise typer.Exit(code=1)

    backend = get_backend(conn)
    if conn.auth == "env":
        console.print(
            f"Connection [b]{name}[/] uses the [b]env[/] backend — set "
            f"[b]{backend.describe(name).split(':', 1)[1]}[/b] in your environment; "
            "nothing to store."
        )
        return
    if conn.auth == "wallet":
        console.print(
            f"Connection [b]{name}[/] uses an Oracle [b]wallet[/] — credentials come "
            "from TNS_ADMIN at connect time; nothing to store."
        )
        return

    password = typer.prompt(f"Password for {conn.user}@{name}", hide_input=True)
    backend.set_password(name, conn, password)
    console.print(f"[green]✓[/] stored password for [b]{name}[/] ({backend.describe(name)})")


@conn_app.command("test")
def conn_test(name: str | None = typer.Argument(None)) -> None:
    """Connect to a database and verify reachability (latency + version)."""
    from wiseql.config import ping

    result = _load_config()
    config = result.config
    target = config.resolve_name(name)
    if target is None:
        console.print(
            "[bold red]no connection given[/] and no default configured — "
            "pass a name or set [b][defaults] connection[/b]."
        )
        raise typer.Exit(code=1)
    conn = config.connections.get(target)
    if conn is None:
        console.print(f"[bold red]unknown connection:[/] {target}")
        raise typer.Exit(code=1)

    console.print(f"Testing [b]{target}[/] → [dim]{conn.target}[/dim] …")
    outcome = ping(target, conn)
    if outcome.ok:
        console.print(f"[bold green]✓ connected[/] in {outcome.elapsed_ms} ms — {outcome.detail}")
    else:
        console.print(f"[bold red]✗ failed[/] after {outcome.elapsed_ms} ms — {outcome.detail}")
        raise typer.Exit(code=1)


@context_app.command("sync")
def context_sync(
    project: str = typer.Argument(None, help="Project name (in the projects folder)."),
    connection: str = typer.Option(None, "--connection", "-c", help="Connection to introspect."),
) -> None:
    """Introspect the database schema into a project's context/tables.md (notes preserved)."""
    from wiseql.config import load_active_config, open_connection
    from wiseql.context import introspect_tables, write_tables_md
    from wiseql.project import PROJECT_MANIFEST, find_project_root

    base = _load_config().config
    if project is not None:
        root = base.projects_root / project
        if not (root / PROJECT_MANIFEST).is_file():
            console.print(f"[bold red]no such project:[/] {project} (in {base.projects_root})")
            raise typer.Exit(code=1)
    else:
        root = find_project_root()
        if root is None:
            console.print(
                "[bold red]no project given and not inside one[/] — pass a project name "
                "([b]wiseql context sync <name>[/]) or run inside a project directory."
            )
            raise typer.Exit(code=1)

    # Scope connections/defaults to the target project.
    config = load_active_config(project_path=root / PROJECT_MANIFEST).config
    name = config.resolve_name(connection)
    conn = config.connections.get(name) if name else None
    if conn is None:
        console.print(f"[bold red]unknown or unset connection:[/] {name or '(none)'}")
        raise typer.Exit(code=1)

    console.print(f"Introspecting [b]{name}[/] [dim]{conn.target}[/dim] …")
    try:
        connection_obj = open_connection(name, conn)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[bold red]✗ connect failed:[/] {str(exc).strip()}")
        raise typer.Exit(code=1)
    try:
        tables = introspect_tables(connection_obj)
    finally:
        connection_obj.close()

    path = write_tables_md(root / "context" / "tables.md", tables, project_name=root.name)
    console.print(f"[green]✓[/] synced {len(tables)} table(s) → [dim]{path}[/]")


def main() -> None:
    app()
