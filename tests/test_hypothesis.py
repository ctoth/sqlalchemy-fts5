"""Property-based tests for sqlalchemy-fts5 using Hypothesis."""

from __future__ import annotations

import string

from hypothesis import given, settings, assume
from hypothesis import strategies as st
from sqlalchemy import MetaData, create_engine, select

from sqlalchemy_fts5 import CreateFTS5Table, FTS5Match, FTS5Table, fts5_bm25


plain_identifier = st.text(
    alphabet=string.ascii_lowercase + "_",
    min_size=1,
    max_size=20,
).filter(lambda value: value[0] != "_")

identifier = st.one_of(
    plain_identifier,
    st.sampled_from(
        ["select", "two words", "hyphen-name", "2fast", 'quote"name', "author's"]
    ),
)

# FTS5 reserves rowid and rank as hidden column names.
column_name = identifier.filter(lambda value: value not in ("rowid", "rank"))

column_names = st.lists(column_name, min_size=1, max_size=10, unique=True)

table_name = identifier.filter(lambda value: value not in ("rowid", "rank"))

# Strategy for FTS5 tokenizer specs
tokenizer = st.sampled_from([
    None, "unicode61", "porter", "porter unicode61",
    "porter ascii", "unicode61 remove_diacritics 2",
])

# Strategy for search terms (alphanumeric, avoids FTS5 syntax chars)
search_term = st.text(
    alphabet=string.ascii_lowercase + " ",
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())


class TestDDLProperties:
    @given(name=table_name, cols=column_names, tok=tokenizer)
    @settings(max_examples=50)
    def test_ddl_always_valid_sql(
        self, name: str, cols: list[str], tok: str | None
    ) -> None:
        """Generated DDL is always syntactically valid."""
        engine = create_engine("sqlite:///:memory:")
        meta = MetaData()
        if tok is None:
            fts = FTS5Table(name, meta, columns=cols)
        else:
            fts = FTS5Table(name, meta, columns=cols, tokenize=tok)
        sql = str(CreateFTS5Table(fts).compile(dialect=engine.dialect))

        assert sql.startswith("CREATE VIRTUAL TABLE")
        assert "USING fts5(" in sql
        assert sql.endswith(")")
        # Every column name appears in the DDL
        for col in cols:
            assert col in sql

    @given(name=table_name, cols=column_names)
    @settings(max_examples=30)
    def test_create_and_use(self, name: str, cols: list[str]) -> None:
        """Any valid FTS5Table can be created and queried."""
        # FTS5 disallows column names that match the table name
        assume(name not in cols)
        engine = create_engine("sqlite:///:memory:")
        meta = MetaData()
        fts = FTS5Table(name, meta, columns=cols)
        meta.create_all(engine)

        with engine.connect() as conn:
            # Insert a row
            values: dict[str, object] = {"rowid": 1}
            for col in cols:
                values[col] = "test"
            conn.execute(fts.insert().values(values))
            conn.commit()

            # Query it back
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "test"))
            ).fetchall()
            assert len(result) == 1

        meta.drop_all(engine)


class TestSearchProperties:
    @given(term=search_term)
    @settings(max_examples=50)
    def test_match_compiles_for_any_term(self, term: str) -> None:
        """FTS5Match compiles for any search term."""
        engine = create_engine("sqlite:///:memory:")
        meta = MetaData()
        fts = FTS5Table("t", meta, columns=["body"])
        expr = FTS5Match(fts, term)
        sql = str(expr.compile(dialect=engine.dialect))
        assert "t MATCH" in sql

    @given(
        docs=st.lists(
            st.text(alphabet=string.ascii_lowercase + " ", min_size=1, max_size=100),
            min_size=1,
            max_size=20,
        )
    )
    @settings(max_examples=20)
    def test_insert_count_matches_query_count(self, docs: list[str]) -> None:
        """Number of inserted docs with a term matches MATCH result count."""
        engine = create_engine("sqlite:///:memory:")
        meta = MetaData()
        fts = FTS5Table("t", meta, columns=["body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            for i, doc in enumerate(docs):
                conn.execute(fts.insert().values(rowid=i + 1, body=doc))
            conn.commit()

            # Pick a word that appears in at least one doc
            all_words: set[str] = set()
            for doc in docs:
                all_words.update(w for w in doc.split() if w.strip())

            assume(len(all_words) > 0)
            search_word = sorted(all_words)[0]

            # Count docs containing the word
            expected = sum(1 for doc in docs if search_word in doc.split())

            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, search_word))
            ).fetchall()
            assert len(result) == expected

        meta.drop_all(engine)


class TestBM25Properties:
    @given(
        docs=st.lists(
            st.text(alphabet=string.ascii_lowercase + " ", min_size=3, max_size=80),
            min_size=2,
            max_size=10,
        )
    )
    @settings(max_examples=15)
    def test_bm25_returns_values_for_all_matches(self, docs: list[str]) -> None:
        """bm25() returns a value for every matching row."""
        engine = create_engine("sqlite:///:memory:")
        meta = MetaData()
        fts = FTS5Table("t", meta, columns=["body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            for i, doc in enumerate(docs):
                conn.execute(fts.insert().values(rowid=i + 1, body=doc))
            conn.commit()

            all_words: set[str] = set()
            for doc in docs:
                all_words.update(w for w in doc.split() if w.strip())
            assume(len(all_words) > 0)
            word = sorted(all_words)[0]

            stmt = (
                select(fts.c.rowid, fts5_bm25(fts).label("score"))
                .where(FTS5Match(fts, word))
                .order_by(fts5_bm25(fts))
            )
            rows = conn.execute(stmt).fetchall()
            # Every row should have a numeric bm25 score
            for row in rows:
                assert isinstance(row.score, (int, float))

        meta.drop_all(engine)
