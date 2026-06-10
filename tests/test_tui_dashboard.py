"""Picker + dashboard tests (TUI redesign). Offline — built against a tmp
project with a recipe that uses an external sql_file and a seeded run."""

from datetime import datetime
from pathlib import Path

import pytest
from textual.widgets import DataTable, TabbedContent

from wiseql.engine.execute import RunResult, StepRun
from wiseql.project import scaffold_project
from wiseql.report import write_report
from wiseql.tui.app import WiseQLApp
from wiseql.tui.dashboard import ProjectDashboardScreen
from wiseql.tui.picker import ProjectPickerScreen
from wiseql.tui.reports import ReportDetailScreen

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'

RECIPE_WITH_SQLFILE = """\
[recipe]
name = "late-check"
description = "external sql file demo"
[steps.recent]
source = "oracle_dev"
sql_file = "sql/recent.sql"
"""
EXTERNAL_SQL = "SELECT return_id, special_marker_xyz FROM returns\n"


def _project(tmp_path: Path) -> Path:
    proj = tmp_path / "projects" / "demo"
    scaffold_project(proj, "demo")
    (proj / "recipes" / "late-check.toml").write_text(RECIPE_WITH_SQLFILE, encoding="utf-8")
    (proj / "recipes" / "sql").mkdir(parents=True, exist_ok=True)
    (proj / "recipes" / "sql" / "recent.sql").write_text(EXTERNAL_SQL, encoding="utf-8")
    r = RunResult(
        ok=False,
        steps=[StepRun("recent", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=3, elapsed_ms=4.0)],
        terminals=["recent"], elapsed_ms=5.0,
    )
    write_report(proj / "runs", r, "late-check", {}, datetime(2026, 6, 7, 8, 0, 0))
    return proj


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(config_path=cfg, projects_dir=tmp_path / "projects")


# --- picker -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_picker_lists_and_opens_dashboard(tmp_path: Path) -> None:
    _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectPickerScreen(app.projects_dir))
        await pilot.pause()
        table = app.screen.query_one("#picker-table", DataTable)
        assert table.row_count == 1
        await pilot.press("enter")  # open 'demo'
        await pilot.pause()
        assert isinstance(app.screen, ProjectDashboardScreen)
        assert app.active_project.name == "demo"


# --- dashboard --------------------------------------------------------------


@pytest.mark.asyncio
async def test_overview_shows_project_details(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        assert "demo" in app.screen.overview_text
        assert "recipes:" in app.screen.overview_text


@pytest.mark.asyncio
async def test_recipes_tab_shows_resolved_sql(tmp_path: Path) -> None:
    # The discriminator: the SQL pane must show the external file's CONTENTS,
    # not "sql_file = ...". The TOML pane shows the raw toml (with sql_file).
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        screen = app.screen
        assert "sql_file" in screen.recipe_toml_text  # raw toml references the file
        assert "special_marker_xyz" in screen.recipe_sql_text  # resolved file contents
        assert "sql_file" not in screen.recipe_sql_text  # not the filename


@pytest.mark.asyncio
async def test_runs_tab_opens_report_detail(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("3")  # Runs tab
        await pilot.pause()
        table = app.screen.query_one("#runs-table", DataTable)
        assert table.row_count == 1
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, ReportDetailScreen)


@pytest.mark.asyncio
async def test_tab_switching(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        tabs = app.screen.query_one("#tabs", TabbedContent)
        await pilot.press("2")
        await pilot.pause()
        assert tabs.active == "recipes"
        await pilot.press("1")
        await pilot.pause()
        assert tabs.active == "overview"
