"""Multi-step DAG execution (S3.1) — the heart of WiseQL.

Walks the recipe's execution plan in topological order. Each **database** step
(``source``) is fetched from Oracle and *materialized* into a real DuckDB table
named after the step; each **local** step (``inputs``) runs its SQL directly in
DuckDB over those upstream tables. Data flows step → step entirely in DuckDB.

Why materialize (``CREATE TABLE … AS``) rather than register a live view: the
Oracle result object is released when its connection closes, and downstream
steps — plus future checkpointing — need stable, independent data.

Database steps go through the same ``open_connection`` (NLS defaults) and
``read_only_violation`` guard as single-step execution, so the read-only
invariants can't drift between the two paths. Local steps run only against the
ephemeral in-memory DuckDB, so the guard doesn't apply to them.

Assertions (S3.3) and parameter prompting (S3.2) build on this; here we just
prove data flows through the DAG.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from wiseql.config import open_connection
from wiseql.config.model import WiseQLConfig
from wiseql.engine.guard import read_only_violation
from wiseql.recipes import LoadResult, build_plan

DEFAULT_SAMPLE_ROWS = 50
ASSERT_SAMPLE_ROWS = 20  # offending rows captured per failed assertion


@dataclass
class AssertionOutcome:
    check: str  # e.g. "no_nulls[customer_id]"
    passed: bool
    detail: str = ""
    sample_columns: list[str] = field(default_factory=list)
    samples: list[tuple] = field(default_factory=list)  # offending rows (report_samples)


@dataclass
class StepRun:
    name: str
    kind: str  # "db" | "local"
    source: str | None
    ok: bool  # executed without error
    columns: list[str] = field(default_factory=list)
    sample: list[tuple] = field(default_factory=list)  # capped preview
    row_count: int = 0  # total rows produced in DuckDB
    elapsed_ms: float = 0.0
    error: str = ""
    assertions: list[AssertionOutcome] = field(default_factory=list)
    on_fail: str = "stop"  # policy from the recipe, echoed for display

    @property
    def assert_failed(self) -> bool:
        return any(not a.passed for a in self.assertions)


@dataclass
class RunResult:
    ok: bool
    steps: list[StepRun] = field(default_factory=list)
    terminals: list[str] = field(default_factory=list)  # result steps (consumed by nobody)
    elapsed_ms: float = 0.0
    error: str = ""  # run-level failure (e.g. invalid plan)

    def step(self, name: str) -> StepRun | None:
        return next((s for s in self.steps if s.name == name), None)

    @property
    def failed_step(self) -> StepRun | None:
        return next((s for s in self.steps if not s.ok), None)


def _ident(name: str) -> str:
    """Quote a step name for safe use as a DuckDB table identifier."""
    return '"' + name.replace('"', '""') + '"'


def _terminals(recipe) -> list[str]:
    consumed: set[str] = set()
    for step in recipe.steps.values():
        consumed.update(step.inputs)
    return [name for name in recipe.steps if name not in consumed]


def run_recipe(
    loaded: LoadResult,
    config: WiseQLConfig,
    *,
    params: dict | None = None,
    environ=None,
) -> RunResult:
    """Execute every step of a recipe through DuckDB and return per-step results.

    Stops at the first failing step (downstream steps depend on it). Never
    raises for operational problems — they surface as ``ok=False``.
    """
    recipe = loaded.recipe
    if recipe is None or not loaded.ok:
        return RunResult(ok=False, error="recipe is invalid")

    plan = build_plan(recipe)
    if not plan.ok:
        reason = next((i.message for i in plan.issues if i.severity == "error"), "invalid plan")
        return RunResult(ok=False, error=reason)

    import duckdb

    run_start = time.perf_counter()
    duck = duckdb.connect()
    oracle_conns: dict[str, object] = {}  # source name → live Oracle connection (reused)
    result = RunResult(ok=True, terminals=_terminals(recipe))

    try:
        for name in plan.order:
            step = recipe.steps[name]
            started = time.perf_counter()
            sql = (loaded.resolved_sql.get(name) or "").strip().rstrip(";").strip()
            try:
                if step.source:  # database step
                    self_run = _run_db_step(
                        duck, oracle_conns, config, name, step.source, sql, params, environ
                    )
                else:  # local DuckDB step
                    self_run = _run_local_step(duck, name, step.inputs, sql)
            except Exception as exc:  # noqa: BLE001 — record and stop the run
                result.steps.append(
                    StepRun(
                        name=name,
                        kind="db" if step.source else "local",
                        source=step.source,
                        ok=False,
                        elapsed_ms=_ms(started),
                        error=str(exc).strip(),
                    )
                )
                result.ok = False
                break

            self_run.elapsed_ms = _ms(started)
            if self_run.ok and step.assert_ is not None:
                self_run.on_fail = step.assert_.on_fail
                _evaluate_assertions(duck, self_run, step.assert_, result.steps)
            result.steps.append(self_run)

            if not self_run.ok:
                result.ok = False
                break
            if self_run.assert_failed and self_run.on_fail != "warn":
                # stop + report_samples are real failures; only stop halts the run.
                result.ok = False
                if self_run.on_fail == "stop":
                    break
    finally:
        for conn in oracle_conns.values():
            try:
                conn.close()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass
        duck.close()

    result.elapsed_ms = _ms(run_start)
    return result


def _run_db_step(duck, oracle_conns, config, name, source, sql, params, environ) -> StepRun:
    run = StepRun(name=name, kind="db", source=source, ok=False)

    violation = read_only_violation(sql)
    if violation:
        run.error = f"read-only guard: {violation}"
        return run

    conn = config.connections.get(source)
    if conn is None:
        run.error = f"connection '{source}' is not configured (wiseql conn list)"
        return run

    if source not in oracle_conns:
        oracle_conns[source] = open_connection(source, conn, environ=environ)
    ora = oracle_conns[source]

    # Zero-copy Oracle → DuckDB via the Arrow PyCapsule interface, materialized.
    odf = ora.fetch_df_all(sql, params or {})
    duck.register("_wiseql_odf", odf)
    try:
        duck.execute(f"CREATE TABLE {_ident(name)} AS SELECT * FROM _wiseql_odf")
    finally:
        duck.unregister("_wiseql_odf")

    return _collect(duck, run)


def _run_local_step(duck, name, inputs, sql) -> StepRun:
    run = StepRun(name=name, kind="local", source=None, ok=False)
    # Upstream steps are already DuckDB tables named after themselves; the
    # step's SQL references them directly (e.g. FROM orders, FROM returns).
    duck.execute(f"CREATE TABLE {_ident(name)} AS {sql}")
    return _collect(duck, run)


def _evaluate_assertions(duck, run: StepRun, spec, prior_steps: list[StepRun]) -> None:
    """Check a step's assertions as SQL against its DuckDB table.

    Column names come from the recipe in lowercase while Oracle-sourced tables
    carry UPPERCASE names — DuckDB resolves quoted identifiers case-insensitively,
    so ``"customer_id"`` matches ``CUSTOMER_ID``. Doing the checks in SQL (not
    Python name-matching) is what makes that work.
    """
    t = _ident(run.name)
    out: list[AssertionOutcome] = []

    if spec.rows_min is not None:
        ok = run.row_count >= spec.rows_min
        out.append(AssertionOutcome("rows_min", ok, f"{run.row_count} rows (min {spec.rows_min})"))

    if spec.rows_max is not None:
        ok = run.row_count <= spec.rows_max
        out.append(AssertionOutcome("rows_max", ok, f"{run.row_count} rows (max {spec.rows_max})"))

    if spec.no_nulls:
        cond = " OR ".join(f"{_ident(c)} IS NULL" for c in spec.no_nulls)
        n = duck.execute(f"SELECT COUNT(*) FROM {t} WHERE {cond}").fetchone()[0]
        cur = duck.execute(f"SELECT * FROM {t} WHERE {cond} LIMIT {ASSERT_SAMPLE_ROWS}")
        samples = cur.fetchall() if n else []
        cols = [d[0] for d in cur.description] if n else []
        label = ", ".join(spec.no_nulls)
        out.append(AssertionOutcome(f"no_nulls[{label}]", n == 0, f"{n} row(s) with NULL", cols, samples))

    if spec.unique:
        cols_sql = ", ".join(_ident(c) for c in spec.unique)
        cur = duck.execute(
            f"SELECT {cols_sql}, COUNT(*) AS occurrences FROM {t} "
            f"GROUP BY {cols_sql} HAVING COUNT(*) > 1 ORDER BY occurrences DESC "
            f"LIMIT {ASSERT_SAMPLE_ROWS}"
        )
        dups = cur.fetchall()
        dcols = [d[0] for d in cur.description]
        total = duck.execute(
            f"SELECT COUNT(*) FROM (SELECT 1 FROM {t} GROUP BY {cols_sql} HAVING COUNT(*) > 1)"
        ).fetchone()[0]
        label = ", ".join(spec.unique)
        out.append(
            AssertionOutcome(
                f"unique[{label}]", total == 0, f"{total} duplicated key(s)", dcols if dups else [], dups
            )
        )

    if spec.equals_step:
        other = next((s for s in prior_steps if s.name == spec.equals_step), None)
        other_count = other.row_count if other is not None else None
        if other_count is None:
            out.append(
                AssertionOutcome(
                    f"equals_step[{spec.equals_step}]", False,
                    f"step '{spec.equals_step}' not found among prior steps",
                )
            )
        else:
            out.append(
                AssertionOutcome(
                    f"equals_step[{spec.equals_step}]",
                    run.row_count == other_count,
                    f"{run.row_count} vs {spec.equals_step}={other_count}",
                )
            )

    run.assertions = out


def _collect(duck, run: StepRun, sample_rows: int = DEFAULT_SAMPLE_ROWS) -> StepRun:
    """Read columns, row count, and a capped sample from the step's table."""
    ident = _ident(run.name)
    run.columns = [d[0] for d in duck.execute(f"SELECT * FROM {ident} LIMIT 0").description]
    run.row_count = duck.execute(f"SELECT COUNT(*) FROM {ident}").fetchone()[0]
    run.sample = duck.execute(f"SELECT * FROM {ident} LIMIT {sample_rows}").fetchall()
    run.ok = True
    return run


def _ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
