# WiseQL Recipe Specification — v1.0

A **recipe** is a TOML file describing a DAG of small SQL steps. WiseQL runs the
steps in dependency order, pipes outputs between them through DuckDB, checks
assertions, and reports everything per step.

This document is the authoritative spec. It is also intended as grounding for
LLMs that generate recipes — see `docs/recipe-generator-prompt.md`.

## File layout

```toml
[recipe]                    # required: exactly one
name        = "my-check"    # required, kebab-case recommended
description = "…"           # optional
params      = ["run_date"]  # optional: parameters injected at run time

[steps.<step_name>]         # one table per step; at least one step required
# … step fields, see below
```

Step names are TOML keys: use `snake_case`, and they must be unique (TOML
enforces this). A step name doubles as the table name its output is available
under to downstream steps.

## Step fields

| Field | Type | Rules |
|---|---|---|
| `sql` | string | SQL text. **Exactly one** of `sql` / `sql_file` per step. |
| `sql_file` | string | Path to a `.sql` file, relative to the recipe file. |
| `source` | string | Connection name (from config/project). Marks a **database step**. |
| `inputs` | array of step names | Upstream steps whose outputs this step reads. Marks a **local step** (runs in DuckDB over those outputs). |
| `description` | string | Optional human note. |
| `assert` | inline table | Optional assertions, see below. |

Rules:

- A step must have **either** `source` (a database step) **or** non-empty
  `inputs` (a local step) — not both, not neither.
- Database steps must contain a **single read-only statement** (`SELECT` or
  `WITH`). WiseQL rejects DML/DDL/PL-SQL/multi-statement SQL at run time.
- `inputs` may only reference step names defined in the same recipe. The
  resulting dependency graph must be **acyclic**.
- In a local step's SQL, each input is available as a table named after the
  step (e.g. `inputs = ["orders"]` → `SELECT * FROM orders`).

## Execution model

This is what makes recipes work, and what a recipe author should keep in mind:

- **Database steps** (`source`) run their SQL against that connection (Oracle
  today; thin mode, read-only) and the result is materialised into a **DuckDB**
  table named after the step.
- **Local steps** (`inputs`) run their SQL **in DuckDB**, over the upstream
  steps' tables — so cross-step joins, anti-joins, and aggregations are just
  SQL over the named inputs. Use **DuckDB SQL dialect** in local steps, and the
  source DB's dialect (e.g. Oracle) in database steps.
- Steps run in topological order; the run **stops at the first failing step**
  (an error, or an assertion with `on_fail = "stop"`).
- Column-name casing: Oracle returns UPPERCASE column names; DuckDB matches
  quoted identifiers case-insensitively, and assertions are checked as SQL, so
  lowercase recipe column names match UPPERCASE source columns.
- Each step's output is checkpointed to Parquet, enabling **resume** (continue a
  failed/killed run from the failed step), **diff** (compare two runs per step),
  and the **Data Explorer** (ad-hoc SQL over a finished run's frozen outputs).
  These are runtime features — the recipe author does nothing special for them.

## Parameters

Declare in `[recipe] params`, use as bind variables in SQL: `:run_date`. Values
are supplied at run time (CLI `--param run_date=2026-06-05`, or a TUI prompt)
and **bound safely** — never string-interpolated.

- Using `:name` in SQL without declaring it → **warning** (could be a false
  positive inside a string literal, so not a hard error).
- Declaring a param never used in any SQL → **warning**.

## Assertions

Assertions are how a recipe catches data problems automatically. They run as SQL
against the step's DuckDB table after it executes.

```toml
assert = { rows_min = 1, rows_max = 100, no_nulls = ["customer_id"], unique = ["order_id"], equals_step = "other", on_fail = "stop" }
```

| Key | Type | Meaning |
|---|---|---|
| `rows_min` | int | Fail if the step returns fewer rows. |
| `rows_max` | int | Fail if the step returns more rows. |
| `no_nulls` | array of column names | Fail if any listed column contains NULL. |
| `unique` | array of column names | Fail if the listed column combination has duplicates. |
| `equals_step` | step name | Fail if this step's row count differs from that step's. |
| `on_fail` | `"stop"` \| `"warn"` \| `"report_samples"` | Default `"stop"`. |

`on_fail` semantics:

- `"stop"` (default) — a failed assertion fails the run and halts it (non-zero
  exit code; the cron contract).
- `"warn"` — advisory; recorded but the run continues and stays "ok".
- `"report_samples"` — the run continues but is marked failed, and the offending
  rows are captured in the report (great for "this should be empty" checks like
  orphan detection).

Unknown fields anywhere in the file are **errors** (typo protection).

## A debugging idiom: "this set should be empty"

Many data-quality checks are best expressed as a local step that isolates the
bad rows, asserted with `rows_max = 0, on_fail = "report_samples"`. When it
fails, the report hands you exactly the offending rows.

## Complete example

```toml
[recipe]
name        = "orphan-returns"
description = "Returns whose order does not exist"
params      = []

[steps.orders]
source = "oracle_dev"
sql = """
SELECT order_id, customer_id, order_date FROM orders
"""
assert = { rows_min = 1 }

[steps.returns]
source   = "oracle_dev"
sql_file = "sql/returns.sql"

[steps.orphans]
inputs = ["orders", "returns"]
sql = """
SELECT r.* FROM returns r
LEFT JOIN orders o USING (order_id)
WHERE o.order_id IS NULL
"""
assert = { rows_max = 0, on_fail = "report_samples" }
```

## Project layout

A recipe usually lives in a **project** — a directory bundling everything about
one debugging/monitoring domain, shareable via git:

```
my-project/
├── project.toml          # manifest: [project] name/description, [defaults] connection, optional [connections.*]
├── context/
│   ├── tables.md         # schema docs (auto-generated by `wiseql context sync`, hand-enriched)
│   └── domain.md         # business terminology
├── recipes/
│   ├── <recipe>.toml
│   └── sql/              # external .sql files referenced by sql_file
└── runs/                 # run reports + checkpoints (gitignored)
```

Connections are referenced **by name** only; the host/service/user live in
config and the password in an OS keyring — so recipes and `project.toml` stay
shareable while credentials remain per-machine.

## Versioning

This is spec **v1.0** — structure, validation, planning, **and execution**
(database→DuckDB piping, assertions, parameters) are all implemented and
stable. Future additions (new assertion kinds, more source dialects) will be
backward-compatible within 1.x.
