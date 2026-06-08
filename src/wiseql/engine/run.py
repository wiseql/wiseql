"""Single-step execution (S2.3): run one database step and return its rows.

This is the narrow first slice of the executor — one ``source`` step, straight
to the database, read-only-guarded. Multi-step DAG piping through DuckDB is
Sprint 3; this module is what it will build on.

``oracledb`` is imported lazily (thin mode, no Instant Client). Nothing here
raises for operational problems — failures come back as ``StepResult(ok=False)``
with the reason in ``error`` — because the callers are a CLI and a TUI that
should report, not crash.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from wiseql.config import open_connection
from wiseql.config.model import Connection
from wiseql.engine.guard import read_only_violation

# Safety cap: fetch at most this many rows for a single-step view, so a stray
# unfiltered query can't pull an entire table into memory.
DEFAULT_MAX_ROWS = 1000


@dataclass
class StepResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0  # rows returned (after the cap)
    truncated: bool = False  # True if more rows existed beyond the cap
    elapsed_ms: float = 0.0
    error: str = ""


def _fail(msg: str, started: float | None = None) -> StepResult:
    return StepResult(ok=False, elapsed_ms=_ms(started) if started else 0.0, error=msg)


def run_step(
    conn_name: str,
    conn: Connection,
    sql: str,
    *,
    params: dict | None = None,
    environ=None,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> StepResult:
    """Execute one read-only SQL statement against ``conn`` and return its rows."""
    violation = read_only_violation(sql)
    if violation:
        return _fail(f"read-only guard: {violation}")

    started = time.perf_counter()
    try:
        connection = open_connection(conn_name, conn, environ=environ)
    except Exception as exc:  # noqa: BLE001 — driver missing / connect failure
        return _fail(str(exc).strip(), started)

    try:
        with connection.cursor() as cur:
            cur.execute(sql, params or {})
            columns = [d[0] for d in cur.description]
            # Fetch one past the cap so we can tell whether more existed.
            fetched = cur.fetchmany(max_rows + 1)
    except Exception as exc:  # noqa: BLE001 — surface any driver/DB error verbatim
        return _fail(str(exc).strip(), started)
    finally:
        connection.close()

    truncated = len(fetched) > max_rows
    rows = [tuple(r) for r in fetched[:max_rows]]
    return StepResult(
        ok=True,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        elapsed_ms=_ms(started),
    )


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
