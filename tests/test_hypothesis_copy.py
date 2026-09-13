"""Copied SQLAlchemy metadata retains FTS synchronization behavior."""

from hypothesis import given, settings, strategies as st
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table


@given(values=st.lists(st.sampled_from(["alpha", "beta", "gamma"]), min_size=1, max_size=10))
@settings(deadline=None)
def test_copied_metadata_keeps_sync_events(values: list[str]) -> None:
    source = MetaData()
    docs = Table("docs", source, Column("id", Integer, primary_key=True), Column("body", String))
    fts = FTS5Table("idx", source, columns=["body"], content=docs, content_rowid="id")
    copied = MetaData()
    copied_docs = docs.to_metadata(copied)
    copied_fts = fts.to_metadata(copied)
    engine = create_engine("sqlite://")
    try:
        copied.create_all(engine)
        with engine.begin() as conn:
            for key, value in enumerate(values, 1):
                conn.execute(copied_docs.insert(), {"id": key, "body": value})
            for word in ("alpha", "beta", "gamma"):
                actual = conn.execute(select(copied_fts.c.rowid).where(FTS5Match(copied_fts, word))).scalars().all()
                assert actual == [key for key, value in enumerate(values, 1) if value == word]
            copied_fts.drop(conn)
            assert conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all() == []
    finally:
        engine.dispose()
