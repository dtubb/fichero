"""Tests for hermeneutics routes.

Hermeneutics manages interpretive frameworks (historical, disciplinary,
thematic…) and their application to claims via Interpretations and
Patterns. Routes live at /api/hermeneutics/... (router has no prefix,
mounted at "/api/hermeneutics").
"""

import pytest

from fichero.hermeneutics_models import (
    FrameworkType,
    InterpretiveActType,
    InterpretiveFramework,
    Interpretation,
    PatternStatus,
    PatternInstance,
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
        assert r.json() == []

    def test_returns_frameworks(self, client, db):
        db.save(_make_framework("fwk-1", "Framework A"))
        db.save(_make_framework("fwk-2", "Framework B"))

        r = client.get(f"{BASE}/frameworks")
        assert r.status_code == 200
        assert len(r.json()) == 2


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

        r = client.post(f"{BASE}/interpretations", json={
            "framework_id": "fwk-int",
            "passage_text": "Workers organized in the factories.",
            "interpretation_text": "This evidence shows class conflict.",
            "act": "contextualizing",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["framework_id"] == "fwk-int"

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
        assert r.json() == []

    def test_returns_interpretations(self, client, db):
        db.save(_make_framework("fwk-li"))
        db.save(_make_interpretation("i-1", "fwk-li"))
        db.save(_make_interpretation("i-2", "fwk-li"))

        r = client.get(f"{BASE}/interpretations")
        assert r.status_code == 200
        assert len(r.json()) == 2
