"""TUI shell tests (Textual's async test harness)."""

import pytest

from wiseql.tui.app import HelpScreen, WiseQLApp


@pytest.mark.asyncio
async def test_app_boots_with_footer_bindings() -> None:
    app = WiseQLApp()
    async with app.run_test() as pilot:
        assert app.title == "WiseQL"
        keys = {b.key for b in app.BINDINGS}
        assert {"f1", "f10"} <= keys
        await pilot.pause()


@pytest.mark.asyncio
async def test_f1_opens_help_and_any_key_closes() -> None:
    app = WiseQLApp()
    async with app.run_test() as pilot:
        await pilot.press("f1")
        assert isinstance(app.screen, HelpScreen)
        await pilot.press("escape")
        assert not isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_ai_seam_is_null_by_default() -> None:
    app = WiseQLApp()
    async with app.run_test():
        assert app.ai.is_available is False
