"""Live end-to-end integration test (S3.1 gate) — requires the docker dev DB.

Opt-in: skips (visibly, with a reason) unless ``WISEQL_ORACLE_DEV_PASSWORD`` is
set, so the offline suite (`make test`) stays green on a machine with no DB.
Run it with the dev DB up:

    WISEQL_ORACLE_DEV_PASSWORD=wiseql123 \\
    UV_PROJECT_ENVIRONMENT=$HOME/.venvs/wiseql uv run pytest tests/test_integration_live.py -v

The gate: orphan-returns flows orders → returns → a DuckDB anti-join and
surfaces exactly the 3 planted orphan returns (dev-db BUG-1).
"""

import os
from pathlib import Path

import pytest

from wiseql.config import Connection, WiseQLConfig
from wiseql.engine import run_recipe
from wiseql.recipes import load_recipe

EXAMPLES = Path(__file__).parent.parent / "examples"

pytestmark = pytest.mark.skipif(
    not os.environ.get("WISEQL_ORACLE_DEV_PASSWORD"),
    reason="set WISEQL_ORACLE_DEV_PASSWORD (and start the docker dev DB) to run live tests",
)


def _dev_config() -> WiseQLConfig:
    return WiseQLConfig(
        connections={
            "oracle_dev": Connection(
                host="localhost", port=1521, service="FREEPDB1", user="wiseql", auth="env"
            )
        }
    )


def test_orphan_returns_finds_three_planted_orphans() -> None:
    loaded = load_recipe(EXAMPLES / "orphan-returns.toml")
    result = run_recipe(loaded, _dev_config())

    # Every step executed; data flowed orders → returns → DuckDB anti-join.
    assert result.step("orders").row_count == 127
    assert result.step("returns").row_count == 33

    orphans = result.step("orphans")
    assert orphans.kind == "local"
    assert orphans.row_count == 3  # the planted BUG-1 orphans (return_id 5901–5903)
    orphan_order_ids = {int(r[1]) for r in orphans.sample}
    assert orphan_order_ids == {9991, 9992, 9993}

    # The recipe's rows_max=0 assertion caught them → the run is a (reported) failure.
    assert orphans.assert_failed
    assert result.ok is False


def test_null_customers_assertion_catches_five_nulls() -> None:
    loaded = load_recipe(EXAMPLES / "null-customers.toml")
    result = run_recipe(loaded, _dev_config(), params={"run_date": "2026-01-01"})

    step = result.step("recent_orders")
    no_nulls = next(a for a in step.assertions if a.check.startswith("no_nulls"))
    assert no_nulls.passed is False
    assert "5 row(s)" in no_nulls.detail  # the 5 planted NULL customer_ids (BUG-2)
    assert len(no_nulls.samples) == 5
    assert result.ok is False


def _two_step_recipe(tmp_path, on_fail_clause: str):
    body = f"""\
[recipe]
name = "stop-demo"
[steps.orders]
source = "oracle_dev"
sql = "SELECT order_id FROM orders"
assert = {{ rows_max = 0{on_fail_clause} }}
[steps.downstream]
inputs = ["orders"]
sql = "SELECT * FROM orders"
"""
    p = tmp_path / "r.toml"
    p.write_text(body, encoding="utf-8")
    return load_recipe(p)


def test_default_stop_halts_run_and_suppresses_downstream(tmp_path) -> None:
    # orders (127 rows) fails rows_max=0 with the DEFAULT on_fail=stop → the run
    # must halt before the downstream step runs.
    loaded = _two_step_recipe(tmp_path, "")
    result = run_recipe(loaded, _dev_config())

    assert result.ok is False
    assert result.step("orders").assert_failed
    assert result.step("downstream") is None  # never executed — run halted
    assert [s.name for s in result.steps] == ["orders"]


def test_warn_mode_keeps_run_ok_and_continues(tmp_path) -> None:
    # Same failing assertion, but on_fail=warn → advisory: run stays ok and the
    # downstream step still runs.
    loaded = _two_step_recipe(tmp_path, ', on_fail = "warn"')
    result = run_recipe(loaded, _dev_config())

    assert result.step("orders").assert_failed
    assert result.ok is True  # warn is advisory
    assert result.step("downstream") is not None  # ran despite the warning
