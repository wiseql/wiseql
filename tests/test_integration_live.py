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

    assert result.ok, result.failed_step and result.failed_step.error
    assert result.step("orders").row_count == 127
    assert result.step("returns").row_count == 33

    orphans = result.step("orphans")
    assert orphans.kind == "local"
    assert orphans.row_count == 3  # the planted BUG-1 orphans (return_id 5901–5903)
    orphan_order_ids = {int(r[1]) for r in orphans.sample}
    assert orphan_order_ids == {9991, 9992, 9993}
