"""Tests for FTS5Match expression."""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.engine import Engine

from sqlalchemy_fts5 import FTS5Match, FTS5Table


class TestFTS5Match:
    def test_compiles_to_match(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        expr = FTS5Match(fts, "hello")
        sql = str(expr.compile(dialect=engine.dialect))
        assert "t MATCH" in sql

    def test_parameterized(self, engine: Engine, metadata: MetaData) -> None:
        """MATCH value should be parameterized, not inlined."""
        fts = FTS5Table("t", metadata, columns=["title"])
        expr = FTS5Match(fts, "hello world")
        compiled = expr.compile(dialect=engine.dialect)
        # The query string should use a bind parameter, not the literal
        assert ":param" in str(compiled) or ":match" in str(compiled) or "?" in str(compiled)

    def test_in_where_clause(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title", "body"])
        stmt = select(fts.c.rowid, fts.c.title).where(FTS5Match(fts, "query"))
        sql = str(stmt.compile(dialect=engine.dialect))
        assert "WHERE" in sql
        assert "t MATCH" in sql

    def test_in_join(self, engine: Engine, metadata: MetaData) -> None:
        docs = Table("docs", metadata,
            Column("id", Integer, primary_key=True),
            Column("title", String),
        )
        fts = FTS5Table("docs_fts", metadata, columns=["title"])
        stmt = (
            select(docs.c.id, docs.c.title)
            .join(fts, docs.c.id == fts.c.rowid)
            .where(FTS5Match(fts, "search"))
        )
        sql = str(stmt.compile(dialect=engine.dialect))
        assert "JOIN" in sql
        assert "docs_fts MATCH" in sql

    def test_fts5_query_syntax(self, engine: Engine, metadata: MetaData) -> None:
        """FTS5 query syntax (AND, OR, NOT, prefix, column filter) passes through."""
        fts = FTS5Table("t", metadata, columns=["title", "body"])
        # These are all valid FTS5 query strings — they should pass through as-is
        for query in [
            "hello AND world",
            "hello OR world",
            "hello NOT world",
            "hello*",
            "title:hello",
            '"exact phrase"',
            "NEAR(hello world, 5)",
        ]:
            expr = FTS5Match(fts, query)
            sql = str(expr.compile(dialect=engine.dialect))
            assert "t MATCH" in sql
