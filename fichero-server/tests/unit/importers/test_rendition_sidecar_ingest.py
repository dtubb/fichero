"""Applying .renditions.json at import time, against a real database."""

from __future__ import annotations

import json

from fichero_server.importers.ingest import apply_rendition_sidecars
from fichero_server.importers.rendition_sidecar import sidecar_path_for
from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import NodeRegion, RegionConfidence

SPLIT_PART = {
    "schema": "fichero-page-renditions-v0-proposed",
    "part": 1,
    "region_on_original": {
        "bbox": [0.0, 0.0, 0.5, 1.0],
        "space": "page-relative-fraction",
        "method": "nominal-even-split",
        "confidence": "nominal",
    },
    "renditions": [
        {"role": "enhanced", "path": "/p/part_1.jpg", "primary": True},
        {"role": "background_removed", "path": "/p/part_1.bg.png"},
        {"role": "original", "path": "/p/IMG.original.jpg", "storage": "staged"},
    ],
}


def _page_with_sidecar(db, tmp_path, payload, name="IMG_067_part_1.jpg") -> Document:
    source = tmp_path / name
    source.write_bytes(b"jpeg")
    sidecar_path_for(source).write_text(json.dumps(payload), encoding="utf-8")
    doc = Document(name=name, path=str(source), metadata={"source_path": str(source)})
    db.save(doc)
    return doc


def test_renditions_become_rows(db, tmp_path):
    doc = _page_with_sidecar(db, tmp_path, SPLIT_PART)

    counts = apply_rendition_sidecars(db, [doc])

    rows = db.query(Rendition, document_id=doc.id)
    assert counts["renditions"] == 2
    assert sorted(r.role for r in rows) == ["background_removed", "enhanced"]


def test_region_in_parent_is_written_to_the_document(db, tmp_path):
    doc = _page_with_sidecar(db, tmp_path, SPLIT_PART)

    apply_rendition_sidecars(db, [doc])

    stored = db.get(Document, doc.id)
    assert stored.region_in_parent is not None
    assert stored.region_in_parent.rect == [0.0, 0.0, 0.5, 1.0]
    assert stored.region_in_parent.confidence is RegionConfidence.nominal


def test_deferred_originals_are_counted_not_attached(db, tmp_path):
    """A split part's `original` is the whole opening — a different frame.
    Attaching it would be the mis-registration this program exists to fix."""
    doc = _page_with_sidecar(db, tmp_path, SPLIT_PART)

    counts = apply_rendition_sidecars(db, [doc])

    assert counts["deferred"] == 1
    assert all(r.role != "original" for r in db.query(Rendition, document_id=doc.id))


def test_existing_region_is_never_overwritten(db, tmp_path):
    """A user correction or a measured fold outranks a re-import of the same
    nominal guess."""
    doc = _page_with_sidecar(db, tmp_path, SPLIT_PART)
    doc.region_in_parent = NodeRegion(
        rect=[0.0, 0.0, 0.48, 1.0],
        confidence=RegionConfidence.user,
        method="user-drawn",
    )
    db.save(doc)

    counts = apply_rendition_sidecars(db, [doc])

    stored = db.get(Document, doc.id)
    assert stored.region_in_parent.confidence is RegionConfidence.user
    assert stored.region_in_parent.rect == [0.0, 0.0, 0.48, 1.0]
    assert counts["regions"] == 0


def test_document_without_a_sidecar_is_skipped_silently(db, tmp_path):
    source = tmp_path / "plain.jpg"
    source.write_bytes(b"jpeg")
    doc = Document(name="plain.jpg", path=str(source), metadata={"source_path": str(source)})
    db.save(doc)

    counts = apply_rendition_sidecars(db, [doc])

    assert counts == {
        "documents": 0,
        "renditions": 0,
        "regions": 0,
        "deferred": 0,
        "warnings": 0,
    }


def test_whole_page_attaches_its_original_and_gets_no_region(db, tmp_path):
    whole = {
        "schema": "fichero-page-renditions-v0-proposed",
        "part": None,
        "region_on_original": {
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "space": "page-relative-fraction",
            "method": "whole-page",
            "confidence": "exact",
        },
        "renditions": [
            {"role": "enhanced", "path": "/p/IMG_002.jpg", "primary": True},
            {"role": "original", "path": "/p/IMG_002.original.jpg"},
        ],
    }
    doc = _page_with_sidecar(db, tmp_path, whole, name="IMG_002.jpg")

    counts = apply_rendition_sidecars(db, [doc])

    assert counts["renditions"] == 2
    assert counts["deferred"] == 0
    assert db.get(Document, doc.id).region_in_parent is None


def test_reimport_is_idempotent_for_the_region(db, tmp_path):
    """Running twice must not flip a region back to nominal."""
    doc = _page_with_sidecar(db, tmp_path, SPLIT_PART)
    apply_rendition_sidecars(db, [doc])
    first = db.get(Document, doc.id).region_in_parent

    apply_rendition_sidecars(db, [doc])
    second = db.get(Document, doc.id).region_in_parent

    assert first.rect == second.rect
    assert second.confidence is RegionConfidence.nominal
