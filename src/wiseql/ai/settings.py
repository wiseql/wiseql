"""AI add-on settings — a small, tool-owned state file (S6.1).

AI enablement is **machine-global** (not per-project), so it lives in its own
``ai.toml`` next to the global config, fully managed by ``wiseql ai setup`` /
``wiseql ai disable``. Keeping it separate from ``config.toml`` means we can
rewrite it wholesale (no user comments to preserve — the comment-preserving
config write deferred in S2.2b never enters the picture) and leaves the layered
``WiseQLConfig`` loader untouched.

The path is derived from the *active* global config path, so ``$WISEQL_CONFIG``
(and explicit overrides) isolate AI state too — the same CI/test isolation the
rest of the config already gets.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

AI_STATE_NAME = "ai.toml"
DEFAULT_MODEL = "gemma3"
DEFAULT_HOST = "http://localhost:11434"


@dataclass
class AISettings:
    enabled: bool = False
    model: str = DEFAULT_MODEL
    host: str = DEFAULT_HOST


def ai_state_path(explicit: Path | None = None) -> Path:
    """``ai.toml`` next to the active global config (honours ``$WISEQL_CONFIG``)."""
    from wiseql.config.loader import GLOBAL_CONFIG_PATH, active_global_path

    base = active_global_path(explicit) or GLOBAL_CONFIG_PATH
    return base.parent / AI_STATE_NAME


def load_ai_settings(path: Path | None = None) -> AISettings:
    """Read AI settings; absent or malformed file → disabled defaults."""
    p = path or ai_state_path()
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, tomllib.TOMLDecodeError):
        return AISettings()
    ai = data.get("ai", {}) if isinstance(data.get("ai"), dict) else {}
    return AISettings(
        enabled=bool(ai.get("enabled", False)),
        model=str(ai.get("model", DEFAULT_MODEL)),
        host=str(ai.get("host", DEFAULT_HOST)),
    )


def save_ai_settings(settings: AISettings, path: Path | None = None) -> Path:
    """Write the ``[ai]`` state file wholesale (tool-owned; no comments to keep)."""
    p = path or ai_state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "# Managed by `wiseql ai setup` — AI add-on state (machine-global).\n"
        "[ai]\n"
        f"enabled = {str(settings.enabled).lower()}\n"
        f'model = "{settings.model}"\n'
        f'host = "{settings.host}"\n'
    )
    p.write_text(body, encoding="utf-8")
    return p
