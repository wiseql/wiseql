# Keep the virtualenv OUTSIDE this folder.
# This directory is synced (Cowork workspace); a .venv inside it gets
# corrupted by sync conflicts. ~/.venvs/wiseql is local-only and safe.
export UV_PROJECT_ENVIRONMENT := $(HOME)/.venvs/wiseql

.PHONY: run run-ai test sync validate plan clean

run:        ## open the TUI
	uv run wiseql

run-ai:     ## open the TUI with the optional AI add-on ([ai] extra)
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
