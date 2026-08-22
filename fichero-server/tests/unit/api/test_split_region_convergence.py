"""In-app split/crop/segment record ONE geometry, and unsplit still works.

Before this, the crop/split routes wrote a child's geometry three ways at
once — `Document.bbox` as pixel ints, `metadata["source_bbox"]` as a copy of
the same numbers, and `metadata["view_kind"]` as a label — while the staged
import path wrote `region_in_parent`. Two shapes for "a page that is part of
another page" is what made in-app and staged splits incomparable.

The round trip matters more than any single assertion: `image.unsplit` is
already audited and undoable, and it must keep working against the converged
shape, or the convergence would have cost the undo it was meant to preserve.
"""

from __future__ import annotations

from PIL import Image

from fichero_server.api.routes.ingest.image_editing import (
    _region_in_parent,
    _split_children,
    split_image_impl,
    unsplit_image_impl,
)
from fichero_server.models import Document
from fichero_server.models.anchors import RegionConfidence


class _SplitRequest:
    """Minimal stand-in for ImageSplitRequest."""

    def __init__(self, bboxes=None):
        self.bboxes = bboxes


def _source(db, tmp_path, width=400, height=200) -> Document:
    path = tmp_path / "opening.png"
    Image.new("RGB", (width, height), "white").save(path)
    doc = Document(name="opening.png", path=str(path), metadata={"source_path": str(path)})
    db.save(doc)
    return doc


class TestPixelToRegion:
    def test_left_half_of_a_page(self):
        region = _region_in_parent((0, 0, 200, 400), 400, 400, "user-split")
        assert region.rect == [0.0, 0.0, 0.5, 1.0]

    def test_right_half_is_offset(self):
        region = _region_in_parent((200, 0, 200, 400), 400, 400, "user-split")
        assert region.rect == [0.5, 0.0, 0.5, 1.0]

    def test_confidence_is_measured_not_nominal(self):
        """These rects come from the actual image — a drag or a detected
        border — not from a 50/50 guess at where a fold might be."""
        region = _region_in_parent((0, 0, 10, 10), 100, 100, "user-crop")
        assert region.confidence is RegionConfidence.measured

    def test_unknown_source_dimensions_yield_no_region(self):
        """A region against an unrecorded frame is the original defect; better
        absent than wrong."""
        assert _region_in_parent((0, 0, 10, 10), 0, 0, "user-split") is None

    def test_degenerate_box_yields_no_region(self):
        assert _region_in_parent((0, 0, 0, 10), 100, 100, "user-split") is None


class TestSplitWritesOneGeometry:
    def test_children_carry_region_in_parent(self, db, tmp_path):
        source = _source(db, tmp_path)

        children = split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200), (200, 0, 200, 200)]))

        regions = [db.get(Document, c.id).region_in_parent for c in children]
        assert all(r is not None for r in regions)
        assert regions[0].rect == [0.0, 0.0, 0.5, 1.0]
        assert regions[1].rect == [0.5, 0.0, 0.5, 1.0]

    def test_the_duplicate_spellings_are_gone(self, db, tmp_path):
        """`source_bbox` duplicated the same numbers and `view_kind` had NO
        readers anywhere in the tree — verified before removing them."""
        source = _source(db, tmp_path)

        children = split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))

        metadata = db.get(Document, children[0].id).metadata or {}
        assert "source_bbox" not in metadata
        assert "view_kind" not in metadata

    def test_split_source_id_is_kept_because_unsplit_needs_it(self, db, tmp_path):
        """`parent_id` alone cannot say a child came from a SPLIT rather than
        being an ordinary page, and it is how `_split_children` finds them."""
        source = _source(db, tmp_path)

        children = split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))

        assert (db.get(Document, children[0].id).metadata or {})["split_source_id"] == source.id

    def test_source_image_is_untouched(self, db, tmp_path):
        source = _source(db, tmp_path)
        before = db.get(Document, source.id).path

        split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))

        assert db.get(Document, source.id).path == before
        assert db.get(Document, source.id).deleted_at is None


class TestRoundTrip:
    """split -> children with regions -> unsplit restores exactly."""

    def test_unsplit_still_finds_and_removes_the_children(self, db, tmp_path):
        source = _source(db, tmp_path)
        split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200), (200, 0, 200, 200)]))
        # Found via `_split_children`, i.e. the same discovery path unsplit
        # uses — asserting on the return value would not prove that still works.
        assert len(_split_children(db, source.id)) == 2

        removed = unsplit_image_impl(db, source.id)

        assert len(removed) == 2
        assert _split_children(db, source.id) == []

    def test_unsplit_preserves_the_source(self, db, tmp_path):
        source = _source(db, tmp_path)
        split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))

        unsplit_image_impl(db, source.id)

        restored = db.get(Document, source.id)
        assert restored is not None
        assert restored.deleted_at is None

    def test_children_are_soft_deleted_not_erased(self, db, tmp_path):
        """Nothing is destroyed — the rows survive with deleted_at set, which
        is what makes the audited undo able to bring them back."""
        source = _source(db, tmp_path)
        children = split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))
        child_id = children[0].id

        unsplit_image_impl(db, source.id)

        row = db.get(Document, child_id)
        assert row is not None
        assert row.deleted_at is not None
        # The geometry survives the soft delete, so a restore is exact.
        assert row.region_in_parent is not None

    def test_resplitting_after_unsplit_is_allowed(self, db, tmp_path):
        source = _source(db, tmp_path)
        split_image_impl(db, source.id, _SplitRequest([(0, 0, 200, 200)]))
        unsplit_image_impl(db, source.id)

        again = split_image_impl(db, source.id, _SplitRequest([(0, 0, 100, 200)]))

        assert len(again) == 1
        assert db.get(Document, again[0].id).region_in_parent.rect == [0.0, 0.0, 0.25, 1.0]
