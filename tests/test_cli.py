"""Headless CLI tests."""

from typer.testing import CliRunner

from wiseql import __version__
from wiseql.cli import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "wise data browser" in result.output
