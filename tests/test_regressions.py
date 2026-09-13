"""Runtime regressions for FTS5 table setup and queries."""

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, select
from sqlalchemy.engine import Engine

from sqlalchemy_fts5 import FTS5Match, FTS5Table, fts5_highlight


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
