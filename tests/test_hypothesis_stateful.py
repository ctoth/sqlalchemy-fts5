"""Exercise index consistency across arbitrary transactional histories."""

from hypothesis import settings, strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table


text_values = st.one_of(
    st.none(),
    st.lists(st.sampled_from(["alpha", "beta", "gamma"]), max_size=6).map(" ".join),
)


class ContentTransactions(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.engine = create_engine("sqlite://")
        self.conn = self.engine.connect()
        self.meta = MetaData()
        self.docs = Table(
            "docs", self.meta, Column("id", Integer, primary_key=True),
            Column("title", String), Column("body", String),
        )
        self.fts = FTS5Table(
            "idx", self.meta, columns=["title", "body"],
            content=self.docs, content_rowid="id",
        )
        self.meta.create_all(self.conn)
        self.conn.commit()
        # Explicit BEGIN makes SQLite DDL and SAVEPOINT rollback transactional,
        # including Python versions with the driver's legacy transaction mode.
        self.conn.exec_driver_sql("BEGIN")
        self.pending: dict[int, tuple[str | None, str | None]] = {}
        self.committed: dict[int, tuple[str | None, str | None]] = {}

    @rule(key=st.integers(-3, 5), title=text_values, body=text_values, undo=st.booleans())
    def put(self, key: int, title: str | None, body: str | None, undo: bool) -> None:
        savepoint = self.conn.begin_nested()
        if key in self.pending:
            self.conn.execute(self.docs.update().where(self.docs.c.id == key).values(title=title, body=body))
        else:
            self.conn.execute(self.docs.insert(), {"id": key, "title": title, "body": body})
        if undo:
            savepoint.rollback()
        else:
            savepoint.commit()
            self.pending[key] = (title, body)

    @rule(key=st.integers(-3, 5))
    def delete(self, key: int) -> None:
        self.conn.execute(self.docs.delete().where(self.docs.c.id == key))
        self.pending.pop(key, None)

    @rule()
    def commit(self) -> None:
        self.conn.commit()
        self.committed = self.pending.copy()
        self.conn.exec_driver_sql("BEGIN")

    @rule()
    def rollback(self) -> None:
        self.conn.rollback()
        self.pending = self.committed.copy()
        self.conn.exec_driver_sql("BEGIN")

    @rule()
    def recreate(self) -> None:
        self.fts.drop(self.conn)
        self.fts.create(self.conn)

    @invariant()
    def index_matches_content(self) -> None:
        for word in ("alpha", "beta", "gamma"):
            expected = {
                key: value for key, value in self.pending.items()
                if any(word in (field or "").split() for field in value)
            }
            rows = self.conn.execute(
                select(self.fts.c.rowid, self.fts.c.title, self.fts.c.body)
                .where(FTS5Match(self.fts, word))
            ).all()
            assert {row[0]: (row[1], row[2]) for row in rows} == expected
        # Ask SQLite to compare the entire index with its external content.
        self.conn.exec_driver_sql("INSERT INTO idx(idx, rank) VALUES ('integrity-check', 1)")

    def teardown(self) -> None:
        self.conn.close()
        self.engine.dispose()


# Hypothesis constructs this unittest class dynamically without a return annotation.
TestContentTransactions = ContentTransactions.TestCase  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
TestContentTransactions.settings = settings(max_examples=100, stateful_step_count=50, deadline=None)
