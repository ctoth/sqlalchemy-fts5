"""Tests for FTS5 DDL generation."""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine

from sqlalchemy_fts5 import CreateFTS5Table, DropFTS5Table, FTS5Table


class TestCreateFTS5Table:
    def test_basic_columns(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a", "b"])
        sql = CreateFTS5Table(fts).compile(dialect=engine.dialect)
        assert str(sql) == "CREATE VIRTUAL TABLE t USING fts5(a, b)"

    def test_single_column(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["title"])
        sql = CreateFTS5Table(fts).compile(dialect=engine.dialect)
        assert str(sql) == "CREATE VIRTUAL TABLE t USING fts5(title)"

    def test_content_table_by_object(
        self, engine: Engine, metadata: MetaData, content_table: Table
    ) -> None:
        fts = FTS5Table(
            "docs_fts", metadata, columns=["title", "body"],
            content=content_table, content_rowid="id",
        )
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "content='docs'" in sql
        assert "content_rowid='id'" in sql

    def test_content_table_by_name(
        self, engine: Engine, metadata: MetaData
    ) -> None:
        fts = FTS5Table(
            "docs_fts", metadata, columns=["title"],
            content="docs", content_rowid="id",
        )
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "content='docs'" in sql

    def test_tokenizer(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table(
            "t", metadata, columns=["a"],
            tokenize="porter unicode61",
        )
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "tokenize='porter unicode61'" in sql

    def test_prefix(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"], prefix="2,3")
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "prefix='2,3'" in sql

    def test_detail(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"], detail="column")
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "detail=column" in sql

    def test_columnsize(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"], columnsize=0)
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "columnsize=0" in sql

    def test_if_not_exists(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"])
        sql = CreateFTS5Table(fts, if_not_exists=True).compile(dialect=engine.dialect)
        assert "IF NOT EXISTS" in str(sql)

    def test_all_options_together(
        self, engine: Engine, metadata: MetaData, content_table: Table
    ) -> None:
        fts = FTS5Table(
            "docs_fts", metadata, columns=["title", "body"],
            content=content_table, content_rowid="id",
            tokenize="porter", prefix="2,3",
            detail="full", columnsize=1,
        )
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))
        assert "USING fts5(" in sql
        assert "title, body" in sql
        assert "content='docs'" in sql
        assert "content_rowid='id'" in sql
        assert "tokenize='porter'" in sql
        assert "prefix='2,3'" in sql
        assert "detail=full" in sql
        assert "columnsize=1" in sql


class TestDropFTS5Table:
    def test_basic_drop(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"])
        sql = DropFTS5Table(fts).compile(dialect=engine.dialect)
        assert str(sql) == "DROP TABLE t"

    def test_if_exists(self, engine: Engine, metadata: MetaData) -> None:
        fts = FTS5Table("t", metadata, columns=["a"])
        sql = DropFTS5Table(fts, if_exists=True).compile(dialect=engine.dialect)
        assert "IF EXISTS" in str(sql)


class TestMetadataCreateAll:
    def test_create_all_emits_fts5_ddl(self, engine: Engine) -> None:
        """metadata.create_all() should create the FTS5 virtual table."""
        meta = MetaData()
        FTS5Table("test_fts", meta, columns=["title", "body"])
        meta.create_all(engine)

        # Verify the FTS5 table exists and works
        with engine.connect() as conn:
            conn.execute(
                meta.tables["test_fts"].insert().values(
                    rowid=1, title="hello", body="world"
                )
            )
            conn.commit()
            result = conn.execute(
                meta.tables["test_fts"].select()
            ).fetchall()
            assert len(result) == 1

    def test_create_all_with_content_table(self, engine: Engine) -> None:
        """metadata.create_all() creates both content table and FTS5 index."""
        meta = MetaData()
        docs = Table(
            "docs", meta,
            Column("id", Integer, primary_key=True),
            Column("title", String),
            Column("body", String),
        )
        FTS5Table(
            "docs_fts", meta, columns=["title", "body"],
            content=docs, content_rowid="id",
        )
        meta.create_all(engine)

        # Both tables should exist
        with engine.connect() as conn:
            conn.execute(docs.insert().values(id=1, title="hi", body="there"))
            conn.commit()

    def test_drop_all(self, engine: Engine) -> None:
        """metadata.drop_all() should drop FTS5 tables cleanly."""
        meta = MetaData()
        FTS5Table("test_fts", meta, columns=["title"])
        meta.create_all(engine)
        meta.drop_all(engine)  # should not raise
