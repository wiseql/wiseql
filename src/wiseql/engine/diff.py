"""Run diffing (S5.2): compare two run reports, step by step.

A diff answers "what changed between two runs of (usually) the same recipe?"
The spine is the **row-count delta** per step — the signal that moves when the
data changes even though the recipe and its assertions don't (e.g. one extra
orphan return: ``orphans 3 → 4``, verdict still failed, assertion still ✗). On
top of that it surfaces ok-status changes, assertion changes, steps present in
only one run, and (informational) timing.

Pure and offline: it operates on loaded ``report.json`` dicts, never the DB.
Convention: ``a`` is the *older* run, ``b`` the *newer*, so deltas read
newer − older (an added row is ``+1``). Recipe/param mismatches are *warned*,
never refused — "yesterday vs today" (different params) and even cross-recipe
diffs are legitimate, if coarse.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssertDiff:
    check: str
    a_passed: bool | None  # None → the check is absent in that run
    b_passed: bool | None
    a_detail: str = ""
    b_detail: str = ""

    @property
    def changed(self) -> bool:
        return self.a_passed != self.b_passed or self.a_detail != self.b_detail


@dataclass
class StepDiff:
    name: str
    in_a: bool
    in_b: bool
    a_rows: int | None = None
    b_rows: int | None = None
    a_ok: bool | None = None
    b_ok: bool | None = None
    a_ms: float | None = None
    b_ms: float | None = None
    assertions: list[AssertDiff] = field(default_factory=list)

    @property
    def row_delta(self) -> int | None:
        if self.a_rows is None or self.b_rows is None:
            return None
        return self.b_rows - self.a_rows

    @property
    def ok_changed(self) -> bool:
        return self.in_a and self.in_b and self.a_ok != self.b_ok

    @property
    def assert_changed(self) -> bool:
        return any(a.changed for a in self.assertions)

    @property
    def changed(self) -> bool:
        if not (self.in_a and self.in_b):
            return True  # step added or removed between the two runs
        # Timing is informational only — a restored (resumed) step has ~0 ms and
        # would otherwise read as a regression. Row count / ok / assertions move.
        return bool(self.row_delta) or self.ok_changed or self.assert_changed


@dataclass
class RunDiff:
    a_label: str
    b_label: str
    recipe_a: str
    recipe_b: str
    a_ok: bool
    b_ok: bool
    params_a: dict = field(default_factory=dict)
    params_b: dict = field(default_factory=dict)
    steps: list[StepDiff] = field(default_factory=list)

    @property
    def same_recipe(self) -> bool:
        return self.recipe_a == self.recipe_b

    @property
    def params_differ(self) -> bool:
        return self.params_a != self.params_b

    @property
    def verdict_changed(self) -> bool:
        return self.a_ok != self.b_ok

    @property
    def changed_steps(self) -> list[StepDiff]:
        return [s for s in self.steps if s.changed]


def _ordered_names(a_steps: dict, b_steps: dict) -> list[str]:
    """B's step order first (the newer run), then any A-only steps, in A's order."""
    order = list(b_steps.keys())
    order += [name for name in a_steps if name not in b_steps]
    return order


def _assert_diffs(a_step: dict | None, b_step: dict | None) -> list[AssertDiff]:
    a_by = {x["check"]: x for x in (a_step or {}).get("assertions", [])}
    b_by = {x["check"]: x for x in (b_step or {}).get("assertions", [])}
    order = list(b_by.keys()) + [c for c in a_by if c not in b_by]
    out: list[AssertDiff] = []
    for check in order:
        a = a_by.get(check)
        b = b_by.get(check)
        out.append(
            AssertDiff(
                check=check,
                a_passed=a["passed"] if a else None,
                b_passed=b["passed"] if b else None,
                a_detail=(a or {}).get("detail", ""),
                b_detail=(b or {}).get("detail", ""),
            )
        )
    return out


def diff_runs(report_a: dict, report_b: dict, *, a_label: str = "a", b_label: str = "b") -> RunDiff:
    """Compare two loaded run reports (``a`` older, ``b`` newer)."""
    a_steps = {s["name"]: s for s in report_a.get("steps", [])}
    b_steps = {s["name"]: s for s in report_b.get("steps", [])}

    steps: list[StepDiff] = []
    for name in _ordered_names(a_steps, b_steps):
        a = a_steps.get(name)
        b = b_steps.get(name)
        steps.append(
            StepDiff(
                name=name,
                in_a=a is not None,
                in_b=b is not None,
                a_rows=a.get("row_count") if a else None,
                b_rows=b.get("row_count") if b else None,
                a_ok=a.get("ok") if a else None,
                b_ok=b.get("ok") if b else None,
                a_ms=a.get("elapsed_ms") if a else None,
                b_ms=b.get("elapsed_ms") if b else None,
                assertions=_assert_diffs(a, b),
            )
        )

    return RunDiff(
        a_label=a_label,
        b_label=b_label,
        recipe_a=report_a.get("recipe", "?"),
        recipe_b=report_b.get("recipe", "?"),
        a_ok=bool(report_a.get("ok")),
        b_ok=bool(report_b.get("ok")),
        params_a=report_a.get("params") or {},
        params_b=report_b.get("params") or {},
        steps=steps,
    )
