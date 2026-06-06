# WiseQL

**The wise data browser.**

WiseQL is a terminal app that runs **SQL recipes** — complex database reads broken into small, observable steps — with live run views, per-step reports, and assertions that catch data issues automatically.

A 400-line SQL query is a black box. WiseQL turns it into a glass box.

> 🚧 **In development.** This release reserves the package name. Follow progress at [wiseql.dev](https://wiseql.dev).

## Planned highlights

- Recipes as TOML: break a monster query into a DAG of small SQL steps with named inputs/outputs
- Norton Commander-style TUI: F-keys, live DAG run view, drill into any step's data
- Per-step assertions (row counts, nulls, uniqueness) that find data issues for you
- Checkpointing (Parquet) — resume failed runs, diff today's run against yesterday's
- Oracle first, PostgreSQL next; DuckDB inside; read-only by default
- Optional local AI add-on for failure explanation — never required, never in the execution path

## License

MIT
