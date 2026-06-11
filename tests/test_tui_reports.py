"""Report-detail tests (S4.2). The run-history list now lives in the dashboard
Runs tab (see test_tui_dashboard); this covers the detail screen itself."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.engine.execute import RunResult, StepRun
from wiseql.project import scaffold_project
from wiseql.report import load_report, write_report
from wiseql.tui.app import WiseQLApp
from wiseql.tui.aireview import AIReviewScreen
from wiseql.tui.reports import ReportDetailScreen
from wiseql.tui.run import StepDetailScreen

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'

RECIPE_WITH_SQLFILE = """\
[recipe]
name = "late-check"
[steps.recent]
source = "oracle_dev"
sql_file = "sql/recent.sql"
"""
EXTERNAL_SQL = "SELECT return_id, special_marker_xyz FROM returns\n"


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(config_path=cfg, projects_dir=tmp_path / "projects")


def _project_with_report(tmp_path: Path) -> tuple[Path, dict]:
    """A project holding the late-check recipe (external sql_file) + a failed run
    report whose recipe matches it — so AI grounding resolves the real SQL."""
    proj = tmp_path / "projects" / "demo"
    scaffold_project(proj, "demo")
    (proj / "recipes" / "late-check.toml").write_text(RECIPE_WITH_SQLFILE, encoding="utf-8")
    (proj / "recipes" / "sql").mkdir(parents=True, exist_ok=True)
    (proj / "recipes" / "sql" / "recent.sql").write_text(EXTERNAL_SQL, encoding="utf-8")
    r = RunResult(
        ok=False,
        steps=[StepRun("recent", "db", "oracle_dev", False, error="ORA-00942", elapsed_ms=2.0)],
        terminals=["recent"], elapsed_ms=3.0,
    )
    path = write_report(proj / "runs", r, "late-check", {}, datetime(2026, 6, 8, 12, 0, 0))
    return proj, load_report(path)


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


# --- F4 AI run review (S6.3) -------------------------------------------------


@pytest.mark.asyncio
async def test_f4_ai_run_review_streams_and_grounds(tmp_path: Path, monkeypatch) -> None:
    class _Fake:
        name = "fake"

        def stream(self, prompt):
            yield "step `recent` failed (ORA-00942). "
            yield "Inspect it first."

    monkeypatch.setattr("wiseql.ai.get_provider", lambda *a, **k: _Fake())
    proj, report = _project_with_report(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportDetailScreen(report, project=proj))
        await pilot.pause()
        await pilot.press("f4")
        for _ in range(6):
            await pilot.pause()
        assert isinstance(app.screen, AIReviewScreen)  # opens on the AI screen
        # grounding: the resolved external SQL, the schema context, and the run report
        assert "special_marker_xyz" in app.screen._prompt
        assert "schema/context" in app.screen._prompt
        assert "run report" in app.screen._prompt and "ORA-00942" in app.screen._prompt
        assert app.screen.buffer.startswith("step `recent` failed")


@pytest.mark.asyncio
async def test_f4_ai_off_shows_hint(tmp_path: Path, monkeypatch) -> None:
    from wiseql.ai import NullProvider

    monkeypatch.setattr("wiseql.ai.get_provider", lambda *a, **k: NullProvider())
    proj, report = _project_with_report(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportDetailScreen(report, project=proj))
        await pilot.pause()
        await pilot.press("f4")
        for _ in range(5):
            await pilot.pause()
        assert isinstance(app.screen, AIReviewScreen)
        assert "off" in app.screen.buffer.lower()


@pytest.mark.asyncio
async def test_f4_ai_extra_missing_shows_install_hint(tmp_path: Path, monkeypatch) -> None:
    class _Enabled:
        name = "ollama"

        def stream(self, prompt):
            raise ModuleNotFoundError("No module named 'ollama'")
            yield

    monkeypatch.setattr("wiseql.ai.get_provider", lambda *a, **k: _Enabled())
    proj, report = _project_with_report(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ReportDetailScreen(report, project=proj))
        await pilot.pause()
        await pilot.press("f4")
        for _ in range(5):
            await pilot.pause()
        assert isinstance(app.screen, AIReviewScreen)
        assert "wiseql[ai]" in app.screen.buffer and "isn't installed" in app.screen.buffer
