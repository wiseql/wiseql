"""WiseQL command-line entry point.

Running ``wiseql`` with no arguments opens the TUI (the primary interface).
Subcommands exist for headless automation (cron, CI).
"""

from __future__ import annotations

import typer

from wiseql import __version__

app = typer.Typer(
    name="wiseql",
    help="WiseQL — the wise data browser. Run with no arguments to open the TUI.",
    no_args_is_help=False,
    add_completion=False,
)


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


def main() -> None:
    app()
