"""Shared fixtures for sqlalchemy-fts5 tests."""

from __future__ import annotations

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine
from sqlalchemy.engine import Engine


@pytest.fixture
def engine() -> Engine:
    """In-memory SQLite engine."""
    return create_engine("sqlite:///:memory:")


@pytest.fixture
def metadata() -> MetaData:
    return MetaData()


@pytest.fixture
def content_table(metadata: MetaData) -> Table:
    """A plain table to use as an FTS5 external content source."""
    return Table(
        "docs",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String),
        Column("body", String),
        Column("author", String),
    )
