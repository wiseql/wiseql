"""Project scaffolding + discovery tests (S4.1)."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from wiseql.cli import app
from wiseql.config import load_active_config
from wiseql.project import AUTO_END, AUTO_START, find_project_root, scaffold_project

runner = CliRunner()


def test_scaffold_creates_structure(tmp_path: Path) -> None:
    dest = tmp_path / "returns-monitoring"
    scaffold_project(dest, "returns-monitoring", description="watch returns")

    assert (dest / "project.toml").is_file()
    assert (dest / "context" / "tables.md").is_file()
    assert (dest / "context" / "domain.md").is_file()
    assert (dest / "recipes").is_dir()
    assert (dest / "runs").is_dir()
    assert (dest / ".gitignore").read_text().strip() == "runs/"

    manifest = (dest / "project.toml").read_text()
    assert 'name        = "returns-monitoring"' in manifest
    assert 'description = "watch returns"' in manifest
    # tables.md carries the auto markers context-sync regenerates
    tables = (dest / "context" / "tables.md").read_text()
    assert AUTO_START in tables and AUTO_END in tables


def test_scaffold_sets_default_connection(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    scaffold_project(dest, "proj", connection="oracle_dev")
    assert 'connection = "oracle_dev"' in (dest / "project.toml").read_text()


def test_scaffold_refuses_nonempty_dir(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    dest.mkdir()
    (dest / "something").write_text("x")
    with pytest.raises(FileExistsError):
        scaffold_project(dest, "proj")


def test_find_project_root_walks_up(tmp_path: Path) -> None:
    dest = tmp_path / "proj"
    scaffold_project(dest, "proj")
    deep = dest / "recipes" / "sub"
    deep.mkdir(parents=True)
    assert find_project_root(deep) == dest.resolve()
    assert find_project_root(tmp_path) is None  # above the project


def test_project_toml_feeds_config_layer(tmp_path: Path) -> None:
    # project.toml [defaults] is picked up by the config loader from a subdir.
    dest = tmp_path / "proj"
    scaffold_project(dest, "proj", connection="oracle_dev")
    result = load_active_config(
        global_path=tmp_path / "none.toml", cwd=dest / "recipes"
    )
    assert result.config.defaults.connection == "oracle_dev"


def _projects_env(tmp_path: Path) -> tuple[dict, Path]:
    """A config pointing projects_dir at a tmp folder, so `init` never touches
    the real ~/.wiseql/projects."""
    pdir = tmp_path / "projects"
    cfg = tmp_path / "config.toml"
    cfg.write_text(f'[defaults]\nprojects_dir = "{pdir}"\n', encoding="utf-8")
    return {"WISEQL_CONFIG": str(cfg)}, pdir


def test_cli_init_creates_in_projects_dir(tmp_path: Path) -> None:
    env, pdir = _projects_env(tmp_path)
    result = runner.invoke(app, ["init", "demo", "--description", "a demo"], env=env)
    assert result.exit_code == 0
    assert (pdir / "demo" / "project.toml").is_file()
    assert "created project" in result.output


def test_cli_init_refuses_existing(tmp_path: Path) -> None:
    env, pdir = _projects_env(tmp_path)
    (pdir / "demo").mkdir(parents=True)
    (pdir / "demo" / "f").write_text("x")
    result = runner.invoke(app, ["init", "demo"], env=env)
    assert result.exit_code == 1
    assert "cannot create project" in result.output


def test_cli_projects_lists(tmp_path: Path) -> None:
    env, pdir = _projects_env(tmp_path)
    scaffold_project(pdir / "alpha", "alpha")
    scaffold_project(pdir / "beta", "beta")
    result = runner.invoke(app, ["projects"], env=env)
    assert result.exit_code == 0
    assert "alpha" in result.output and "beta" in result.output
