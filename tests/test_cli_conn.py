"""CLI ``conn`` tests (S2.1).

Config is pointed at a temp file via ``$WISEQL_CONFIG`` and the project layer
is neutralized by running in a temp cwd — so these never read the developer's
real config and never contact a database (``conn list`` is metadata-only).
"""

from pathlib import Path

from typer.testing import CliRunner

from wiseql.cli import app

runner = CliRunner()

CONFIG = """\
[connections.oracle_dev]
host    = "localhost"
service = "FREEPDB1"
user    = "wiseql"
auth    = "env"

[connections.wallet_conn]
auth = "wallet"
dsn  = "corp_tns"

[defaults]
connection = "oracle_dev"
"""


def _env(tmp_path: Path) -> dict[str, str]:
    cfg = tmp_path / "config.toml"
    cfg.write_text(CONFIG, encoding="utf-8")
    # Widen Rich's output so table columns don't wrap under the test pipe.
    return {"WISEQL_CONFIG": str(cfg), "COLUMNS": "200"}


def test_conn_list_shows_connections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # no project.toml here
    result = runner.invoke(app, ["conn", "list"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "oracle_dev" in result.output
    assert "localhost:1521/FREEPDB1" in result.output
    assert "(default)" in result.output
    assert "env:WISEQL_ORACLE_DEV_PASSWORD" in result.output


def test_conn_list_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "empty.toml"
    empty.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["conn", "list"], env={"WISEQL_CONFIG": str(empty)})
    assert "No connections configured" in result.output


def test_conn_login_env_backend_explains(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["conn", "login", "oracle_dev"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "WISEQL_ORACLE_DEV_PASSWORD" in result.output


def test_conn_login_wallet_explains(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["conn", "login", "wallet_conn"], env=_env(tmp_path))
    assert result.exit_code == 0
    assert "wallet" in result.output.lower()


def test_conn_login_unknown(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["conn", "login", "nope"], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "unknown connection" in result.output


def test_conn_test_unknown_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["conn", "test", "nope"], env=_env(tmp_path))
    assert result.exit_code == 1
    assert "unknown connection" in result.output
