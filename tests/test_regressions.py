"""Runtime regressions for FTS5 table setup and queries."""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.engine import Engine

from sqlalchemy_fts5 import FTS5Match, FTS5Table, fts5_bm25, fts5_highlight, fts5_snippet


@pytest.mark.parametrize("by_name", [False, True])
def test_external_content_reads_quoted_names(engine: Engine, by_name: bool) -> None:
    meta = MetaData()
    docs = Table(
        "content's table", meta,
        Column('row"id', Integer, primary_key=True), Column("body", String),
    )
    fts = FTS5Table(
        "idx", meta, columns=["body"],
        content=docs.name if by_name else docs, content_rowid='row"id',
    )
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(docs.insert(), {'row"id': 1, "body": "hello world"})
        row = conn.execute(
            select(fts.c.body, fts5_highlight(fts, 0))
            .where(FTS5Match(fts, "hello"))
        ).one()
        assert tuple(row) == ("hello world", "<b>hello</b> world")


def test_index_existing_content_and_keep_it_synced(engine: Engine) -> None:
    meta = MetaData()
    docs = Table("docs", meta, Column("id", Integer, primary_key=True), Column("body", String))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(docs.insert(), [{"id": 1, "body": "hello"}, {"id": 2, "body": "hello"}])
    fts = FTS5Table("idx", meta, columns=["body"], content=docs, content_rowid="id")
    meta.create_all(engine)
    with engine.begin() as conn:
        assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "hello"))).scalars().all() == [1, 2]
        conn.execute(docs.update().where(docs.c.id == 1).values(body="world"))
        conn.execute(docs.delete().where(docs.c.id == 2))
        assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "hello"))).all() == []
        assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "world"))).scalars().all() == [1]
    meta.create_all(engine)
    with engine.connect() as conn:
        assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "world"))).scalars().all() == [1]


@pytest.mark.parametrize("name", ["search index", "select", 'quote"name', "hyphen-name"])
def test_auxiliary_functions_quote_names(engine: Engine, name: str) -> None:
    meta = MetaData()
    fts = FTS5Table(name, meta, columns=["body"])
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(fts.insert(), {"body": "hello world"})
        assert conn.execute(select(fts5_bm25(fts)).select_from(fts).where(FTS5Match(fts, "hello"))).scalar_one() < 0
        for expression in [fts5_highlight(fts, 0), fts5_snippet(fts, 0)]:
            assert conn.execute(select(expression).select_from(fts).where(FTS5Match(fts, "hello"))).scalar_one() == "<b>hello</b> world"


@pytest.mark.parametrize("schema", ["main", "attached"])
def test_schema_qualified_match(engine: Engine, schema: str) -> None:
    meta = MetaData(schema=schema)
    fts = FTS5Table("search index", meta, columns=["body"])
    with engine.begin() as conn:
        if schema == "attached":
            conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS attached")
        meta.create_all(conn)
        conn.execute(fts.insert(), {"rowid": 1, "body": "hello"})
        assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "hello"))).scalars().all() == [1]


def test_empty_columns_rejected_before_metadata_mutation() -> None:
    meta = MetaData()
    with pytest.raises(ValueError, match="at least one"):
        FTS5Table("idx", meta, columns=[])
    assert not meta.tables


@pytest.mark.parametrize("rowid", [None, ""])
def test_external_content_requires_rowid(rowid: str | None) -> None:
    meta = MetaData()
    with pytest.raises(ValueError, match="content_rowid"):
        FTS5Table("idx", meta, columns=["body"], content="docs", content_rowid=rowid)
    assert not meta.tables


def test_trigger_identifiers_are_not_bind_parameters(engine: Engine) -> None:
    meta = MetaData()
    docs = Table("content :param", meta, Column("id", Integer, primary_key=True), Column("body", String))
    fts = FTS5Table("fts :param", meta, columns=["body"], content=docs, content_rowid="id")
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.execute(docs.insert(), {"id": 1, "body": "alpha"})
        assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "alpha"))).scalars().all() == ["alpha"]
    meta.drop_all(engine)
