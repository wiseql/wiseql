"""Connections-screen tests (S2.2).

DB-free (``ping`` is monkeypatched) and Keychain-free (a dict-backed fake
``keyring`` module). The screen is pushed directly — it's independent of the
app's entry model.
"""

import sys
import types
from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.config import PingResult
from wiseql.tui.app import WiseQLApp
from wiseql.tui.connections import ConnectionsScreen, LoginModal

CONFIG = """\
[connections.env_conn]
host    = "localhost"
service = "FREEPDB1"
user    = "wiseql"
auth    = "env"

[connections.kr_conn]
host    = "localhost"
service = "FREEPDB1"
user    = "wiseql"
auth    = "keyring"
"""


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(config_path=cfg, projects_dir=tmp_path / "projects")


def _screen(tmp_path: Path) -> ConnectionsScreen:
    return ConnectionsScreen(config_path=tmp_path / "config.toml")


@pytest.mark.asyncio
async def test_lists_connections(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_screen(tmp_path))
        await pilot.pause()
        assert isinstance(app.screen, ConnectionsScreen)
        table = app.screen.query_one("#conn-table", DataTable)
        assert table.row_count == 2
        assert "env_conn" in str(table.get_cell("env_conn", "name"))
        assert table.get_cell("env_conn", "target") == "localhost:1521/FREEPDB1"


@pytest.mark.asyncio
async def test_test_action_updates_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "wiseql.tui.connections.ping",
        lambda name, conn, **kw: PingResult(ok=True, elapsed_ms=12.3, detail="Oracle 23"),
    )
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_screen(tmp_path))
        await pilot.pause()
        await pilot.press("t")  # cursor on row 0 = env_conn
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#conn-table", DataTable)
        assert "✓" in str(table.get_cell("env_conn", "status"))
        assert "12.3" in str(table.get_cell("env_conn", "status"))


@pytest.mark.asyncio
async def test_test_action_reports_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "wiseql.tui.connections.ping",
        lambda name, conn, **kw: PingResult(ok=False, elapsed_ms=9.0, detail="ORA-01017: bad creds"),
    )
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_screen(tmp_path))
        await pilot.pause()
        await pilot.press("t")
        await app.workers.wait_for_complete()
        await pilot.pause()
        table = app.screen.query_one("#conn-table", DataTable)
        assert "✗" in str(table.get_cell("env_conn", "status"))
        assert "ORA-01017" in str(table.get_cell("env_conn", "status"))


@pytest.mark.asyncio
async def test_login_opens_modal_for_keyring_and_stores(tmp_path: Path, monkeypatch) -> None:
    store: dict[tuple[str, str], str] = {}
    fake = types.ModuleType("keyring")
    fake.get_password = lambda s, u: store.get((s, u))
    fake.set_password = lambda s, u, pw: store.__setitem__((s, u), pw)
    monkeypatch.setitem(sys.modules, "keyring", fake)

    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_screen(tmp_path))
        await pilot.pause()
        await pilot.press("down")  # row 1 = kr_conn
        await pilot.press("l")
        assert isinstance(app.screen, LoginModal)
        await pilot.press("s", "3", "c", "r", "t")
        await pilot.press("enter")
        await pilot.pause()
        assert store == {("wiseql", "kr_conn"): "s3crt"}


@pytest.mark.asyncio
async def test_login_warns_for_env_backend(tmp_path: Path) -> None:
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app.push_screen(_screen(tmp_path))
        await pilot.pause()
        await pilot.press("l")  # row 0 = env_conn → no modal, just a warning
        assert isinstance(app.screen, ConnectionsScreen)
