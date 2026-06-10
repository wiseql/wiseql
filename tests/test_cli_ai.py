"""CLI ``ai`` tests (S6.1). Offline — the base venv has no `ollama`, so the
not-installed path is authentic. ``$WISEQL_CONFIG`` isolates ai.toml to tmp."""

import sys
from pathlib import Path

from typer.testing import CliRunner

from wiseql.ai.settings import load_ai_settings
from wiseql.cli import app

runner = CliRunner()


def _env(tmp_path: Path) -> dict[str, str]:
    cfg = tmp_path / "config.toml"
    cfg.write_text("", encoding="utf-8")
    return {"WISEQL_CONFIG": str(cfg), "COLUMNS": "200"}


def test_ai_status_off_exits_0(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ai", "status"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "off" in result.output


def test_ai_setup_without_extra_exits_1(tmp_path: Path, monkeypatch) -> None:
    # Force the [ai] extra to look absent regardless of the venv's real state.
    monkeypatch.setitem(sys.modules, "ollama", None)  # `import ollama` → ImportError
    result = runner.invoke(app, ["ai", "setup"], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "isn't installed" in result.output
    assert "wiseql[ai]" in result.output  # literal install hint, brackets intact


def test_ai_disable_writes_state(tmp_path: Path) -> None:
    result = runner.invoke(app, ["ai", "disable"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert (tmp_path / "ai.toml").is_file()
    assert load_ai_settings(tmp_path / "ai.toml").enabled is False
