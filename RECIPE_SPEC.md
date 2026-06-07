# WiseQL Recipe Specification — v0.1

A **recipe** is a TOML file describing a DAG of small SQL steps. WiseQL runs
the steps, pipes outputs between them, checks assertions, and reports
everything.

This document is the authoritative spec. It is also intended as context for
LLMs that generate recipes.

## File layout

```toml
[recipe]                    # required: exactly one
name        = "my-check"    # required, kebab-case recommended
description = "…"           # optional
params      = ["run_date"]  # optional: parameters injected at run time

[steps.<step_name>]         # one table per step; at least one step required
# … step fields, see below
```

Step names are TOML keys: use `snake_case`, must be unique (TOML enforces this).

## Step fields

| Field | Type | Rules |
|---|---|---|
| `sql` | string | SQL text. **Exactly one** of `sql` / `sql_file` per step. |
| `sql_file` | string | Path to a `.sql` file, relative to the recipe file. |
| `source` | string | Connection name (from config/project). Marks a **database step**. |
| `inputs` | array of step names | Upstream steps whose outputs this step reads. Marks a **local step** (runs in DuckDB over those outputs, referenced by step name as table names). |
| `description` | string | Optional human note. |
| `assert` | inline table | Optional assertions, see below. |

Rules:

- A step must have **either** `source` (database step) **or** non-empty
  `inputs` (local step) — not both, not neither.
- Database steps must contain a single read-only statement (`SELECT` / `WITH`).
  WiseQL rejects anything else at run time.
- `inputs` may only reference step names defined in the same recipe.
  The resulting graph must be acyclic.
- In a local step's SQL, each input is available as a table named after the
  step (e.g. `inputs = ["orders"]` → `SELECT * FROM orders`).

## Parameters

Declare in `[recipe] params`, use as bind variables in SQL: `:run_date`.
Values are supplied at run time (CLI `--param run_date=2026-06-05` or TUI
prompt) and bound safely — never string-interpolated.

- Using `:name` in SQL without declaring it → **warning** (might be a false
  positive inside string literals, so not an error).
- Declaring a param never used in any SQL → **warning**.

## Assertions

```toml
assert = { rows_min = 1, rows_max = 100, no_nulls = ["customer_id"], unique = ["order_id"], equals_step = "other", on_fail = "stop" }
```

| Key | Type | Meaning |
|---|---|---|
| `rows_min` | int | Fail if step returns fewer rows. |
| `rows_max` | int | Fail if step returns more rows. |
| `no_nulls` | array of column names | Fail if any listed column contains NULL. |
| `unique` | array of column names | Fail if the listed column combination has duplicates. |
| `equals_step` | step name | Fail if row count differs from that step's. |
| `on_fail` | `"stop"` \| `"warn"` \| `"report_samples"` | Default `"stop"`. `report_samples` continues and captures offending rows in the report. |

Unknown fields anywhere in the file are **errors** (typo protection).

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

## Versioning

This is spec v0.1 (Sprint 1): structure, validation, and planning only.
Execution semantics (Sprint 2+) may add fields; additions will be
backward-compatible within 0.x where possible.
