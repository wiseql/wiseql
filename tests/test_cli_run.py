"""CLI ``run`` tests (S2.3) — the automation surface, where the exit code is
the contract (cron / CI). All offline: the read-only guard fails before any DB
connection, and the other cases fail before execution entirely.
"""

from pathlib import Path

from typer.testing import CliRunner

from wiseql.cli import app

runner = CliRunner()
EXAMPLES = Path(__file__).parent.parent / "examples"

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _env(tmp_path: Path) -> dict[str, str]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return {"WISEQL_CONFIG": str(cfg), "COLUMNS": "200"}


def _recipe(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "r.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_run_invalid_recipe_exits_1(tmp_path: Path) -> None:
    bad = _recipe(tmp_path, '[recipe]\nname = "x"\n')  # no steps
    result = runner.invoke(app, ["run", str(bad)], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "invalid recipe" in result.output


def test_run_guard_blocks_write_exits_1(tmp_path: Path) -> None:
    evil = _recipe(
        tmp_path,
        '[recipe]\nname = "evil"\n[steps.s]\nsource = "oracle_dev"\nsql = "DELETE FROM orders"\n',
    )
    result = runner.invoke(app, ["run", str(evil)], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "read-only guard" in result.output  # blocked before any DB contact


def test_run_unknown_connection_exits_1(tmp_path: Path) -> None:
    r = _recipe(
        tmp_path,
        '[recipe]\nname = "x"\n[steps.s]\nsource = "ghost"\nsql = "SELECT 1 FROM dual"\n',
    )
    result = runner.invoke(app, ["run", str(r)], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "not configured" in result.output


def test_run_bad_param_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["run", str(EXAMPLES / "daily-volume.toml"), "--param", "foo"],
        env=_env(tmp_path),
    )
    assert result.exit_code == 2
    assert "bad --param" in result.output


def test_run_single_local_step_rejected_exits_1(tmp_path: Path) -> None:
    # --step on a local (DuckDB) step can't run standalone — needs the full recipe.
    result = runner.invoke(
        app,
        ["run", str(EXAMPLES / "orphan-returns.toml"), "--step", "orphans"],
        env=_env(tmp_path),
    )
    assert result.exit_code == 1
    assert "full recipe" in result.output
