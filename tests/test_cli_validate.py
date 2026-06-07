"""CLI validate/plan tests (S1.1 / S1.2)."""

from pathlib import Path

from typer.testing import CliRunner

from wiseql.cli import app

EXAMPLES = Path(__file__).parent.parent / "examples"
BROKEN = Path(__file__).parent / "fixtures" / "broken"

runner = CliRunner()


def test_validate_good_recipes_exit_zero() -> None:
    paths = [str(p) for p in sorted(EXAMPLES.glob("*.toml"))]
    result = runner.invoke(app, ["validate", *paths])
    assert result.exit_code == 0
    assert "INVALID" not in result.output


def test_validate_broken_recipe_exit_one() -> None:
    result = runner.invoke(app, ["validate", str(BROKEN / "no_sql.toml")])
    assert result.exit_code == 1
    assert "INVALID" in result.output


def test_validate_cycle_is_invalid() -> None:
    result = runner.invoke(app, ["validate", str(BROKEN / "cycle.toml")])
    assert result.exit_code == 1
    assert "cycle" in result.output


def test_plan_shows_waves() -> None:
    result = runner.invoke(app, ["plan", str(EXAMPLES / "orphan-returns.toml")])
    assert result.exit_code == 0
    assert "wave 1" in result.output
    assert "wave 2" in result.output
    assert "orphans" in result.output


def test_plan_invalid_recipe_fails() -> None:
    result = runner.invoke(app, ["plan", str(BROKEN / "both_sql.toml")])
    assert result.exit_code == 1
