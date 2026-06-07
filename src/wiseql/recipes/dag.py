"""DAG resolution: execution order, cycle detection, parallel waves."""

from __future__ import annotations

from dataclasses import dataclass, field

from wiseql.recipes.loader import Issue
from wiseql.recipes.model import Recipe


@dataclass
class ExecutionPlan:
    """Topologically ordered plan.

    ``waves`` groups steps that have no dependencies on each other —
    they could run in parallel; the TUI renders them as plan levels.
    """

    waves: list[list[str]] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def order(self) -> list[str]:
        return [s for wave in self.waves for s in wave]

    @property
    def ok(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)


def build_plan(recipe: Recipe) -> ExecutionPlan:
    """Kahn's algorithm in waves; reports cycles as errors."""
    plan = ExecutionPlan()

    deps: dict[str, set[str]] = {
        name: {ref for ref in step.inputs if ref in recipe.steps}
        for name, step in recipe.steps.items()
    }

    remaining = dict(deps)
    while remaining:
        ready = sorted(name for name, d in remaining.items() if not d)
        if not ready:
            cycle = ", ".join(sorted(remaining))
            plan.issues.append(
                Issue("error", "steps", f"dependency cycle involving: {cycle}")
            )
            return plan
        plan.waves.append(ready)
        for done in ready:
            del remaining[done]
        for d in remaining.values():
            d.difference_update(ready)

    # terminal steps (consumed by nobody) are the recipe's results
    consumed: set[str] = set()
    for step in recipe.steps.values():
        consumed.update(step.inputs)
    terminals = [name for name in recipe.steps if name not in consumed]
    if len(terminals) > 1 and len(recipe.steps) > 1:
        plan.issues.append(
            Issue(
                "warning",
                "steps",
                "multiple terminal steps (results): " + ", ".join(sorted(terminals)),
            )
        )

    return plan


def describe_step(recipe: Recipe, name: str) -> str:
    """One-line step description for plans and the TUI tree."""
    step = recipe.steps[name]
    if step.is_local:
        kind = f"local (DuckDB) ← {', '.join(step.inputs)}"
    else:
        kind = f"db ({step.source})"
    if step.assert_ is not None:
        checks = step.assert_.model_dump(exclude_none=True, exclude_defaults=True)
        checks.pop("on_fail", None)
        if checks:
            kind += f"  ✓ {', '.join(checks)}"
    return kind
