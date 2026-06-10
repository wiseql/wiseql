"""Report-detail tests (S4.2). The run-history list now lives in the dashboard
Runs tab (see test_tui_dashboard); this covers the detail screen itself."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.engine.execute import RunResult, StepRun
from wiseql.report import load_report, write_report
from wiseql.tui.app import WiseQLApp
from wiseql.tui.reports import ReportDetailScreen
from wiseql.tui.run import StepDetailScreen

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(config_path=cfg, projects_dir=tmp_path / "projects")


def _report(tmp_path: Path) -> dict:
    r = RunResult(
        ok=False,
        steps=[StepRun("orders", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=5, elapsed_ms=3.0)],
        terminals=["orders"], elapsed_ms=4.0,
    )
    path = write_report(tmp_path / "runs", r, "orphan-returns", {}, datetime(2026, 6, 8, 12, 0, 0))
    return load_report(path)


@pytest.mark.asyncio
async def test_report_detail_lists_steps_and_opens_step(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportDetailScreen(_report(tmp_path)))
        await pilot.pause()
        assert isinstance(app.screen, ReportDetailScreen)
        table = app.screen.query_one("#rep-table", DataTable)
        assert table.row_count == 1
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, StepDetailScreen)
