"""SQLAlchemy FTS5 — SQLite full-text search for SQLAlchemy.

Provides virtual table DDL, table-level MATCH, ranking/highlight/snippet
functions, external content table sync, and typed ORM mapping.
"""

from sqlalchemy_fts5._ddl import CreateFTS5Table, DropFTS5Table
from sqlalchemy_fts5._expression import FTS5Match
from sqlalchemy_fts5._functions import fts5_bm25, fts5_highlight, fts5_snippet
from sqlalchemy_fts5._table import FTS5Table

__all__ = [
    "CreateFTS5Table",
    "DropFTS5Table",
    "FTS5Match",
    "FTS5Table",
    "fts5_bm25",
    "fts5_highlight",
    "fts5_snippet",
]
