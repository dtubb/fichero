"""Tests for interpretation routes.

Interpretations apply hermeneutic frameworks to claims or document passages.
SwiftUI uses these routes to display interpretive analyses in the reader view.
"""

import pytest
from datetime import datetime

from fichero.hermeneutics_models import (
    FrameworkType,
    Interpretation,
    InterpretiveActType,
    InterpretiveFramework,
)
from fichero.models import Document, DocType, FileType, Status


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_framework(db, name: str = "Test Framework") -> InterpretiveFramework:
    fw = InterpretiveFramework(
        name=name,
        framework_type=FrameworkType.thematic,
        description="A test framework",
    )
    db.save(fw)
    return fw


def _make_doc(db) -> Document:
    doc = Document(
        name="doc.pdf",
        doc_type=DocType.file,
        file_type=FileType.pdf,
        path="/path/doc.pdf",
        status=Status.completed,
    )
    db.save(doc)
    return doc


def _make_interpretation(
    db,
    framework_id: str,
    document_id: str | None = None,
    act: InterpretiveActType = InterpretiveActType.reading,
) -> Interpretation:
    interp = Interpretation(
        framework_id=framework_id,
        document_id=document_id,
        interpretation_text="This is an interpretation",
        act=act,
        confidence=0.8,
    )
    db.save(interp)
    return interp


# ---------------------------------------------------------------------------
# GET /api/interpretations
# ---------------------------------------------------------------------------


class TestListInterpretations:
    def test_list_empty(self, client):
        r = client.get("/api/interpretations")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_returns_interpretations(self, client, db):
        fw = _make_framework(db)
        _make_interpretation(db, fw.id)
        r = client.get("/api/interpretations")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_by_framework_id(self, client, db):
        fw1 = _make_framework(db, "Framework A")
        fw2 = _make_framework(db, "Framework B")
        _make_interpretation(db, fw1.id)
        _make_interpretation(db, fw2.id)
        r = client.get(f"/api/interpretations?framework_id={fw1.id}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["framework_id"] == fw1.id

    def test_filter_by_document_id(self, client, db):
        fw = _make_framework(db)
        doc = _make_doc(db)
        _make_interpretation(db, fw.id, document_id=doc.id)
        _make_interpretation(db, fw.id)  # no doc
        r = client.get(f"/api/interpretations?document_id={doc.id}")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["document_id"] == doc.id

    def test_filter_by_act(self, client, db):
        fw = _make_framework(db)
        _make_interpretation(db, fw.id, act=InterpretiveActType.reading)
        _make_interpretation(db, fw.id, act=InterpretiveActType.critiquing)
        r = client.get("/api/interpretations?act=critiquing")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["act"] == "critiquing"

    def test_min_confidence_filter(self, client, db):
        fw = _make_framework(db)
        high = Interpretation(
            framework_id=fw.id,
            interpretation_text="high confidence",
            act=InterpretiveActType.reading,
            confidence=0.9,
        )
        db.save(high)
        low = Interpretation(
            framework_id=fw.id,
            interpretation_text="low confidence",
            act=InterpretiveActType.reading,
            confidence=0.2,
        )
        db.save(low)
        r = client.get("/api/interpretations?min_confidence=0.5")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# POST /api/interpretations
# ---------------------------------------------------------------------------


class TestCreateInterpretation:
    def test_create_with_framework(self, client, db):
        fw = _make_framework(db)
        payload = {
            "framework_id": fw.id,
            "passage_text": "The passage being interpreted",
            "interpretation_text": "A meaningful reading",
            "act": "reading",
            "confidence": 0.75,
        }
        r = client.post("/api/interpretations", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data["framework_id"] == fw.id
        assert data["act"] == "reading"

    def test_create_no_target_returns_400(self, client, db):
        fw = _make_framework(db)
        payload = {
            "framework_id": fw.id,
            "interpretation_text": "text",
            "act": "reading",
        }
        r = client.post("/api/interpretations", json=payload)
        assert r.status_code == 400

    def test_create_missing_framework_returns_404(self, client):
        payload = {
            "framework_id": "nonexistent-fw",
            "passage_text": "passage",
            "interpretation_text": "text",
            "act": "reading",
        }
        r = client.post("/api/interpretations", json=payload)
        assert r.status_code == 404

    def test_create_missing_claim_returns_404(self, client, db):
        fw = _make_framework(db)
        payload = {
            "framework_id": fw.id,
            "claim_id": "no-such-claim",
            "interpretation_text": "text",
            "act": "reading",
        }
        r = client.post("/api/interpretations", json=payload)
        assert r.status_code == 404

    def test_create_missing_document_returns_404(self, client, db):
        fw = _make_framework(db)
        payload = {
            "framework_id": fw.id,
            "document_id": "no-such-doc",
            "interpretation_text": "text",
            "act": "reading",
        }
        r = client.post("/api/interpretations", json=payload)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/interpretations/{id}
# ---------------------------------------------------------------------------


class TestGetInterpretation:
    def test_get_returns_detail(self, client, db):
        fw = _make_framework(db)
        interp = _make_interpretation(db, fw.id)
        r = client.get(f"/api/interpretations/{interp.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == interp.id
        assert "citation_lineage" in data

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/interpretations/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/interpretations/{id}
# ---------------------------------------------------------------------------


class TestPatchInterpretation:
    def test_patch_interpretation_text(self, client, db):
        fw = _make_framework(db)
        interp = _make_interpretation(db, fw.id)
        r = client.patch(
            f"/api/interpretations/{interp.id}",
            json={"interpretation_text": "Revised reading"},
        )
        assert r.status_code == 200
        assert r.json()["interpretation_text"] == "Revised reading"

    def test_patch_confidence(self, client, db):
        fw = _make_framework(db)
        interp = _make_interpretation(db, fw.id)
        r = client.patch(f"/api/interpretations/{interp.id}", json={"confidence": 0.95})
        assert r.status_code == 200
        assert r.json()["confidence"] == 0.95

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/interpretations/missing", json={"confidence": 0.5})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/interpretations/{id}
# ---------------------------------------------------------------------------


class TestDeleteInterpretation:
    def test_delete_removes_interpretation(self, client, db):
        fw = _make_framework(db)
        interp = _make_interpretation(db, fw.id)
        r = client.delete(f"/api/interpretations/{interp.id}")
        assert r.status_code == 200
        r2 = client.get(f"/api/interpretations/{interp.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/interpretations/missing")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/interpretations/taxonomy/methods
# ---------------------------------------------------------------------------


class TestMethodTaxonomy:
    def test_returns_taxonomy(self, client):
        r = client.get("/api/interpretations/taxonomy/methods")
        assert r.status_code == 200
        data = r.json()
        assert "acts" in data
        assert "frameworks" in data
