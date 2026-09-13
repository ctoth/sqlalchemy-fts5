"""Property tests for metadata ownership, schemas, and expression composition."""

from hypothesis import given, settings, strategies as st
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, literal, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table


@given(schema=st.sampled_from(["main", "attached"]), by_name=st.booleans())
@settings(deadline=None)
def test_external_sync_in_schema(schema: str, by_name: bool) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData(schema=schema)
        docs = Table("docs", meta, Column("id", Integer, primary_key=True), Column("body", String))
        fts = FTS5Table("idx", meta, columns=["body"], content=docs.name if by_name else docs, content_rowid="id")
        with engine.begin() as conn:
            if schema == "attached":
                conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS attached")
            meta.create_all(conn)
            conn.execute(docs.insert(), {"id": 1, "body": "alpha"})
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "alpha"))).scalars().all() == ["alpha"]
            conn.execute(docs.update().values(body="beta"))
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "alpha"))).all() == []
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "beta"))).scalars().all() == ["beta"]
            conn.execute(docs.delete())
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "beta"))).all() == []
            fts.drop(conn)
            assert conn.exec_driver_sql(f"SELECT name FROM {schema}.sqlite_master WHERE type='trigger'").all() == []
    finally:
        engine.dispose()


@given(rowid=st.sampled_from([None, "id", "row id"]))
@settings(deadline=None)
def test_contentless_tables_do_not_install_external_triggers(rowid: str | None) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData()
        fts = FTS5Table("idx", meta, columns=["body"], content="", content_rowid=rowid)
        meta.create_all(engine)
        with engine.begin() as conn:
            conn.execute(fts.insert(), {"rowid": 1, "body": "alpha"})
            assert conn.execute(select(fts.c.rowid).where(FTS5Match(fts, "alpha"))).scalars().all() == [1]
            assert conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all() == []
    finally:
        engine.dispose()


@given(extra=st.lists(st.sampled_from(["title", "summary"]), unique=True))
@settings(deadline=None)
def test_table_owns_column_configuration(extra: list[str]) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData()
        columns = ["body"]
        fts = FTS5Table("idx", meta, columns=columns)
        columns.clear()
        columns.extend(extra)
        meta.create_all(engine)
        with engine.begin() as conn:
            conn.execute(fts.insert(), {"body": "alpha"})
            assert conn.execute(select(fts.c.body).where(FTS5Match(fts, "alpha"))).scalars().all() == ["alpha"]
    finally:
        engine.dispose()


@given(term=st.sampled_from(["alpha", "beta", "gamma"]))
@settings(deadline=None)
def test_match_contributes_its_from_table(term: str) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData()
        fts = FTS5Table("idx", meta, columns=["body"])
        meta.create_all(engine)
        with engine.begin() as conn:
            conn.execute(fts.insert(), {"body": "alpha beta"})
            statement = select(literal(1)).where(FTS5Match(fts, term))
            assert conn.execute(statement).scalars().all() == ([1] if term != "gamma" else [])
    finally:
        engine.dispose()


@given(counts=st.lists(st.integers(0, 5), min_size=2, max_size=2))
@settings(deadline=None)
def test_match_statement_cache_distinguishes_schemas(counts: list[int]) -> None:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS attached")
            tables: list[Table] = []
            for schema, count in zip(["main", "attached"], counts):
                meta = MetaData(schema=schema)
                fts = FTS5Table("idx", meta, columns=["body"])
                meta.create_all(conn)
                for _ in range(count):
                    conn.execute(fts.insert(), {"body": "alpha"})
                tables.append(fts)
            for index in [0, 1, 0, 1]:
                statement = select(literal(1)).where(FTS5Match(tables[index], "alpha"))
                assert len(conn.execute(statement).all()) == counts[index]
    finally:
        engine.dispose()
