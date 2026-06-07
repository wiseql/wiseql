"""Recipe loading and validation with exact, human-friendly errors."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from wiseql.recipes.model import Recipe

Severity = Literal["error", "warning"]

# Bind-variable tokens like :run_date — used for param cross-checking.
# May false-positive inside string literals (e.g. 'HH:MI'), hence warnings only.
_BIND_RE = re.compile(r"(?<![:\w]):([A-Za-z_][A-Za-z0-9_]*)")


@dataclass(frozen=True)
class Issue:
    severity: Severity
    where: str  # "recipe", "steps.<name>", "file"
    message: str

    def __str__(self) -> str:
        return f"[{self.severity}] {self.where}: {self.message}"


@dataclass
class LoadResult:
    path: Path
    recipe: Recipe | None
    issues: list[Issue] = field(default_factory=list)
    # step name -> SQL text with sql_file already resolved
    resolved_sql: dict[str, str] = field(default_factory=dict)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return self.recipe is not None and not self.errors


def _pydantic_issues(exc: ValidationError) -> list[Issue]:
    issues: list[Issue] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "recipe"
        issues.append(Issue("error", loc, err["msg"]))
    return issues


def load_recipe(path: str | Path) -> LoadResult:
    """Parse + validate a recipe file. Never raises for content problems."""
    path = Path(path)
    result = LoadResult(path=path, recipe=None)

    # --- file & TOML layer -------------------------------------------------
    try:
        raw = path.read_bytes()
    except OSError as exc:
        result.issues.append(Issue("error", "file", f"cannot read {path}: {exc}"))
        return result

    try:
        data = tomllib.loads(raw.decode("utf-8"))
    except tomllib.TOMLDecodeError as exc:
        result.issues.append(Issue("error", "file", f"invalid TOML: {exc}"))
        return result

    # --- structural layer (pydantic) ---------------------------------------
    try:
        recipe = Recipe.model_validate(data)
    except ValidationError as exc:
        result.issues.extend(_pydantic_issues(exc))
        return result

    result.recipe = recipe

    if not recipe.steps:
        result.issues.append(Issue("error", "steps", "recipe defines no steps"))
        return result

    # --- semantic layer -----------------------------------------------------
    step_names = set(recipe.steps)

    for name, step in recipe.steps.items():
        where = f"steps.{name}"

        # exactly one of sql / sql_file
        if (step.sql is None) == (step.sql_file is None):
            result.issues.append(
                Issue("error", where, "exactly one of 'sql' or 'sql_file' is required")
            )
            continue

        # resolve sql_file relative to the recipe file
        if step.sql_file is not None:
            sql_path = path.parent / step.sql_file
            try:
                result.resolved_sql[name] = sql_path.read_text(encoding="utf-8")
            except OSError as exc:
                result.issues.append(
                    Issue("error", where, f"cannot read sql_file '{step.sql_file}': {exc}")
                )
                continue
        else:
            result.resolved_sql[name] = step.sql or ""

        if not result.resolved_sql[name].strip():
            result.issues.append(Issue("error", where, "SQL is empty"))

        # database step XOR local step
        if step.source and step.inputs:
            result.issues.append(
                Issue("error", where, "a step cannot have both 'source' and 'inputs'")
            )
        if not step.source and not step.inputs:
            result.issues.append(
                Issue(
                    "error",
                    where,
                    "a step needs 'source' (database step) or 'inputs' (local step)",
                )
            )

        # input references must exist (cycle detection lives in dag.py)
        for ref in step.inputs:
            if ref not in step_names:
                result.issues.append(
                    Issue("error", where, f"input '{ref}' is not a step in this recipe")
                )
            if ref == name:
                result.issues.append(Issue("error", where, "step cannot input itself"))

        # assert.equals_step must reference an existing step
        if step.assert_ and step.assert_.equals_step:
            if step.assert_.equals_step not in step_names:
                result.issues.append(
                    Issue(
                        "error",
                        where,
                        f"assert.equals_step '{step.assert_.equals_step}' is not a step",
                    )
                )

    # --- parameter cross-checks (warnings only) -----------------------------
    declared = set(recipe.recipe.params)
    used: set[str] = set()
    for name, sql in result.resolved_sql.items():
        for match in _BIND_RE.finditer(sql):
            token = match.group(1)
            used.add(token)
            if token not in declared:
                result.issues.append(
                    Issue(
                        "warning",
                        f"steps.{name}",
                        f"bind variable :{token} is not declared in recipe.params",
                    )
                )
    for param in declared - used:
        result.issues.append(
            Issue("warning", "recipe", f"param '{param}' is declared but never used")
        )

    return result
