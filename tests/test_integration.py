"""Integration tests — real SQLite FTS5 operations end to end."""

from __future__ import annotations

from sqlalchemy import Column, Integer, MetaData, String, Table, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from sqlalchemy_fts5 import FTS5Match, FTS5Table, fts5_bm25, fts5_highlight, fts5_snippet


# ---------------------------------------------------------------------------
# Standalone FTS5 (no content table)
# ---------------------------------------------------------------------------


class TestStandaloneFTS5:
    def test_insert_and_match(self, engine: Engine) -> None:
        """Insert rows and retrieve via MATCH."""
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["title", "body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, title="Python SQLAlchemy", body="ORM for databases"))
            conn.execute(fts.insert().values(rowid=2, title="Rust Diesel", body="ORM for Rust"))
            conn.execute(fts.insert().values(rowid=3, title="JavaScript Prisma", body="TypeScript ORM"))
            conn.commit()

            result = conn.execute(
                select(fts.c.rowid, fts.c.title).where(FTS5Match(fts, "Python"))
            ).fetchall()
            assert len(result) == 1
            assert result[0].rowid == 1
            assert result[0].title == "Python SQLAlchemy"

    def test_no_results(self, engine: Engine) -> None:
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["title"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, title="hello"))
            conn.commit()
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "nonexistent"))
            ).fetchall()
            assert len(result) == 0

    def test_bm25_ordering(self, engine: Engine) -> None:
        """bm25() returns values usable for ORDER BY."""
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["title", "body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            # Row 1 has "database" in both columns — should rank higher
            conn.execute(fts.insert().values(rowid=1, title="database", body="database database"))
            conn.execute(fts.insert().values(rowid=2, title="database", body="something else"))
            conn.commit()

            stmt = (
                select(fts.c.rowid)
                .where(FTS5Match(fts, "database"))
                .order_by(fts5_bm25(fts))
            )
            rows = conn.execute(stmt).fetchall()
            assert len(rows) == 2
            # Row 1 should rank first (more negative bm25 = better match)
            assert rows[0].rowid == 1

    def test_highlight(self, engine: Engine) -> None:
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["title", "body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, title="hello world", body="test"))
            conn.commit()

            stmt = (
                select(fts5_highlight(fts, 0, "[", "]"))
                .select_from(fts)
                .where(FTS5Match(fts, "hello"))
            )
            result = conn.execute(stmt).scalar()
            assert result is not None
            assert "[hello]" in result

    def test_snippet(self, engine: Engine) -> None:
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(
                rowid=1, body="the quick brown fox jumps over the lazy dog near the river"
            ))
            conn.commit()

            stmt = (
                select(fts5_snippet(fts, 0, "[", "]", "...", 5))
                .select_from(fts)
                .where(FTS5Match(fts, "fox"))
            )
            result = conn.execute(stmt).scalar()
            assert result is not None
            assert "[fox]" in result

    def test_multiple_match_terms(self, engine: Engine) -> None:
        """FTS5 query syntax works through MATCH."""
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["title", "body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, title="Python tutorial", body="learn Python basics"))
            conn.execute(fts.insert().values(rowid=2, title="Rust tutorial", body="learn Rust basics"))
            conn.execute(fts.insert().values(rowid=3, title="Python advanced", body="advanced Python patterns"))
            conn.commit()

            # AND query
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "Python AND tutorial"))
            ).fetchall()
            assert len(result) == 1
            assert result[0].rowid == 1

            # OR query
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "Python OR Rust"))
            ).fetchall()
            assert len(result) == 3

            # Prefix query
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "Pyth*"))
            ).fetchall()
            assert len(result) == 2

    def test_phrase_query(self, engine: Engine) -> None:
        meta = MetaData()
        fts = FTS5Table("articles", meta, columns=["body"])
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, body="the quick brown fox"))
            conn.execute(fts.insert().values(rowid=2, body="brown quick fox"))
            conn.commit()

            # Exact phrase
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, '"quick brown"'))
            ).fetchall()
            assert len(result) == 1
            assert result[0].rowid == 1

    def test_drop_all_after_create(self, engine: Engine) -> None:
        """Tables created with create_all can be dropped with drop_all."""
        meta = MetaData()
        FTS5Table("test_fts", meta, columns=["a"])
        meta.create_all(engine)
        meta.drop_all(engine)
        # Recreate — should not raise
        meta.create_all(engine)


# ---------------------------------------------------------------------------
# External content table with sync triggers
# ---------------------------------------------------------------------------


class TestContentSync:
    def _setup(self, engine: Engine) -> tuple[MetaData, Table, Table]:
        meta = MetaData()
        docs = Table(
            "docs", meta,
            Column("id", Integer, primary_key=True),
            Column("title", String),
            Column("body", String),
        )
        fts = FTS5Table(
            "docs_fts", meta, columns=["title", "body"],
            content=docs, content_rowid="id",
        )
        meta.create_all(engine)
        return meta, docs, fts

    def test_insert_syncs(self, engine: Engine) -> None:
        """INSERT into content table triggers FTS index update."""
        _, docs, fts = self._setup(engine)

        with engine.connect() as conn:
            conn.execute(docs.insert().values(id=1, title="hello", body="world"))
            conn.commit()

            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "hello"))
            ).fetchall()
            assert len(result) == 1
            assert result[0].rowid == 1

    def test_delete_syncs(self, engine: Engine) -> None:
        """DELETE from content table removes from FTS index."""
        _, docs, fts = self._setup(engine)

        with engine.connect() as conn:
            conn.execute(docs.insert().values(id=1, title="hello", body="world"))
            conn.commit()

            conn.execute(docs.delete().where(docs.c.id == 1))
            conn.commit()

            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "hello"))
            ).fetchall()
            assert len(result) == 0

    def test_update_syncs(self, engine: Engine) -> None:
        """UPDATE on content table updates FTS index."""
        _, docs, fts = self._setup(engine)

        with engine.connect() as conn:
            conn.execute(docs.insert().values(id=1, title="hello", body="world"))
            conn.commit()

            conn.execute(docs.update().where(docs.c.id == 1).values(title="goodbye"))
            conn.commit()

            # Old term should not match
            old = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "hello"))
            ).fetchall()
            assert len(old) == 0

            # New term should match
            new = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "goodbye"))
            ).fetchall()
            assert len(new) == 1

    def test_bulk_insert(self, engine: Engine) -> None:
        """Multiple inserts all get indexed."""
        _, docs, fts = self._setup(engine)

        with engine.connect() as conn:
            conn.execute(docs.insert(), [
                {"id": i, "title": f"doc {i}", "body": f"body of document {i}"}
                for i in range(1, 51)
            ])
            conn.commit()

            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "document"))
            ).fetchall()
            assert len(result) == 50

    def test_triggers_dropped_on_drop_all(self, engine: Engine) -> None:
        """drop_all cleans up sync triggers."""
        meta, _, _ = self._setup(engine)
        meta.drop_all(engine)

        # Verify triggers are gone
        with engine.connect() as conn:
            triggers = conn.execute(text(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )).fetchall()
            trigger_names = [t[0] for t in triggers]
            assert "docs_fts_ai" not in trigger_names
            assert "docs_fts_ad" not in trigger_names
            assert "docs_fts_au" not in trigger_names


# ---------------------------------------------------------------------------
# ORM mapping
# ---------------------------------------------------------------------------


class TestORMMapping:
    def test_mapped_model(self, engine: Engine) -> None:
        """FTS5 table can be used with SQLAlchemy ORM and Mapped[] types."""

        class Base(DeclarativeBase):
            pass

        docs = Table(
            "docs", Base.metadata,
            Column("id", Integer, primary_key=True),
            Column("title", String),
            Column("body", String),
        )

        fts = FTS5Table(
            "docs_fts", Base.metadata, columns=["title", "body"],
            content=docs, content_rowid="id",
        )

        class Doc(Base):
            __table__ = docs
            id: Mapped[int]
            title: Mapped[str | None]
            body: Mapped[str | None]

        Base.metadata.create_all(engine)

        with Session(engine) as session:
            session.add(Doc(id=1, title="Python ORM", body="SQLAlchemy is great"))
            session.add(Doc(id=2, title="Rust ORM", body="Diesel is great"))
            session.commit()

        # Query using Core expression with ORM table
        with engine.connect() as conn:
            result = conn.execute(
                select(docs.c.id, docs.c.title)
                .join(fts, docs.c.id == fts.c.rowid)
                .where(FTS5Match(fts, "Python"))
            ).fetchall()
            assert len(result) == 1
            assert result[0].title == "Python ORM"

    def test_tokenizer(self, engine: Engine) -> None:
        """Porter tokenizer stemming works."""
        meta = MetaData()
        fts = FTS5Table("t", meta, columns=["body"], tokenize="porter unicode61")
        meta.create_all(engine)

        with engine.connect() as conn:
            conn.execute(fts.insert().values(rowid=1, body="running quickly"))
            conn.commit()

            # "run" should match "running" via porter stemmer
            result = conn.execute(
                select(fts.c.rowid).where(FTS5Match(fts, "run"))
            ).fetchall()
            assert len(result) == 1
