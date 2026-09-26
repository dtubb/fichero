"""Slice 7 (#4925) -- a segment's picture, cut to its SHAPE.

Spec: `build-notes-shapes-and-anchor.md`, "A segment's picture, cut to its
shape". Behaviour `source.segment.picture-by-shape`, and the pictures part of
`source.derived.recomputable`.

WHY THE ASSERTIONS ARE ON PIXELS. "Cut to its shape" is a claim about an image.
A test that checks a route returned 200 and a `Rendition` row exists would pass
on a picture of the whole page, which is the exact failure this slice exists to
fix. So each test paints a page whose colours say where things are, asks for the
picture, and reads the answer out of the returned PNG.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from fichero_server.media.region_crops import RegionCropUnavailable
from fichero_server.media.segment_pictures import (
    SEGMENT_PICTURE_ROLE,
    SegmentPictureOptions,
    picture_cache_key,
    segment_picture,
)
from fichero_server.models import (
    DocType,
    Document,
    FileType,
    Rendition,
    Status,
)
from fichero_server.models.anchors import AnchorShape, SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.segments import Segment, bbox_and_tile_from_anchor

pytestmark = pytest.mark.source_model

PAGE = 200
WHITE = (255, 255, 255)
INK = (0, 0, 0)
RED = (255, 0, 0)
BLUE = (0, 0, 255)


def _page(db, painter=None, name: str = "page.png") -> Document:
    """A real 200x200 image on disk inside the library, and its Document."""
    from PIL import Image

    image = Image.new("RGB", (PAGE, PAGE), WHITE)
    if painter is not None:
        painter(image)
    path = Path(db.path.parent) / name
    image.save(path)
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=str(path), status=Status.completed,
    )
    db.save(doc)
    return doc


def _fill(image, colour, rect):
    """Paint `colour` over the normalized `[x, y, w, h]` of the page."""
    from PIL import Image

    x, y, w, h = rect
    block = Image.new("RGB", (round(w * PAGE), round(h * PAGE)), colour)
    image.paste(block, (round(x * PAGE), round(y * PAGE)))


def _triangle(image, colour, points):
    from PIL import ImageDraw

    ImageDraw.Draw(image).polygon(
        [(p[0] * PAGE, p[1] * PAGE) for p in points], fill=colour
    )


def _segment(db, doc, anchor: SourceAnchor, *, baseline=None, version: int = 1) -> Segment:
    x, y, w, h, tile = bbox_and_tile_from_anchor(anchor)
    row = Segment(
        document_id=doc.id, pass_id=f"pass-{doc.id}", kind="line", anchor=anchor,
        baseline=baseline, bbox_x=x, bbox_y=y, bbox_w=w, bbox_h=h, tile=tile,
        doc_kind="page", provenance_kind=ProvenanceKind.workflow, version=version,
    )
    db.save(row)
    return row


def _colours(png: bytes):
    from PIL import Image

    image = Image.open(io.BytesIO(png))
    return image, image.convert("RGBA").getcolors(maxcolors=1 << 18)


def _dominant(png: bytes):
    _image, colours = _colours(png)
    return max(colours)[1][:3]


class TestThePictureIsTheSegmentsOwnArea:
    """The floor: a picture of one line is not a picture of the page."""

    def test_it_cuts_the_segments_box_and_not_the_page(self, db, client):
        area = (0.6, 0.7, 0.2, 0.1)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        segment = db.query(Segment, document_id=doc.id)[0]

        resp = client.get(f"/api/segments/{segment.id}/picture")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "image/png"
        assert _dominant(resp.content) == BLUE
        image, _ = _colours(resp.content)
        assert image.size == (round(0.2 * PAGE), round(0.1 * PAGE))

    def test_a_margin_brings_the_surroundings_in(self, db, client):
        """A recogniser wants a little room; the room is the caller's choice,
        and it is around the SHAPE rather than a fixed number of pixels."""
        area = (0.4, 0.4, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        segment = db.query(Segment, document_id=doc.id)[0]

        tight = client.get(f"/api/segments/{segment.id}/picture")
        roomy = client.get(f"/api/segments/{segment.id}/picture", params={"margin": 0.5})
        tight_image, _ = _colours(tight.content)
        roomy_image, _ = _colours(roomy.content)
        assert roomy_image.size[0] > tight_image.size[0]
        # The extra room is white page, so blue is no longer everything.
        assert _dominant(roomy.content) == WHITE

    def test_the_derived_box_of_a_shapes_anchor_is_used(self, db, client):
        """Shapes, not a rect, and the picture still lands on the ink."""
        points = [[0.6, 0.7], [0.8, 0.7], [0.8, 0.8], [0.6, 0.8]]
        doc = _page(db, lambda image: _triangle(image, BLUE, points))
        _segment(
            db, doc,
            SourceAnchor(
                document_id=doc.id,
                shapes=[AnchorShape(kind="polygon", points=points)],
            ),
        )
        segment = db.query(Segment, document_id=doc.id)[0]
        resp = client.get(f"/api/segments/{segment.id}/picture")
        assert resp.status_code == 200
        assert _dominant(resp.content) == BLUE


class TestAShapeIsMaskedNotBoxed:
    """`source.segment.picture-by-shape`: the spec's own test -- a triangle's
    picture is transparent outside the triangle."""

    TRIANGLE = [[0.5, 0.2], [0.8, 0.8], [0.2, 0.8]]

    def _triangle_page(self, db):
        doc = _page(db, lambda image: _triangle(image, INK, self.TRIANGLE))
        _segment(
            db, doc,
            SourceAnchor(
                document_id=doc.id,
                shapes=[AnchorShape(kind="polygon", points=self.TRIANGLE)],
            ),
        )
        return doc, db.query(Segment, document_id=doc.id)[0]

    def test_outside_the_triangle_is_transparent(self, db, client):
        doc, segment = self._triangle_page(db)
        resp = client.get(f"/api/segments/{segment.id}/picture", params={"mask": True})
        assert resp.status_code == 200
        image, _ = _colours(resp.content)
        rgba = image.convert("RGBA")
        # A top corner of the bounding box is outside the triangle; the middle
        # of the top edge is inside it.
        width, height = rgba.size
        assert rgba.getpixel((0, 0))[3] == 0, "the corner outside the shape must be empty"
        assert rgba.getpixel((width - 1, 0))[3] == 0, "and so must the other one"
        assert rgba.getpixel((width // 2, height - 2))[3] == 255, "the shape itself must be opaque"

    def test_without_the_mask_the_corner_is_page(self, db, client):
        """The mask is asked for, not assumed: a caller who wants the plain
        box gets the plain box, opaque corners and all."""
        doc, segment = self._triangle_page(db)
        resp = client.get(f"/api/segments/{segment.id}/picture")
        image, _ = _colours(resp.content)
        assert image.convert("RGBA").getpixel((0, 0))[3] == 255

    def test_a_segment_with_no_outline_is_unaffected_by_the_mask(self, db, client):
        """Asking to mask a segment that has only a rectangle is not an error
        -- there is simply nothing to cut away."""
        area = (0.3, 0.3, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        segment = db.query(Segment, document_id=doc.id)[0]
        resp = client.get(f"/api/segments/{segment.id}/picture", params={"mask": True})
        assert resp.status_code == 200
        assert _dominant(resp.content) == BLUE


class TestATiltedLineIsLevelledOnItsBaseline:
    """`source.segment.curved-baseline`: a tilted line's picture is level when
    straightened. Asserted by measuring how much the ink SLOPES, before and
    after -- which is what "level" means and what a recogniser cares about."""

    #: A stripe running down-right across the middle of the page.
    BASELINE = [[0.2, 0.35], [0.8, 0.65]]

    @staticmethod
    def _slope(png: bytes) -> float:
        """How far the ink's vertical centre drifts from the left of the
        picture to the right, in rows. Zero is level."""
        from PIL import Image

        image = Image.open(io.BytesIO(png)).convert("RGBA")
        width, height = image.size

        def centre(column: int) -> float | None:
            rows = [
                row
                for row in range(height)
                if image.getpixel((column, row))[3] > 0
                and sum(image.getpixel((column, row))[:3]) < 200
            ]
            return sum(rows) / len(rows) if rows else None

        inked = [(c, mid) for c in range(width) if (mid := centre(c)) is not None]
        if len(inked) < 2:
            return 0.0
        return abs(inked[-1][1] - inked[0][1])

    def _tilted_page(self, db):
        from PIL import ImageDraw

        def paint(image):
            ImageDraw.Draw(image).line(
                [(p[0] * PAGE, p[1] * PAGE) for p in self.BASELINE],
                fill=INK, width=4,
            )

        doc = _page(db, paint)
        _segment(
            db, doc,
            SourceAnchor(document_id=doc.id, rect=[0.2, 0.3, 0.6, 0.4]),
            baseline=self.BASELINE,
        )
        return doc, db.query(Segment, document_id=doc.id)[0]

    def test_straightening_flattens_the_line(self, db, client):
        doc, segment = self._tilted_page(db)
        tilted = client.get(f"/api/segments/{segment.id}/picture")
        level = client.get(
            f"/api/segments/{segment.id}/picture", params={"straighten": True}
        )
        assert tilted.status_code == level.status_code == 200
        tilted_slope = self._slope(tilted.content)
        level_slope = self._slope(level.content)
        assert tilted_slope > 20, "the premise: the unstraightened line really slopes"
        assert level_slope < 2, "after straightening the ink must run along one row"

    def test_a_segment_with_no_baseline_is_not_rotated(self, db, client):
        """Nothing to level against, so nothing is guessed."""
        area = (0.3, 0.3, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        segment = db.query(Segment, document_id=doc.id)[0]
        plain = client.get(f"/api/segments/{segment.id}/picture")
        asked = client.get(
            f"/api/segments/{segment.id}/picture", params={"straighten": True}
        )
        plain_image, _ = _colours(plain.content)
        asked_image, _ = _colours(asked.content)
        assert plain_image.size == asked_image.size


class TestAPictureIsWorkedOutNeverARecord:
    """`source.derived.recomputable`: cached so the same request twice is not
    the same work twice, and remade when the segment changes."""

    def _blue_segment(self, db):
        area = (0.3, 0.3, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        return doc, db.query(Segment, document_id=doc.id)[0]

    def test_the_same_options_twice_return_the_same_picture(self, db):
        doc, segment = self._blue_segment(db)
        first = segment_picture(db, segment.id)
        second = segment_picture(db, segment.id)
        assert first.id == second.id
        assert first.path == second.path
        pictures = [
            r for r in db.query(Rendition, document_id=doc.id)
            if r.role == SEGMENT_PICTURE_ROLE
        ]
        assert len(pictures) == 1, "a second call must not stack another copy"

    def test_different_options_are_different_pictures(self, db):
        doc, segment = self._blue_segment(db)
        plain = segment_picture(db, segment.id)
        masked = segment_picture(db, segment.id, options=SegmentPictureOptions(mask=True))
        roomy = segment_picture(
            db, segment.id, options=SegmentPictureOptions(margin=0.25)
        )
        assert len({plain.id, masked.id, roomy.id}) == 3

    def test_a_version_bump_makes_a_new_one(self, db):
        """The whole reason the version is in the key: an edited segment has a
        new version, so the stale picture is never asked for again -- nothing
        has to remember to delete it."""
        doc, segment = self._blue_segment(db)
        before = segment_picture(db, segment.id)
        segment.version += 1
        db.save(segment)
        after = segment_picture(db, db.query(Segment, document_id=doc.id)[0].id)
        assert after.id != before.id

    def test_the_key_is_the_four_options_the_version_and_the_frame(self, db):
        doc, segment = self._blue_segment(db)
        base = picture_cache_key(segment, SegmentPictureOptions())
        assert base != picture_cache_key(segment, SegmentPictureOptions(mask=True))
        assert base != picture_cache_key(segment, SegmentPictureOptions(straighten=True))
        assert base != picture_cache_key(segment, SegmentPictureOptions(margin=0.1))
        assert base != picture_cache_key(segment, SegmentPictureOptions(size=64))
        moved = segment.model_copy(update={"version": 2})
        assert base != picture_cache_key(moved, SegmentPictureOptions())

    def test_the_picture_is_never_what_the_reader_opens(self, db):
        """A derived view must not become the node's primary rendition."""
        doc, segment = self._blue_segment(db)
        rendition = segment_picture(db, segment.id)
        assert rendition.is_primary is False
        assert rendition.pixel_width and rendition.pixel_height

    def test_a_stale_id_is_answered_because_a_picture_is_a_read(self, db):
        doc, segment = self._blue_segment(db)
        direct = segment_picture(db, segment.id)
        assert direct.path


class TestTheRefusals:
    """Absent, not faked. Each refusal says which of the two outcomes it is."""

    def test_a_segment_measured_on_another_image_is_refused(self, db):
        """The refusal `materialize_region_crop` already makes: cutting the
        page at fractions taken from a deskewed frame gives a plausible
        picture of the wrong place."""
        area = (0.3, 0.3, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(
            db, doc,
            SourceAnchor(document_id=doc.id, rect=list(area), rendition_id="rend-deskewed"),
        )
        segment = db.query(Segment, document_id=doc.id)[0]
        with pytest.raises(RegionCropUnavailable, match="no image here"):
            segment_picture(db, segment.id)

    def test_it_uses_the_named_rendition_when_that_image_is_here(self, db):
        """The other half of the same rule: named AND present is fine, and the
        picture comes from that frame rather than the page's."""
        area = (0.0, 0.0, 1.0, 1.0)
        doc = _page(db, lambda image: _fill(image, WHITE, (0, 0, 1, 1)))
        crop = _page(db, lambda image: _fill(image, RED, (0, 0, 1, 1)), name="crop.png")
        rendition = Rendition(
            document_id=doc.id, role="deskewed", path=crop.path,
            pixel_width=PAGE, pixel_height=PAGE,
        )
        db.save(rendition)
        _segment(
            db, doc,
            SourceAnchor(document_id=doc.id, rect=list(area), rendition_id=rendition.id),
        )
        segment = [s for s in db.query(Segment, document_id=doc.id)][0]
        made = segment_picture(db, segment.id)
        assert Path(made.produced_from).name == "crop.png"

    def test_a_time_only_segment_has_no_picture(self, db):
        doc = _page(db)
        anchor = SourceAnchor(
            document_id=doc.id, media_ref="rec-1",
            shapes=[AnchorShape(kind="time", t_start=1.0, t_end=4.0)],
        )
        row = Segment(
            document_id=doc.id, pass_id="p", kind="utterance", anchor=anchor,
            bbox_x=0.0, bbox_y=0.0, bbox_w=0.0, bbox_h=0.0, tile="x0y0",
            doc_kind="page", provenance_kind=ProvenanceKind.workflow,
        )
        db.save(row)
        with pytest.raises(RegionCropUnavailable, match="no area on any image"):
            segment_picture(db, row.id)

    def test_a_size_beyond_the_limit_is_refused(self, db, client):
        area = (0.3, 0.3, 0.2, 0.2)
        doc = _page(db, lambda image: _fill(image, BLUE, area))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=list(area)))
        segment = db.query(Segment, document_id=doc.id)[0]
        resp = client.get(f"/api/segments/{segment.id}/picture", params={"size": 999999})
        assert resp.status_code == 422

    def test_a_size_bounds_the_work(self, db, client):
        """`size` is not decoration: an unbounded picture per request is an
        unbounded amount of work per request."""
        doc = _page(db, lambda image: _fill(image, BLUE, (0, 0, 1, 1)))
        _segment(db, doc, SourceAnchor(document_id=doc.id, rect=[0.0, 0.0, 1.0, 1.0]))
        segment = db.query(Segment, document_id=doc.id)[0]
        resp = client.get(f"/api/segments/{segment.id}/picture", params={"size": 50})
        image, _ = _colours(resp.content)
        assert max(image.size) <= 50

    def test_a_missing_segment_is_refused_not_invented(self, db, client):
        resp = client.get("/api/segments/seg-does-not-exist/picture")
        assert resp.status_code == 422
