"""Data Explorer (S5.3): ad-hoc DuckDB SQL over a run's frozen checkpoints.

A run's ``checkpoints/<step>.parquet`` files are mounted as DuckDB **views**
named after each step, so a developer can run arbitrary read queries over the
exact intermediate data a run produced — ``GROUP BY``, joins across steps,
spot-checks — without re-running anything or reaching for an external tool.

Offline by construction: the data is frozen Parquet and the engine is an
in-memory DuckDB, so there is no Oracle (and no production DB) to mutate.
Mounting via views (not tables) keeps it lazy — large checkpoints aren't read
until a query touches them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXPLORER_ROWS = 500


def _ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sqlstr(value) -> str:
    return str(value).replace("'", "''")


@dataclass
class ExplorerResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)
    row_count: int = 0  # rows returned (after the display cap)
    truncated: bool = False  # more rows existed than the cap
    error: str = ""


@dataclass
class TableInfo:
    name: str
    row_count: int
    columns: list[str]


class CheckpointExplorer:
    """In-memory DuckDB with a run's checkpoints mounted as step-named views."""

    def __init__(self, run_dir: Path) -> None:
        import duckdb

        self.run_dir = Path(run_dir)
        self.duck = duckdb.connect()
        self.tables: list[str] = []
        cdir = self.run_dir / "checkpoints"
        if cdir.is_dir():
            for p in sorted(cdir.glob("*.parquet")):
                name = p.stem
                self.duck.execute(
                    f"CREATE VIEW {_ident(name)} AS SELECT * FROM read_parquet('{_sqlstr(p)}')"
                )
                self.tables.append(name)

    def table_info(self) -> list[TableInfo]:
        """Per-mounted-step name, row count, and columns — for the side panel."""
        out: list[TableInfo] = []
        for name in self.tables:
            ident = _ident(name)
            cols = [d[0] for d in self.duck.execute(f"SELECT * FROM {ident} LIMIT 0").description]
            n = self.duck.execute(f"SELECT COUNT(*) FROM {ident}").fetchone()[0]
            out.append(TableInfo(name=name, row_count=n, columns=cols))
        return out

    def query(self, sql: str, *, max_rows: int = DEFAULT_EXPLORER_ROWS) -> ExplorerResult:
        """Run a read query; capped, never raises — errors come back as text."""
        sql = (sql or "").strip().rstrip(";").strip()
        if not sql:
            return ExplorerResult(ok=False, error="empty query")
        try:
            cur = self.duck.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(max_rows + 1)
            truncated = len(fetched) > max_rows
            rows = fetched[:max_rows]
            return ExplorerResult(
                ok=True, columns=columns, rows=rows, row_count=len(rows), truncated=truncated
            )
        except Exception as exc:  # noqa: BLE001 — surface as text, don't crash the TUI
            return ExplorerResult(ok=False, error=str(exc).strip())

    def close(self) -> None:
        try:
            self.duck.close()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass
