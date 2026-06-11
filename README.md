# WiseQL

**The wise data browser.** A terminal app that runs **SQL recipes** — a complex
database read broken into a DAG of small, observable steps — with a live run
view, per-step reports, assertions that catch data issues automatically,
checkpoint/resume, run diffing, an in-app data explorer, and an optional local
AI layer that explains what a run did.

A 400-line SQL query is a black box. WiseQL turns it into a glass box.

> Early but usable. Oracle first (thin mode — no Instant Client needed),
> PostgreSQL next; DuckDB inside; read-only by default.

## Install

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/) (or pipx).

```bash
# from GitHub (with the optional AI add-on)
uv tool install "wiseql[ai] @ git+https://github.com/wiseql/wiseql.git"

# …or without AI
uv tool install "git+https://github.com/wiseql/wiseql.git"

# …or from a local clone
git clone https://github.com/wiseql/wiseql.git && cd wiseql
uv tool install '.[ai]'
```

This puts `wiseql` on your PATH. Check it:

```bash
wiseql version
wiseql --help
```

(`pipx install "wiseql[ai] @ git+https://github.com/wiseql/wiseql.git"` works too.)

## Connect to your database

Connections live in `~/.config/wiseql/config.toml` and hold everything **except**
the password (recipes reference them by name, so they stay shareable):

```toml
[connections.main]
driver  = "oracle"
host    = "db.example.com"
port    = 1521
service = "PROD"
user    = "me_readonly"
auth    = "keyring"          # OS keychain (default) · or "env" · or "wallet"

[defaults]
connection = "main"
```

Then store the password and test reachability:

```bash
wiseql conn login main      # prompts once, stores in your OS keyring
wiseql conn test main       # connects, reports latency + DB version
wiseql conn list            # see configured connections
```

> Use a **read-only** database user. WiseQL refuses non-SELECT SQL, but a
> read-only user is the real guarantee.

## Create a project and run a recipe

```bash
wiseql init returns-monitoring -c main           # scaffolds project.toml, recipes/, context/, runs/
cd returns-monitoring
wiseql context sync returns-monitoring -c main   # introspect the schema into context/tables.md
```

Add a recipe under `recipes/` (write one by hand — see
[RECIPE_SPEC.md](./RECIPE_SPEC.md) — or generate them, below). Then:

```bash
wiseql validate recipes/*.toml     # structural validation (add --ai for a semantic second opinion)
wiseql                             # open the TUI → pick the project → pick a recipe → F2 to run
wiseql run recipes/late-returns.toml --param run_date=2026-06-01   # …or headless (cron/CI; exit code is the contract)
```

In the TUI: **F2** run · **Enter** drill into a step's data · **Ctrl+R** resume a
failed run · **Ctrl+D** diff vs the previous run · **Ctrl+E** explore a run's
data with ad-hoc SQL · **F4** (on a run) AI-explain what happened · **F9**
settings.

## Generate recipes with AI

If you have an AI assistant with access to your schema/SQL, paste the prompt in
[docs/recipe-generator-prompt.md](./docs/recipe-generator-prompt.md) — it emits a
complete WiseQL project (project.toml + recipes + context) for your database.
Then `wiseql validate recipes/*.toml` and run them.

## Optional: the local AI add-on

AI is **off by default** and never required. It runs locally via
[Ollama](https://ollama.com) — nothing leaves your machine.

```bash
# install Ollama, then:
ollama serve &
ollama pull gemma3            # or any local model tag you prefer
wiseql ai setup --model gemma3
wiseql ai status             # should say: ✓ ready
```

With it enabled, **F4** on a run streams an explanation (what the run did, what
looks correct, what's wrong and where to look), and `wiseql validate --ai` adds
a semantic recipe review. If Ollama is off or the model is missing, AI features
show a hint and the rest of the app is unaffected.

## Docs

- [RECIPE_SPEC.md](./RECIPE_SPEC.md) — the recipe format (authoritative)
- [docs/recipe-generator-prompt.md](./docs/recipe-generator-prompt.md) — generate recipes from your schema

## License

MIT
