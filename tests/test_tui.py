"""TUI tests (Sprint 1: recipe browser)."""

from pathlib import Path

import pytest
from textual.widgets import ListView, Static, Tree

from wiseql.tui.app import HelpScreen, WiseQLApp

EXAMPLES = Path(__file__).parent.parent / "examples"
BROKEN = Path(__file__).parent / "fixtures" / "broken"


@pytest.mark.asyncio
async def test_app_boots_with_footer_bindings() -> None:
    app = WiseQLApp(recipes_dir=EXAMPLES)
    async with app.run_test() as pilot:
        assert app.title == "WiseQL"
        keys = {b.key for b in app.BINDINGS}
        assert {"f1", "f4", "f5", "f10"} <= keys
        await pilot.pause()


@pytest.mark.asyncio
async def test_f1_opens_help_and_any_key_closes() -> None:
    app = WiseQLApp(recipes_dir=EXAMPLES)
    async with app.run_test() as pilot:
        await pilot.press("f1")
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_browser_lists_and_shows_first_recipe() -> None:
    app = WiseQLApp(recipes_dir=EXAMPLES)
    async with app.run_test() as pilot:
        await pilot.pause()
        list_view = app.query_one("#recipe-list", ListView)
        assert len(list_view) == len(sorted(EXAMPLES.glob("*.toml")))
        text = app.detail_text
        assert "daily-volume" in text  # first alphabetically
        assert "valid" in text
        tree = app.query_one("#dag-tree", Tree)
        assert tree.display is True


@pytest.mark.asyncio
async def test_browser_shows_errors_for_broken_recipe() -> None:
    app = WiseQLApp(recipes_dir=BROKEN)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert "INVALID" in app.detail_text


@pytest.mark.asyncio
async def test_ai_seam_is_null_by_default() -> None:
    app = WiseQLApp(recipes_dir=EXAMPLES)
    async with app.run_test():
        assert app.ai.is_available is False
