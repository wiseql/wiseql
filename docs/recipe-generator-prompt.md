# WiseQL recipe-generator prompt

Paste the block below into an AI assistant that **has access to your database
schema and/or your existing SQL** (e.g. a coding assistant connected to your DB,
or just paste your `CREATE TABLE` statements and queries after it). It will emit
a complete WiseQL project you can drop onto a machine and run.

Replace the two `<<< … >>>` placeholders, then send.

---

```text
You are generating a WiseQL project. WiseQL is a terminal tool that runs "recipes":
a complex database read broken into a DAG of small, observable SQL steps, with
per-step assertions that catch data problems. I will give you my schema and the
questions/queries I care about; you produce the project files.

## What a recipe is (the format you MUST follow)

A recipe is a TOML file. Structure:

  [recipe]
  name        = "kebab-case-name"      # required
  description = "one line"             # optional
  params      = ["run_date"]           # optional; bind vars used as :run_date in SQL

  [steps.<snake_case_step_name>]       # >=1 step; step name = the table its output is exposed as
  # exactly ONE of:
  #   source = "<connection_name>"     # a DATABASE step: SQL runs on the DB (Oracle dialect), result lands in DuckDB
  #   inputs = ["stepA", "stepB"]      # a LOCAL step: SQL runs in DuckDB over those upstream steps' tables
  sql = """ ... """                    # or:  sql_file = "sql/whatever.sql"  (exactly one of sql/sql_file)
  description = "optional"
  assert = { ... }                     # optional, see below

Hard rules:
- Every step has EITHER `source` (database step) OR non-empty `inputs` (local step) — never both, never neither.
- Database-step SQL must be a SINGLE read-only statement (SELECT or WITH). No DML/DDL/PL-SQL/multiple statements.
- `inputs` may only name steps defined in the same recipe; the graph must be acyclic.
- In a local step, each input is a table named after the step: inputs=["orders"] -> `FROM orders`.
- Database steps use the SOURCE database's SQL dialect (Oracle). Local steps use DuckDB SQL dialect.
- Unknown TOML fields are errors — only use the fields listed here.

Assertions (inline table on a step; checked after the step runs):
  rows_min = <int>            # fail if fewer rows
  rows_max = <int>            # fail if more rows
  no_nulls = ["col", ...]     # fail if any listed column has NULL
  unique   = ["col", ...]     # fail if the column combination has duplicates
  equals_step = "other_step"  # fail if row count differs from that step
  on_fail = "stop" | "warn" | "report_samples"   # default "stop"
- "stop": failed assertion halts the run (use for preconditions).
- "warn": advisory, run continues and stays ok.
- "report_samples": run continues but is marked failed AND the offending rows are captured — use this
  for "this set should be empty" checks (e.g. a step that isolates bad rows, asserted rows_max = 0).

Design guidance:
- Decompose each question into small steps: pull the raw inputs as database steps, then do the
  joins/anti-joins/aggregations as local steps over them. Small steps = observable + debuggable.
- Prefer the "isolate the bad rows in a local step, assert rows_max = 0, on_fail = report_samples" idiom
  for data-quality checks — the run report then shows exactly what's wrong.
- Add cheap sanity assertions to the raw input steps (rows_min = 1, no_nulls on keys).
- Reference connections by NAME only — never put hosts/passwords in recipes.

## Output: a complete project, as a tree of files

Produce these files, each in its own fenced code block with its path as a header:

1. `project.toml`
   [project]
   name = "<<< project name >>>"
   description = "..."
   [defaults]
   connection = "<connection name, e.g. main>"

2. `context/tables.md`  — a short schema reference of the tables you used (table -> columns, keys, gotchas).
   (On the target machine `wiseql context sync` can regenerate this from the live DB; include your best version.)

3. `context/domain.md`  — 3-8 lines of business terminology relevant to these recipes.

4. `recipes/<one file per question>.toml`  — one recipe per question/check below. Put any long SQL
   inline with triple-quoted strings (don't bother with sql_file).

For each recipe, briefly explain (outside the code block) what it checks and which assertion catches the problem.

## Now use MY inputs

- Connection name to reference in recipes: <<< e.g. "main" >>>
- My schema (tables/columns/keys) and/or representative SQL queries, and the questions or
  data-quality checks I want as recipes:

<<< PASTE YOUR SCHEMA, QUERIES, AND THE QUESTIONS/CHECKS YOU WANT HERE.
    If you need more detail about a table to write a correct recipe, ask me before guessing. >>>
```

---

## After the AI replies

1. Create the project folder on the target machine and save the files at the paths it gave
   (or run `wiseql init <name>` first, then drop the recipes into `recipes/`).
2. Make sure the connection name in `[defaults] connection` (and any `source =`) matches a
   connection you've configured — see the README "Connect to your database".
3. Validate before running:  `wiseql validate recipes/*.toml`
   (with the AI add-on enabled you can add `--ai` for a semantic second opinion).
4. Run one:  `wiseql` → open the project → pick the recipe → F2. Or headless: `wiseql run recipes/<name>.toml`.

The model can hallucinate column names — `wiseql validate` catches structural mistakes, and the
first run surfaces anything the schema didn't match. Treat the generated recipes as a strong draft.
