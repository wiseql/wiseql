"""Read-only guard — a debugger never mutates.

A database step must be a single read-only statement. Per ``RECIPE_SPEC.md``
that means ``SELECT`` *or* ``WITH`` (CTEs are common in real debugging queries),
nothing else. We enforce it ourselves rather than trusting the driver to refuse
writes.

The check blanks out comments and string literals first, so:
- a query starting with ``-- note`` then ``SELECT …`` passes,
- ``SELECT 'a;b' FROM dual`` is *not* mistaken for two statements,
- ``SELECT … ; DELETE …``, ``BEGIN … END;`` and bare DML are rejected.
"""

from __future__ import annotations

import re

_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT = re.compile(r"--[^\n]*")
_STRING_LITERAL = re.compile(r"'(?:''|[^'])*'")

_ALLOWED_HEADS = {"select", "with"}


def _strip_noise(sql: str) -> str:
    """Remove comments and blank out string literals — leaving structure only."""
    sql = _BLOCK_COMMENT.sub(" ", sql)
    sql = _LINE_COMMENT.sub(" ", sql)
    sql = _STRING_LITERAL.sub("''", sql)
    return sql


def read_only_violation(sql: str) -> str | None:
    """Return a human-readable reason the SQL is *not* an allowed read-only
    statement, or None if it is fine."""
    structural = _strip_noise(sql).strip()
    # A single trailing semicolon is fine; anything after it is a second statement.
    structural = structural.rstrip(";").strip()
    if not structural:
        return "statement is empty"
    # Check the leading keyword first: a write or PL/SQL block (DELETE, BEGIN …)
    # gets the informative "SELECT / WITH only" reason rather than tripping the
    # multi-statement check on its internal semicolons.
    head = structural.split(None, 1)[0].lower()
    if head not in _ALLOWED_HEADS:
        return f"only SELECT / WITH queries are allowed (statement starts with '{head.upper()}')"
    if ";" in structural:
        return "multiple statements are not allowed (one read-only query per step)"
    return None
