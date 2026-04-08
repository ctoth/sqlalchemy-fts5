"""Tests for FTS5 auxiliary functions."""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.engine import Engine

from sqlalchemy_fts5 import FTS5Table, fts5_bm25, fts5_highlight, fts5_snippet


class TestBM25:
    def test_compiles(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        sql = str(fts5_bm25(fts).compile(dialect=engine.dialect))
        assert "bm25(t)" in sql


class TestHighlight:
    def test_default_tags(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title", "body"])
        sql = str(fts5_highlight(fts, 0).compile(dialect=engine.dialect))
        assert "highlight(t" in sql

    def test_custom_tags(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        sql = str(fts5_highlight(fts, 0, "<em>", "</em>").compile(dialect=engine.dialect))
        assert "highlight(t" in sql

    def test_column_index(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title", "body"])
        sql = str(fts5_highlight(fts, 1).compile(dialect=engine.dialect))
        assert "highlight(t" in sql


class TestSnippet:
    def test_default(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        sql = str(fts5_snippet(fts, 0).compile(dialect=engine.dialect))
        assert "snippet(t" in sql

    def test_custom_params(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        sql = str(
            fts5_snippet(fts, 0, "<mark>", "</mark>", "---", 32)
            .compile(dialect=engine.dialect)
        )
        assert "snippet(t" in sql
