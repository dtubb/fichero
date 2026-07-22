"""Tests for the annotation cropping helpers (#914 extension)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from fichero.models.knowledge import Annotation, AnnotationKind
from fichero.models import Document, DocType
from fichero.workflows.tools._annotation_input import (
    annotation_crops_for_document,
    crop_image,
    crop_text,
    _parse_page_index,
)


# -----------------------------------------------------------------------------
# crop_text
# -----------------------------------------------------------------------------


class TestCropText:
    def test_returns_substring_when_char_range_set(self):
        doc = Document(
            name="x", doc_type=DocType.file,
            page_content="The quick brown fox jumped.",
        )
        ann = Annotation(
            document_id=doc.id,
            kind=AnnotationKind.highlight,
            char_start=4,
            char_end=15,
        )
        assert crop_text(doc, ann) == "quick brown"

    def test_falls_back_to_annotation_text_when_no_range(self):
        doc = Document(name="x", doc_type=DocType.file, page_content="")
        ann = Annotation(
            document_id=doc.id,
            kind=AnnotationKind.note,
            text="standalone note",
        )
        assert crop_text(doc, ann) == "standalone note"

    def test_returns_none_for_empty_annotation(self):
        doc = Document(name="x", doc_type=DocType.file, page_content="some text")
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.bookmark)
        assert crop_text(doc, ann) is None


# -----------------------------------------------------------------------------
# crop_image (PIL)
# -----------------------------------------------------------------------------


@pytest.fixture
def big_image(tmp_path: Path) -> Path:
    """A 200×200 PNG so the crop test exercises real PIL."""
    img = Image.new("RGB", (200, 200), color=(255, 0, 0))
    # Paint a 50×50 blue square at (75,75) — so a crop centred there
    # should be mostly blue.
    for x in range(75, 125):
        for y in range(75, 125):
            img.putpixel((x, y), (0, 0, 255))
    path = tmp_path / "big.png"
    img.save(path)
    return path


class TestCropImage:
    def test_returns_png_bytes_for_bbox(self, big_image):
        ann = Annotation(
            document_id="d", kind=AnnotationKind.highlight,
            # bbox is normalized [0,1] fractions (x,y,w,h): 0.4,0.4,0.2,0.2
            # on a 200×200 image = a 40×40 crop at (80,80), inside the blue square.
            bbox=[0.4, 0.4, 0.2, 0.2],
        )
        png = crop_image(big_image, ann)
        assert png is not None
        # Decode + check the crop is mostly blue.
        cropped = Image.open(io.BytesIO(png))
        assert cropped.size == (40, 40)
        # Centre pixel should be blue (painted region).
        assert cropped.getpixel((20, 20)) == (0, 0, 255)

    def test_returns_none_without_bbox(self, big_image):
        ann = Annotation(document_id="d", kind=AnnotationKind.note)
        assert crop_image(big_image, ann) is None

    def test_returns_none_for_missing_file(self, tmp_path):
        ann = Annotation(
            document_id="d", kind=AnnotationKind.highlight,
            bbox=[0, 0, 0.1, 0.1],
        )
        assert crop_image(tmp_path / "no.png", ann) is None


# -----------------------------------------------------------------------------
# _parse_page_index
# -----------------------------------------------------------------------------


class TestParsePageIndex:
    def test_page_14(self):
        assert _parse_page_index("Page 14") == 13

    def test_bare_number(self):
        assert _parse_page_index("3") == 2

    def test_p_prefix(self):
        assert _parse_page_index("p. 7") == 6

    def test_none(self):
        assert _parse_page_index(None) is None

    def test_no_number(self):
        assert _parse_page_index("cover") is None


# -----------------------------------------------------------------------------
# annotation_crops_for_document
# -----------------------------------------------------------------------------


class TestAnnotationCropsForDocument:
    def test_mixed_text_and_image(self, big_image):
        text_doc = Document(
            name="x", doc_type=DocType.file,
            page_content="alpha beta gamma delta",
        )
        anns = [
            Annotation(
                document_id=text_doc.id,
                kind=AnnotationKind.highlight,
                char_start=6, char_end=10,
            ),
            Annotation(
                document_id=text_doc.id,
                kind=AnnotationKind.rating,
                rating=4,
            ),  # rating-only — should be filtered out
        ]
        results = annotation_crops_for_document(text_doc, anns)
        assert len(results) == 1
        assert results[0]["crop_kind"] == "text"
        assert results[0]["content"] == "beta"

    def test_rating_only_filtered_out(self):
        doc = Document(name="x", doc_type=DocType.file, page_content="content")
        anns = [
            Annotation(document_id=doc.id, kind=AnnotationKind.rating, rating=5),
        ]
        results = annotation_crops_for_document(doc, anns)
        assert results == []
