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


def _load_config():
    """Load layered config, printing any errors. Returns the ConfigResult.

    ``$WISEQL_CONFIG`` overrides the global config file path (handy for CI and
    for pointing at an alternate config without touching ``~/.config``).
    """
    import os

    from wiseql.config import load_config

    global_path = None
    if env_path := os.environ.get("WISEQL_CONFIG"):
        global_path = Path(env_path)

    result = load_config(global_path=global_path)
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


def main() -> None:
    app()
