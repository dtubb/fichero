"""Which statements a name's paragraph says (#6835).

spec: kg-paragraph-realisation (`kg.para.rejected-never-stated`, `kg.para.mentions-are-a-list`)

Through the real route, `GET /api/kg/entities/{id}/readable`.
"""
from __future__ import annotations

import pytest

from fichero_server.models.knowledge import (
    ClaimCurationState,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
)


def _entity(db, name: str) -> KnowledgeEntity:
    entity = KnowledgeEntity(canonical_name=name)
    db.save(entity)
    return entity


def _claim(db, subject: KnowledgeEntity, verb: str, obj: str, page: KnowledgeEntity, **kw) -> KnowledgeClaim:
    claim = KnowledgeClaim(
        text=f"{subject.canonical_name} {verb} {obj}", svo_subject=subject.canonical_name,
        svo_verb=verb, svo_object=obj, subject_entity_id=subject.id,
        entity_ids=sorted({subject.id, page.id}), source_languages=["es"], **kw,
    )
    db.save(claim)
    return claim


def _read(client, entity: KnowledgeEntity) -> dict:
    r = client.get(f"/api/kg/entities/{entity.id}/readable")
    assert r.status_code == 200
    return r.json()


@pytest.fixture
def ines(db):
    with db.defer_embeddings():
        yield _entity(db, "Inés Valcárcel")


@pytest.mark.parametrize("damage", [
    {"curation_state": ClaimCurationState.rejected},
    {"epistemic_status": EpistemicStatus.rejected},
    {"merged_into_id": "another-statement"},
])
def test_a_rejected_or_merged_statement_is_never_stated(client, db, ines, damage):
    with db.defer_embeddings():
        kept = _claim(db, ines, "nació en", "Villa Arenal", ines)
        gone = _claim(db, ines, "murió en", "San Telmo", ines, **damage)
    body = _read(client, ines)
    said = [cid for s in body["sentences"] for cid in s["claim_ids"]]
    assert said == [kept.id]
    assert "San Telmo" not in body["paragraph"]
    assert gone.id not in [m["claim_id"] for m in body["also_mentioned_in"]]


def test_a_mention_is_listed_not_narrated(client, db, ines):
    with db.defer_embeddings():
        clemente = _entity(db, "Clemente Ibarra")
        baltasar = _entity(db, "Baltasar Oquendo")
        own = _claim(db, ines, "nació en", "Villa Arenal", ines, source_document_id="doc-1")
        later = _claim(db, clemente, "pagó a", "Baltasar Oquendo", ines,
                       time_start="1740-01-01", source_document_id="doc-3")
        earlier = _claim(db, baltasar, "vendió", "una mula", ines,
                         time_start="1731-01-01", source_document_id="doc-2")
    body = _read(client, ines)
    assert [s["claim_ids"] for s in body["sentences"]] == [[own.id]]
    assert "pagó" not in body["paragraph"] and "mula" not in body["paragraph"]
    assert body["also_mentioned_in"] == [
        {"claim_id": earlier.id, "text": "Baltasar Oquendo vendió una mula.", "document_id": "doc-2"},
        {"claim_id": later.id, "text": "Clemente Ibarra pagó a Baltasar Oquendo.", "document_id": "doc-3"},
    ]


def test_an_object_statement_stays_in_the_paragraph_and_not_in_the_list(client, db, ines):
    with db.defer_embeddings():
        baltasar = _entity(db, "Baltasar Oquendo")
        said = _claim(db, baltasar, "demandó a", "Inés Valcárcel", ines)
    body = _read(client, ines)
    assert [s["claim_ids"] for s in body["sentences"]] == [[said.id]]
    assert body["also_mentioned_in"] == []


# ---- the withdrawn test itself, with no database and no route ------------------------------


@pytest.mark.parametrize("fields, withdrawn", [
    ({}, False),
    ({"curation_state": ClaimCurationState.curated}, False),
    ({"epistemic_status": EpistemicStatus.tentative}, False),
    ({"curation_state": ClaimCurationState.rejected}, True),
    ({"epistemic_status": EpistemicStatus.rejected}, True),
    ({"merged_into_id": "another-statement"}, True),
])
def test_a_statement_is_withdrawn_when_rejected_or_merged(fields, withdrawn):
    from fichero_server.knowledge.readable import _is_withdrawn
    assert _is_withdrawn(KnowledgeClaim(text="x", **fields)) is withdrawn
