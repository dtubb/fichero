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
        "openings": 0,
        "adopted": 0,
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


class TestOpeningAdoption:
    """Split parts get the OPENING they came from, as a real parent node.

    The staging pipeline hands us the halves as real files and leaves the
    photographed opening unimported — which is why every part's `original`
    rendition had nowhere to attach.
    """

    def _part(self, db, tmp_path, part: int, stem: str = "IMG_067", parent_id=None):
        payload = {
            "schema": "fichero-page-renditions-v0-proposed",
            "part": part,
            "original_image_stem": stem,
            "region_on_original": {
                "bbox": [0.0 if part == 1 else 0.5, 0.0, 0.5, 1.0],
                "space": "page-relative-fraction",
                "method": "nominal-even-split",
                "confidence": "nominal",
            },
            "renditions": [
                {"role": "enhanced", "path": f"/p/{stem}_part_{part}.jpg", "primary": True},
                {"role": "original", "path": f"/p/_r/{stem}.original.jpg"},
            ],
        }
        name = f"{stem}_part_{part}.jpg"
        source = tmp_path / name
        source.write_bytes(b"jpeg")
        sidecar_path_for(source).write_text(json.dumps(payload), encoding="utf-8")
        doc = Document(
            name=name,
            path=str(source),
            parent_id=parent_id,
            sequence=part,
            metadata={"source_path": str(source), "ingest_mode": "link"},
        )
        db.save(doc)
        return doc

    def test_opening_is_created_and_adopts_both_parts(self, db, tmp_path):
        left = self._part(db, tmp_path, 1)
        right = self._part(db, tmp_path, 2)

        counts = apply_rendition_sidecars(db, [left, right])

        assert counts["openings"] == 1
        assert counts["adopted"] == 2
        opening = db.get(Document, db.get(Document, left.id).parent_id)
        assert opening.prototype_key == "opening"
        assert db.get(Document, right.id).parent_id == opening.id

    def test_the_opening_carries_the_archival_original(self, db, tmp_path):
        """The whole point: the original finally has a node to live on."""
        left = self._part(db, tmp_path, 1)

        apply_rendition_sidecars(db, [left])

        opening_id = db.get(Document, left.id).parent_id
        rows = db.query(Rendition, document_id=opening_id)
        assert [r.role for r in rows] == ["original"]
        assert rows[0].is_primary is True

    def test_parts_become_pages_and_keep_their_region(self, db, tmp_path):
        left = self._part(db, tmp_path, 1)

        apply_rendition_sidecars(db, [left])

        stored = db.get(Document, left.id)
        assert stored.prototype_key == "page"
        assert stored.region_in_parent.rect == [0.0, 0.0, 0.5, 1.0]

    def test_reimport_reuses_the_same_opening(self, db, tmp_path):
        left = self._part(db, tmp_path, 1)
        right = self._part(db, tmp_path, 2)
        apply_rendition_sidecars(db, [left, right])
        first_parent = db.get(Document, left.id).parent_id

        counts = apply_rendition_sidecars(db, [left, right])

        assert counts["openings"] == 0
        assert counts["adopted"] == 0
        assert db.get(Document, left.id).parent_id == first_parent

    def test_different_stems_get_different_openings(self, db, tmp_path):
        a = self._part(db, tmp_path, 1, stem="IMG_067")
        b = self._part(db, tmp_path, 1, stem="IMG_068")

        apply_rendition_sidecars(db, [a, b])

        assert db.get(Document, a.id).parent_id != db.get(Document, b.id).parent_id

    def test_whole_page_is_never_adopted(self, db, tmp_path):
        """A page that was never split belongs to no opening; inventing one
        would assert a containment that does not exist."""
        whole = {
            "schema": "fichero-page-renditions-v0-proposed",
            "part": None,
            "original_image_stem": "IMG_002",
            "renditions": [{"role": "enhanced", "path": "/p/IMG_002.jpg", "primary": True}],
        }
        doc = _page_with_sidecar(db, tmp_path, whole, name="IMG_002.jpg")

        counts = apply_rendition_sidecars(db, [doc])

        assert counts["openings"] == 0
        assert db.get(Document, doc.id).parent_id is None
