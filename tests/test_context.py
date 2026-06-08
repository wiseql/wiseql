"""Context-sync tests (S4.3). Offline — introspection is separated from the
merge/render, so the note-preserving merge is tested without a database."""

from pathlib import Path

from typer.testing import CliRunner

from wiseql.cli import app
from wiseql.context import Column, Table, merge_tables_md, render_auto_block, write_tables_md
from wiseql.project import AUTO_END, AUTO_START, scaffold_project

runner = CliRunner()


def _fake_tables() -> list[Table]:
    return [
        Table(
            "CUSTOMERS",
            [Column("CUSTOMER_ID", "NUMBER", False, pk=True), Column("FULL_NAME", "VARCHAR2(100)", False)],
            comment="customer master",
        ),
        Table(
            "ORDERS",
            [Column("ORDER_ID", "NUMBER", True), Column("CUSTOMER_ID", "NUMBER", True)],
        ),
    ]


def test_render_marks_pk_and_nullability() -> None:
    md = render_auto_block(_fake_tables())
    assert "### CUSTOMERS" in md
    assert "customer master" in md
    assert "| CUSTOMER_ID | NUMBER | no | PK |" in md
    # orders.order_id is nullable and not a PK (the degenerate dev schema)
    assert "| ORDER_ID | NUMBER | yes |  |" in md


def test_merge_preserves_hand_notes_across_resync(tmp_path: Path) -> None:
    proj = tmp_path / "p"
    scaffold_project(proj, "p")
    tables_md = proj / "context" / "tables.md"
    note = "\n## My notes\norders.customer_id is nullable due to guest checkout.\n"
    tables_md.write_text(tables_md.read_text() + note, encoding="utf-8")

    write_tables_md(tables_md, _fake_tables(), project_name="p")
    after1 = tables_md.read_text()
    assert "My notes" in after1  # hand note survived the first sync
    assert "### ORDERS" in after1

    # re-sync with a different schema (orders dropped)
    write_tables_md(tables_md, _fake_tables()[:1], project_name="p")
    after2 = tables_md.read_text()
    assert "My notes" in after2  # still preserved
    assert "### ORDERS" not in after2  # auto-block was regenerated


def test_merge_creates_file_with_markers_when_missing(tmp_path: Path) -> None:
    p = tmp_path / "tables.md"
    write_tables_md(p, _fake_tables(), project_name="proj")
    text = p.read_text()
    assert AUTO_START in text and AUTO_END in text
    assert "### CUSTOMERS" in text


def test_merge_appends_block_when_markers_absent(tmp_path: Path) -> None:
    p = tmp_path / "tables.md"
    p.write_text("# hand-written\nimportant context\n", encoding="utf-8")
    write_tables_md(p, _fake_tables())
    text = p.read_text()
    assert "hand-written" in text  # preserved
    assert AUTO_START in text  # block appended


def test_cli_context_sync_outside_project_errors(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)  # no project.toml here or above
    empty = tmp_path / "cfg.toml"
    empty.write_text("", encoding="utf-8")
    result = runner.invoke(app, ["context", "sync"], env={"WISEQL_CONFIG": str(empty)})
    assert result.exit_code == 1
    assert "not in a project" in result.output
