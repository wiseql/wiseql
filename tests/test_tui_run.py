"""Live run-view tests (S3.4 / S4). RunScreen is pushed directly; the param→run
flow is driven through the dashboard. DB-free: run_recipe is monkeypatched and
fires on_step so the live table updates are exercised."""

from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.config import WiseQLConfig
from wiseql.engine import AssertionOutcome, RunResult, StepRun
from wiseql.project import scaffold_project
from wiseql.recipes import load_recipe
from wiseql.tui.app import WiseQLApp
from wiseql.tui.dashboard import ProjectDashboardScreen
from wiseql.tui.params import ParamModal
from wiseql.tui.run import RunScreen, StepDetailScreen

EXAMPLES = Path(__file__).parent.parent / "examples"
CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(config_path=cfg, projects_dir=tmp_path / "projects")


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
    def _run(loaded, config, *, params=None, environ=None, on_step=None, runs_dir=None, resume_from=None):
        if capture is not None:
            capture["params"] = params
            capture["resume_from"] = resume_from
        if on_step:
            for s in steps:
                on_step(s.name, None)
                on_step(s.name, s)
        return RunResult(ok=ok, steps=steps, terminals=[steps[-1].name], elapsed_ms=10.0)

    return _run


def _run_screen(loaded_name="orphan-returns.toml", recipe_name="orphan-returns"):
    loaded = load_recipe(EXAMPLES / loaded_name)
    return RunScreen(loaded, WiseQLConfig(), {}, recipe_name, runs_dir=None)


@pytest.mark.asyncio
async def test_run_screen_lights_up_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(_orphan_steps(), ok=False))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_run_screen())
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#run-table", DataTable)
        assert table.row_count == 3
        assert "ok" in str(table.get_cell("orders", "status"))
        assert str(table.get_cell("orders", "rows")) == "127"
        assert "assert" in str(table.get_cell("orphans", "status"))
        assert "failed" in app.screen.status_text


@pytest.mark.asyncio
async def test_run_screen_execution_error(tmp_path: Path, monkeypatch) -> None:
    steps = [StepRun("orders", "db", "oracle_dev", False, error="ORA-00942: table missing", elapsed_ms=3.0)]
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(steps, ok=False))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_run_screen("daily-volume.toml", "daily-volume"))
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#run-table", DataTable)
        assert "error" in str(table.get_cell("orders", "status"))
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, StepDetailScreen)


@pytest.mark.asyncio
async def test_dashboard_f2_parameterised_prompts_then_runs(tmp_path: Path, monkeypatch) -> None:
    capture: dict = {}
    one = [StepRun("recent_orders", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=1)]
    monkeypatch.setattr("wiseql.tui.run.run_recipe", _fake_run(one, ok=True, capture=capture))

    proj = tmp_path / "projects" / "p"
    scaffold_project(proj, "p")
    (proj / "recipes" / "nc.toml").write_text(
        (EXAMPLES / "null-customers.toml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("2")  # Recipes tab (selects the only recipe)
        await pilot.pause()
        await pilot.press("f2")  # run → parameterised → ParamModal
        await pilot.pause()
        assert isinstance(app.screen, ParamModal)
        await pilot.press(*list("20260101"))
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
        assert capture["params"] == {"run_date": "20260101"}
