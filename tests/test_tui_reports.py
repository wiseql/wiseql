"""Report-viewer tests (S4.2). Offline — reports are written to a temp runs/."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.engine.execute import RunResult, StepRun
from wiseql.report import write_report
from wiseql.tui.app import WiseQLApp
from wiseql.tui.reports import ReportDetailScreen, ReportsScreen
from wiseql.tui.run import StepDetailScreen

EXAMPLES = Path(__file__).parent.parent / "examples"
CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(recipes_dir=EXAMPLES, config_path=cfg)


def _seed_two_runs(runs_dir: Path) -> None:
    r = RunResult(
        ok=True,
        steps=[StepRun("orders", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=5, elapsed_ms=3.0)],
        terminals=["orders"], elapsed_ms=4.0,
    )
    write_report(runs_dir, r, "daily-volume", {}, datetime(2026, 6, 8, 12, 0, 0))
    write_report(runs_dir, r, "orphan-returns", {}, datetime(2026, 6, 8, 12, 0, 1))


@pytest.mark.asyncio
async def test_reports_screen_lists_newest_first(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _seed_two_runs(runs)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportsScreen(runs_dir=runs))
        await pilot.pause()
        table = app.screen.query_one("#reports-table", DataTable)
        assert table.row_count == 2
        # newest first → orphan-returns (12:00:01) on row 0
        assert "orphan-returns" in str(table.get_cell("0", "recipe"))


@pytest.mark.asyncio
async def test_reports_screen_empty(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportsScreen(runs_dir=tmp_path / "runs"))
        await pilot.pause()
        assert app.screen.query_one("#reports-table", DataTable).row_count == 0


@pytest.mark.asyncio
async def test_enter_opens_report_then_step_detail(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    _seed_two_runs(runs)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportsScreen(runs_dir=runs))
        await pilot.pause()
        await pilot.press("enter")  # open newest report
        await pilot.pause()
        assert isinstance(app.screen, ReportDetailScreen)
        assert app.screen.query_one("#rep-table", DataTable).row_count == 1
        await pilot.press("enter")  # open the step's detail
        await pilot.pause()
        assert isinstance(app.screen, StepDetailScreen)


@pytest.mark.asyncio
async def test_f6_opens_reports_screen(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("f6")
        await pilot.pause()
        assert isinstance(app.screen, ReportsScreen)
