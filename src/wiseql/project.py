"""Project scaffolding and discovery (S4.1).

A WiseQL *project* is a directory bundling everything about one
debugging/monitoring domain — shareable via git:

    <name>/
    ├── project.toml        # [project] metadata + [defaults]/[connections]
    ├── context/
    │   ├── tables.md        # schema reference (wiseql context sync fills it)
    │   └── domain.md        # business terminology
    ├── recipes/             # recipe .toml files (+ sql/)
    ├── runs/                # run reports + checkpoints (gitignored)
    └── .gitignore

``project.toml`` carries a ``[project]`` table (metadata) alongside the
``[defaults]``/``[connections]`` tables the config loader already reads — the
loader ignores unknown top-level tables, so the two coexist.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_MANIFEST = "project.toml"

# Marker block in tables.md that `context sync` regenerates; everything outside
# it (hand-written notes) is preserved across syncs.
AUTO_START = "<!-- wiseql:auto:start -->"
AUTO_END = "<!-- wiseql:auto:end -->"


def _manifest(name: str, description: str, connection: str | None) -> str:
    default = (
        f'connection = "{connection}"'
        if connection
        else '# connection = "oracle_dev"   # name a connection from ~/.config/wiseql/config.toml'
    )
    return f"""\
# WiseQL project manifest.
[project]
name        = "{name}"
description = "{description}"

[defaults]
{default}

# Project-local connections may be defined here (no secrets — login per machine):
# [connections.oracle_dev]
# driver  = "oracle"
# host    = "localhost"
# port    = 1521
# service = "FREEPDB1"
# user    = "wiseql"
# auth    = "keyring"
"""


def _tables_md(name: str) -> str:
    return f"""\
# {name} — tables

Schema reference for this project. Run `wiseql context sync` to populate the
auto-generated block below from the database. Add your own notes anywhere
*outside* the markers — they are preserved across syncs.

{AUTO_START}
_(empty — run `wiseql context sync`)_
{AUTO_END}
"""


def _domain_md(name: str) -> str:
    return f"""\
# {name} — domain

Business terminology, gotchas, and domain knowledge for this project. This
file is grounding context for recipe authoring and the optional AI layer.
"""


def scaffold_project(
    dest: Path, name: str, description: str = "", connection: str | None = None
) -> list[Path]:
    """Create a project skeleton at ``dest``. Returns the files created.

    Raises ``FileExistsError`` if ``dest`` already exists and is non-empty, so
    an existing project is never clobbered.
    """
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise FileExistsError(f"{dest} already exists and is not empty")

    files = {
        dest / PROJECT_MANIFEST: _manifest(name, description, connection),
        dest / "context" / "tables.md": _tables_md(name),
        dest / "context" / "domain.md": _domain_md(name),
        dest / "recipes" / ".gitkeep": "",
        dest / ".gitignore": "runs/\n",
    }
    created: list[Path] = []
    for path, content in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created.append(path)
    # runs/ exists but is gitignored — no tracked file inside it.
    (dest / "runs").mkdir(exist_ok=True)
    return created


def find_project_root(start: Path | None = None) -> Path | None:
    """Nearest ancestor of ``start`` (inclusive) containing ``project.toml``,
    or None. The single source of truth for 'which project am I in' — used for
    both config loading and ``runs/`` placement."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if (directory / PROJECT_MANIFEST).is_file():
            return directory
    return None
