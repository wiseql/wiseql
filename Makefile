# Keep the virtualenv OUTSIDE this folder.
# This directory is synced (Cowork workspace); a .venv inside it gets
# corrupted by sync conflicts. ~/.venvs/wiseql is local-only and safe.
export UV_PROJECT_ENVIRONMENT := $(HOME)/.venvs/wiseql

.PHONY: run test sync validate plan clean

# Dev launcher includes the optional AI client so the app behaves like a real
# `wiseql[ai]` install: AI is controlled purely by config (`wiseql ai setup` /
# `ai disable`), never by which command you run. The shipped package stays
# AI-free — the client is only in the [ai] extra, and `make test` runs without it.
run:        ## open the TUI (AI available; enable/disable via `wiseql ai`)
	uv run --extra ai wiseql

test:       ## run the test suite
	uv run pytest -q

sync:       ## (re)create the environment
	uv sync

validate:   ## validate all example recipes
	uv run wiseql validate examples/*.toml

plan:       ## show the demo recipe plan
	uv run wiseql plan examples/orphan-returns.toml

clean:
	rm -rf $(HOME)/.venvs/wiseql dist build
