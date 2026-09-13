"""Generated SQLite executions checked against an independent content model."""

from hypothesis import example, given, settings, strategies as st
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table, fts5_bm25, fts5_highlight, fts5_snippet


names = st.one_of(
    st.sampled_from(["select", "two words", 'a"b', "author's", ":param", "é漢字", "a.b", "a%b"]),
    st.text(alphabet="abcXYZ09 _-'\".:;%é漢", min_size=1, max_size=15),
)
words = ("alpha", "beta", "gamma")
documents = st.lists(st.sampled_from(words), min_size=0, max_size=8).map(" ".join)
operations = st.lists(
    st.tuples(st.sampled_from(["put", "delete", "move"]), st.integers(1, 5), documents),
    min_size=1, max_size=25,
)


@given(name=names, schema=st.sampled_from([None, "main", "attached"]))
@settings(max_examples=80, deadline=None)
def test_generated_names_support_all_query_helpers(name: str, schema: str | None) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData(schema=schema)
        fts = FTS5Table("fts " + name, meta, columns=["body"])
        with engine.begin() as conn:
            if schema == "attached":
                conn.exec_driver_sql("ATTACH DATABASE ':memory:' AS attached")
            meta.create_all(conn)
            conn.execute(fts.insert(), {"rowid": 1, "body": "alpha beta"})
            row = conn.execute(
                select(fts.c.rowid, fts5_bm25(fts), fts5_highlight(fts, 0), fts5_snippet(fts, 0))
                .where(FTS5Match(fts, "alpha"))
            ).one()
            assert row[0] == 1
            assert row[1] < 0
            assert row[2] == row[3] == "<b>alpha</b> beta"
            meta.drop_all(conn)
    finally:
        engine.dispose()


@given(name=names, initial=st.lists(documents, max_size=5), ops=operations, by_name=st.booleans())
@example(name=":param", initial=["alpha"], ops=[("put", 1, "beta")], by_name=True)
@settings(max_examples=80, deadline=None)
def test_external_content_operations_match_model(
    name: str, initial: list[str], ops: list[tuple[str, int, str]], by_name: bool,
) -> None:
    engine = create_engine("sqlite://")
    try:
        meta = MetaData()
        body = "body " + name
        rowid = "id " + name
        docs = Table("content " + name, meta, Column(rowid, Integer, primary_key=True), Column(body, String))
        model = dict(enumerate(initial, 1))
        with engine.begin() as conn:
            meta.create_all(conn)
            for key, value in model.items():
                conn.execute(docs.insert(), {rowid: key, body: value})
            fts = FTS5Table("fts " + name, meta, columns=[body], content=docs.name if by_name else docs, content_rowid=rowid)
            meta.create_all(conn)

            def check_model() -> None:
                for word in words:
                    expected = {key: value for key, value in model.items() if word in value.split()}
                    actual = dict(conn.execute(select(fts.c.rowid, fts.c[body]).where(FTS5Match(fts, word))).tuples().all())
                    assert actual == expected

            check_model()
            for operation, key, value in ops:
                if operation == "put":
                    if key in model:
                        conn.execute(docs.update().where(docs.c[rowid] == key).values({body: value}))
                    else:
                        conn.execute(docs.insert(), {rowid: key, body: value})
                    model[key] = value
                elif operation == "delete":
                    conn.execute(docs.delete().where(docs.c[rowid] == key))
                    model.pop(key, None)
                elif key in model:
                    destination = max(model) + 1
                    conn.execute(docs.update().where(docs.c[rowid] == key).values({rowid: destination}))
                    model[destination] = model.pop(key)
                check_model()
            # Recreating the index must recover the current model, without stale triggers.
            fts.drop(conn)
            fts.create(conn)
            check_model()
            meta.drop_all(conn)
            assert conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all() == []
    finally:
        engine.dispose()
