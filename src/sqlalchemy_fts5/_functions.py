"""FTS5 auxiliary functions — bm25, highlight, snippet."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Table, func
from sqlalchemy.sql import expression
from sqlalchemy.sql.functions import Function


def fts5_bm25(table: Table) -> Function[Any]:
    """FTS5 ``bm25()`` ranking function.

    Returns a value where more-negative = better match.
    Use in ORDER BY for relevance ranking::

        stmt = (
            select(Item)
            .where(FTS5Match(fts, "query"))
            .order_by(fts5_bm25(fts))
        )
    """
    return func.bm25(expression.literal_column(table.name))


def fts5_highlight(
    table: Table,
    column_index: int,
    open_tag: str = "<b>",
    close_tag: str = "</b>",
) -> Function[Any]:
    """FTS5 ``highlight()`` function.

    Returns the text of the specified column with matching terms wrapped
    in *open_tag* / *close_tag*::

        stmt = select(fts5_highlight(fts, 0, "<em>", "</em>"))

    Args:
        table: The FTS5 table.
        column_index: 0-based index of the column to highlight.
        open_tag: Markup inserted before each match.
        close_tag: Markup inserted after each match.
    """
    return func.highlight(
        expression.literal_column(table.name),
        column_index,
        open_tag,
        close_tag,
    )


def fts5_snippet(
    table: Table,
    column_index: int,
    open_tag: str = "<b>",
    close_tag: str = "</b>",
    ellipsis: str = "...",
    max_tokens: int = 64,
) -> Function[Any]:
    """FTS5 ``snippet()`` function.

    Like *highlight* but returns a short fragment of text around the match::

        stmt = select(fts5_snippet(fts, 0, max_tokens=30))

    Args:
        table: The FTS5 table.
        column_index: 0-based index of the column.
        open_tag: Markup inserted before each match.
        close_tag: Markup inserted after each match.
        ellipsis: Placeholder for omitted surrounding text.
        max_tokens: Approximate maximum tokens in the returned snippet.
    """
    return func.snippet(
        expression.literal_column(table.name),
        column_index,
        open_tag,
        close_tag,
        ellipsis,
        max_tokens,
    )
