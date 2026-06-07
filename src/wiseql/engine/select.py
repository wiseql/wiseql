"""Choosing which step to run for single-step execution (S2.3).

S2.3 runs exactly one *database* step. Local steps (``inputs``) run in DuckDB
over upstream outputs — that's Sprint 3 — so they're rejected here with a clear
message rather than a confusing failure.
"""

from __future__ import annotations

from dataclasses import dataclass

from wiseql.recipes import LoadResult


@dataclass(frozen=True)
class StepChoice:
    name: str
    sql: str
    source: str  # connection name


def choose_step(result: LoadResult, step: str | None = None) -> tuple[StepChoice | None, str | None]:
    """Return (choice, None) on success or (None, reason) on failure."""
    recipe = result.recipe
    if recipe is None:
        return None, "recipe is invalid"

    if step is not None:
        s = recipe.steps.get(step)
        if s is None:
            return None, f"no step named '{step}' in this recipe"
        if not s.source:
            return None, (
                f"step '{step}' is a local step (DuckDB over upstream outputs) — "
                "multi-step execution arrives in Sprint 3"
            )
        return StepChoice(step, result.resolved_sql.get(step, ""), s.source), None

    db_steps = [(n, s) for n, s in recipe.steps.items() if s.source]
    if not db_steps:
        return None, "recipe has no database step to run"
    if len(db_steps) > 1:
        names = ", ".join(n for n, _ in db_steps)
        return None, f"recipe has multiple database steps ({names}); choose one with --step"
    name, _ = db_steps[0]
    return StepChoice(name, result.resolved_sql.get(name, ""), db_steps[0][1].source), None
