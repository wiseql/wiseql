"""Execution engine: run recipe steps against a database.

Sprint 2.3 covers single-step execution with a read-only guard; the multi-step
DAG executor (DuckDB piping, assertions) builds on this in Sprint 3.
"""

from wiseql.engine.execute import RunResult, StepRun, run_recipe
from wiseql.engine.guard import read_only_violation
from wiseql.engine.run import DEFAULT_MAX_ROWS, StepResult, run_step
from wiseql.engine.select import StepChoice, choose_step

__all__ = [
    "DEFAULT_MAX_ROWS",
    "RunResult",
    "StepChoice",
    "StepResult",
    "StepRun",
    "choose_step",
    "read_only_violation",
    "run_recipe",
    "run_step",
]
