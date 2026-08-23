"""Materializing a region node's own pixels.

A diary entry is a BAND of a page and shares the page's file — the region is
real, the bytes are not. Running a tool on it today means running it on the
whole page, because `files[i]` is the page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.media.region_crops import (
    REGION_CROP_ROLE,
    RegionCropUnavailable,
    materialize_region_crop,
    owns_its_pixels,
)
from fichero_server.models import Document, Rendition
from fichero_server.models.anchors import AnchorSpace, NodeRegion


def _page(db, tmp_path, size=(400, 800)) -> Document:
    from PIL import Image

    path = tmp_path / "page.png"
    Image.new("RGB", size, "white").save(path)
    doc = Document(name="page.png", path=str(path))
    db.save(doc)
    return doc


def _entry(db, page, rect, rendition_id=None) -> Document:
    entry = Document(
        name="entry", parent_id=page.id,
        # The shape `crop_image_child_impl` and the in-app split produce: the
        # child points at its PARENT's file.
        path=page.path,
        region_in_parent=NodeRegion(rect=rect, rendition_id=rendition_id),
    )
    db.save(entry)
    return entry


class TestWhenThereIsNothingToDo:
    def test_a_node_with_no_region_is_left_alone(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        assert materialize_region_crop(db, page, test_package) is None

    def test_a_node_that_owns_its_pixels_is_left_alone(self, db, tmp_path, test_package):
        """A workflow split part HAS its own file — no crop needed."""
        from PIL import Image

        page = _page(db, tmp_path)
        own = tmp_path / "part.png"
        Image.new("RGB", (10, 10), "blue").save(own)
        child = Document(
            name="part", parent_id=page.id, path=str(own),
            region_in_parent=NodeRegion(rect=[0, 0, 0.5, 1.0]),
        )
        db.save(child)

        assert materialize_region_crop(db, child, test_package) is None

    def test_owns_its_pixels_is_about_path_identity(self, db, tmp_path):
        page = _page(db, tmp_path)
        shared = Document(name="e", parent_id=page.id, path=page.path)
        owned = Document(name="p", parent_id=page.id, path=str(tmp_path / "other.png"))
        assert owns_its_pixels(shared, page) is False
        assert owns_its_pixels(owned, page) is True


class TestTheCrop:
    def test_the_band_becomes_a_rendition_of_the_entry(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.25, 1.0, 0.25])

        rendition = materialize_region_crop(db, entry, test_package)

        assert rendition is not None
        assert rendition.document_id == entry.id
        assert rendition.role == REGION_CROP_ROLE
        assert Path(rendition.path).is_file()

    def test_the_crop_is_the_size_the_region_describes(self, db, tmp_path, test_package):
        """A quarter-height band of an 800px page is 200px tall."""
        page = _page(db, tmp_path, size=(400, 800))
        entry = _entry(db, page, [0.0, 0.25, 1.0, 0.25])

        rendition = materialize_region_crop(db, entry, test_package)

        assert (rendition.pixel_width, rendition.pixel_height) == (400, 200)

    def test_the_frame_is_RECORDED_not_implied(self, db, tmp_path, test_package):
        """The only reason a tool may safely measure against this picture."""
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 0.5, 0.5])

        rendition = materialize_region_crop(db, entry, test_package)

        assert rendition.pixel_width and rendition.pixel_height

    def test_it_is_not_primary(self, db, tmp_path, test_package):
        """Whether an entry OPENS on its crop is a view decision. A storage
        default that changed what the reader opens would smuggle a product
        choice into a data field."""
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.5])

        assert materialize_region_crop(db, entry, test_package).is_primary is False

    def test_the_bytes_leave_the_temp_directory(self, db, tmp_path, test_package):
        """A Rendition row pointing into $TMPDIR is a promise the library
        cannot keep."""
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.5])

        stored = Path(materialize_region_crop(db, entry, test_package).path)

        assert stored.is_file()
        assert "/T/" not in str(stored) or str(test_package) in str(stored)


class TestIdempotence:
    def test_a_second_call_reuses_the_first_crop(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.5])

        first = materialize_region_crop(db, entry, test_package)
        second = materialize_region_crop(db, entry, test_package)

        assert first.id == second.id
        assert len(db.query(Rendition, document_id=entry.id)) == 1

    def test_re_running_does_not_stack_crops(self, db, tmp_path, test_package):
        """Keyed on the node and role, NOT on a filename — `_copy_to_library`
        renames on collision, so a path-keyed check never matches and every
        re-run stacks another copy. This program has made that mistake once."""
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.5])

        for _ in range(3):
            materialize_region_crop(db, entry, test_package)

        assert len(db.query(Rendition, document_id=entry.id)) == 1


class TestRefusals:
    def test_a_region_measured_on_another_rendition_is_REFUSED(self, db, tmp_path, test_package):
        """The load-bearing boundary. Cropping the original at fractions taken
        from a rotated frame yields a plausible band of the WRONG part."""
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.5], rendition_id="rend-rotated")

        with pytest.raises(RegionCropUnavailable, match="rend-rotated"):
            materialize_region_crop(db, entry, test_package)

    def test_the_refusal_explains_what_is_missing(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = _entry(db, page, [0, 0, 1, 0.5], rendition_id="r1")
        with pytest.raises(RegionCropUnavailable, match="transform"):
            materialize_region_crop(db, entry, test_package)

    def test_a_pixel_space_region_is_refused(self, db, tmp_path, test_package):
        page = _page(db, tmp_path)
        entry = Document(
            name="e", parent_id=page.id, path=page.path,
            region_in_parent=NodeRegion(
                rect=[0, 0, 100, 100], space=AnchorSpace.pixel
            ),
        )
        db.save(entry)

        with pytest.raises(ValueError, match="normalized"):
            materialize_region_crop(db, entry, test_package)

    def test_a_missing_parent_image_is_reported_not_skipped(self, db, tmp_path, test_package):
        page = Document(name="gone.png", path=str(tmp_path / "gone.png"))
        db.save(page)
        entry = _entry(db, page, [0, 0, 1, 0.5])

        with pytest.raises(RegionCropUnavailable, match="missing on disk"):
            materialize_region_crop(db, entry, test_package)

    def test_a_band_too_thin_to_have_pixels_is_refused(self, db, tmp_path, test_package):
        """A region can be valid geometry and still round to zero pixels."""
        page = _page(db, tmp_path, size=(400, 800))
        entry = _entry(db, page, [0.0, 0.0, 1.0, 0.0004])

        with pytest.raises(RegionCropUnavailable, match="empty at the parent's size"):
            materialize_region_crop(db, entry, test_package)
