"""Results-screen tests (S2.3). DB-free: ``run_step`` is monkeypatched."""

from pathlib import Path

import pytest
from textual.widgets import DataTable

from wiseql.engine import StepResult
from wiseql.tui.app import WiseQLApp
from wiseql.tui.results import ResultsScreen

EXAMPLES = Path(__file__).parent.parent / "examples"

CONFIG = """\
[connections.oracle_dev]
host    = "localhost"
service = "FREEPDB1"
user    = "wiseql"
auth    = "env"
"""


def _app(tmp_path: Path) -> WiseQLApp:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    return WiseQLApp(recipes_dir=EXAMPLES, config_path=cfg)


def _patch_run(monkeypatch, result: StepResult) -> None:
    monkeypatch.setattr("wiseql.tui.results.run_step", lambda *a, **k: result)


@pytest.mark.asyncio
async def test_f2_runs_single_db_step_and_shows_grid(tmp_path: Path, monkeypatch) -> None:
    _patch_run(
        monkeypatch,
        StepResult(
            ok=True,
            columns=["ORDER_ID", "CUSTOMER_ID"],
            rows=[(1001, 2), (1201, None)],
            row_count=2,
            elapsed_ms=7.5,
        ),
    )
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        # daily-volume has exactly one database step ("orders"), no params
        app._show(EXAMPLES / "daily-volume.toml")  # select that recipe
        await pilot.pause()
        await pilot.press("f2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert isinstance(app.screen, ResultsScreen)
        grid = app.screen.query_one("#result-grid", DataTable)
        assert grid.row_count == 2
        assert len(grid.columns) == 2
        # NULL renders as ∅
        assert "∅" in str(grid.get_row_at(1))


@pytest.mark.asyncio
async def test_f2_shows_error_on_failure(tmp_path: Path, monkeypatch) -> None:
    _patch_run(monkeypatch, StepResult(ok=False, error="ORA-00942: table missing"))
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "daily-volume.toml")
        await pilot.pause()
        await pilot.press("f2")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert "ORA-00942" in app.screen.status_text


@pytest.mark.asyncio
async def test_f2_warns_for_parameterised_recipe(tmp_path: Path, monkeypatch) -> None:
    # null-customers declares params → F2 should warn, not push a results screen
    called = False

    def _boom(*a, **k):
        nonlocal called
        called = True
        return StepResult(ok=True)

    monkeypatch.setattr("wiseql.tui.results.run_step", _boom)
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "null-customers.toml")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert not isinstance(app.screen, ResultsScreen)
        assert called is False


@pytest.mark.asyncio
async def test_f2_warns_when_multiple_db_steps(tmp_path: Path) -> None:
    # orphan-returns has two database steps → choose_step refuses without --step
    app = _app(tmp_path)
    async with app.run_test() as pilot:
        app._show(EXAMPLES / "orphan-returns.toml")
        await pilot.pause()
        await pilot.press("f2")
        await pilot.pause()
        assert not isinstance(app.screen, ResultsScreen)
