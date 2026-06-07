"""Auth backend seam — where a connection's *secret* comes from.

Connections store everything except the password; this module resolves the
password at connect time from one of three backends:

- ``keyring`` (default) — OS keychain, prompts once, stores securely. Daily dev.
- ``env`` — ``$WISEQL_<CONN>_PASSWORD``. CI / scripted runs.
- ``wallet`` — Oracle Wallet / TNS supplies credentials at connect time, so
  WiseQL holds no secret at all. Stubbed in Sprint 2.

The seam mirrors the ``AIProvider``/``NullProvider`` pattern: a small ABC with
swappable implementations. ``keyring`` is imported lazily *inside* its methods
so that the default test path (env backend) never touches the real Keychain —
a real-keyring call would block on a macOS GUI prompt.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Mapping

from wiseql.config.model import Connection

# Keyring service namespace; the connection name is the keyring "username".
KEYRING_SERVICE = "wiseql"


class AuthBackend(ABC):
    """Resolves (and optionally stores) the password for a connection."""

    name: str = "abstract"

    @abstractmethod
    def get_password(self, conn_name: str, conn: Connection) -> str | None:
        """Return the secret, or None if not stored / not applicable."""

    def set_password(self, conn_name: str, conn: Connection, password: str) -> None:
        """Persist the secret. Not every backend supports this."""
        raise NotImplementedError(
            f"the '{self.name}' backend cannot store passwords"
        )

    def describe(self, conn_name: str) -> str:
        """Human hint about where this backend looks for the secret."""
        return self.name


class EnvBackend(AuthBackend):
    """Password from ``$WISEQL_<CONN>_PASSWORD``. The environment mapping is
    injectable so tests stay hermetic."""

    name = "env"

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def var_name(self, conn_name: str) -> str:
        return f"WISEQL_{conn_name.upper()}_PASSWORD"

    def get_password(self, conn_name: str, conn: Connection) -> str | None:
        return self._environ.get(self.var_name(conn_name))

    def describe(self, conn_name: str) -> str:
        return f"env:{self.var_name(conn_name)}"


class KeyringBackend(AuthBackend):
    """Password from the OS keychain via the ``keyring`` library.

    ``keyring`` is imported lazily so importing this module never pulls in the
    Keychain, and code paths that use the env backend never trigger a prompt.
    """

    name = "keyring"

    def get_password(self, conn_name: str, conn: Connection) -> str | None:
        import keyring

        return keyring.get_password(KEYRING_SERVICE, conn_name)

    def set_password(self, conn_name: str, conn: Connection, password: str) -> None:
        import keyring

        keyring.set_password(KEYRING_SERVICE, conn_name, password)

    def describe(self, conn_name: str) -> str:
        return f"keyring:{KEYRING_SERVICE}/{conn_name}"


class WalletBackend(AuthBackend):
    """Oracle Wallet / TNS — the wallet supplies credentials at connect time,
    so WiseQL stores no password. Stub in Sprint 2; real wallet wiring lands
    with the broader Oracle work."""

    name = "wallet"

    def get_password(self, conn_name: str, conn: Connection) -> str | None:
        return None

    def describe(self, conn_name: str) -> str:
        return "wallet:TNS_ADMIN"


_BACKENDS: dict[str, type[AuthBackend]] = {
    "env": EnvBackend,
    "keyring": KeyringBackend,
    "wallet": WalletBackend,
}


def get_backend(conn: Connection, *, environ: Mapping[str, str] | None = None) -> AuthBackend:
    """Construct the auth backend named by ``conn.auth``."""
    cls = _BACKENDS[conn.auth]
    if cls is EnvBackend:
        return EnvBackend(environ=environ)
    return cls()
