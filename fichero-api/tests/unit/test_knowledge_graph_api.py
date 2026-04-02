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
    assert claim["prediction"]["uncertainty_spans"][0]["reason"] == "location ambiguous — could refer to multiple sectors"
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


# =============================================================================
# Migration tests (run against real Database via db fixture)
# =============================================================================

def test_migrate_claims_idempotent(db):
    """Migration is idempotent — running twice has no effect."""
    from fichero.knowledge_models import KnowledgeClaim, SourceType
    from fichero.migrations import migrate_claims_to_multi_source

    # Create a pre-migration claim (source_type=document, empty source_ids)
    doc = Document(name="old-source", doc_type=DocType.file, path="/tmp/old.txt")
    db.save(doc)

    old_claim = KnowledgeClaim(
        text="This is a very old claim.",
        source_document_id=doc.id,
        source_type=SourceType.document,  # default — not yet migrated
        source_ids=[],  # empty — not yet migrated
        curation_state="curated",
    )
    db.save(old_claim)
    old_id = old_claim.id

    # First migration pass
    migrated_1, skipped_1 = migrate_claims_to_multi_source(db, dry_run=False)
    assert migrated_1 >= 1

    # Reload and verify
    reloaded = db.get(KnowledgeClaim, old_id)
    assert reloaded.source_ids == [doc.id]
    assert reloaded.source_type == SourceType.document

    # Second migration pass — should be skipped (already migrated)
    migrated_2, skipped_2 = migrate_claims_to_multi_source(db, dry_run=False)
    # The previously migrated claim + whatever else was in the DB
    assert migrated_2 == 0  # nothing left to migrate

    # Verify state unchanged after second pass
    reloaded2 = db.get(KnowledgeClaim, old_id)
    assert reloaded2.source_ids == [doc.id]


def test_migrate_claims_dry_run(db):
    """Dry run does not modify data."""
    from fichero.knowledge_models import KnowledgeClaim, SourceType
    from fichero.migrations import migrate_claims_to_multi_source

    doc = Document(name="dry-run-test", doc_type=DocType.file, path="/tmp/dry.txt")
    db.save(doc)

    pre_migration = KnowledgeClaim(
        text="This claim has not been migrated yet.",
        source_document_id=doc.id,
        source_type=SourceType.document,
        source_ids=[],
        curation_state="shortlisted",
    )
    db.save(pre_migration)
    pre_id = pre_migration.id

    migrated, skipped = migrate_claims_to_multi_source(db, dry_run=True)

    # Dry run should not change anything
    reloaded = db.get(KnowledgeClaim, pre_id)
    assert reloaded.source_ids == []
    assert reloaded.source_type == SourceType.document
    assert migrated >= 1


# =============================================================================
# Semantic Search tests (Step 5)
# =============================================================================

def test_embed_claims_and_semantic_search(client, db):
    """Embed claims and search them semantically."""
    doc = Document(name="source", doc_type=DocType.file, path="/tmp/source.txt")
    db.save(doc)

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={
            "text": "The mine operated continuously from 1950 to 1975.",
            "source_document_id": doc.id,
            "curation_state": "curated",
        },
    )
    assert claim_resp.status_code == 200
    claim = claim_resp.json()

    # Embed the claim
    embed_resp = client.post("/api/knowledge-graph/claims/semantic/embed")
    assert embed_resp.status_code == 200
    assert embed_resp.json()["embedded"] >= 1

    # Search semantically — should find the claim
    search_resp = client.get("/api/knowledge-graph/claims/semantic?q=gold+mining+operations&limit=5")
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) >= 1


def test_semantic_search_503_when_not_embedded(client, db):
    """Semantic search returns 503 if embeddings not built yet."""
    doc = Document(name="source", doc_type=DocType.file, path="/tmp/source.txt")
    db.save(doc)

    claim_resp = client.post(
        "/api/knowledge-graph/claims",
        json={"text": "Some claim.", "source_document_id": doc.id},
    )
    assert claim_resp.status_code == 200

    # No embed step — should get 503
    search_resp = client.get("/api/knowledge-graph/claims/semantic?q=some+query")
    assert search_resp.status_code == 503


def test_embed_entities_and_semantic_search(client, db):
    """Embed entities and search them semantically."""
    # Create an entity
    entity_resp = client.post(
        "/api/knowledge-graph/entities",
        json={"canonical_name": "Cerro Bolivar", "entity_type": "location"},
    )
    assert entity_resp.status_code == 200
    entity = entity_resp.json()

    # Embed entities
    embed_resp = client.post("/api/knowledge-graph/entities/semantic/embed")
    assert embed_resp.status_code == 200
    assert embed_resp.json()["embedded"] >= 1

    # Search semantically
    search_resp = client.get("/api/knowledge-graph/entities/semantic?q=iron+ore+deposits")
    assert search_resp.status_code == 200
    results = search_resp.json()
    assert len(results) >= 1
    # Cerro Bolivar should be returned
    ids = [r["id"] for r in results]
    assert entity["id"] in ids


def test_find_similar_claims(client, db):
    """Find similar claims using vector similarity."""
    doc = Document(name="source", doc_type=DocType.file, path="/tmp/source.txt")
    db.save(doc)

    # Create two related claims
    claim1_resp = client.post(
        "/api/knowledge-graph/claims",
        json={"text": "The mine produced iron ore continuously.", "source_document_id": doc.id},
    )
    assert claim1_resp.status_code == 200
    claim1 = claim1_resp.json()

    claim2_resp = client.post(
        "/api/knowledge-graph/claims",
        json={"text": "Production at the mine stopped in 1975.", "source_document_id": doc.id},
    )
    assert claim2_resp.status_code == 200

    # Embed all claims
    embed_resp = client.post("/api/knowledge-graph/claims/semantic/embed")
    assert embed_resp.status_code == 200

    # Find similar to claim1
    similar_resp = client.get(f"/api/knowledge-graph/claims/{claim1['id']}/similar?limit=5")
    assert similar_resp.status_code == 200
    similar = similar_resp.json()
    assert len(similar) >= 1
    # claim2 should appear as similar
    similar_ids = [s["id"] for s in similar]
    assert claim2_resp.json()["id"] in similar_ids


# =============================================================================
# Prediction Run tests (Step 4)
# =============================================================================

def test_list_predictions(client, db):
    """List prediction runs returns empty list when none exist."""
    resp = client.get("/api/knowledge-graph/predictions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_generate_heuristic_predictions_requires_embedding(client, db):
    """Heuristic prediction generation requires embeddings to exist first."""
    doc = Document(name="source", doc_type=DocType.file, path="/tmp/source.txt")
    db.save(doc)

    client.post(
        "/api/knowledge-graph/claims",
        json={"text": "Some claim about mining.", "source_document_id": doc.id},
    )
    # No embeddings yet — should fail
    pred_resp = client.post("/api/knowledge-graph/predictions/generate/heuristic", json={"top_k": 5})
    assert pred_resp.status_code == 503


def test_apply_prediction_returns_501_without_trained_model(client, db):
    """Apply prediction is not implemented until full PyKEEN model training exists."""
    resp = client.post("/api/knowledge-graph/predictions/some-run-id/apply")
    assert resp.status_code == 501
