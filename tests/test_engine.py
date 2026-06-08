"""Engine tests (S2.3): read-only guard + step selection. DB-free.

The guard is the sharp edge — the discriminating cases are that a ``WITH`` CTE
*passes* (the spec allows it) while ``SELECT … ; DELETE …`` and bare DML *fail*.
"""

from pathlib import Path

import pytest

from wiseql.engine import StepResult, choose_step, read_only_violation, run_step
from wiseql.recipes import load_recipe

EXAMPLES = Path(__file__).parent.parent / "examples"


# --- read-only guard --------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM orders",
        "select order_id from orders where order_date >= :d",
        "  \n  SELECT 1 FROM dual",
        "-- a leading comment\nSELECT 1 FROM dual",
        "/* block */ SELECT 1 FROM dual",
        "WITH x AS (SELECT 1 AS n FROM dual) SELECT n FROM x",  # CTE must pass
        "SELECT 'a;b' AS s FROM dual",  # semicolon inside a literal is fine
        "SELECT * FROM orders;",  # single trailing semicolon ok
    ],
)
def test_guard_allows_read_only(sql: str) -> None:
    assert read_only_violation(sql) is None


@pytest.mark.parametrize(
    "sql,needle",
    [
        ("DELETE FROM orders", "SELECT / WITH"),
        ("UPDATE orders SET x = 1", "SELECT / WITH"),
        ("INSERT INTO orders VALUES (1)", "SELECT / WITH"),
        ("DROP TABLE orders", "SELECT / WITH"),
        ("BEGIN DELETE FROM orders; END;", "SELECT / WITH"),
        ("SELECT 1 FROM dual; DELETE FROM orders", "multiple statements"),
        ("   ", "empty"),
        ("-- only a comment", "empty"),
    ],
)
def test_guard_rejects_writes_and_multistatement(sql: str, needle: str) -> None:
    reason = read_only_violation(sql)
    assert reason is not None
    assert needle in reason


def test_run_step_blocks_write_without_touching_db() -> None:
    from wiseql.config.model import Connection

    # No DB contact: the guard fails first, so the (bogus) connection is never used.
    result = run_step("c", Connection(host="nowhere", service="X"), "DELETE FROM orders")
    assert isinstance(result, StepResult)
    assert result.ok is False
    assert "read-only guard" in result.error


# --- step selection ---------------------------------------------------------


def test_choose_single_db_step() -> None:
    loaded = load_recipe(EXAMPLES / "null-customers.toml")
    choice, why = choose_step(loaded)
    assert why is None
    assert choice is not None
    assert choice.name == "recent_orders"
    assert choice.source == "oracle_dev"
    assert "FROM orders" in choice.sql


def test_choose_rejects_local_step() -> None:
    loaded = load_recipe(EXAMPLES / "orphan-returns.toml")
    choice, why = choose_step(loaded, step="orphans")  # a local (inputs) step
    assert choice is None
    assert "full recipe" in why


def test_choose_requires_step_when_multiple_db_steps() -> None:
    loaded = load_recipe(EXAMPLES / "orphan-returns.toml")  # orders + returns
    choice, why = choose_step(loaded)
    assert choice is None
    assert "multiple database steps" in why


def test_choose_unknown_step() -> None:
    loaded = load_recipe(EXAMPLES / "null-customers.toml")
    choice, why = choose_step(loaded, step="nope")
    assert choice is None
    assert "no step named" in why
