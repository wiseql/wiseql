"""In-app editor tests (S8). Offline."""

from pathlib import Path

import pytest
from textual.widgets import Input, TextArea

from wiseql.tui.app import WiseQLApp
from wiseql.tui.editor import EditorScreen, NameModal


def _app(tmp_path: Path) -> WiseQLApp:
    return WiseQLApp(projects_dir=tmp_path / "projects")


@pytest.mark.asyncio
async def test_editor_loads_file_content(tmp_path: Path) -> None:
    f = tmp_path / "r.toml"
    f.write_text("name = 'original'\n", encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)
        assert app.screen.query_one("#editor", TextArea).text == "name = 'original'\n"


@pytest.mark.asyncio
async def test_editor_saves_edits_to_disk(tmp_path: Path) -> None:
    f = tmp_path / "r.toml"
    f.write_text("before", encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        app.screen.query_one("#editor", TextArea).text = "after edit"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert f.read_text(encoding="utf-8") == "after edit"


@pytest.mark.asyncio
async def test_editor_can_create_a_new_file(tmp_path: Path) -> None:
    f = tmp_path / "sub" / "new.toml"  # doesn't exist yet
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        app.screen.query_one("#editor", TextArea).text = "fresh"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        assert f.read_text(encoding="utf-8") == "fresh"


@pytest.mark.asyncio
async def test_escape_leaves_editor_when_clean_or_saved(tmp_path: Path) -> None:
    # The focused TextArea swallows Escape unless the binding is priority — make
    # sure the user can actually leave (the reported bug).
    from wiseql.tui.picker import ProjectPickerScreen

    f = tmp_path / "r.toml"
    f.write_text("x=1", encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        # clean → Escape leaves immediately
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)
        # edited then saved → Escape leaves
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        app.screen.query_one("#editor", TextArea).text = "edited"
        await pilot.pause()
        await pilot.press("ctrl+s")
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)


@pytest.mark.asyncio
async def test_escape_with_unsaved_changes_warns_then_discards(tmp_path: Path) -> None:
    from wiseql.tui.picker import ProjectPickerScreen

    f = tmp_path / "r.toml"
    f.write_text("before", encoding="utf-8")
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(EditorScreen(f))
        await pilot.pause()
        app.screen.query_one("#editor", TextArea).text = "unsaved change"
        await pilot.pause()
        await pilot.press("escape")  # first Esc: warn, stay
        await pilot.pause()
        assert isinstance(app.screen, EditorScreen)
        await pilot.press("escape")  # second Esc: discard, leave
        await pilot.pause()
        assert isinstance(app.screen, ProjectPickerScreen)
        assert f.read_text(encoding="utf-8") == "before"  # discarded, not written


@pytest.mark.asyncio
async def test_name_modal_returns_entered_value(tmp_path: Path) -> None:
    app = _app(tmp_path)
    got = {}
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(NameModal("New recipe name"), lambda v: got.__setitem__("v", v))
        await pilot.pause()
        app.screen.query_one("#name-input", Input).value = "late-returns"
        await pilot.press("enter")
        await pilot.pause()
        assert got["v"] == "late-returns"
