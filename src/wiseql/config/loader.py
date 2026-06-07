"""Config loading with layering: global → project → flag overrides.

Each layer contributes ``[connections.*]`` and ``[defaults]`` tables. Later
layers override earlier ones *field by field* within a connection — so a
project can override just the ``user`` of a connection defined globally and
inherit the rest.

Only the ``connections`` and ``defaults`` top-level tables are read; any other
top-level keys are ignored. This keeps layering robust when ``project.toml``
later grows unrelated sections (project name, paths, …). Unknown keys *inside*
a connection remain hard errors (typo protection), enforced by the pydantic
model's ``extra="forbid"``.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from wiseql.config.model import Connection, Defaults, WiseQLConfig

# Personal, machine-wide config.
GLOBAL_CONFIG_PATH = Path.home() / ".config" / "wiseql" / "config.toml"
# Project manifest, looked for in the current directory.
PROJECT_CONFIG_NAME = "project.toml"


@dataclass
class ConfigResult:
    config: WiseQLConfig
    errors: list[str] = field(default_factory=list)
    # Layer files that existed and were read, in precedence order.
    sources: list[Path] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _read_toml(path: Path, errors: list[str]) -> dict | None:
    """Read a TOML file. Returns None if absent; records an error on malformed
    TOML or read failure."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        errors.append(f"cannot read {path}: {exc}")
        return None
    try:
        return tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        errors.append(f"invalid TOML in {path}: {exc}")
        return None


def _merge_layer(
    merged_conns: dict[str, dict],
    merged_defaults: dict,
    data: dict,
) -> None:
    """Fold one layer's raw tables into the accumulating dicts (field-level
    override per connection)."""
    raw_conns = data.get("connections")
    if isinstance(raw_conns, dict):
        for name, fields in raw_conns.items():
            if isinstance(fields, dict):
                merged_conns.setdefault(name, {}).update(fields)
    raw_defaults = data.get("defaults")
    if isinstance(raw_defaults, dict):
        merged_defaults.update(raw_defaults)


def load_config(
    *,
    global_path: Path | None = None,
    project_path: Path | None = None,
    cwd: Path | None = None,
    overrides: dict | None = None,
) -> ConfigResult:
    """Load and merge configuration layers.

    Precedence (later wins): global file → project file → ``overrides`` dict
    (the CLI-flag layer, e.g. ``{"defaults": {"connection": "x"}}``). Paths
    default to the standard locations; pass them explicitly in tests.
    """
    errors: list[str] = []
    sources: list[Path] = []

    global_path = global_path if global_path is not None else GLOBAL_CONFIG_PATH
    if project_path is None:
        base = cwd if cwd is not None else Path.cwd()
        project_path = base / PROJECT_CONFIG_NAME

    merged_conns: dict[str, dict] = {}
    merged_defaults: dict = {}

    for path in (global_path, project_path):
        data = _read_toml(path, errors)
        if data is not None:
            sources.append(path)
            _merge_layer(merged_conns, merged_defaults, data)
    if overrides:
        _merge_layer(merged_conns, merged_defaults, overrides)

    # Validate each connection independently so one bad entry names itself
    # rather than failing the whole config opaquely.
    connections: dict[str, Connection] = {}
    for name, fields in merged_conns.items():
        try:
            connections[name] = Connection.model_validate(fields)
        except ValidationError as exc:
            for err in exc.errors():
                loc = ".".join(str(p) for p in err["loc"]) or "?"
                errors.append(f"connection '{name}': {loc} — {err['msg']}")

    try:
        defaults = Defaults.model_validate(merged_defaults)
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"]) or "?"
            errors.append(f"defaults: {loc} — {err['msg']}")
        defaults = Defaults()

    config = WiseQLConfig(connections=connections, defaults=defaults)
    return ConfigResult(config=config, errors=errors, sources=sources)
