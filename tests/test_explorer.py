"""Data Explorer tests (S5.3). Offline — checkpoints are local Parquet."""

from pathlib import Path

import duckdb

from wiseql.engine import CheckpointExplorer
from wiseql.engine.execute import _write_checkpoint


def _run_with_checkpoint(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    cdir = run_dir / "checkpoints"
    cdir.mkdir(parents=True)
    duck = duckdb.connect()
    duck.execute(
        "CREATE TABLE orders AS SELECT * FROM "
        "(VALUES (1,'AB'),(2,'AB'),(3,'BC'),(4,'BC'),(5,'BC')) t(order_id, store_id)"
    )
    _write_checkpoint(duck, cdir, "orders")
    duck.close()
    return run_dir


def test_mounts_checkpoints_and_groups(tmp_path: Path) -> None:
    ex = CheckpointExplorer(_run_with_checkpoint(tmp_path))
    try:
        assert ex.tables == ["orders"]
        info = ex.table_info()[0]
        assert info.row_count == 5 and info.columns == ["order_id", "store_id"]
        # the demo: ad-hoc GROUP BY over a step's frozen output, no re-run
        r = ex.query("SELECT store_id, COUNT(*) AS n FROM orders GROUP BY store_id ORDER BY store_id")
        assert r.ok
        assert r.columns == ["store_id", "n"]
        assert r.rows == [("AB", 2), ("BC", 3)]
    finally:
        ex.close()


def test_bad_sql_returns_error_not_crash(tmp_path: Path) -> None:
    ex = CheckpointExplorer(_run_with_checkpoint(tmp_path))
    try:
        r = ex.query("SELECT * FROM does_not_exist")
        assert r.ok is False and r.error  # surfaced as text, no exception
        assert ex.query("   ").ok is False  # empty query guarded
    finally:
        ex.close()


def test_result_is_capped(tmp_path: Path) -> None:
    ex = CheckpointExplorer(_run_with_checkpoint(tmp_path))
    try:
        r = ex.query("SELECT * FROM orders", max_rows=2)
        assert r.ok and r.row_count == 2 and r.truncated is True
    finally:
        ex.close()


def test_no_checkpoints_dir_mounts_nothing(tmp_path: Path) -> None:
    empty = tmp_path / "bare"
    empty.mkdir()
    ex = CheckpointExplorer(empty)
    try:
        assert ex.tables == []
        assert ex.table_info() == []
    finally:
        ex.close()
