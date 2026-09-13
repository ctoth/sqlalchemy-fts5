"""FTS5Table — factory for SQLAlchemy Table objects backed by FTS5 virtual tables."""

from __future__ import annotations

# pyright: reportUnusedFunction=false

from typing import Any

from sqlalchemy import Column, Connection, Integer, MetaData, String, Table, event, text

# Importing _ddl registers the @compiles handlers that intercept
# CreateTable/DropTable for FTS5-marked tables.
import sqlalchemy_fts5._ddl as _ddl

_DDL_HANDLERS = _ddl


def FTS5Table(
    name: str,
    metadata: MetaData,
    *,
    columns: list[str],
    content: Table | str | None = None,
    content_rowid: str | None = None,
    tokenize: str | None = None,
    prefix: str | None = None,
    detail: str | None = None,
    columnsize: int | None = None,
) -> Table:
    """Create a :class:`~sqlalchemy.Table` representing an FTS5 virtual table.

    The returned Table integrates with ``metadata.create_all()`` and
    ``metadata.drop_all()`` — the ``@compiles`` handlers in ``_ddl`` intercept
    the standard ``CreateTable`` / ``DropTable`` and emit FTS5 DDL instead.

    If *content* is provided (external content table), DDL triggers are
    automatically created to keep the FTS index in sync with the content table
    on INSERT, DELETE, and UPDATE. Existing content is indexed when the FTS
    table is first created.

    Args:
        name: Table name.
        metadata: SQLAlchemy MetaData to attach the table to.
        columns: FTS5 indexed column names.
        content: External content table (a Table object or table name string).
            When set, the FTS5 table stores no content itself and reads from
            the content table on demand.
        content_rowid: Column in the content table that maps to ``rowid``.
            Required for non-empty external *content*.
        tokenize: FTS5 tokenizer specification (e.g. ``"porter unicode61"``).
        prefix: Prefix index sizes (e.g. ``"2,3"``).
        detail: FTS5 detail mode: ``"full"``, ``"column"``, or ``"none"``.
        columnsize: Whether to store column sizes (0 or 1).

    Returns:
        A Table with FTS5 DDL, a ``rowid`` primary key column, and
        String columns for each indexed column.
    """
    if not columns:
        raise ValueError("FTS5 requires at least one indexed column")
    if content is not None and content != "" and not content_rowid:
        raise ValueError("content_rowid is required for external content")

    sa_columns: list[Column[Any]] = [Column("rowid", Integer, primary_key=True)]
    sa_columns.extend(Column(col, String) for col in columns)

    fts5_options: dict[str, Any] = {}
    if content is not None:
        fts5_options["content"] = content
    if content_rowid is not None:
        fts5_options["content_rowid"] = content_rowid
    if tokenize is not None:
        fts5_options["tokenize"] = tokenize
    if prefix is not None:
        fts5_options["prefix"] = prefix
    if detail is not None:
        fts5_options["detail"] = detail
    if columnsize is not None:
        fts5_options["columnsize"] = columnsize

    table = Table(
        name,
        metadata,
        *sa_columns,
        info={"fts5_columns": columns, "fts5_options": fts5_options},
    )

    # If there's an external content table, create sync triggers after
    # the FTS5 table is created, and drop them before it's dropped.
    if content is not None and content_rowid is not None:
        @event.listens_for(table, "after_create")
        def _create_triggers(
            target: Table, connection: Connection, **kw: Any
        ) -> None:
            _create_sync_triggers(connection, target, fts5_options, columns)
            preparer = connection.dialect.identifier_preparer
            table_name = _ddl.format_table_identifier(preparer, target)
            command_column = _ddl.quote_identifier(preparer, target.name)
            connection.exec_driver_sql(
                f"INSERT INTO {table_name}({command_column}) VALUES ('rebuild')"
            )

        @event.listens_for(table, "before_drop")
        def _drop_triggers(
            target: Table, connection: Connection, **kw: Any
        ) -> None:
            _drop_sync_triggers(connection, name)

    return table


def _create_sync_triggers(
    connection: Connection,
    fts_table: Table,
    options: dict[str, Any],
    columns: list[str],
) -> None:
    """Create INSERT/DELETE/UPDATE triggers to keep FTS index in sync.

    These triggers follow the pattern recommended by the SQLite FTS5
    documentation for external content tables.
    """
    preparer = connection.dialect.identifier_preparer
    fts_name = _ddl.format_table_identifier(preparer, fts_table)
    fts_command_column = _ddl.quote_identifier(preparer, fts_table.name)
    content_ref: Table | str = options["content"]
    content_name = _ddl.format_table_identifier(preparer, content_ref)
    rowid_col = _ddl.quote_identifier(preparer, options["content_rowid"])
    rowid = _ddl.quote_identifier(preparer, "rowid")

    quoted_columns = [_ddl.quote_identifier(preparer, column) for column in columns]
    col_list = ", ".join(quoted_columns)
    new_col_list = ", ".join(f"new.{column}" for column in quoted_columns)
    old_col_list = ", ".join(f"old.{column}" for column in quoted_columns)

    # INSERT trigger
    connection.execute(text(
        f"CREATE TRIGGER IF NOT EXISTS "
        f"{_ddl.quote_identifier(preparer, f'{fts_table.name}_ai')} "
        f"AFTER INSERT ON {content_name} "
        f"BEGIN"
        f"  INSERT INTO {fts_name}({rowid}, {col_list}) "
        f"VALUES (new.{rowid_col}, {new_col_list});"
        f" END"
    ))

    # DELETE trigger: uses FTS5 'delete' command to remove from index
    connection.execute(text(
        f"CREATE TRIGGER IF NOT EXISTS "
        f"{_ddl.quote_identifier(preparer, f'{fts_table.name}_ad')} "
        f"AFTER DELETE ON {content_name} "
        f"BEGIN"
        f"  INSERT INTO {fts_name}({fts_command_column}, {rowid}, {col_list})"
        f" VALUES('delete', old.{rowid_col}, {old_col_list});"
        f" END"
    ))

    # UPDATE trigger: delete old entry, insert new
    connection.execute(text(
        f"CREATE TRIGGER IF NOT EXISTS "
        f"{_ddl.quote_identifier(preparer, f'{fts_table.name}_au')} "
        f"AFTER UPDATE ON {content_name} "
        f"BEGIN"
        f"  INSERT INTO {fts_name}({fts_command_column}, {rowid}, {col_list})"
        f" VALUES('delete', old.{rowid_col}, {old_col_list});"
        f"  INSERT INTO {fts_name}({rowid}, {col_list}) "
        f"VALUES (new.{rowid_col}, {new_col_list});"
        f" END"
    ))


def _drop_sync_triggers(connection: Connection, fts_name: str) -> None:
    """Drop the INSERT/DELETE/UPDATE sync triggers."""
    preparer = connection.dialect.identifier_preparer
    for suffix in ("_ai", "_ad", "_au"):
        trigger_name = _ddl.quote_identifier(preparer, f"{fts_name}{suffix}")
        connection.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
