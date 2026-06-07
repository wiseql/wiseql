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


def main() -> None:
    app()
