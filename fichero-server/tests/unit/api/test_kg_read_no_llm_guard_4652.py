"""`kg.read.no-llm` (#4652): the render routes call no model and their output is a pure function of the claims.

The guard asserts on calls (every `chat` entry point raises) and on purity (same claims, same bytes);
an import check would fail, since `paragraph`/`readable` import `fichero_server.llm` through the models package.
"""
from __future__ import annotations

import pytest

from fichero_server.models import Document, DocType
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity


def _boom(*args, **kwargs):
    raise AssertionError("a render route called a language model")


@pytest.fixture
def no_model(monkeypatch):
    import fichero_server.api.routes.kg.render as render
    import fichero_server.llm as llm

    monkeypatch.setattr(llm, "chat", _boom)
    monkeypatch.setattr(render, "chat", _boom)


def _claims(db):
    with db.defer_embeddings():
        doc = Document(name="Source", doc_type=DocType.file)
        db.save(doc)
        page = KnowledgeEntity(canonical_name="Inés Valcárcel")
        db.save(page)
        claims = []
        for i, obj in enumerate(("una mula", "dos bueyes")):
            claim = KnowledgeClaim(
                text=f"Inés Valcárcel vendió {obj}", svo_subject="Inés Valcárcel", svo_verb="vendió",
                svo_object=obj, subject_entity_id=page.id, entity_ids=[page.id], source_languages=["es"], source_document_id=doc.id,
                time_start=f"173{i}-01-01")
            db.save(claim)
            claims.append(claim)
    return page, claims


def test_readable_route_calls_no_model_and_is_pure(client, db, no_model):
    page, _ = _claims(db)
    first = client.get(f"/api/kg/entities/{page.id}/readable")
    second = client.get(f"/api/kg/entities/{page.id}/readable")
    assert first.status_code == 200 and first.json()["paragraph"]
    assert first.json() == second.json()


def test_paragraph_route_calls_no_model_and_is_pure(client, db, no_model):
    _, claims = _claims(db)
    payload = {"claim_ids": [c.id for c in claims]}
    first = client.post("/api/kg/render/paragraph", json=payload)
    second = client.post("/api/kg/render/paragraph", json=payload)
    assert first.status_code == 200 and first.json()["text"]
    assert first.json() == second.json()
