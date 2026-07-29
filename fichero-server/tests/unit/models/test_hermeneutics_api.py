"""Unit tests for hermeneutics API routes."""

from fichero_server.models import ActionAudit, KnowledgeClaim


def test_framework_crud(client, db):
    """Create, read, update, delete interpretive frameworks."""
    # Create
    resp = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Marxist Historical Materialism",
            "framework_type": "historical",
            "description": "Analyze history through class struggle and economic determinism.",
            "core_questions": [
                "Who controls the means of production?",
                "What are the class relations?",
            ],
            "key_concepts": ["dialectical materialism", "class struggle"],
            "typical_applications": ["Labor history", "Revolutionary movements"],
            "creator": "Karl Marx",
            "language": "en",
        },
    )
    assert resp.status_code == 200
    fw = resp.json()
    assert fw["name"] == "Marxist Historical Materialism"
    assert fw["framework_type"] == "historical"
    assert fw["is_active"] is True

    # List
    list_resp = client.get("/api/hermeneutics/frameworks")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] >= 1

    # Get
    get_resp = client.get(f"/api/hermeneutics/frameworks/{fw['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == fw["id"]

    # Filter by type
    filter_resp = client.get("/api/hermeneutics/frameworks?framework_type=historical")
    assert filter_resp.status_code == 200
    historical = filter_resp.json()["items"]
    assert all(f["framework_type"] == "historical" for f in historical)

    # Update
    patch_resp = client.patch(
        f"/api/hermeneutics/frameworks/{fw['id']}",
        json={"description": "Updated description."},
    )
    assert patch_resp.status_code == 200
    assert "Updated description" in patch_resp.json()["description"]

    # Soft-delete
    del_resp = client.delete(f"/api/hermeneutics/frameworks/{fw['id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["status"] == "deactivated"

    # Verify deactivated
    get_after_del = client.get(f"/api/hermeneutics/frameworks/{fw['id']}")
    assert get_after_del.status_code == 200
    assert get_after_del.json()["is_active"] is False


def test_framework_not_found(client):
    """404 for missing framework."""
    resp = client.get("/api/hermeneutics/frameworks/nonexistent-id")
    assert resp.status_code == 404


def test_interpretation_crud(client, db):
    """Create and retrieve interpretations."""
    # Create a framework first
    fw_resp = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Postcolonial Theory",
            "framework_type": "theoretical",
            "description": "Analyze texts through the lens of colonial power structures.",
        },
    )
    assert fw_resp.status_code == 200
    fw = fw_resp.json()

    # Interpretations now validate claim_id references an existing claim — seed it.
    db.save(KnowledgeClaim(id="test-claim-123", text="c", source_document_id="d", entity_ids=[]))

    # Create interpretation
    int_resp = client.post(
        "/api/hermeneutics/interpretations",
        json={
            "framework_id": fw["id"],
            "claim_id": "test-claim-123",
            "interpretation_text": "This passage reflects colonial power dynamics in the region.",
            "act": "contextualizing",
            "confidence": 0.72,
            "key_insights": ["Reference to colonial administrative apparatus"],
            "tensions": ["Oversimplifies complex local agency"],
        },
    )
    assert int_resp.status_code == 200
    interp = int_resp.json()
    assert interp["framework_id"] == fw["id"]
    assert interp["claim_id"] == "test-claim-123"
    assert interp["confidence"] == 0.72

    # List by framework
    list_resp = client.get(f"/api/hermeneutics/interpretations?framework_id={fw['id']}")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] >= 1

    # Get
    get_resp = client.get(f"/api/hermeneutics/interpretations/{interp['id']}")
    assert get_resp.status_code == 200

    # Update
    patch_resp = client.patch(
        f"/api/hermeneutics/interpretations/{interp['id']}",
        json={"confidence": 0.85, "key_insights": ["Updated insight"]},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["confidence"] == 0.85

    # Filter by act
    act_resp = client.get("/api/hermeneutics/interpretations?act=contextualizing")
    assert act_resp.status_code == 200


def test_interpretation_requires_framework(client):
    """Interpretation without a framework returns 404."""
    resp = client.post(
        "/api/hermeneutics/interpretations",
        json={
            "framework_id": "nonexistent-framework",
            "claim_id": "test-claim",
            "interpretation_text": "Test.",
            "act": "reading",
        },
    )
    assert resp.status_code == 404


def test_interpretation_requires_target(client, db):
    """Interpretation must have claim_id, document_id, or passage_text."""
    fw_resp = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Feminist Theory",
            "framework_type": "theoretical",
            "description": "Analyze gender power dynamics.",
        },
    )
    fw = fw_resp.json()

    resp = client.post(
        "/api/hermeneutics/interpretations",
        json={
            "framework_id": fw["id"],
            "interpretation_text": "Test.",
            "act": "reading",
        },
    )
    assert resp.status_code == 400
    assert "claim_id" in resp.json()["detail"]


def test_pattern_crud(client, db):
    """Create, list, and update pattern instances."""
    # Create
    resp = client.post(
        "/api/hermeneutics/patterns",
        json={
            "name": "Cyclical Theory of History",
            "description": "Recurring pattern of rise-and-fall cycles in historiography.",
            "pattern_type": "temporal",
            "claim_ids": ["claim-1", "claim-2"],
            "entity_ids": [],
            "frequency": 2,
            "significance": 0.65,
            "status": "tentative",
            "supporting_passages": ["Source A, p. 42", "Source B, p. 17"],
        },
    )
    assert resp.status_code == 200
    pattern = resp.json()
    assert pattern["name"] == "Cyclical Theory of History"
    assert pattern["frequency"] == 2
    assert pattern["status"] == "tentative"

    # List
    list_resp = client.get("/api/hermeneutics/patterns")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] >= 1

    # Filter by status
    filter_resp = client.get("/api/hermeneutics/patterns?status=tentative")
    assert filter_resp.status_code == 200
    assert all(p["status"] == "tentative" for p in filter_resp.json()["items"])

    # Get
    get_resp = client.get(f"/api/hermeneutics/patterns/{pattern['id']}")
    assert get_resp.status_code == 200

    # Update
    patch_resp = client.patch(
        f"/api/hermeneutics/patterns/{pattern['id']}",
        json={"status": "confirmed", "significance": 0.8},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "confirmed"

    # Add claim to pattern
    add_resp = client.post(
        f"/api/hermeneutics/patterns/{pattern['id']}/claims/claim-3"
    )
    assert add_resp.status_code == 200
    assert "claim-3" in add_resp.json()["claim_ids"]


def test_circle_state_crud(client, db):
    """Create and navigate hermeneutic circle states."""
    # Create
    resp = client.post(
        "/api/hermeneutics/circle-state",
        json={
            "claim_id": "test-claim-abc",
            "current_focus": "part",
            "focus_id": "passage-1",
            "focus_label": "Opening paragraph",
            "direction": "part_to_whole",
        },
    )
    assert resp.status_code == 200
    state = resp.json()
    assert state["claim_id"] == "test-claim-abc"
    assert state["current_focus"] == "part"
    assert state["circle_level"] == 0
    assert len(state["navigation_log"]) == 1

    # List by claim
    list_resp = client.get("/api/hermeneutics/circle-state?claim_id=test-claim-abc")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] >= 1

    # Navigate whole→part, so focus moves TO part
    nav_resp = client.post(
        f"/api/hermeneutics/circle-state/{state['id']}/navigate",
        json={
            "direction": "whole_to_part",
            "focus_id": "document-1",
            "focus_label": "Section 3 of document",
        },
    )
    assert nav_resp.status_code == 200
    navigated = nav_resp.json()
    assert navigated["circle_level"] == 1
    assert navigated["current_focus"] == "part"
    assert len(navigated["navigation_log"]) == 2

    # Backtrack
    back_resp = client.post(f"/api/hermeneutics/circle-state/{state['id']}/backtrack")
    assert back_resp.status_code == 200
    assert back_resp.json()["circle_level"] == 0


def test_circle_state_not_found(client):
    """404 for missing circle state."""
    resp = client.get("/api/hermeneutics/circle-state/nonexistent")
    assert resp.status_code == 404


def test_interpretation_suggestions_endpoint_is_gone(client, db):
    """The permanent-501 /suggestions stub was deleted in the 2026-07-27
    endpoint cleanup — nothing may fabricate AI suggestions; a future real
    implementation replaces this guard with grounded-output tests."""
    resp = client.post(
        "/api/hermeneutics/suggestions",
        json={"claim_ids": ["claim-1"], "num_suggestions": 3},
    )
    assert resp.status_code in (404, 405)


def test_hermeneutics_write_routes_write_action_audit(client, db):
    framework = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Audit framework",
            "framework_type": "historical",
            "description": "Track route audits.",
        },
    )
    assert framework.status_code == 200
    framework_id = framework.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "framework.create"

    patched_framework = client.patch(
        f"/api/hermeneutics/frameworks/{framework_id}",
        json={"description": "Updated route audit."},
    )
    assert patched_framework.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "framework.update"

    deleted_framework = client.delete(f"/api/hermeneutics/frameworks/{framework_id}")
    assert deleted_framework.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "framework.delete"

    live_framework = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Live framework",
            "framework_type": "theoretical",
            "description": "For route audit flow.",
        },
    )
    assert live_framework.status_code == 200
    live_framework_id = live_framework.json()["id"]
    db.save(KnowledgeClaim(id="audit-claim", text="c", source_document_id="d", entity_ids=[]))

    interpretation = client.post(
        "/api/hermeneutics/interpretations",
        json={
            "framework_id": live_framework_id,
            "claim_id": "audit-claim",
            "interpretation_text": "Audit interpretation",
            "act": "reading",
        },
    )
    assert interpretation.status_code == 200
    interpretation_id = interpretation.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "interpretation.create"

    patched_interpretation = client.patch(
        f"/api/hermeneutics/interpretations/{interpretation_id}",
        json={"interpretation_text": "Audit interpretation updated"},
    )
    assert patched_interpretation.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "interpretation.update"

    pattern = client.post(
        "/api/hermeneutics/patterns",
        json={
            "name": "Audit pattern",
            "description": "Track pattern actions.",
            "pattern_type": "motif",
        },
    )
    assert pattern.status_code == 200
    pattern_id = pattern.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "pattern.create"

    patched_pattern = client.patch(
        f"/api/hermeneutics/patterns/{pattern_id}",
        json={"description": "Track updated pattern actions."},
    )
    assert patched_pattern.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "pattern.update"

    claimed_pattern = client.post(
        f"/api/hermeneutics/patterns/{pattern_id}/claims/audit-claim"
    )
    assert claimed_pattern.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "pattern.add_claim"

    circle_state = client.post(
        "/api/hermeneutics/circle-state",
        json={
            "claim_id": "audit-claim",
            "current_focus": "whole",
            "focus_id": "audit-whole",
            "focus_label": "Audit whole",
            "direction": "whole_to_part",
        },
    )
    assert circle_state.status_code == 200
    circle_state_id = circle_state.json()["id"]
    assert db.all(ActionAudit)[-1].action_name == "circle_state.create"

    navigated_circle = client.post(
        f"/api/hermeneutics/circle-state/{circle_state_id}/navigate",
        json={
            "direction": "whole_to_part",
            "focus_id": "audit-part",
            "focus_label": "Audit part",
        },
    )
    assert navigated_circle.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "circle_state.navigate"

    backtracked_circle = client.post(
        f"/api/hermeneutics/circle-state/{circle_state_id}/backtrack"
    )
    assert backtracked_circle.status_code == 200
    assert db.all(ActionAudit)[-1].action_name == "circle_state.backtrack"
