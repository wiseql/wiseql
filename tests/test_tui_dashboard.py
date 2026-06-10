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


# --- real entry flow (no overrides beyond the injected projects_dir) --------


@pytest.mark.asyncio
async def test_app_opens_to_picker(tmp_path: Path) -> None:
    _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # entry is the centered picker, independent of cwd
        assert isinstance(app.screen, ProjectPickerScreen)
        assert app.screen.query_one("#picker-table", DataTable).row_count == 1


@pytest.mark.asyncio
async def test_picker_open_then_back_to_picker(tmp_path: Path) -> None:
    _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # open the project → dashboard
        await pilot.pause()
        assert isinstance(app.screen, ProjectDashboardScreen)
        await pilot.press("escape")  # back to the picker
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)


@pytest.mark.asyncio
async def test_new_project_from_picker_creates_and_opens(tmp_path: Path) -> None:
    from wiseql.tui.wizard import ProjectWizard

    pdir = tmp_path / "projects"
    pdir.mkdir()
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)
        await pilot.press("n")  # new-project wizard
        await pilot.pause()
        assert isinstance(app.screen, ProjectWizard)
        await pilot.press(*list("fresh"))
        await pilot.press("enter")
        await pilot.pause()
        # created in the projects folder and opened immediately (no relaunch)
        assert (pdir / "fresh" / "project.toml").is_file()
        assert isinstance(app.screen, ProjectDashboardScreen)
        assert app.active_project == pdir / "fresh"


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


def _stage_resumable(proj: Path) -> Path:
    """Add a DOUBLE recipe + an interrupted run (seed checkpointed) to a project."""
    import datetime

    import duckdb

    from wiseql.engine.execute import _write_checkpoint
    from wiseql.recipes import load_recipe
    from wiseql.report import sql_fingerprint, write_manifest

    body = (
        '[recipe]\nname = "double"\n'
        '[steps.seed]\nsource = "oracle_dev"\nsql = "SELECT n FROM nums"\n'
        '[steps.derived]\ninputs = ["seed"]\nsql = "SELECT n * 2 AS n2 FROM seed"\n'
    )
    recipe = proj / "recipes" / "double.toml"
    recipe.write_text(body, encoding="utf-8")
    run_dir = proj / "runs" / "20260610T120000_000000"
    cdir = run_dir / "checkpoints"
    cdir.mkdir(parents=True)
    duck = duckdb.connect()
    duck.execute("CREATE TABLE seed AS SELECT * FROM (VALUES (1),(2),(3)) t(n)")
    _write_checkpoint(duck, cdir, "seed")
    duck.close()
    write_manifest(
        run_dir, recipe_name="double", params={},
        step_sql=sql_fingerprint(load_recipe(recipe).resolved_sql), status="failed",
        started_at=datetime.datetime(2026, 6, 10, 12, 0, 0),
    )
    return run_dir


@pytest.mark.asyncio
async def test_runs_tab_ctrl_r_resumes_interrupted_run(tmp_path: Path) -> None:
    from wiseql.tui.run import RunScreen

    proj = _project(tmp_path)
    run_dir = _stage_resumable(proj)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("3")  # Runs tab
        await pilot.pause()
        # newest run is the staged interrupted "double" (sorts after the seeded one)
        table = app.screen.query_one("#runs-table", DataTable)
        table.move_cursor(row=0)
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert isinstance(app.screen, RunScreen)
        assert app.screen._resume_from == run_dir


@pytest.mark.asyncio
async def test_runs_tab_ctrl_d_diffs_against_previous(tmp_path: Path) -> None:
    from wiseql.tui.diff import DiffScreen

    proj = _project(tmp_path)  # writes one "late-check" run (3 rows) at 2026-06-07
    # a second, newer run of the same recipe with a different row count
    r2 = RunResult(
        ok=False,
        steps=[StepRun("recent", "db", "oracle_dev", True, columns=["X"], sample=[(1,)], row_count=5, elapsed_ms=4.0)],
        terminals=["recent"], elapsed_ms=6.0,
    )
    write_report(proj / "runs", r2, "late-check", {}, datetime(2026, 6, 8, 9, 0, 0))

    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("3")  # Runs tab
        await pilot.pause()
        table = app.screen.query_one("#runs-table", DataTable)
        table.move_cursor(row=0)  # newest run (the 5-row one)
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert isinstance(app.screen, DiffScreen)
        recent = next(s for s in app.screen._diff.steps if s.name == "recent")
        assert recent.row_delta == 2  # 3 (older) → 5 (newer)


@pytest.mark.asyncio
async def test_f3_opens_connections(tmp_path: Path) -> None:
    from wiseql.tui.connections import ConnectionsScreen

    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("f3")
        await pilot.pause()
        assert isinstance(app.screen, ConnectionsScreen)


@pytest.mark.asyncio
async def test_ctrl_t_without_default_connection_does_not_run(tmp_path: Path) -> None:
    # The scaffolded project + this config declare no default connection, so the
    # sync guard must fire — no worker, no DB connection.
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert len(app.workers) == 0


@pytest.mark.asyncio
async def test_ctrl_n_from_dashboard_switches_project(tmp_path: Path) -> None:
    # Open one project, create another via Ctrl+N → the dashboard switches to it
    # without stacking dashboards.
    from wiseql.tui.wizard import ProjectWizard

    _project(tmp_path)  # 'demo'
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")  # open demo → dashboard
        await pilot.pause()
        assert isinstance(app.screen, ProjectDashboardScreen)
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert isinstance(app.screen, ProjectWizard)
        await pilot.press(*list("second"))
        await pilot.press("enter")
        await pilot.pause()
        assert app.active_project.name == "second"
        assert isinstance(app.screen, ProjectDashboardScreen)
        dashboards = [s for s in app.screen_stack if isinstance(s, ProjectDashboardScreen)]
        assert len(dashboards) == 1  # switched, not stacked


@pytest.mark.asyncio
async def test_tab_switch_moves_focus_to_content(tmp_path: Path) -> None:
    # Switching a tab must land focus in its content so ↑/↓/Enter work without
    # the mouse (the reported UX bug).
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("2")  # Recipes
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "recipe-list"
        await pilot.press("3")  # Runs
        await pilot.pause()
        assert app.focused.id == "runs-table"
        await pilot.press("right")  # ←/→ also switch + focus (wraps to Overview)
        await pilot.pause()
        assert app.focused.id == "overview-pane"


@pytest.mark.asyncio
async def test_recipes_enter_focuses_detail_esc_returns_to_list(tmp_path: Path) -> None:
    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("2")  # Recipes → list focused
        await pilot.pause()
        assert app.focused.id == "recipe-list"
        await pilot.press("enter")  # focus the detail pane to scroll it
        await pilot.pause()
        assert app.focused.id == "recipe-detail"
        await pilot.press("escape")  # back to the list (not the picker)
        await pilot.pause()
        assert app.focused.id == "recipe-list"
        assert isinstance(app.screen, ProjectDashboardScreen)
        await pilot.press("escape")  # now leave the project
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)


@pytest.mark.asyncio
async def test_f1_help_closes_on_escape_without_leaving_dashboard(tmp_path: Path) -> None:
    from wiseql.tui.app import HelpScreen

    proj = _project(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        await pilot.pause()
        # Esc closes Help and stays on the dashboard — it must NOT leak to the
        # dashboard's own Esc (which would go back to the picker).
        assert isinstance(app.screen, ProjectDashboardScreen)


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
