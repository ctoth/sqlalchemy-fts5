"""Propstore-shaped FTS5 proof tests."""

from __future__ import annotations

from sqlalchemy import MetaData, create_engine, select

from sqlalchemy_fts5 import FTS5Match, FTS5Table, fts5_bm25


def test_concept_like_fts_returns_stable_ids_and_ranks() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    concepts = FTS5Table(
        "concept_search",
        metadata,
        columns=["concept_id", "label", "symbol", "aliases", "normalized_text"],
        tokenize="porter unicode61",
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            concepts.insert(),
            (
                {
                    "rowid": 1,
                    "concept_id": "concept:mass",
                    "label": "Mass",
                    "symbol": "m",
                    "aliases": "inertial mass gravitational mass",
                    "normalized_text": "measure of matter resistance to acceleration",
                },
                {
                    "rowid": 2,
                    "concept_id": "concept:force",
                    "label": "Force",
                    "symbol": "F",
                    "aliases": "interaction push pull",
                    "normalized_text": "cause of acceleration",
                },
            ),
        )

        rows = connection.execute(
            select(concepts.c.concept_id, fts5_bm25(concepts).label("rank"))
            .where(FTS5Match(concepts, "inertial"))
            .order_by(fts5_bm25(concepts), concepts.c.concept_id)
        ).fetchall()

    assert [(row.concept_id, isinstance(row.rank, float)) for row in rows] == [
        ("concept:mass", True)
    ]


def test_claim_like_fts_returns_stable_ids_and_ranks() -> None:
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    claims = FTS5Table(
        "claim_search",
        metadata,
        columns=[
            "claim_id",
            "text_payload",
            "equation_text",
            "provenance_text",
            "rendered_text",
        ],
        tokenize="porter unicode61",
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            claims.insert(),
            (
                {
                    "rowid": 1,
                    "claim_id": "claim:newton-2",
                    "text_payload": "Force equals mass times acceleration.",
                    "equation_text": "F = m a",
                    "provenance_text": "Newton mechanics source",
                    "rendered_text": "A net force accelerates mass.",
                },
                {
                    "rowid": 2,
                    "claim_id": "claim:energy",
                    "text_payload": "Energy is conserved in an isolated system.",
                    "equation_text": "dE/dt = 0",
                    "provenance_text": "conservation law source",
                    "rendered_text": "Total energy remains constant.",
                },
            ),
        )

        rows = connection.execute(
            select(claims.c.claim_id, fts5_bm25(claims).label("rank"))
            .where(FTS5Match(claims, "accelerates"))
            .order_by(fts5_bm25(claims), claims.c.claim_id)
        ).fetchall()

    assert [(row.claim_id, isinstance(row.rank, float)) for row in rows] == [
        ("claim:newton-2", True)
    ]
