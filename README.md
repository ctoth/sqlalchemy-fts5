# sqlalchemy-fts5

SQLite FTS5 full-text search for SQLAlchemy 2.0+.

Nobody has built this properly yet. Peewee has `FTS5Model` but will never support type hints. SQLAlchemy has great typing but zero FTS5 support. This fills the gap.

## Install

```
pip install sqlalchemy-fts5
```

Requires SQLAlchemy 2.0+ and a SQLite build with FTS5 enabled (most are).

## Quick start

```python
from sqlalchemy import Column, Integer, String, MetaData, Table, create_engine, select
from sqlalchemy_fts5 import FTS5Table, FTS5Match, fts5_bm25

engine = create_engine("sqlite:///my.db")
meta = MetaData()

# Create an FTS5 virtual table
docs = FTS5Table("docs", meta, columns=["title", "body"])
meta.create_all(engine)

# Insert
with engine.connect() as conn:
    conn.execute(docs.insert().values(rowid=1, title="Python", body="SQLAlchemy is good"))
    conn.execute(docs.insert().values(rowid=2, title="Rust", body="Diesel is also good"))
    conn.commit()

# Search
with engine.connect() as conn:
    results = conn.execute(
        select(docs.c.rowid, docs.c.title)
        .where(FTS5Match(docs, "Python"))
        .order_by(fts5_bm25(docs))
    ).fetchall()
```

## External content tables

FTS5 can index a regular table without duplicating the data. Sync triggers are created automatically.

```python
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

class Base(DeclarativeBase):
    pass

class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    body: Mapped[str]

articles_fts = FTS5Table(
    "articles_fts", Base.metadata,
    columns=["title", "body"],
    content=Article.__table__,
    content_rowid="id",
)

Base.metadata.create_all(engine)

# Inserts/updates/deletes on the articles table automatically
# update the FTS index via triggers. Just query:
with engine.connect() as conn:
    results = conn.execute(
        select(Article.__table__)
        .join(articles_fts, Article.id == articles_fts.c.rowid)
        .where(FTS5Match(articles_fts, "search terms"))
    ).fetchall()
```

## FTS5 options

```python
FTS5Table(
    "docs", meta,
    columns=["title", "body"],
    tokenize="porter unicode61",   # stemming
    prefix="2,3",                   # prefix indexes for faster prefix queries
    content=other_table,            # external content
    content_rowid="id",             # rowid mapping
    detail="full",                  # detail mode: full, column, or none
    columnsize=0,                   # disable column size storage
)
```

## Auxiliary functions

```python
from sqlalchemy_fts5 import fts5_bm25, fts5_highlight, fts5_snippet

# Relevance ranking (lower = better match)
select(docs.c.rowid).order_by(fts5_bm25(docs))

# Highlight matches in text
select(fts5_highlight(docs, 0, "<b>", "</b>")).select_from(docs)

# Snippet with context
select(fts5_snippet(docs, 0, "<b>", "</b>", "...", 64)).select_from(docs)
```

## FTS5 query syntax

All FTS5 query syntax passes through `FTS5Match`:

```python
FTS5Match(fts, "python AND sqlite")       # boolean
FTS5Match(fts, "python OR rust")           # OR
FTS5Match(fts, "python NOT javascript")    # NOT
FTS5Match(fts, '"exact phrase"')           # phrase
FTS5Match(fts, "pyth*")                    # prefix
FTS5Match(fts, "title:python")             # column filter
FTS5Match(fts, "NEAR(python sqlite, 5)")   # proximity
```

## How it works

`FTS5Table()` returns a normal SQLAlchemy `Table` with metadata in `table.info` that marks it as FTS5. When SQLAlchemy compiles `CreateTable` for a table with this marker, a `@compiles` handler intercepts it and emits `CREATE VIRTUAL TABLE ... USING fts5(...)` instead. Same mechanism for `DropTable`. No monkey-patching, no private APIs — just the `@compiles` extension point that SQLAlchemy provides for exactly this purpose.

Works with `metadata.create_all()`, `metadata.drop_all()`, and ORM `Mapped[]` types.

## License

MIT
