"""Run reports (S4.2): persist a RunResult to JSON and read it back.

Reports land in ``runs/<timestamp>/report.json``. Step samples carry raw
database values — ``datetime`` (and defensively ``Decimal``) — which aren't
JSON-native, so a custom encoder maps them to strings. ``report_to_runresult``
rebuilds a ``RunResult`` so the TUI report viewer reuses the live run-view and
step-detail rendering.

Report writing is invoked from ``run_recipe`` (one place), so CLI and TUI runs
both produce reports.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from wiseql.engine.execute import AssertionOutcome, RunResult, StepRun

REPORT_NAME = "report.json"


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(sep=" ")
    if isinstance(obj, Decimal):
        return str(obj)
    raise TypeError(f"not JSON-serialisable: {type(obj).__name__}")


def _assert_dict(a: AssertionOutcome) -> dict:
    return {
        "check": a.check,
        "passed": a.passed,
        "detail": a.detail,
        "sample_columns": a.sample_columns,
        "samples": [list(r) for r in a.samples],
    }


def _step_dict(s: StepRun) -> dict:
    return {
        "name": s.name,
        "kind": s.kind,
        "source": s.source,
        "ok": s.ok,
        "row_count": s.row_count,
        "elapsed_ms": s.elapsed_ms,
        "error": s.error,
        "on_fail": s.on_fail,
        "columns": s.columns,
        "sample": [list(r) for r in s.sample],
        "assertions": [_assert_dict(a) for a in s.assertions],
    }


def to_report(result: RunResult, recipe_name: str, params: dict, started_at: datetime) -> dict:
    return {
        "recipe": recipe_name,
        "started_at": started_at.isoformat(sep=" ", timespec="seconds"),
        "params": params or {},
        "ok": result.ok,
        "elapsed_ms": result.elapsed_ms,
        "error": result.error,
        "terminals": result.terminals,
        "steps": [_step_dict(s) for s in result.steps],
    }


def write_report(
    runs_dir: Path, result: RunResult, recipe_name: str, params: dict, started_at: datetime
) -> Path:
    """Write ``runs/<timestamp>/report.json``; sub-second stamp avoids collisions."""
    runs_dir = Path(runs_dir)
    stamp = started_at.strftime("%Y%m%dT%H%M%S_%f")
    run_dir = runs_dir / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / REPORT_NAME
    payload = to_report(result, recipe_name, params, started_at)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return path


def list_reports(runs_dir: Path) -> list[Path]:
    """All run report files, newest first (timestamped dir names sort lexically)."""
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    return sorted(runs_dir.glob(f"*/{REPORT_NAME}"), reverse=True)


def load_report(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


@dataclass
class ReportInfo:
    """Summary row for the report-history list."""

    path: Path
    recipe: str
    started_at: str
    ok: bool
    step_count: int


def report_info(path: Path) -> ReportInfo:
    r = load_report(path)
    return ReportInfo(
        path=path,
        recipe=r.get("recipe", "?"),
        started_at=r.get("started_at", "?"),
        ok=bool(r.get("ok")),
        step_count=len(r.get("steps", [])),
    )


def report_to_runresult(report: dict) -> RunResult:
    """Rebuild a RunResult from a loaded report, for the TUI viewer to render."""
    steps = [
        StepRun(
            name=sd["name"],
            kind=sd["kind"],
            source=sd["source"],
            ok=sd["ok"],
            columns=sd.get("columns", []),
            sample=[tuple(r) for r in sd.get("sample", [])],
            row_count=sd.get("row_count", 0),
            elapsed_ms=sd.get("elapsed_ms", 0.0),
            error=sd.get("error", ""),
            on_fail=sd.get("on_fail", "stop"),
            assertions=[
                AssertionOutcome(
                    check=a["check"],
                    passed=a["passed"],
                    detail=a.get("detail", ""),
                    sample_columns=a.get("sample_columns", []),
                    samples=[tuple(r) for r in a.get("samples", [])],
                )
                for a in sd.get("assertions", [])
            ],
        )
        for sd in report.get("steps", [])
    ]
    return RunResult(
        ok=bool(report.get("ok")),
        steps=steps,
        terminals=report.get("terminals", []),
        elapsed_ms=report.get("elapsed_ms", 0.0),
        error=report.get("error", ""),
    )
