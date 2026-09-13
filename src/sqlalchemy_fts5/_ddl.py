"""DDL constructs for FTS5 virtual tables.

Two mechanisms for emitting FTS5 DDL:

1. **Explicit**: ``CreateFTS5Table(table)`` / ``DropFTS5Table(table)`` — custom DDL
   elements with their own ``@compiles`` handlers.

2. **Implicit via metadata.create_all()**: We intercept the standard
   ``CreateTable`` and ``DropTable`` compilation for tables that have
   ``fts5_columns`` in their ``table.info``, and emit FTS5 DDL instead.
"""

from __future__ import annotations

# pyright: reportUnusedFunction=false

from typing import Any

from sqlalchemy import Table
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.compiler import IdentifierPreparer
from sqlalchemy.sql.ddl import CreateTable, DropTable, ExecutableDDLElement


def _is_fts5_table(table: Table) -> bool:
    """Check if a Table was created by FTS5Table()."""
    return bool(table.info.get("fts5_columns"))


def quote_identifier(preparer: IdentifierPreparer, identifier: str) -> str:
    """Render one SQLite identifier according to the active dialect."""
    return preparer.quote(identifier)


def format_table_identifier(
    preparer: IdentifierPreparer, table: Table | str
) -> str:
    """Render a Table or public string table name as an identifier."""
    if isinstance(table, Table):
        return preparer.format_table(table)
    return quote_identifier(preparer, table)


def _render_fts5_string_literal(value: str) -> str:
    """Render an FTS5 option value as a SQLite string literal."""
    return "'" + value.replace("'", "''") + "'"


def _render_fts5_create(table: Table, compiler: Any, if_not_exists: bool = False) -> str:
    """Render CREATE VIRTUAL TABLE ... USING fts5(...)."""
    info = table.info
    fts_columns: list[str] = info.get("fts5_columns", [])
    options: dict[str, Any] = info.get("fts5_options", {})
    preparer: IdentifierPreparer = compiler.preparer

    parts = [quote_identifier(preparer, column) for column in fts_columns]

    if "content" in options:
        content_ref: Table | str = options["content"]
        # FTS5 quotes these names itself when reading the content table.
        content_name = content_ref.name if isinstance(content_ref, Table) else content_ref
        parts.append(f"content={_render_fts5_string_literal(content_name)}")

    if "content_rowid" in options:
        content_rowid: str = options["content_rowid"]
        parts.append(f"content_rowid={_render_fts5_string_literal(content_rowid)}")

    if "tokenize" in options:
        tokenize: str = options["tokenize"]
        parts.append(f"tokenize={_render_fts5_string_literal(tokenize)}")

    if "prefix" in options:
        prefix: str = options["prefix"]
        parts.append(f"prefix={_render_fts5_string_literal(prefix)}")

    if "detail" in options:
        parts.append(f"detail={options['detail']}")

    if "columnsize" in options:
        parts.append(f"columnsize={options['columnsize']}")

    table_name = format_table_identifier(preparer, table)
    column_spec = ", ".join(parts)
    maybe_ine = "IF NOT EXISTS " if if_not_exists else ""

    return f"CREATE VIRTUAL TABLE {maybe_ine}{table_name} USING fts5({column_spec})"


def _render_fts5_drop(table: Table, compiler: Any, if_exists: bool = False) -> str:
    """Render DROP TABLE for an FTS5 virtual table."""
    preparer: IdentifierPreparer = compiler.preparer
    table_name = format_table_identifier(preparer, table)
    maybe_ie = "IF EXISTS " if if_exists else ""
    return f"DROP TABLE {maybe_ie}{table_name}"


# ---------------------------------------------------------------------------
# Explicit DDL elements (for direct use)
# ---------------------------------------------------------------------------


class CreateFTS5Table(ExecutableDDLElement):
    """Emit ``CREATE VIRTUAL TABLE ... USING fts5(...)``."""

    __visit_name__ = "create_fts5_table"
    inherit_cache = False
    element: Table
    if_not_exists: bool

    def __init__(self, table: Table, *, if_not_exists: bool = False):
        self.element = table
        self.if_not_exists = if_not_exists


class DropFTS5Table(ExecutableDDLElement):
    """Emit ``DROP TABLE`` for an FTS5 virtual table."""

    __visit_name__ = "drop_fts5_table"
    inherit_cache = False
    element: Table
    if_exists: bool

    def __init__(self, table: Table, *, if_exists: bool = False):
        self.element = table
        self.if_exists = if_exists


@compiles(CreateFTS5Table, "sqlite")
def _compile_create_fts5_explicit(
    element: CreateFTS5Table, compiler: Any, **kw: Any
) -> str:
    return _render_fts5_create(element.element, compiler, element.if_not_exists)


@compiles(DropFTS5Table, "sqlite")
def _compile_drop_fts5_explicit(
    element: DropFTS5Table, compiler: Any, **kw: Any
) -> str:
    return _render_fts5_drop(element.element, compiler, element.if_exists)


# ---------------------------------------------------------------------------
# Implicit: intercept CreateTable / DropTable for FTS5 tables
# ---------------------------------------------------------------------------
# When metadata.create_all() fires, it creates a CreateTable for every table.
# We intercept that and substitute FTS5 DDL for tables marked as FTS5.
#
# We save and chain to the original compiler so non-FTS5 tables are unaffected.

_original_create_table = CreateTable.__dict__.get("_compiler_dispatcher", None)
_original_drop_table = DropTable.__dict__.get("_compiler_dispatcher", None)


@compiles(CreateTable, "sqlite")
def _compile_create_table_with_fts5(
    element: CreateTable, compiler: Any, **kw: Any
) -> str:
    table: Table = element.element
    if _is_fts5_table(table):
        return _render_fts5_create(table, compiler, element.if_not_exists)
    # Fall through to SQLAlchemy's default CreateTable compilation
    return compiler.visit_create_table(element, **kw)


@compiles(DropTable, "sqlite")
def _compile_drop_table_with_fts5(
    element: DropTable, compiler: Any, **kw: Any
) -> str:
    table: Table = element.element
    if _is_fts5_table(table):
        return _render_fts5_drop(table, compiler, element.if_exists)
    return compiler.visit_drop_table(element, **kw)
