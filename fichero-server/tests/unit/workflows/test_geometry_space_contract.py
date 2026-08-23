"""Consumers must READ the space a rect declares (2026-08-23).

Step 3 gave every rect a `space`. This is the audit finding that followed: the
field existed and nothing consumed it. Every caller that multiplies a rect by
a frame's width and height was still assuming normalized — which was safe only
because `Annotation.bbox` used to be validated into [0, 1], so "these are
fractions" was true by construction.

Adding `space` made a pixel rect REPRESENTABLE, and each of those callers
quietly inherited a way to be enormously wrong: a PDF rect at x=72 POINTS,
scaled as though 72 were a fraction, lands 44,000 points off the page — and
the crop still "succeeds".

`region_math` already had the guard and used it. These are the consumers that
did not.
"""

from __future__ import annotations

import pytest

from fichero_server.media.region_math import require_normalized
from fichero_server.models.anchors import AnchorSpace, NodeRegion, SourceAnchor


class TestTheGuardTakesEitherGeometry:
    """Both types are read the same way by callers, so both must be checkable."""

    def test_a_normalized_region_passes(self):
        # Not raising IS the behaviour; the explicit assert states it.
        assert require_normalized(NodeRegion(rect=[0, 0, 1, 1]), "region") is None

    def test_a_normalized_anchor_passes(self):
        assert (
            require_normalized(SourceAnchor(document_id="d", rect=[0, 0, 1, 1]), "anchor")
            is None
        )

    def test_a_pixel_anchor_is_refused(self):
        anchor = SourceAnchor(
            document_id="d", rect=[72, 144, 200, 24], space=AnchorSpace.pixel
        )
        with pytest.raises(ValueError, match="normalized space"):
            require_normalized(anchor, "anchor")

    def test_the_message_names_the_space_it_actually_got(self):
        """A guard that only says "wrong" sends the reader back to the data."""
        anchor = SourceAnchor(
            document_id="d", rect=[1, 1, 10, 10], space=AnchorSpace.pixel
        )
        with pytest.raises(ValueError, match="pixel"):
            require_normalized(anchor, "anchor")


class TestCropRefusesAPixelAnchor:
    """`crop_image` returns Optional and every failure path returns None, so
    refusing fits the existing contract: better no crop than the wrong crop."""

    def _annotation(self, space):
        from fichero_server.models.knowledge import Annotation, AnnotationKind

        return Annotation(
            document_id="d", kind=AnnotationKind.highlight,
            anchor=SourceAnchor(
                document_id="d", rect=[0.4, 0.4, 0.2, 0.2] if
                space is AnchorSpace.normalized else [40, 40, 20, 20],
                space=space,
            ),
        )

    def test_a_pixel_anchor_yields_no_crop(self, tmp_path):
        from PIL import Image

        from fichero_server.workflows.tools._annotation_input import crop_image

        path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), "white").save(path)

        assert crop_image(path, self._annotation(AnchorSpace.pixel)) is None

    def test_a_normalized_anchor_still_crops(self, tmp_path):
        from PIL import Image

        from fichero_server.workflows.tools._annotation_input import crop_image

        path = tmp_path / "page.png"
        Image.new("RGB", (200, 200), "white").save(path)

        assert crop_image(path, self._annotation(AnchorSpace.normalized)) is not None


class TestRenditionsRecordTheirFrame:
    """`Rendition` has carried pixel_width/pixel_height all along and nothing
    filled them (2026-08-23 audit).

    Without them the "same frame = rendition, different frame = node" rule is
    unverifiable: a rotated rendition, whose width and height are swapped, is
    indistinguishable from a same-frame one, and a child's `region_in_parent`
    no longer says unambiguously which frame its fractions are OF.
    """

    def test_a_persisted_rendition_records_its_pixel_size(self, db, tmp_path, test_package):
        from PIL import Image

        from fichero_server.models import Document, Rendition
        from fichero_server.workflows.tools.image_edit_chains import (
            persist_workflow_renditions,
        )

        source = tmp_path / "scan.png"
        Image.new("RGB", (300, 200), "white").save(source)
        doc = Document(name="scan.png", path=str(source),
                       metadata={"source_path": str(source)})
        db.save(doc)

        out = tmp_path / "out" / "scan_rotated.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        # Rotated: the frame is 200x300, NOT the original 300x200.
        Image.new("RGB", (200, 300), "white").save(out)

        persist_workflow_renditions(
            {"documents": [{"id": doc.id}], "library_path": str(test_package)},
            {},
            role="rotated",
            results=[{"source": str(source), "outputs": [str(out)]}],
        )

        rows = db.query(Rendition, document_id=doc.id)
        assert len(rows) == 1
        assert (rows[0].pixel_width, rows[0].pixel_height) == (200, 300)

    def test_an_unreadable_image_records_absence_not_a_guess(self, tmp_path):
        from fichero_server.workflows.tools.image_edit_chains import _pixel_size

        broken = tmp_path / "not-an-image.png"
        broken.write_bytes(b"definitely not a PNG")

        assert _pixel_size(broken) == (None, None)
