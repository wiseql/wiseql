"""Connecting to a database and testing reachability.

python-oracledb runs in **thin mode** (the default — no Oracle Instant Client
needed); the only live dependency is a reachable database. ``oracledb`` is
imported lazily so the rest of the config layer (and its tests) never require
the driver to be installed.

This module is intentionally small in Sprint 2: it backs ``wiseql conn test``.
The full step executor (Sprint 2.3 / Sprint 3) builds on the same connect path.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from wiseql.config.auth import get_backend
from wiseql.config.model import Connection


@dataclass(frozen=True)
class PingResult:
    """Outcome of a ``conn test``."""

    ok: bool
    elapsed_ms: float
    detail: str = ""  # server banner on success, error message on failure


# Session defaults applied to every WiseQL connection, so date/timestamp binds
# and outputs are unambiguous regardless of the server's NLS configuration.
_SESSION_SETUP = (
    "ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD'",
    "ALTER SESSION SET NLS_TIMESTAMP_FORMAT = 'YYYY-MM-DD HH24:MI:SS'",
)


def _dsn(conn: Connection) -> str:
    if conn.dsn:
        return conn.dsn
    if not (conn.host and conn.service):
        raise ValueError(
            "connection needs either 'dsn' or both 'host' and 'service'"
        )
    return f"{conn.host}:{conn.port}/{conn.service}"


def open_connection(conn_name: str, conn: Connection, *, environ=None):
    """Open a thin-mode Oracle connection with WiseQL's session defaults applied.

    The single connect path for the whole app — ``ping``, single-step ``run_step``,
    and the multi-step executor all go through here, so the read-only invariants
    (ISO date formats, and the caller's guard) can never drift between them.

    Raises ``RuntimeError`` if the driver is missing and propagates any
    driver/DB connection error; callers translate these into their result types.
    """
    try:
        import oracledb
    except ImportError as exc:
        raise RuntimeError("python-oracledb is not installed (run: make sync)") from exc

    password = get_backend(conn, environ=environ).get_password(conn_name, conn)
    connection = oracledb.connect(user=conn.user, password=password, dsn=_dsn(conn))
    with connection.cursor() as cur:
        for stmt in _SESSION_SETUP:
            cur.execute(stmt)
    return connection


def ping(conn_name: str, conn: Connection, *, environ=None) -> PingResult:
    """Connect (thin mode), run ``SELECT 1 FROM dual``, and report latency.

    Never raises: connection/driver problems come back as ``ok=False`` with the
    reason in ``detail`` — the caller is a CLI/TUI that should report, not crash.
    """
    start = time.perf_counter()
    try:
        connection = open_connection(conn_name, conn, environ=environ)
    except Exception as exc:  # noqa: BLE001 — surface any driver/DB error verbatim
        return PingResult(ok=False, elapsed_ms=_ms(start), detail=str(exc).strip())

    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1 FROM dual")
            cur.fetchone()
        banner = (connection.version or "").strip()
    except Exception as exc:  # noqa: BLE001
        return PingResult(ok=False, elapsed_ms=_ms(start), detail=str(exc).strip())
    finally:
        connection.close()

    return PingResult(ok=True, elapsed_ms=_ms(start), detail=f"Oracle {banner}")


def _ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)
