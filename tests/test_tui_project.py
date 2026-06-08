"""TUI project-model tests — the REAL entry path (no recipes_dir shortcut).

A tmp ``projects_dir`` is injected, so discovery, activation, the Ctrl+N wizard,
and Ctrl+T sync are exercised exactly as the launched app runs them — and never
touch the real ~/.wiseql/projects.
"""

from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.project import scaffold_project
from wiseql.tui.app import WiseQLApp
from wiseql.tui.projects import ProjectsScreen
from wiseql.tui.wizard import ProjectWizard

CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path, projects_dir: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    # No recipes_dir → the real projects model, scoped to the injected folder.
    return WiseQLApp(config_path=cfg, projects_dir=projects_dir)


@pytest.mark.asyncio
async def test_no_projects_opens_picker(tmp_path: Path) -> None:
    pdir = tmp_path / "projects"
    pdir.mkdir()
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)  # empty picker
        assert app.active_project is None


@pytest.mark.asyncio
async def test_single_project_auto_activates(tmp_path: Path) -> None:
    pdir = tmp_path / "projects"
    scaffold_project(pdir / "only", "only")
    (pdir / "only" / "recipes" / "r.toml").write_text(
        '[recipe]\nname="r"\n[steps.s]\nsource="oracle_dev"\nsql="SELECT 1 FROM dual"\n',
        encoding="utf-8",
    )
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        # one project → opens straight to the recipe browser, scoped to it
        assert not isinstance(app.screen, ProjectsScreen)
        assert app.active_project == pdir / "only"


@pytest.mark.asyncio
async def test_two_projects_pick_one_activates(tmp_path: Path) -> None:
    pdir = tmp_path / "projects"
    scaffold_project(pdir / "alpha", "alpha")
    scaffold_project(pdir / "beta", "beta")
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)  # 2 projects → picker
        await pilot.press("enter")  # activate first (alpha)
        await pilot.pause()
        assert app.active_project == pdir / "alpha"
        assert not isinstance(app.screen, ProjectsScreen)


@pytest.mark.asyncio
async def test_ctrl_n_creates_in_projects_dir_and_activates(tmp_path: Path) -> None:
    pdir = tmp_path / "projects"
    pdir.mkdir()
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert isinstance(app.screen, ProjectWizard)
        await pilot.press(*list("mydemo"))
        await pilot.press("enter")
        await pilot.pause()
        # created in the PROJECTS FOLDER (not cwd) and immediately active —
        # so Ctrl+T / F6 work with no relaunch (the reported bug).
        assert (pdir / "mydemo" / "project.toml").is_file()
        assert app.active_project == pdir / "mydemo"


@pytest.mark.asyncio
async def test_f7_opens_projects_and_independent_of_cwd(tmp_path: Path, monkeypatch) -> None:
    # cwd is somewhere with NO project — discovery must still find the folder's projects.
    monkeypatch.chdir(tmp_path)
    pdir = tmp_path / "elsewhere" / "projects"
    scaffold_project(pdir / "p1", "p1")
    scaffold_project(pdir / "p2", "p2")
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("f7")
        await pilot.pause()
        assert isinstance(app.screen, ProjectsScreen)
        table = app.screen.query_one("#projects-table", DataTable)
        assert table.row_count == 2  # both projects listed regardless of cwd


@pytest.mark.asyncio
async def test_ctrl_t_without_active_project_does_not_spawn_worker(tmp_path: Path) -> None:
    pdir = tmp_path / "projects"
    pdir.mkdir()  # no projects → picker, no active project
    app = _app(tmp_path, pdir)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.active_project is None
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert len(app.workers) == 0  # guarded early-return, no DB connection
