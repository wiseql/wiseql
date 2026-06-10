"""AI Settings screen (S6.1). Offline — AI is off, so the screen shows the
visible-but-disabled hint. ``$WISEQL_CONFIG`` isolates ai.toml to tmp."""

from pathlib import Path

import pytest

from wiseql.tui.app import WiseQLApp
from wiseql.tui.settings import SettingsScreen


def _isolate(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("WISEQL_CONFIG", str(cfg))


@pytest.mark.asyncio
async def test_settings_screen_reports_off(tmp_path: Path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    app = WiseQLApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(SettingsScreen())
        # let the probe worker run and post back
        for _ in range(5):
            await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert app.screen.status is not None
        assert app.screen.status.enabled is False and app.screen.status.ready is False


@pytest.mark.asyncio
async def test_dashboard_f9_opens_settings(tmp_path: Path, monkeypatch) -> None:
    from wiseql.project import scaffold_project
    from wiseql.tui.dashboard import ProjectDashboardScreen

    _isolate(tmp_path, monkeypatch)
    proj = tmp_path / "projects" / "demo"
    scaffold_project(proj, "demo")
    app = WiseQLApp(config_path=tmp_path / "config.toml", projects_dir=tmp_path / "projects")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(ProjectDashboardScreen(proj, app.config_path))
        await pilot.pause()
        await pilot.press("f9")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
