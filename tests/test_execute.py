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
from wiseql.engine.execute import StepRun, _evaluate_assertions, _run_local_step
from wiseql.recipes import load_recipe
from wiseql.recipes.model import StepAssert

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


# --- assertions (seeded DuckDB; no Oracle) ----------------------------------


def _seed_assert(create_sql: str, spec: StepAssert, prior=None) -> StepRun:
    duck = duckdb.connect()
    duck.execute(f"CREATE TABLE t AS {create_sql}")
    run = StepRun(name="t", kind="local", source=None, ok=True)
    run.row_count = duck.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    _evaluate_assertions(duck, run, spec, prior or [])
    duck.close()
    return run


def test_assert_no_nulls_is_case_insensitive() -> None:
    # THE discriminating test: lowercase assertion column vs UPPERCASE table column
    # (as Oracle returns them). Must find the 1 planted NULL — not silently pass.
    run = _seed_assert(
        'SELECT * FROM (VALUES (1,5),(2,NULL),(3,7)) v("ORDER_ID","CUSTOMER_ID")',
        StepAssert(no_nulls=["customer_id"]),
    )
    a = run.assertions[0]
    assert a.passed is False
    assert "1 row" in a.detail
    assert len(a.samples) == 1


def test_assert_no_nulls_passes_when_clean() -> None:
    run = _seed_assert(
        'SELECT * FROM (VALUES (1,5),(2,6)) v("ORDER_ID","CUSTOMER_ID")',
        StepAssert(no_nulls=["customer_id"]),
    )
    assert run.assertions[0].passed is True


def test_assert_unique_detects_duplicates() -> None:
    run = _seed_assert(
        'SELECT * FROM (VALUES (1),(2),(2),(2)) v("ORDER_ID")',
        StepAssert(unique=["order_id"]),
    )
    a = run.assertions[0]
    assert a.passed is False
    assert "1 duplicated key" in a.detail
    # the duplicated key (2) with its occurrence count is captured
    assert a.samples and a.samples[0][0] == 2


def test_assert_rows_min_and_max() -> None:
    run = _seed_assert(
        "SELECT * FROM (VALUES (1),(2),(3)) v(n)",
        StepAssert(rows_min=5, rows_max=2),
    )
    assert [a.passed for a in run.assertions] == [False, False]


def test_assert_equals_step() -> None:
    prior = [StepRun(name="orders", kind="db", source="x", ok=True, row_count=3)]
    run = _seed_assert(
        "SELECT * FROM (VALUES (1),(2)) v(n)",  # 2 rows
        StepAssert(equals_step="orders"),  # orders has 3 → mismatch
        prior=prior,
    )
    assert run.assertions[0].passed is False
    assert "2 vs orders=3" in run.assertions[0].detail


def test_assert_failed_property() -> None:
    run = _seed_assert("SELECT * FROM (VALUES (1)) v(n)", StepAssert(rows_min=99))
    assert run.assert_failed is True
