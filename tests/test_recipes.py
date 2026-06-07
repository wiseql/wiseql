"""Recipe loader + DAG tests (S1.1 / S1.2)."""

from pathlib import Path

from wiseql.recipes import build_plan, load_recipe

EXAMPLES = Path(__file__).parent.parent / "examples"
BROKEN = Path(__file__).parent / "fixtures" / "broken"


# --- good recipes -----------------------------------------------------------

def test_all_examples_are_valid() -> None:
    for path in sorted(EXAMPLES.glob("*.toml")):
        result = load_recipe(path)
        assert result.ok, f"{path.name}: {[str(i) for i in result.errors]}"


def test_sql_file_is_resolved() -> None:
    result = load_recipe(EXAMPLES / "orphan-returns.toml")
    assert result.ok
    assert "FROM returns" in result.resolved_sql["returns"]


def test_param_recipe_has_no_warnings() -> None:
    result = load_recipe(EXAMPLES / "null-customers.toml")
    assert result.ok
    assert result.warnings == []


def test_plan_waves_orphan_returns() -> None:
    result = load_recipe(EXAMPLES / "orphan-returns.toml")
    assert result.recipe is not None
    plan = build_plan(result.recipe)
    assert plan.ok
    assert plan.waves == [["orders", "returns"], ["orphans"]]


# --- broken recipes ----------------------------------------------------------

def _errors_of(name: str) -> str:
    result = load_recipe(BROKEN / name)
    return " | ".join(str(i) for i in result.errors)


def test_no_sql() -> None:
    assert "exactly one of 'sql' or 'sql_file'" in _errors_of("no_sql.toml")


def test_both_sql() -> None:
    assert "exactly one of 'sql' or 'sql_file'" in _errors_of("both_sql.toml")


def test_bad_input_ref() -> None:
    assert "'ghosts' is not a step" in _errors_of("bad_input_ref.toml")


def test_unknown_field_is_error() -> None:
    errors = _errors_of("unknown_field.toml")
    assert "sqll" in errors  # pydantic extra="forbid" names the typo


def test_cycle_detected() -> None:
    result = load_recipe(BROKEN / "cycle.toml")
    assert result.recipe is not None  # structurally fine
    plan = build_plan(result.recipe)
    assert not plan.ok
    assert "cycle" in str(plan.issues[0])


# --- param warnings -----------------------------------------------------------

def test_undeclared_bind_is_warning(tmp_path: Path) -> None:
    recipe = tmp_path / "r.toml"
    recipe.write_text(
        '[recipe]\nname = "t"\n'
        '[steps.s]\nsource = "x"\nsql = "SELECT * FROM t WHERE d > :mystery"\n'
    )
    result = load_recipe(recipe)
    assert result.ok  # warnings don't invalidate
    assert any(":mystery" in str(w) for w in result.warnings)


def test_unused_param_is_warning(tmp_path: Path) -> None:
    recipe = tmp_path / "r.toml"
    recipe.write_text(
        '[recipe]\nname = "t"\nparams = ["ghost"]\n'
        '[steps.s]\nsource = "x"\nsql = "SELECT 1 FROM dual"\n'
    )
    result = load_recipe(recipe)
    assert result.ok
    assert any("ghost" in str(w) for w in result.warnings)
