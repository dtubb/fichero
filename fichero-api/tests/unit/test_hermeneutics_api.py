"""Unit tests for hermeneutics API routes."""

from fichero.hermeneutics_models import (
    CircleNavigationDirection,
    FrameworkType,
    HermeneuticCircleState,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
    PatternInstance,
    PatternStatus,
)


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
    assert len(list_resp.json()) >= 1

    # Get
    get_resp = client.get(f"/api/hermeneutics/frameworks/{fw['id']}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == fw["id"]

    # Filter by type
    filter_resp = client.get("/api/hermeneutics/frameworks?framework_type=historical")
    assert filter_resp.status_code == 200
    historical = filter_resp.json()
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
    assert len(list_resp.json()) >= 1

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
    assert len(list_resp.json()) >= 1

    # Filter by status
    filter_resp = client.get("/api/hermeneutics/patterns?status=tentative")
    assert filter_resp.status_code == 200
    assert all(p["status"] == "tentative" for p in filter_resp.json())

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
    list_resp = client.get(f"/api/hermeneutics/circle-state?claim_id=test-claim-abc")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1

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


def test_interpretation_suggestions(client, db):
    """AI interpretation suggestions return framework-based recommendations."""
    # Create a framework
    fw_resp = client.post(
        "/api/hermeneutics/frameworks",
        json={
            "name": "Annales School",
            "framework_type": "historical",
            "description": "Longue durée and geographic determinism in history.",
            "core_questions": [
                "What is the longue durée structure?",
                "How does geography shape events?",
            ],
            "key_concepts": ["longue durée", "geography", "mentalités"],
        },
    )
    fw = fw_resp.json()

    # Get suggestions
    sugg_resp = client.post(
        "/api/hermeneutics/suggestions",
        json={
            "claim_ids": ["claim-1", "claim-2"],
            "framework_ids": [fw["id"]],
            "num_suggestions": 3,
        },
    )
    assert sugg_resp.status_code == 200
    suggestions = sugg_resp.json()
    assert len(suggestions) >= 1
    assert suggestions[0]["framework_id"] == fw["id"]
    assert suggestions[0]["framework_name"] == "Annales School"


def test_interpretation_suggestions_no_frameworks(client, db):
    """Suggestions fails gracefully when no active frameworks exist."""
    resp = client.post(
        "/api/hermeneutics/suggestions",
        json={
            "claim_ids": ["claim-1"],
            "num_suggestions": 3,
        },
    )
    assert resp.status_code == 400
    assert "No active frameworks" in resp.json()["detail"]


def test_interpretation_suggestions_invalid_num(client, db):
    """Suggestions validates num_suggestions range (Pydantic returns 422)."""
    resp = client.post(
        "/api/hermeneutics/suggestions",
        json={
            "claim_ids": ["claim-1"],
            "num_suggestions": 99,
        },
    )
    assert resp.status_code == 422  # Pydantic validation error
