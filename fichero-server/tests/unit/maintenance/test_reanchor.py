"""Bbox step 4 — the re-anchor pass marks frame-unproven renditions.

The rule is honesty over guessing (rulings 2026-08-20): a rendition whose
pixels disagree with the node's frame while claiming identity (transform
None) gets ``frame_status="unknown"`` so overlays render unanchored on it.
Nothing is ever guessed into a transform.
"""

from fichero_server.maintenance.reanchor import (
    FRAME_STATUS_KEY,
    FRAME_UNKNOWN,
    apply_reanchor,
    classify_rendition,
    plan_reanchor,
)
from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import NodeRegion


def _doc(db, doc_id="doc-1"):
    doc = Document(id=doc_id, name="page.jpg")
    db.save(doc)
    return doc


def _rendition(db, doc_id, role, width=None, height=None, transform=None, rid=None):
    rendition = Rendition(
        **({"id": rid} if rid else {}),
        document_id=doc_id,
        role=role,
        path=f"files/{role}.jpg",
        pixel_width=width,
        pixel_height=height,
        transform=transform,
    )
    db.save(rendition)
    return rendition


class TestClassification:
    def test_matching_aspect_is_frame_true(self):
        r = Rendition(document_id="d", role="enhanced", path="p",
                      pixel_width=2000, pixel_height=3000)
        bucket, _ = classify_rendition(r, 2000 / 3000)
        assert bucket == "frame_true"

    def test_pure_resample_is_frame_true(self):
        r = Rendition(document_id="d", role="enhanced", path="p",
                      pixel_width=1000, pixel_height=1500)
        bucket, _ = classify_rendition(r, 2000 / 3000)
        assert bucket == "frame_true"

    def test_divergent_aspect_without_transform_is_divergent(self):
        r = Rendition(document_id="d", role="enhanced", path="p",
                      pixel_width=1800, pixel_height=3000)  # cropped narrower
        bucket, reason = classify_rendition(r, 2000 / 3000)
        assert bucket == "divergent"
        assert "no transform" in reason

    def test_recorded_transform_is_never_touched(self):
        transform = NodeRegion(rect=[0.05, 0.0, 0.9, 1.0])
        r = Rendition(document_id="d", role="enhanced", path="p",
                      pixel_width=1800, pixel_height=3000, transform=transform)
        bucket, _ = classify_rendition(r, 2000 / 3000)
        assert bucket == "already_transformed"

    def test_missing_dims_is_no_evidence_not_divergent(self):
        r = Rendition(document_id="d", role="enhanced", path="p")
        bucket, _ = classify_rendition(r, 2000 / 3000)
        assert bucket == "no_evidence"

    def test_thumbnail_role_is_exempt(self):
        r = Rendition(document_id="d", role="thumbnail", path="p",
                      pixel_width=100, pixel_height=100)
        bucket, _ = classify_rendition(r, 2000 / 3000)
        assert bucket == "frame_true"


class TestPlanAndApply:
    def test_divergent_rendition_gets_marked_and_pass_is_idempotent(self, db):
        doc = _doc(db)
        _rendition(db, doc.id, "original", 2000, 3000)
        marked = _rendition(db, doc.id, "enhanced", 1800, 3000)

        plan = plan_reanchor(db)
        assert [rid for rid, _ in plan.to_mark] == [marked.id]

        assert apply_reanchor(db, plan) == 1
        row = db.get(Rendition, marked.id)
        assert getattr(row, FRAME_STATUS_KEY) == FRAME_UNKNOWN
        assert "frame unproven" in (row.note or "")

        # Second pass finds nothing new — marked rows classify as such.
        again = plan_reanchor(db)
        assert again.to_mark == []
        assert again.counts["already_marked"] == 1

    def test_document_without_original_dims_marks_nothing(self, db):
        doc = _doc(db, "doc-2")
        _rendition(db, doc.id, "enhanced", 1800, 3000)
        plan = plan_reanchor(db)
        assert plan.to_mark == []
        assert plan.counts["no_evidence"] == 1
