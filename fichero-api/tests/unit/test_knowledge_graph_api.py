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
