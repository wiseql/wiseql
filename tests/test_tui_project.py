"""TUI project-action tests (S4.1/S4.3): the Ctrl+N wizard and Ctrl+T sync —
the new TUI entry points. Offline (Ctrl+T's no-project branch needs no DB)."""

from pathlib import Path

import pytest

from wiseql.tui.app import WiseQLApp
from wiseql.tui.wizard import ProjectWizard

EXAMPLES = Path(__file__).parent.parent / "examples"
CONFIG = '[connections.oracle_dev]\nhost = "localhost"\nservice = "FREEPDB1"\nuser = "wiseql"\nauth = "env"\n'


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(recipes_dir=EXAMPLES, config_path=cfg)


@pytest.mark.asyncio
async def test_ctrl_n_wizard_scaffolds_project(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # wizard scaffolds into cwd
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()
        assert isinstance(app.screen, ProjectWizard)
        await pilot.press(*list("mydemo"))
        await pilot.press("enter")
        await pilot.pause()
        assert (tmp_path / "mydemo" / "project.toml").is_file()
        assert (tmp_path / "mydemo" / "context" / "tables.md").is_file()


@pytest.mark.asyncio
async def test_ctrl_n_wizard_cancel_creates_nothing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+n")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        # nothing scaffolded — only the config file we created is present
        assert {p.name for p in tmp_path.iterdir()} == {"config.toml"}


@pytest.mark.asyncio
async def test_ctrl_t_outside_project_does_not_spawn_worker(tmp_path: Path, monkeypatch) -> None:
    # cwd has no project.toml → sync must early-return (the "not in a project"
    # branch the user hits first), never opening a DB connection.
    monkeypatch.chdir(tmp_path)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert len(app.workers) == 0  # no _sync_worker spawned
