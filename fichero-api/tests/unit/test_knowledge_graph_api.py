"""Unit tests for dev-tier knowledge graph API routes."""

from fichero.models import DocType, Document


def test_knowledge_graph_claim_entity_flow(client, db):
    source_doc = Document(name="letter-1", doc_type=DocType.file, path="/tmp/letter-1.txt")
    db.save(source_doc)

    entity_resp = client.post(
        "/api/knowledge-graph/entities",
        json={
            "canonical_name": "Daniel Tubb",
            "entity_type": "person",
            "aliases": ["D. Tubb"],
        },
    )
    assert entity_resp.status_code == 200
    entity = entity_resp.json()

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "Daniel worked as a miner in Colombia in 1959.",
            "source_document_id": source_doc.id,
            "entity_ids": [entity["id"]],
            "confidence": 0.72,
            "curation_state": "unreviewed",
        },
    )
    assert claim_resp.status_code == 200
    claim = claim_resp.json()
    assert claim["source_document_id"] == source_doc.id
    assert claim["entity_ids"] == [entity["id"]]

    by_entity_resp = client.get(f"/api/knowledge-graph/claims?entity_id={entity['id']}")
    assert by_entity_resp.status_code == 200
    by_entity_claims = by_entity_resp.json()
    assert len(by_entity_claims) == 1
    assert by_entity_claims[0]["id"] == claim["id"]

    by_query_resp = client.get("/api/knowledge-graph/claims?q=D.%20Tubb")
    assert by_query_resp.status_code == 200
    by_query_claims = by_query_resp.json()
    assert len(by_query_claims) == 1
    assert by_query_claims[0]["id"] == claim["id"]


def test_knowledge_graph_scope_and_inclusion(client, db):
    folder = Document(name="box-a", doc_type=DocType.folder)
    source_doc = Document(
        name="diary-page",
        doc_type=DocType.file,
        path="/tmp/diary-page.txt",
        parent_id=folder.id,
    )
    db.save(folder)
    db.save(source_doc)

    entity_resp = client.post(
        "/api/knowledge-graph/entities",
        json={
            "canonical_name": "Bogota",
            "entity_type": "location",
        },
    )
    assert entity_resp.status_code == 200
    entity_id = entity_resp.json()["id"]

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "The author references Bogota repeatedly.",
            "source_document_id": source_doc.id,
            "entity_ids": [entity_id],
            "curation_state": "shortlisted",
        },
    )
    assert claim_resp.status_code == 200
    claim_id = claim_resp.json()["id"]

    scope_resp = client.get(f"/api/knowledge-graph/claims?scope_type=folder&target_id={folder.id}")
    assert scope_resp.status_code == 200
    scope_claims = scope_resp.json()
    assert len(scope_claims) == 1
    assert scope_claims[0]["id"] == claim_id

    include_resp = client.post(
        "/api/knowledge-graph/inclusion",
        json={
            "scope_type": "document",
            "target_id": source_doc.id,
            "included": False,
            "reason": "Out of current review scope",
        },
    )
    assert include_resp.status_code == 200
    assert include_resp.json()["included"] is False

    included_only_resp = client.get("/api/knowledge-graph/claims?included_only=true")
    assert included_only_resp.status_code == 200
    assert included_only_resp.json() == []

    overview_resp = client.get(f"/api/knowledge-graph/overview?scope_type=folder&target_id={folder.id}")
    assert overview_resp.status_code == 200
    payload = overview_resp.json()
    assert payload["counts"]["claims"] == 1
    assert payload["counts"]["shortlisted_claims"] == 1
    assert payload["counts"]["included_claims"] == 0


def test_knowledge_graph_multi_source_claim(client, db):
    """Phase 1: claim with multi-source fields (source_ids, claim_type, epistemic_status)."""
    doc_a = Document(name="letter-a", doc_type=DocType.file, path="/tmp/letter-a.txt")
    doc_b = Document(name="letter-b", doc_type=DocType.file, path="/tmp/letter-b.txt")
    db.save(doc_a)
    db.save(doc_b)

    entity_resp = client.post(
        "/api/knowledge-graph/entities",
        json={"canonical_name": "Bogota", "entity_type": "location"},
    )
    assert entity_resp.status_code == 200
    entity_id = entity_resp.json()["id"]

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "The mine operated from 1950-1965.",
            "source_document_id": doc_a.id,
            "source_ids": [doc_b.id],
            "source_page_labels": ["12", "34"],
            "source_languages": ["en", "es"],
            "source_type": "multiple",
            "entity_ids": [entity_id],
            "claim_type": "historiography",
            "epistemic_status": "confirmed",
            "curation_state": "curated",
            "confidence": 0.85,
        },
    )
    assert claim_resp.status_code == 200
    claim = claim_resp.json()
    assert claim["source_document_id"] == doc_a.id
    assert claim["source_ids"] == [doc_b.id]
    assert claim["source_page_labels"] == ["12", "34"]
    assert claim["source_languages"] == ["en", "es"]
    assert claim["source_type"] == "multiple"
    assert claim["claim_type"] == "historiography"
    assert claim["epistemic_status"] == "confirmed"
    assert claim["curation_state"] == "curated"
    assert claim["confidence"] == 0.85

    # filter by claim_type
    by_type_resp = client.get("/api/knowledge-graph/claims?claim_type=historiography")
    assert by_type_resp.status_code == 200
    assert len(by_type_resp.json()) == 1

    # filter by epistemic_status
    by_status_resp = client.get("/api/knowledge-graph/claims?epistemic_status=confirmed")
    assert by_status_resp.status_code == 200
    assert len(by_status_resp.json()) == 1

    by_status_none_resp = client.get("/api/knowledge-graph/claims?epistemic_status=tentative")
    assert by_status_none_resp.status_code == 200
    assert len(by_status_none_resp.json()) == 0

    # filter by source_language
    lang_resp = client.get("/api/knowledge-graph/claims?source_language=es")
    assert lang_resp.status_code == 200
    assert len(lang_resp.json()) == 1

    # filter by source_type
    type_resp = client.get("/api/knowledge-graph/claims?source_type=multiple")
    assert type_resp.status_code == 200
    assert len(type_resp.json()) == 1


def test_knowledge_graph_claim_with_prediction_metadata(client, db):
    """Phase 1: claim with PyKEEN prediction metadata."""
    doc = Document(name="field-note", doc_type=DocType.file, path="/tmp/field-note.txt")
    db.save(doc)

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "Evidence of mineral deposits found in Sector 7.",
            "source_document_id": doc.id,
            "prediction": {
                "confidence": 0.91,
                "model": "pykeen/transe/colombia-mines-v1",
                "entities": [
                    {"text": "Sector 7", "type": "location", "start": 27, "end": 36},
                    {"text": "mineral deposits", "type": "concept", "start": 14, "end": 29},
                ],
                "uncertainty_spans": [
                    {"start": 27, "end": 36, "reason": "location ambiguous — could refer to multiple sectors"},
                ],
                "predicted_links": [
                    {"target_claim_id": "abc123", "link_type": "supports"},
                ],
            },
            "confidence": 0.5,
        },
    )
    assert claim_resp.status_code == 200
    claim = claim_resp.json()
    assert claim["prediction"] is not None
    assert claim["prediction"]["confidence"] == 0.91
    assert claim["prediction"]["model"] == "pykeen/transe/colombia-mines-v1"
    assert len(claim["prediction"]["entities"]) == 2
    assert claim["prediction"]["entities"][0]["text"] == "Sector 7"
    assert len(claim["prediction"]["uncertainty_spans"]) == 1
    assert claim["prediction"]["uncertainty_spans"][0]["reason"] == "location ambiguous"
    assert len(claim["prediction"]["predicted_links"]) == 1
    assert claim["prediction"]["predicted_links"][0]["link_type"] == "supports"


def test_knowledge_graph_claims_filtered_endpoint(client, db):
    """Phase 1: GET /claims/filtered with advanced filter combination."""
    doc = Document(name="source", doc_type=DocType.file, path="/tmp/source.txt")
    db.save(doc)

    # create two claims with different types/statuses
    claim_a = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "Gold was extracted here.",
            "source_document_id": doc.id,
            "claim_type": "fact",
            "epistemic_status": "confirmed",
            "curation_state": "curated",
            "confidence": 0.9,
        },
    )
    assert claim_a.status_code == 200
    claim_a_id = claim_a.json()["id"]

    claim_b = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "The mine may have closed by 1970.",
            "source_document_id": doc.id,
            "claim_type": "interpretation",
            "epistemic_status": "tentative",
            "curation_state": "shortlisted",
            "confidence": 0.4,
        },
    )
    assert claim_b.status_code == 200

    # filter by curation + epistemic (combination)
    filtered_resp = client.get(
        "/api/knowledge-graph/claims/filtered"
        "?curation_state=shortlisted&epistemic_status=tentative"
    )
    assert filtered_resp.status_code == 200
    filtered = filtered_resp.json()
    assert len(filtered) == 1
    assert filtered[0]["id"] == claim_b.json()["id"]

    # filter by claim_type only
    fact_resp = client.get("/api/knowledge-graph/claims/filtered?claim_type=fact")
    assert fact_resp.status_code == 200
    assert len(fact_resp.json()) == 1
    assert fact_resp.json()[0]["id"] == claim_a_id

    # no matches
    none_resp = client.get("/api/knowledge-graph/claims/filtered?epistemic_status=rejected")
    assert none_resp.status_code == 200
    assert none_resp.json() == []
