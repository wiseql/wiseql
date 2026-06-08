"""Executor tests (S3.1). Offline — no Oracle.

The pre-DB branches (guard, missing connection, invalid plan) are driven through
``run_recipe``; the DuckDB local-step join logic is tested by seeding tables
directly, so the anti-join is exercised without a database. The live end-to-end
gate (orphan-returns → 3 planted orphans) runs in the demo / integration test.
"""

from pathlib import Path

import duckdb

from wiseql.config import WiseQLConfig
from wiseql.engine import run_recipe
from wiseql.engine.execute import _run_local_step
from wiseql.recipes import load_recipe

BROKEN = Path(__file__).parent / "fixtures" / "broken"


def _recipe(tmp_path: Path, body: str):
    p = tmp_path / "r.toml"
    p.write_text(body, encoding="utf-8")
    return load_recipe(p)


# --- pre-DB branches via run_recipe -----------------------------------------


def test_run_recipe_guard_blocks_write(tmp_path: Path) -> None:
    loaded = _recipe(
        tmp_path,
        '[recipe]\nname = "e"\n[steps.s]\nsource = "c"\nsql = "DELETE FROM orders"\n',
    )
    result = run_recipe(loaded, WiseQLConfig())  # guard fails before any connect
    assert result.ok is False
    assert "read-only guard" in result.failed_step.error


def test_run_recipe_missing_connection(tmp_path: Path) -> None:
    loaded = _recipe(
        tmp_path,
        '[recipe]\nname = "m"\n[steps.s]\nsource = "ghost"\nsql = "SELECT 1 FROM dual"\n',
    )
    result = run_recipe(loaded, WiseQLConfig())  # no connections configured
    assert result.ok is False
    assert "not configured" in result.failed_step.error


def test_run_recipe_invalid_plan_is_run_level_error() -> None:
    loaded = load_recipe(BROKEN / "cycle.toml")
    result = run_recipe(loaded, WiseQLConfig())
    assert result.ok is False
    assert result.error  # run-level (not a per-step) failure
    assert not result.steps


# --- DuckDB local-step join logic (the orphan anti-join), seeded directly ----


def test_local_step_anti_join_finds_orphans() -> None:
    duck = duckdb.connect()
    duck.execute("CREATE TABLE orders AS SELECT * FROM (VALUES (1),(2),(3)) t(order_id)")
    duck.execute("CREATE TABLE returns AS SELECT * FROM (VALUES (1),(2),(99)) t(order_id)")
    run = _run_local_step(
        duck,
        "orphans",
        ["orders", "returns"],
        "SELECT r.order_id FROM returns r LEFT JOIN orders o USING (order_id) "
        "WHERE o.order_id IS NULL",
    )
    assert run.ok
    assert run.kind == "local"
    assert run.row_count == 1
    assert run.sample == [(99,)]
    duck.close()


def test_local_step_materializes_table_for_downstream() -> None:
    duck = duckdb.connect()
    duck.execute("CREATE TABLE src AS SELECT * FROM (VALUES (10),(20)) t(n)")
    _run_local_step(duck, "doubled", ["src"], "SELECT n * 2 AS n2 FROM src")
    # the step's output is now a real table a downstream step could read
    assert duck.execute("SELECT SUM(n2) FROM doubled").fetchone()[0] == 60
    duck.close()
