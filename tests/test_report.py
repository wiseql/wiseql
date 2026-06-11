"""Run report tests (S4.2). Offline.

Gate: a real ``datetime`` and a ``None`` (exactly what Oracle returns — dates as
datetime, NULLs as None) survive write → load without the encoder throwing.
"""

from datetime import datetime
from pathlib import Path

from wiseql.config import WiseQLConfig
from wiseql.engine import run_recipe
from wiseql.engine.execute import AssertionOutcome, RunResult, StepRun
from wiseql.recipes import load_recipe
from wiseql.report import (
    list_reports,
    load_report,
    report_info,
    report_to_runresult,
    to_report,
    write_report,
)


def _result() -> RunResult:
    step = StepRun(
        "orders", "db", "oracle_dev", True,
        columns=["ORDER_ID", "ORDER_DATE", "CUSTOMER_ID"],
        sample=[(1, datetime(2026, 5, 2), 7), (2, datetime(2026, 5, 3), None)],
        row_count=2, elapsed_ms=5.0, on_fail="report_samples",
        assertions=[
            AssertionOutcome(
                "no_nulls[customer_id]", False, "1 row(s) with NULL",
                ["ORDER_ID", "ORDER_DATE", "CUSTOMER_ID"], [(2, datetime(2026, 5, 3), None)],
            )
        ],
    )
    return RunResult(ok=False, steps=[step], terminals=["orders"], elapsed_ms=6.0)


def test_roundtrip_survives_datetime_and_null(tmp_path: Path) -> None:
    path = write_report(
        tmp_path / "runs", _result(), "orphan-returns", {"run_date": "2026-01-01"},
        datetime(2026, 6, 8, 12, 0, 0),
    )
    assert path.exists()
    report = load_report(path)  # must not raise on datetime / None
    assert report["recipe"] == "orphan-returns"
    assert report["ok"] is False
    sample = report["steps"][0]["sample"]
    assert sample[0][1] == "2026-05-02 00:00:00"  # datetime → ISO string
    assert sample[1][2] is None  # NULL → JSON null
    assert report["steps"][0]["assertions"][0]["passed"] is False


def test_list_reports_newest_first(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    write_report(runs, _result(), "r", {}, datetime(2026, 6, 8, 12, 0, 0))
    write_report(runs, _result(), "r", {}, datetime(2026, 6, 8, 12, 0, 1))
    reports = list_reports(runs)
    assert len(reports) == 2
    assert reports[0] > reports[1]  # newest (later timestamp) first


def test_report_info_summary(tmp_path: Path) -> None:
    path = write_report(tmp_path / "runs", _result(), "orphan-returns", {}, datetime(2026, 6, 8, 12, 0, 0))
    info = report_info(path)
    assert info.recipe == "orphan-returns"
    assert info.ok is False
    assert info.step_count == 1


def test_report_to_runresult_rebuilds_for_viewer(tmp_path: Path) -> None:
    path = write_report(tmp_path / "runs", _result(), "r", {}, datetime(2026, 6, 8, 12, 0, 0))
    rr = report_to_runresult(load_report(path))
    assert rr.ok is False
    assert rr.step("orders").row_count == 2
    assert rr.step("orders").assert_failed
    assert rr.step("orders").assertions[0].samples[0][2] is None


def test_trim_report_for_ai_drops_samples_keeps_diagnostics() -> None:
    from wiseql.report import trim_report_for_ai

    report = to_report(_result(), "orphan-returns", {"run_date": "2026-01-01"}, datetime(2026, 6, 8, 12, 0, 0))
    trimmed = trim_report_for_ai(report)
    step = trimmed["steps"][0]
    assert "sample" not in step  # bulky output rows dropped
    assert step["columns"] and step["row_count"] == 2  # diagnostics kept
    a = step["assertions"][0]
    assert a["check"] and a["passed"] is False and a["detail"]  # assertion kept
    assert len(a["samples"]) <= 3  # offending rows capped
    assert trimmed["recipe"] == "orphan-returns" and trimmed["ok"] is False


def test_run_recipe_writes_report_even_when_run_fails(tmp_path: Path) -> None:
    # A db step with an unconfigured connection fails — but the run still reached
    # execution, so a report is written (the cron use-case: failures recorded).
    recipe = tmp_path / "r.toml"
    recipe.write_text(
        '[recipe]\nname = "r"\n[steps.s]\nsource = "ghost"\nsql = "SELECT 1 FROM dual"\n',
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    result = run_recipe(load_recipe(recipe), WiseQLConfig(), runs_dir=runs)
    assert result.ok is False
    assert result.report_path is not None
    assert len(list_reports(runs)) == 1
