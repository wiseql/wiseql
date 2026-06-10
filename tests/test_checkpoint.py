"""Checkpointing & resume tests (S5.1). Offline — no Oracle.

The resume tests fabricate an interrupted run: a checkpoint for a *database*
step (so resume restores it from parquet, never touching Oracle) plus a local
step that executes in DuckDB over the restored table. This exercises the real
``read_parquet`` round-trip and the resume continuation without a database.
"""

from pathlib import Path
from types import SimpleNamespace

import duckdb

from wiseql.config import WiseQLConfig
from wiseql.engine import run_recipe
from wiseql.engine.execute import _restore_checkpoint, _write_checkpoint
from wiseql.recipes import load_recipe
from wiseql.report import (
    checkpoint_steps,
    list_resumable_runs,
    read_manifest,
    set_manifest_status,
    sql_fingerprint,
    write_manifest,
)

# A db step (restored on resume) feeding a local step (runs in DuckDB).
DOUBLE = """
[recipe]
name = "double"
[steps.seed]
source = "oracle_dev"
sql = "SELECT n FROM nums"
[steps.derived]
inputs = ["seed"]
sql = "SELECT n * 2 AS n2 FROM seed"
"""

# Same, but the terminal step stops on any rows — so it must not be checkpointed.
DOUBLE_STOP = """
[recipe]
name = "double"
[steps.seed]
source = "oracle_dev"
sql = "SELECT n FROM nums"
[steps.derived]
inputs = ["seed"]
sql = "SELECT n * 2 AS n2 FROM seed"
assert = { rows_max = 0, on_fail = "stop" }
"""


def _recipe(tmp_path: Path, body: str):
    p = tmp_path / "double.toml"
    p.write_text(body, encoding="utf-8")
    return load_recipe(p)


def _stage_interrupted_run(tmp_path: Path, loaded, *, params=None, status="failed") -> Path:
    """Create a run dir with a manifest + a `seed` checkpoint, as if killed after step 1."""
    run_dir = tmp_path / "runs" / "20260610T120000_000000"
    cdir = run_dir / "checkpoints"
    cdir.mkdir(parents=True)
    duck = duckdb.connect()
    duck.execute("CREATE TABLE seed AS SELECT * FROM (VALUES (1),(2),(3)) t(n)")
    _write_checkpoint(duck, cdir, "seed")
    duck.close()
    write_manifest(
        run_dir, recipe_name="double", params=params or {},
        step_sql=sql_fingerprint(loaded.resolved_sql), status=status,
        started_at=__import__("datetime").datetime(2026, 6, 10, 12, 0, 0),
    )
    return run_dir


# --- checkpoint helpers (unit) ----------------------------------------------


def test_checkpoint_roundtrip_and_atomic(tmp_path: Path) -> None:
    cdir = tmp_path / "checkpoints"
    cdir.mkdir()
    duck = duckdb.connect()
    duck.execute('CREATE TABLE seed AS SELECT * FROM (VALUES (1),(2),(3)) v("N")')
    _write_checkpoint(duck, cdir, "seed")
    duck.close()

    assert (cdir / "seed.parquet").is_file()
    assert not (cdir / "seed.parquet.tmp").exists()  # atomic: tmp renamed away

    duck2 = duckdb.connect()
    step = SimpleNamespace(source="oracle_dev", inputs=[])
    run = _restore_checkpoint(duck2, cdir, "seed", step)
    duck2.close()
    assert run.ok and run.restored
    assert run.kind == "db" and run.row_count == 3
    assert run.columns == ["N"]


# --- resume through run_recipe (offline; seed restored, derived executed) ----


def test_resume_restores_prefix_and_continues(tmp_path: Path) -> None:
    loaded = _recipe(tmp_path, DOUBLE)
    run_dir = _stage_interrupted_run(tmp_path, loaded)

    # No oracle_dev connection configured — proves `seed` is restored, not run.
    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir)

    assert result.ok
    seed = result.step("seed")
    assert seed.restored and seed.row_count == 3
    derived = result.step("derived")
    assert not derived.restored and derived.row_count == 3
    assert sorted(r[0] for r in derived.sample) == [2, 4, 6]  # real read_parquet round-trip
    # derived now has its own checkpoint; manifest finalised ok
    assert checkpoint_steps(run_dir) == {"seed", "derived"}
    assert read_manifest(run_dir)["status"] == "ok"
    assert (run_dir / "report.json").is_file()


def test_resume_refreshes_manifest_fingerprints(tmp_path: Path) -> None:
    # The manifest's `derived` fingerprint is stale (the original recipe differed
    # there) — but `derived` has no checkpoint, so the resume is allowed (the
    # drift check only guards checkpointed steps) and must refresh the manifest
    # to the current fingerprint, so a later resume of a still-incomplete run
    # doesn't spuriously flag the now-checkpointed step.
    loaded = _recipe(tmp_path, DOUBLE)
    run_dir = _stage_interrupted_run(tmp_path, loaded)
    manifest = read_manifest(run_dir)
    manifest["step_sql"]["derived"] = "stale-from-an-earlier-recipe"
    write_manifest(
        run_dir, recipe_name="double", params={}, step_sql=manifest["step_sql"],
        status="failed", started_at=__import__("datetime").datetime(2026, 6, 10, 12, 0, 0),
    )

    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir)
    assert result.ok  # derived (uncheckpointed) ran; its stale fingerprint didn't block it
    assert read_manifest(run_dir)["step_sql"] == sql_fingerprint(loaded.resolved_sql)


def test_resume_refuses_on_sql_drift(tmp_path: Path) -> None:
    loaded = _recipe(tmp_path, DOUBLE)
    run_dir = _stage_interrupted_run(tmp_path, loaded)
    # Corrupt the stored fingerprint for the checkpointed step.
    manifest = read_manifest(run_dir)
    manifest["step_sql"]["seed"] = "deadbeef"
    write_manifest(
        run_dir, recipe_name="double", params={}, step_sql=manifest["step_sql"],
        status="failed", started_at=__import__("datetime").datetime(2026, 6, 10, 12, 0, 0),
    )
    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir)
    assert result.ok is False
    assert "recipe changed" in result.error and "seed" in result.error
    assert not result.steps  # refused before executing anything


def test_resume_refuses_on_param_mismatch(tmp_path: Path) -> None:
    loaded = _recipe(tmp_path, DOUBLE)
    run_dir = _stage_interrupted_run(tmp_path, loaded, params={"run_date": "2026-01-01"})
    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir, params={"run_date": "2026-02-02"})
    assert result.ok is False
    assert "parameters differ" in result.error


def test_resume_missing_manifest_is_refused(tmp_path: Path) -> None:
    loaded = _recipe(tmp_path, DOUBLE)
    empty = tmp_path / "runs" / "nope"
    empty.mkdir(parents=True)
    result = run_recipe(loaded, WiseQLConfig(), resume_from=empty)
    assert result.ok is False
    assert "no run.json" in result.error


def test_fully_checkpointed_failed_run_refuses_resume(tmp_path: Path) -> None:
    # A failed run where EVERY step is checkpointed (e.g. terminal report_samples):
    # restoring all and reporting would skip assertions and flip failed→ok. Refuse,
    # and don't classify it resumable in the first place.
    loaded = _recipe(tmp_path, DOUBLE)
    run_dir = _stage_interrupted_run(tmp_path, loaded)  # seed checkpointed, status failed
    # checkpoint derived too → done == total
    duck = duckdb.connect()
    duck.execute("CREATE TABLE derived AS SELECT * FROM (VALUES (2),(4),(6)) t(n2)")
    _write_checkpoint(duck, run_dir / "checkpoints", "derived")
    duck.close()

    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir)
    assert result.ok is False
    assert "nothing to resume" in result.error
    assert not result.steps  # never restored/ran anything

    # and it must not even be offered as resumable
    assert list_resumable_runs(tmp_path / "runs", "double") == []


def test_stop_failure_step_is_not_checkpointed(tmp_path: Path) -> None:
    loaded = _recipe(tmp_path, DOUBLE_STOP)
    run_dir = _stage_interrupted_run(tmp_path, loaded)
    result = run_recipe(loaded, WiseQLConfig(), resume_from=run_dir)
    assert result.ok is False  # derived produced rows → rows_max=0 stop
    assert result.step("derived").assert_failed
    # the failed step left no checkpoint — checkpoints stay a clean prefix
    assert checkpoint_steps(run_dir) == {"seed"}


# --- manifest + resumable discovery (unit) ----------------------------------


def test_manifest_lifecycle(tmp_path: Path) -> None:
    from datetime import datetime

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    write_manifest(
        run_dir, recipe_name="r", params={"a": "1"}, step_sql={"s": "h"},
        status="running", started_at=datetime(2026, 6, 10, 9, 0, 0),
    )
    assert read_manifest(run_dir)["status"] == "running"
    set_manifest_status(run_dir, "failed")
    m = read_manifest(run_dir)
    assert m["status"] == "failed"
    assert m["params"] == {"a": "1"} and m["recipe"] == "r"  # untouched by status flip


def test_list_resumable_runs_filters(tmp_path: Path) -> None:
    from datetime import datetime

    loaded = _recipe(tmp_path, DOUBLE)
    runs = tmp_path / "runs"
    # one failed-with-checkpoint (resumable), one clean ok (not), one wrong recipe
    failed = _stage_interrupted_run(tmp_path, loaded, status="failed")  # recipe "double"
    ok_dir = runs / "20260610T130000_000000"
    (ok_dir / "checkpoints").mkdir(parents=True)
    (ok_dir / "checkpoints" / "seed.parquet").write_bytes(b"x")
    write_manifest(ok_dir, recipe_name="double", params={}, step_sql={}, status="ok",
                   started_at=datetime(2026, 6, 10, 13, 0, 0))

    resumable = list_resumable_runs(runs, "double")
    assert [r.path for r in resumable] == [failed]
    assert resumable[0].done_steps == 1
    assert list_resumable_runs(runs, "other-recipe") == []
