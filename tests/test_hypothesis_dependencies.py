"""FTS creation follows the dependencies of its external content table."""

from hypothesis import given, settings, strategies as st
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table, create_engine, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table


@given(by_name=st.booleans(), depth=st.integers(1, 5))
@settings(deadline=None)
def test_content_dependency_chain(by_name: bool, depth: int) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData()
        docs = Table(
            "docs", meta, Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent0.id")), Column("body", String),
        )
        fts = FTS5Table("idx", meta, columns=["body"], content=docs.name if by_name else docs, content_rowid="id")
        for index in range(depth):
            columns = [Column("id", Integer, primary_key=True)]
            if index + 1 < depth:
                columns.append(Column("parent_id", Integer, ForeignKey(f"parent{index + 1}.id")))
            Table(f"parent{index}", meta, *columns)
        meta.create_all(engine)
        with engine.begin() as conn:
            conn.execute(docs.insert(), {"id": 1, "body": "alpha"})
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "alpha"))).scalars().all() == ["alpha"]
        meta.drop_all(engine)
    finally:
        engine.dispose()
