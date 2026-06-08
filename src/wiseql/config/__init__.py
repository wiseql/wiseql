"""Configuration & connection management.

Connections are named definitions holding everything *except* the secret;
recipes reference them by name. Config layers global → project → flags. The
password is resolved at connect time from a swappable auth backend.
"""

from wiseql.config.auth import AuthBackend, EnvBackend, KeyringBackend, WalletBackend, get_backend
from wiseql.config.connect import PingResult, open_connection, ping
from wiseql.config.loader import ConfigResult, load_active_config, load_config
from wiseql.config.model import Connection, Defaults, WiseQLConfig

__all__ = [
    "AuthBackend",
    "ConfigResult",
    "Connection",
    "Defaults",
    "EnvBackend",
    "KeyringBackend",
    "PingResult",
    "WalletBackend",
    "WiseQLConfig",
    "get_backend",
    "load_active_config",
    "load_config",
    "open_connection",
    "ping",
]
