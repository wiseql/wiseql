"""Live run-view tests (S3.4). DB-free: ``run_recipe`` is monkeypatched and
fires the ``on_step`` callback so the live table updates are exercised."""

from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.engine import AssertionOutcome, RunResult, StepRun
from wiseql.tui.app import WiseQLApp
from wiseql.tui.params import ParamModal
from wiseql.tui.run import RunScreen, StepDetailScreen

EXAMPLES = Path(__file__).parent.parent / "examples"

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(recipes_dir=EXAMPLES, config_path=cfg)


def _orphan_steps() -> list[StepRun]:
    return [
        StepRun("orders", "db", "oracle_dev", True, columns=["ORDER_ID"], sample=[(1,)], row_count=127, elapsed_ms=5.0),
        StepRun("returns", "db", "oracle_dev", True, columns=["RETURN_ID"], sample=[(1,)], row_count=33, elapsed_ms=4.0),
        StepRun(
            "orphans", "local", None, True,
            columns=["RETURN_ID", "ORDER_ID"], sample=[(5901, 9991)], row_count=3, elapsed_ms=1.0,
            on_fail="report_samples",
            assertions=[AssertionOutcome("rows_max", False, "3 rows (max 0)", ["RETURN_ID", "ORDER_ID"], [(5901, 9991)])],
        ),
    ]


def _fake_run(steps, *, ok, capture=None):
    def _run(loaded, config, *, params=None, environ=None, on_step=None, runs_dir=None):
        if capture is not None:
            capture["params"] = params
        if on_step:
            for s in steps:
                on_step(s.name, None)
                on_step(s.name, s)
        return RunResult(ok=ok, steps=steps, terminals=[steps[-1].name], elapsed_ms=10.0)

    return _run


@pytest.mark.asyncio
async def test_f2_runs_full_recipe_live(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(_orphan_steps(), ok=False))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "orphan-returns.toml")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#run-table", DataTable)
        assert table.row_count == 3  # all plan steps listed
        assert "ok" in str(table.get_cell("orders", "status"))
        assert str(table.get_cell("orders", "rows")) == "127"
        assert "assert" in str(table.get_cell("orphans", "status"))  # ⚠ assert ✗
        assert "failed" in app.screen.status_text


@pytest.mark.asyncio
async def test_f2_parameterised_recipe_prompts_then_runs(tmp_path: Path, monkeypatch) -> None:
    capture: dict = {}
    one = [StepRun("recent_orders", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=1)]
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(one, ok=True, capture=capture))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "null-customers.toml")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, ParamModal)
        await pilot.press(*list("20260101"))
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
        assert capture["params"] == {"run_date": "20260101"}


@pytest.mark.asyncio
async def test_enter_opens_step_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(_orphan_steps(), ok=False))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "orphan-returns.toml")
        await pilot.pause()
        await pilot.press("f2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press("down", "down")  # move cursor to 'orphans'
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, StepDetailScreen)


@pytest.mark.asyncio
async def test_execution_failed_step_shows_error_and_detail(tmp_path: Path, monkeypatch) -> None:
    # An execution error (not an assertion) lights the step ✗ error, rows "—",
    # and its detail renders the error without an output grid.
    steps = [StepRun("orders", "db", "oracle_dev", False, error="ORA-00942: table missing", elapsed_ms=3.0)]
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(steps, ok=False))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "daily-volume.toml")
        await pilot.pause()
        await pilot.press("f2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#run-table", DataTable)
        assert "error" in str(table.get_cell("orders", "status"))
        assert str(table.get_cell("orders", "rows")) == "—"
        await pilot.press("enter")  # cursor on 'orders' (row 0)
        await pilot.pause()
        assert isinstance(app.screen, StepDetailScreen)


@pytest.mark.asyncio
async def test_multi_db_step_recipe_now_runs_in_tui(tmp_path: Path, monkeypatch) -> None:
    # orphan-returns has two db steps — in Sprint 2/3.1 the TUI couldn't run it;
    # F2 must now open the run view instead of warning.
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(_orphan_steps(), ok=True))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "orphan-returns.toml")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
