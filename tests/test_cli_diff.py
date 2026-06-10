"""CLI ``diff`` tests (S5.2). Offline — fabricates two run reports on disk."""

from datetime import datetime
from pathlib import Path

from typer.testing import CliRunner

from wiseql.cli import app
from wiseql.engine.execute import RunResult, StepRun
from wiseql.project import scaffold_project
from wiseql.report import write_report

runner = CliRunner()


def _write_run(runs_dir: Path, orphans: int, when: datetime) -> Path:
    result = RunResult(
        ok=False,
        steps=[
            StepRun("orders", "db", "oracle_dev", True, row_count=127, elapsed_ms=5.0),
            StepRun("orphans", "local", None, True, row_count=orphans, elapsed_ms=2.0),
        ],
        terminals=["orphans"], elapsed_ms=8.0,
    )
    return write_report(runs_dir, result, "orphan-returns", {}, when)


def test_diff_by_path_shows_row_delta(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    a = _write_run(runs, 3, datetime(2026, 6, 9, 8, 0, 0))
    b = _write_run(runs, 4, datetime(2026, 6, 10, 8, 0, 0))
    # pass the run directories (parents of report.json)
    result = runner.invoke(app, ["diff", str(a.parent), str(b.parent)], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "orphan-returns" in result.output
    assert "+1" in result.output
    assert "1 step(s) changed" in result.output


def test_diff_by_run_id_within_project(tmp_path: Path) -> None:
    proj = tmp_path / "demo"
    scaffold_project(proj, "demo")
    a = _write_run(proj / "runs", 3, datetime(2026, 6, 9, 8, 0, 0))
    b = _write_run(proj / "runs", 4, datetime(2026, 6, 10, 8, 0, 0))
    # run ids are the run-dir names; resolved under the project found from cwd
    import os

    cwd = os.getcwd()
    try:
        os.chdir(proj)
        result = runner.invoke(app, ["diff", a.parent.name, b.parent.name], env={"COLUMNS": "200"})
    finally:
        os.chdir(cwd)
    assert result.exit_code == 0, result.output
    assert "+1" in result.output


def test_diff_no_such_run_exits_1(tmp_path: Path) -> None:
    proj = tmp_path / "demo"
    scaffold_project(proj, "demo")
    import os

    cwd = os.getcwd()
    try:
        os.chdir(proj)
        result = runner.invoke(app, ["diff", "nope-a", "nope-b"], env={"COLUMNS": "200"})
    finally:
        os.chdir(cwd)
    assert result.exit_code == 1
    assert "no such run" in result.output
