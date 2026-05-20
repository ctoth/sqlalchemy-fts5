"""FTS5 MATCH expression — table-level MATCH for full-text queries."""

from __future__ import annotations

# pyright: reportUnusedFunction=false

from typing import Any

from sqlalchemy import Table
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql import coercions, elements, operators, roles
from sqlalchemy.sql.base import Generative


class FTS5Match(Generative, elements.BinaryExpression[Any]):
    """Produce ``table MATCH :query`` for FTS5 full-text search.

    Usage::

        from sqlalchemy_fts5 import FTS5Match

        stmt = (
            select(Item)
            .join(items_fts, Item.id == items_fts.c.rowid)
            .where(FTS5Match(items_fts, "search terms"))
        )

    Generates::

        WHERE items_fts MATCH :param_1
    """

    __visit_name__ = "fts5_match"
    inherit_cache = True

    fts5_table: Table

    def __init__(self, table: Table, against: Any):
        self.fts5_table = table
        against = coercions.expect(roles.ExpressionElementRole, against)
        # Placeholder left side — the actual table name is rendered by @compiles
        left: elements.ColumnElement[Any] = elements.literal_column(table.name)
        super().__init__(left, against, operators.match_op)


@compiles(FTS5Match, "sqlite")
def _compile_fts5_match(element: FTS5Match, compiler: Any, **kw: Any) -> str:
    # Use the compiler's identifier preparer to properly quote the table name
    table_name = compiler.preparer.format_table(element.fts5_table)
    right = compiler.process(element.right, **kw)
    return f"{table_name} MATCH {right}"
