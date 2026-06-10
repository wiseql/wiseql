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


# --- resume (S5.1) ----------------------------------------------------------

DOUBLE = (
    '[recipe]\nname = "double"\n'
    '[steps.seed]\nsource = "oracle_dev"\nsql = "SELECT n FROM nums"\n'
    '[steps.derived]\ninputs = ["seed"]\nsql = "SELECT n * 2 AS n2 FROM seed"\n'
)


def _project_with_staged_run(tmp_path: Path) -> Path:
    """A project holding the DOUBLE recipe + an interrupted run (seed checkpointed)."""
    import datetime

    import duckdb

    from wiseql.engine.execute import _write_checkpoint
    from wiseql.project import scaffold_project
    from wiseql.recipes import load_recipe
    from wiseql.report import sql_fingerprint, write_manifest

    proj = tmp_path / "demo"
    scaffold_project(proj, "demo")
    recipe = proj / "recipes" / "double.toml"
    recipe.write_text(DOUBLE, encoding="utf-8")

    run_dir = proj / "runs" / "20260610T120000_000000"
    cdir = run_dir / "checkpoints"
    cdir.mkdir(parents=True)
    duck = duckdb.connect()
    duck.execute("CREATE TABLE seed AS SELECT * FROM (VALUES (1),(2),(3)) t(n)")
    _write_checkpoint(duck, cdir, "seed")
    duck.close()
    write_manifest(
        run_dir, recipe_name="double", params={},
        step_sql=sql_fingerprint(load_recipe(recipe).resolved_sql), status="failed",
        started_at=datetime.datetime(2026, 6, 10, 12, 0, 0),
    )
    return recipe


def test_run_resume_with_step_exits_2(tmp_path: Path) -> None:
    r = _recipe(tmp_path, DOUBLE)
    result = runner.invoke(app, ["run", str(r), "--step", "seed", "--resume", "last"], env=_env(tmp_path))
    assert result.exit_code == 2
    assert "cannot be combined" in result.output


def test_run_resume_no_such_run_exits_1(tmp_path: Path) -> None:
    recipe = _project_with_staged_run(tmp_path)
    result = runner.invoke(app, ["run", str(recipe), "--resume", "bogus"], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "no such run" in result.output


def test_run_resume_last_completes_offline(tmp_path: Path) -> None:
    # seed restored from its checkpoint (never touches Oracle); derived runs in DuckDB.
    recipe = _project_with_staged_run(tmp_path)
    result = runner.invoke(app, ["run", str(recipe), "--resume", "last"], env=_env(tmp_path))
    assert result.exit_code == 0, result.output
    assert "↻" in result.output and "restored" in result.output  # seed restored
    assert "derived" in result.output and "run ✓ ok" in result.output
