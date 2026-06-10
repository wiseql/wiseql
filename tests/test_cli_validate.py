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


# --- validate --ai (S6.2) ---------------------------------------------------

from wiseql.ai import AIResult  # noqa: E402


class _FakeProvider:
    """Duck-typed provider capturing what validate_recipe was given."""

    def __init__(self, available=True, text="step 3 reads a column step 1 doesn't output"):
        self.available, self.text = available, text
        self.seen_text = None
        self.seen_context = None

    def validate_recipe(self, recipe_text, context):
        self.seen_text, self.seen_context = recipe_text, context
        return AIResult(available=self.available, text=self.text if self.available else "")


def test_validate_ai_off_shows_hint_keeps_exit(tmp_path: Path, monkeypatch) -> None:
    # Default (NullProvider): advisory hint, exit code stays structural (0 = valid).
    monkeypatch.setenv("WISEQL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["validate", str(EXAMPLES / "orphan-returns.toml"), "--ai"])
    assert result.exit_code == 0
    assert "AI review skipped" in result.output


def test_validate_ai_findings_and_resolved_sql(monkeypatch) -> None:
    # The recipe uses an external sql_file; the AI must receive the *resolved* SQL,
    # not just the filename (the load-bearing S6.2 fix).
    fake = _FakeProvider()
    monkeypatch.setattr("wiseql.ai.get_provider", lambda *a, **k: fake)
    result = runner.invoke(app, ["validate", str(EXAMPLES / "orphan-returns.toml"), "--ai"])
    assert result.exit_code == 0
    assert "AI review" in result.output
    assert "step 3 reads a column" in result.output
    # the returns step is an external sql_file — its resolved SQL must be present
    assert "FROM returns" in (fake.seen_text or "")
    assert "sql_file" not in fake.seen_text.split("resolved SQL")[1]  # appendix has SQL, not a pointer


def test_validate_ai_skipped_on_structurally_invalid(monkeypatch) -> None:
    fake = _FakeProvider()
    monkeypatch.setattr("wiseql.ai.get_provider", lambda *a, **k: fake)
    result = runner.invoke(app, ["validate", str(BROKEN / "cycle.toml"), "--ai"])
    assert result.exit_code == 1
    assert fake.seen_text is None  # no AI opinion on a broken recipe
