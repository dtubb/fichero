"""Tests for GET /api/kg/review/graph-candidates (#988 step 2).

The graph-context candidate generator proposes entity-merge pairs from
co-occurrence neighbourhood overlap — duplicates that never share a
surface form but are co-mentioned with the same other entities. This
endpoint surfaces those proposals into the review queue.
"""

from fichero.models.knowledge import (
    ClaimType,
    EntityMatchCandidate,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
    PendingMatchMethod,
)


def _entity(entity_id: str, name: str) -> KnowledgeEntity:
    return KnowledgeEntity(id=entity_id, canonical_name=name)


def _claim(claim_id: str, doc_id: str, entity_ids: list[str]) -> KnowledgeClaim:
    return KnowledgeClaim(
        id=claim_id,
        text=f"claim {claim_id}",
        source_document_id=doc_id,
        source_ids=[doc_id],
        claim_type=ClaimType.fact,
        epistemic_status=EpistemicStatus.tentative,
        confidence=0.8,
        entity_ids=entity_ids,
    )


def _seed_overlapping_pair(db) -> None:
    """A and B never co-mentioned, but both share neighbours C and D.

    A's neighbourhood is {C, D}; B's is {C, D, E} — Jaccard(A, B) = 2/3,
    shared_neighbours = 2. C and D are diluted with private neighbours
    (F, G, H on C) so they fall below threshold and only A-B surfaces.
    """
    for eid, name in [
        ("ent-a", "Andrés"),
        ("ent-b", "Andrés Restrepo"),
        ("ent-c", "Carmen"),
        ("ent-d", "Diego"),
        ("ent-e", "Elena"),
        ("ent-f", "Felipe"),
        ("ent-g", "Gabriela"),
        ("ent-h", "Hugo"),
    ]:
        db.save(_entity(eid, name))
    db.save(_claim("c1", "doc1", ["ent-a", "ent-c"]))
    db.save(_claim("c2", "doc2", ["ent-a", "ent-d"]))
    db.save(_claim("c3", "doc3", ["ent-b", "ent-c"]))
    db.save(_claim("c4", "doc4", ["ent-b", "ent-d"]))
    db.save(_claim("c5", "doc5", ["ent-b", "ent-e"]))
    db.save(_claim("c6", "doc6", ["ent-c", "ent-f"]))
    db.save(_claim("c7", "doc7", ["ent-c", "ent-g"]))
    db.save(_claim("c8", "doc8", ["ent-c", "ent-h"]))


class TestGraphCandidates:
    def test_empty_library_returns_empty_list(self, client):
        r = client.get("/api/kg/review/graph-candidates")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_surfaces_overlapping_pair(self, client, db):
        _seed_overlapping_pair(db)

        r = client.get("/api/kg/review/graph-candidates")
        assert r.status_code == 200
        rows = r.json()["items"]
        assert len(rows) == 1
        row = rows[0]
        assert {row["entity_a_id"], row["entity_b_id"]} == {"ent-a", "ent-b"}
        assert row["shared_neighbours"] == 2
        assert row["jaccard"] == 2 / 3
        assert row["already_queued"] is False

    def test_threshold_filters_weak_pairs(self, client, db):
        _seed_overlapping_pair(db)

        # A-B Jaccard is 2/3 ≈ 0.667 — a threshold above that drops it.
        r = client.get("/api/kg/review/graph-candidates?threshold=0.7")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_soft_deleted_entity_excluded(self, client, db):
        _seed_overlapping_pair(db)
        ghost = db.get(KnowledgeEntity, "ent-b")
        ghost.merged_into_id = "ent-a"
        db.save(ghost)

        r = client.get("/api/kg/review/graph-candidates")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_already_queued_pair_is_marked(self, client, db):
        _seed_overlapping_pair(db)
        db.save(EntityMatchCandidate(
            survivor_entity_id="ent-a",
            candidate_entity_id="ent-b",
            score=0.9,
            method=PendingMatchMethod.graph_context,
        ))

        r = client.get("/api/kg/review/graph-candidates")
        assert r.status_code == 200
        rows = r.json()["items"]
        assert len(rows) == 1
        assert rows[0]["already_queued"] is True
