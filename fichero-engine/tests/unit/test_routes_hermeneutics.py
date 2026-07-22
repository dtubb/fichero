"""Tests for hermeneutics routes.

Hermeneutics manages interpretive frameworks (historical, disciplinary,
thematic…) and their application to claims via Interpretations and
Patterns. Routes live at /api/hermeneutics/... (router has no prefix,
mounted at "/api/hermeneutics").
"""

from fichero.models import KnowledgeClaim
from fichero.models.hermeneutics import (
    FrameworkType,
    InterpretiveActType,
    InterpretiveFramework,
    Interpretation,
)


BASE = "/api/hermeneutics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_framework(fwk_id: str = "fwk-1", name: str = "Marxist Lens") -> InterpretiveFramework:
    return InterpretiveFramework(
        id=fwk_id,
        name=name,
        framework_type=FrameworkType.theoretical,
        description="Materialist analysis of history",
    )


def _make_interpretation(
    interp_id: str = "interp-1",
    framework_id: str = "fwk-1",
) -> Interpretation:
    return Interpretation(
        id=interp_id,
        framework_id=framework_id,
        interpretation_text="Labor conditions reflect class struggle.",
        act=InterpretiveActType.contextualizing,
    )


# ---------------------------------------------------------------------------
# POST /api/hermeneutics/frameworks
# ---------------------------------------------------------------------------


class TestCreateFramework:
    def test_create_framework(self, client):
        r = client.post(f"{BASE}/frameworks", json={
            "name": "Postcolonial Theory",
            "framework_type": "theoretical",
            "description": "Examines colonial legacies.",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "Postcolonial Theory"
        assert "id" in data


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/frameworks
# ---------------------------------------------------------------------------


class TestListFrameworks:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/frameworks")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_frameworks(self, client, db):
        db.save(_make_framework("fwk-1", "Framework A"))
        db.save(_make_framework("fwk-2", "Framework B"))

        r = client.get(f"{BASE}/frameworks")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestGetFramework:
    def test_get_existing(self, client, db):
        db.save(_make_framework("fwk-get", "Named Framework"))

        r = client.get(f"{BASE}/frameworks/fwk-get")
        assert r.status_code == 200
        assert r.json()["name"] == "Named Framework"

    def test_get_missing_returns_404(self, client):
        r = client.get(f"{BASE}/frameworks/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestUpdateFramework:
    def test_update_description(self, client, db):
        db.save(_make_framework("fwk-upd", "Updatable"))

        r = client.patch(f"{BASE}/frameworks/fwk-upd", json={
            "description": "Updated description."
        })
        assert r.status_code == 200
        assert r.json()["description"] == "Updated description."

    def test_update_missing_returns_404(self, client):
        r = client.patch(f"{BASE}/frameworks/no-such", json={"description": "X"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/hermeneutics/frameworks/{id}
# ---------------------------------------------------------------------------


class TestDeleteFramework:
    def test_delete_framework(self, client, db):
        db.save(_make_framework("fwk-del", "To Delete"))

        r = client.delete(f"{BASE}/frameworks/fwk-del")
        assert r.status_code == 200

    def test_delete_missing_returns_404(self, client):
        r = client.delete(f"{BASE}/frameworks/no-such")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/hermeneutics/interpretations
# ---------------------------------------------------------------------------


class TestCreateInterpretation:
    def test_create_interpretation(self, client, db):
        db.save(_make_framework("fwk-int"))
        db.save(KnowledgeClaim(id="claim-int-1", text="c", source_document_id="d", entity_ids=[]))

        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "fwk-int",
            "claim_id": "claim-int-1",
            "passage_text": "Workers organized in the factories.",
            "interpretation_text": "This evidence shows class conflict.",
            "act": "contextualizing",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["framework_id"] == "fwk-int"

    def test_create_interpretation_populates_predicate_canonical(self, client, db):
        db.save(_make_framework("fwk-int-pred"))
        db.save(KnowledgeClaim(id="claim-int-pred-1", text="c", source_document_id="d", entity_ids=[]))

        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "fwk-int-pred",
            "claim_id": "claim-int-pred-1",
            "passage_text": "The reading foregrounds labor.",
            "interpretation_text": "This reading foregrounds labor history.",
            "act": "contextualizing",
            "predicate": "foregrounds",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["predicate"] == "foregrounds"
        assert data["predicate_canonical"] == "foregrounds"

    def test_missing_framework_returns_404(self, client):
        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "no-such-framework",
            "interpretation_text": "Some text.",
            "act": "reading",
        })
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/interpretations
# ---------------------------------------------------------------------------


class TestListInterpretations:
    def test_empty_list(self, client):
        r = client.get(f"{BASE}/interpretations")
        assert r.status_code == 200
        assert r.json() == {"items": [], "count": 0}

    def test_returns_interpretations(self, client, db):
        db.save(_make_framework("fwk-li"))
        db.save(_make_interpretation("i-1", "fwk-li"))
        db.save(_make_interpretation("i-2", "fwk-li"))

        r = client.get(f"{BASE}/interpretations")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2

    def test_update_interpretation_updates_predicate_canonical(self, client, db):
        db.save(_make_framework("fwk-upd"))
        interp = _make_interpretation("i-upd", "fwk-upd")
        db.save(interp)

        r = client.patch(f"{BASE}/interpretations/{interp.id}", json={
            "predicate": "contests reading",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["predicate"] == "contests reading"
        assert data["predicate_canonical"] == "contests_reading"


# ---------------------------------------------------------------------------
# GET /api/hermeneutics/taxonomy/methods  (#1126 — merged from kg_interpretations)
# ---------------------------------------------------------------------------


class TestTaxonomyMethods:
    def test_returns_acts_and_frameworks(self, client):
        r = client.get(f"{BASE}/taxonomy/methods")
        assert r.status_code == 200
        data = r.json()
        assert "acts" in data
        assert "frameworks" in data
        assert len(data["acts"]) > 0
        assert len(data["frameworks"]) > 0
        # Spot-check structure
        act = data["acts"][0]
        assert "value" in act and "label" in act


# ---------------------------------------------------------------------------
# Canonical /api/kg/interpretations/* URLs (#1126 — same router, two mounts)
# ---------------------------------------------------------------------------

KG_BASE = "/api/kg/interpretations"


class TestKgInterpretationsCanonicalUrls:
    """Verify the KG_ENDPOINTS.md canonical paths are reachable (#1126)."""

    def test_frameworks_list(self, client):
        r = client.get(f"{KG_BASE}/frameworks")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_frameworks_create(self, client):
        r = client.post(f"{KG_BASE}/frameworks", json={
            "name": "Structural Functionalism",
            "framework_type": "theoretical",
            "description": "Societies as systems of interrelated parts.",
        })
        assert r.status_code == 200
        assert r.json()["name"] == "Structural Functionalism"

    def test_frameworks_get(self, client, db):
        db.save(_make_framework("fwk-kg", "KG Framework"))
        r = client.get(f"{KG_BASE}/frameworks/fwk-kg")
        assert r.status_code == 200
        assert r.json()["name"] == "KG Framework"

    def test_frameworks_get_missing(self, client):
        r = client.get(f"{KG_BASE}/frameworks/no-such")
        assert r.status_code == 404

    def test_interpretations_list(self, client):
        r = client.get(f"{KG_BASE}/interpretations")
        assert r.status_code == 200
        assert isinstance(r.json()["items"], list)

    def test_interpretations_create(self, client, db):
        db.save(_make_framework("fwk-kg2"))
        # Interpretations now validate that claim_id references an existing
        # claim (hermeneutics linking) — seed it before creating.
        db.save(KnowledgeClaim(
            id="claim-kg2-1",
            text="A claim to interpret.",
            source_document_id="doc-kg2",
            entity_ids=[],
        ))
        r = client.post(f"{KG_BASE}/interpretations", json={
            "framework_id": "fwk-kg2",
            "claim_id": "claim-kg2-1",
            "passage_text": "Evidence passage.",
            "interpretation_text": "Structural reading.",
            "act": "contextualizing",
        })
        assert r.status_code == 200
        assert r.json()["framework_id"] == "fwk-kg2"

    def test_interpretations_get(self, client, db):
        db.save(_make_framework("fwk-kg3"))
        db.save(_make_interpretation("interp-kg", "fwk-kg3"))
        r = client.get(f"{KG_BASE}/interpretations/interp-kg")
        assert r.status_code == 200
        assert r.json()["id"] == "interp-kg"

    def test_taxonomy_methods(self, client):
        r = client.get(f"{KG_BASE}/taxonomy/methods")
        assert r.status_code == 200
        data = r.json()
        assert "acts" in data and "frameworks" in data
