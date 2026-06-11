"""Run reports (S4.2) + run manifest/checkpoints (S5.1).

A run lives in its own directory ``runs/<timestamp>/`` holding three things:

- ``report.json`` — the full per-step result, written **at the end** of a run.
  Step samples carry raw database values (``datetime``, defensively
  ``Decimal``) that aren't JSON-native, so a custom encoder maps them to
  strings. ``report_to_runresult`` rebuilds a ``RunResult`` so the TUI report
  viewer reuses the live run-view rendering.
- ``run.json`` — a small manifest written **at the start** (status
  ``running``) and flipped to ``ok``/``failed`` at the end. It exists so an
  *interrupted* run (killed before the report is written) is still
  discoverable, and it records per-step resolved-SQL fingerprints + params so a
  resume can refuse if the recipe drifted underneath it (S5.1).
- ``checkpoints/<step>.parquet`` — each fully-successful step's output, written
  by the executor so a resume can skip it.

Report and manifest writing are invoked from ``run_recipe`` (one place), so CLI
and TUI runs both produce them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from wiseql.engine.execute import AssertionOutcome, RunResult, StepRun

REPORT_NAME = "report.json"
MANIFEST_NAME = "run.json"
CHECKPOINTS_DIRNAME = "checkpoints"


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
        "restored": s.restored,
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


def run_dir_for(runs_dir: Path, started_at: datetime) -> Path:
    """Create and return ``runs/<timestamp>/`` (sub-second stamp avoids collisions)."""
    stamp = started_at.strftime("%Y%m%dT%H%M%S_%f")
    run_dir = Path(runs_dir) / stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def checkpoints_dir(run_dir: Path) -> Path:
    """Create and return the ``checkpoints/`` subdir of a run dir."""
    d = Path(run_dir) / CHECKPOINTS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_report_in(
    run_dir: Path, result: RunResult, recipe_name: str, params: dict, started_at: datetime
) -> Path:
    """Write ``<run_dir>/report.json`` into an already-created run dir."""
    path = Path(run_dir) / REPORT_NAME
    payload = to_report(result, recipe_name, params, started_at)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")
    return path


def write_report(
    runs_dir: Path, result: RunResult, recipe_name: str, params: dict, started_at: datetime
) -> Path:
    """Write ``runs/<timestamp>/report.json`` (creates the run dir)."""
    return write_report_in(run_dir_for(runs_dir, started_at), result, recipe_name, params, started_at)


# --- run manifest + checkpoint discovery (S5.1) -----------------------------


def sql_fingerprint(resolved_sql: dict[str, str]) -> dict[str, str]:
    """Per-step SHA-256 of resolved SQL — the provenance a resume validates against."""
    return {
        name: hashlib.sha256((sql or "").encode("utf-8")).hexdigest()
        for name, sql in resolved_sql.items()
    }


def write_manifest(
    run_dir: Path,
    *,
    recipe_name: str,
    params: dict,
    step_sql: dict[str, str],
    status: str,
    started_at: datetime,
) -> Path:
    """Write ``<run_dir>/run.json`` (status ``running``|``ok``|``failed``)."""
    payload = {
        "recipe": recipe_name,
        "started_at": started_at.isoformat(sep=" ", timespec="seconds"),
        "params": params or {},
        "status": status,
        "step_sql": step_sql,
    }
    path = Path(run_dir) / MANIFEST_NAME
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read_manifest(run_dir: Path) -> dict | None:
    path = Path(run_dir) / MANIFEST_NAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def set_manifest_status(run_dir: Path, status: str) -> None:
    """Flip a manifest's status in place (best-effort; no-op if absent)."""
    manifest = read_manifest(run_dir)
    if manifest is None:
        return
    manifest["status"] = status
    (Path(run_dir) / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def checkpoint_steps(run_dir: Path) -> set[str]:
    """Step names that have a complete checkpoint parquet (``.tmp`` files ignored)."""
    cdir = Path(run_dir) / CHECKPOINTS_DIRNAME
    if not cdir.is_dir():
        return set()
    return {p.stem for p in cdir.glob("*.parquet")}


@dataclass
class ResumableRun:
    """A run dir that can be resumed: interrupted/failed with at least one checkpoint."""

    path: Path
    recipe: str
    started_at: str
    status: str
    done_steps: int


def list_resumable_runs(runs_dir: Path, recipe_name: str | None = None) -> list[ResumableRun]:
    """Run dirs resumable now, newest first.

    Resumable = manifest status ``running`` (killed mid-run, no report) or
    ``failed`` (a step errored / stopped), **and** at least one checkpoint to
    skip **and** at least one step still to run. A clean ``ok`` run — or a
    failed run where every step happens to be checkpointed (e.g. a terminal
    ``report_samples`` failure) — has nothing left to execute. Optionally
    filtered to one recipe.
    """
    runs_dir = Path(runs_dir)
    if not runs_dir.is_dir():
        return []
    out: list[ResumableRun] = []
    for d in sorted((p for p in runs_dir.iterdir() if p.is_dir()), reverse=True):
        manifest = read_manifest(d)
        if manifest is None or manifest.get("status") not in ("running", "failed"):
            continue
        done = checkpoint_steps(d)
        total = len(manifest.get("step_sql") or {})
        if not done or total == 0 or len(done) >= total:
            continue
        if recipe_name is not None and manifest.get("recipe") != recipe_name:
            continue
        out.append(
            ResumableRun(
                path=d,
                recipe=manifest.get("recipe", "?"),
                started_at=manifest.get("started_at", "?"),
                status=manifest.get("status", "?"),
                done_steps=len(done),
            )
        )
    return out


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


# Offending-row samples kept per assertion when feeding a report to the AI.
AI_SAMPLE_ROWS = 3


def trim_report_for_ai(report: dict) -> dict:
    """A compact copy of a report for an AI prompt.

    Drops the bulky per-step output ``sample`` rows (normal output is noise for
    an explanation) but keeps the diagnostic fields — step status, row counts,
    errors, column lists, and a *few* offending assertion rows (those are what
    explain a failure). A local model's context window is small; this keeps the
    prompt focused and from overflowing.
    """
    steps = []
    for s in report.get("steps", []):
        steps.append({
            "name": s.get("name"),
            "kind": s.get("kind"),
            "source": s.get("source"),
            "ok": s.get("ok"),
            "restored": s.get("restored", False),
            "row_count": s.get("row_count"),
            "elapsed_ms": s.get("elapsed_ms"),
            "error": s.get("error", ""),
            "on_fail": s.get("on_fail", "stop"),
            "columns": s.get("columns", []),
            "assertions": [
                {
                    "check": a.get("check"),
                    "passed": a.get("passed"),
                    "detail": a.get("detail", ""),
                    "sample_columns": a.get("sample_columns", []),
                    "samples": [list(r) for r in a.get("samples", [])][:AI_SAMPLE_ROWS],
                }
                for a in s.get("assertions", [])
            ],
        })
    return {
        "recipe": report.get("recipe"),
        "ok": report.get("ok"),
        "params": report.get("params", {}),
        "error": report.get("error", ""),
        "terminals": report.get("terminals", []),
        "steps": steps,
    }


def report_to_runresult(report: dict) -> RunResult:
    """Rebuild a RunResult from a loaded report, for the TUI viewer to render."""
    steps = [
        StepRun(
            name=sd["name"],
            kind=sd["kind"],
            source=sd["source"],
            ok=sd["ok"],
            restored=sd.get("restored", False),
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
