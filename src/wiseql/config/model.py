"""Pydantic models for connections and configuration.

``extra="forbid"`` on every model: a typo in a connection field (``hsot``)
is a hard error with an exact message, never a silently-ignored key. A
debugging tool must not guess.

These models describe *connection definitions only* — never secrets. The
password lives in an auth backend (keyring / env / wallet); see ``auth.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Where projects live when the config doesn't say otherwise. A *visible* folder
# in the user's home (not a hidden dotfolder) so projects are easy to find and
# edit in a file manager. Override per-machine with [defaults] projects_dir.
DEFAULT_PROJECTS_DIR = "~/wiseql"

Driver = Literal["oracle"]  # PostgreSQL arrives in a later sprint
AuthMethod = Literal["keyring", "env", "wallet"]


class Connection(BaseModel):
    """A named connection definition — everything needed to connect *except*
    the secret. Recipes reference connections by name, so they stay shareable
    while credentials remain per-machine."""

    model_config = ConfigDict(extra="forbid")

    driver: Driver = "oracle"
    host: str | None = None
    port: int = 1521
    service: str | None = None
    user: str | None = None
    auth: AuthMethod = "keyring"
    # Explicit DSN / TNS alias. When set (typically with auth="wallet"),
    # it takes precedence over host/port/service for building the connect string.
    dsn: str | None = None

    @property
    def target(self) -> str:
        """Human-readable connect target, e.g. ``localhost:1521/FREEPDB1``."""
        if self.dsn:
            return self.dsn
        host = self.host or "?"
        service = self.service or "?"
        return f"{host}:{self.port}/{service}"


class Defaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: str | None = None
    # Folder holding all WiseQL projects. The app lists/creates projects here,
    # independent of the working directory. ``~`` is expanded.
    projects_dir: str | None = None


class WiseQLConfig(BaseModel):
    """The merged, in-memory configuration after layering global → project →
    flags. Built by ``config.loader``; not parsed directly from one file."""

    model_config = ConfigDict(extra="forbid")

    connections: dict[str, Connection] = Field(default_factory=dict)
    defaults: Defaults = Field(default_factory=Defaults)

    def resolve_name(self, name: str | None) -> str | None:
        """The connection name to use: explicit ``name`` or the configured
        default. Returns None if neither is available."""
        return name or self.defaults.connection

    @property
    def projects_root(self) -> Path:
        """The (expanded) folder holding all projects — config value or default."""
        return Path(self.defaults.projects_dir or DEFAULT_PROJECTS_DIR).expanduser()
