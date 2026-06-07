"""Config layering + connection model tests (S2.1).

All DB-independent and Keychain-free: the auth tests use the ``env`` backend
with an injected mapping, so the real macOS Keychain is never touched.
"""

from pathlib import Path

import pytest

from wiseql.config import EnvBackend, get_backend, load_config
from wiseql.config.model import Connection

GLOBAL = """\
[connections.oracle_dev]
driver  = "oracle"
host    = "localhost"
port    = 1521
service = "FREEPDB1"
user    = "wiseql"
auth    = "env"

[defaults]
connection = "oracle_dev"
"""


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_global_connection(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", GLOBAL)
    result = load_config(global_path=g, project_path=tmp_path / "missing.toml")
    assert result.ok
    conn = result.config.connections["oracle_dev"]
    assert conn.target == "localhost:1521/FREEPDB1"
    assert result.config.defaults.connection == "oracle_dev"


def test_missing_files_are_not_errors(tmp_path: Path) -> None:
    result = load_config(
        global_path=tmp_path / "nope.toml", project_path=tmp_path / "nope2.toml"
    )
    assert result.ok
    assert result.config.connections == {}
    assert result.sources == []


def test_project_overrides_global_field_level(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", GLOBAL)
    project = _write(
        tmp_path,
        "project.toml",
        '[connections.oracle_dev]\nuser = "app_ro"\n',
    )
    result = load_config(global_path=g, project_path=project)
    conn = result.config.connections["oracle_dev"]
    # project changed only the user; host/service inherited from global
    assert conn.user == "app_ro"
    assert conn.host == "localhost"
    assert conn.service == "FREEPDB1"
    assert {p.name for p in result.sources} == {"config.toml", "project.toml"}


def test_flag_overrides_win(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", GLOBAL)
    result = load_config(
        global_path=g,
        project_path=tmp_path / "x.toml",
        overrides={"defaults": {"connection": "other"}},
    )
    assert result.config.defaults.connection == "other"


def test_unknown_connection_field_is_error(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", '[connections.c]\nhsot = "x"\n')
    result = load_config(global_path=g, project_path=tmp_path / "x.toml")
    assert not result.ok
    assert any("connection 'c'" in e and "hsot" in e for e in result.errors)


def test_malformed_toml_is_reported(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", "this is = = not toml")
    result = load_config(global_path=g, project_path=tmp_path / "x.toml")
    assert not result.ok
    assert any("invalid TOML" in e for e in result.errors)


def test_unrelated_top_level_keys_ignored(tmp_path: Path) -> None:
    # project.toml will later carry a [project] table — must not break loading.
    g = _write(
        tmp_path,
        "config.toml",
        '[project]\nname = "demo"\n\n[connections.c]\nhost = "h"\nservice = "s"\n',
    )
    result = load_config(global_path=g, project_path=tmp_path / "x.toml")
    assert result.ok
    assert result.config.connections["c"].host == "h"


def test_resolve_name_prefers_explicit_then_default(tmp_path: Path) -> None:
    g = _write(tmp_path, "config.toml", GLOBAL)
    config = load_config(global_path=g, project_path=tmp_path / "x.toml").config
    assert config.resolve_name("explicit") == "explicit"
    assert config.resolve_name(None) == "oracle_dev"


# --- auth backend seam (Keychain-free) --------------------------------------


def test_env_backend_reads_injected_var() -> None:
    conn = Connection(auth="env", user="wiseql")
    backend = get_backend(conn, environ={"WISEQL_ORACLE_DEV_PASSWORD": "secret"})
    assert isinstance(backend, EnvBackend)
    assert backend.get_password("oracle_dev", conn) == "secret"
    assert backend.get_password("missing", conn) is None


def test_env_backend_var_name() -> None:
    assert EnvBackend().var_name("oracle_dev") == "WISEQL_ORACLE_DEV_PASSWORD"


def test_wallet_backend_holds_no_secret() -> None:
    conn = Connection(auth="wallet")
    backend = get_backend(conn)
    assert backend.get_password("c", conn) is None


def test_env_backend_cannot_store() -> None:
    with pytest.raises(NotImplementedError):
        EnvBackend().set_password("c", Connection(auth="env"), "pw")


def test_keyring_backend_roundtrip(monkeypatch) -> None:
    """The default backend's set→get round-trip, with a dict-backed fake
    keyring so the real macOS Keychain is never touched. Guards the one thing
    that could break: service/username key consistency between set and get."""
    import sys
    import types

    from wiseql.config.auth import KEYRING_SERVICE, KeyringBackend

    store: dict[tuple[str, str], str] = {}
    fake = types.ModuleType("keyring")
    fake.get_password = lambda service, user: store.get((service, user))
    fake.set_password = lambda service, user, pw: store.__setitem__((service, user), pw)
    monkeypatch.setitem(sys.modules, "keyring", fake)

    conn = Connection(auth="keyring", user="wiseql")
    backend = KeyringBackend()
    assert backend.get_password("oracle_dev", conn) is None  # nothing stored yet
    backend.set_password("oracle_dev", conn, "s3cret")
    assert backend.get_password("oracle_dev", conn) == "s3cret"
    # stored under (service, connection-name) — not the DB user
    assert store == {(KEYRING_SERVICE, "oracle_dev"): "s3cret"}
