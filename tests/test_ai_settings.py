"""AI settings persistence (S6.1). Offline."""

from pathlib import Path

from wiseql.ai.settings import (
    AISettings,
    ai_state_path,
    load_ai_settings,
    save_ai_settings,
)


def test_save_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "ai.toml"
    save_ai_settings(AISettings(enabled=True, model="gemma3:4b", host="http://h:1"), p)
    s = load_ai_settings(p)
    assert s.enabled is True and s.model == "gemma3:4b" and s.host == "http://h:1"


def test_absent_file_is_disabled_defaults(tmp_path: Path) -> None:
    s = load_ai_settings(tmp_path / "nope.toml")
    assert s.enabled is False and s.model == "gemma3"


def test_state_path_follows_wiseql_config(tmp_path: Path, monkeypatch) -> None:
    cfg = tmp_path / "sub" / "config.toml"
    monkeypatch.setenv("WISEQL_CONFIG", str(cfg))
    # ai.toml sits next to the active config, so $WISEQL_CONFIG isolates it.
    assert ai_state_path() == cfg.parent / "ai.toml"
