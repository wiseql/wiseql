"""Run-diff tests (S5.2). Offline — operates on fabricated report dicts.

The spine is the row-count delta: when an extra orphan return appears, the
recipe and its assertions don't change (orphans still fails rows_max=0), so the
*only* moving signal is row_count 3 → 4. The primary gate asserts exactly that.
"""

from wiseql.engine import diff_runs


def _assert(check, passed, detail=""):
    return {"check": check, "passed": passed, "detail": detail, "sample_columns": [], "samples": []}


def _step(name, rows, *, ok=True, ms=1.0, asserts=None):
    return {
        "name": name, "kind": "local", "source": None, "ok": ok,
        "row_count": rows, "elapsed_ms": ms, "error": "", "on_fail": "stop",
        "columns": [], "sample": [], "assertions": asserts or [],
    }


def _report(recipe, ok, steps, params=None):
    return {"recipe": recipe, "ok": ok, "params": params or {}, "steps": steps}


def _orphans_report(n_orphans):
    return _report(
        "orphan-returns", False,
        [
            _step("orders", 127),
            _step("returns", 33),
            _step("orphans", n_orphans, asserts=[_assert("rows_max", False, f"{n_orphans} rows (max 0)")]),
        ],
    )


def test_row_delta_is_the_primary_signal() -> None:
    d = diff_runs(_orphans_report(3), _orphans_report(4), a_label="A", b_label="B")
    assert [s.name for s in d.changed_steps] == ["orphans"]  # only orphans moved
    orphans = next(s for s in d.steps if s.name == "orphans")
    assert orphans.row_delta == 1 and orphans.changed
    assert d.verdict_changed is False  # failed → failed
    # the assertion's pass/fail didn't change, but its detail (magnitude) did
    ad = orphans.assertions[0]
    assert ad.a_passed is False and ad.b_passed is False and ad.changed


def test_ok_status_change_is_flagged() -> None:
    a = _report("r", True, [_step("s", 5, ok=True)])
    b = _report("r", False, [_step("s", 0, ok=False)])
    d = diff_runs(a, b)
    s = d.steps[0]
    assert s.ok_changed and s.changed
    assert d.verdict_changed


def test_assertion_state_change_detected() -> None:
    a = _report("r", False, [_step("s", 5, asserts=[_assert("no_nulls[x]", False, "2 rows")])])
    b = _report("r", True, [_step("s", 5, asserts=[_assert("no_nulls[x]", True, "0 rows")])])
    d = diff_runs(a, b)
    s = d.steps[0]
    assert s.assert_changed and s.changed
    assert s.row_delta == 0  # rows same; the assertion is what moved


def test_step_added_and_removed() -> None:
    a = _report("r", True, [_step("only_a", 1), _step("shared", 2)])
    b = _report("r", True, [_step("shared", 2), _step("only_b", 3)])
    d = diff_runs(a, b)
    by = {s.name: s for s in d.steps}
    assert by["only_a"].in_a and not by["only_a"].in_b and by["only_a"].changed
    assert by["only_b"].in_b and not by["only_b"].in_a and by["only_b"].changed
    assert not by["shared"].changed  # identical


def test_identical_runs_have_no_changes() -> None:
    r = _orphans_report(3)
    d = diff_runs(r, r)
    assert d.changed_steps == []
    assert not d.verdict_changed


def test_recipe_and_param_mismatch_warns_not_refuses() -> None:
    a = _report("recipe-x", True, [_step("s", 1)], params={"run_date": "2026-06-01"})
    b = _report("recipe-y", True, [_step("s", 1)], params={"run_date": "2026-06-02"})
    d = diff_runs(a, b)  # must not raise
    assert d.same_recipe is False
    assert d.params_differ is True
    assert len(d.steps) == 1  # still produces a diff
