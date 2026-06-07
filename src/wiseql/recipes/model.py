"""Pydantic models for the recipe format (RECIPE_SPEC.md v0.1).

``extra="forbid"`` everywhere: typos in field names are hard errors with
exact messages — a debugging tool must not guess.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StepAssert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows_min: int | None = None
    rows_max: int | None = None
    no_nulls: list[str] | None = None
    unique: list[str] | None = None
    equals_step: str | None = None
    on_fail: Literal["stop", "warn", "report_samples"] = "stop"


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    sql: str | None = None
    sql_file: str | None = None
    source: str | None = None
    inputs: list[str] = Field(default_factory=list)
    description: str | None = None
    assert_: StepAssert | None = Field(default=None, alias="assert")

    @property
    def is_local(self) -> bool:
        """Local steps run in DuckDB over upstream outputs."""
        return bool(self.inputs)


class RecipeMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    params: list[str] = Field(default_factory=list)


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    recipe: RecipeMeta
    steps: dict[str, Step]
