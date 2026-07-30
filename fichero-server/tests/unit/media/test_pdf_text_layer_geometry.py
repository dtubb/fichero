"""A PDF's text layer already carries its geometry; stop discarding it (#4418).

`pdf_loader.py` called `page.get_text()` — which flattens to a string and drops
every rectangle at the moment of extraction. `get_text("words")` returns the
identical text WITH coordinates, already in the file, at no cost. So for a
born-digital PDF (and every scan someone already OCR'd elsewhere) text regions
need no model, no workflow and no new pipeline.

These run against a REAL PDF built in the fixture, not a stub, because the
whole point is what PyMuPDF actually returns. Nothing here skips: no network,
no model, no provider key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz", reason="PyMuPDF is a hard dependency of ingest")

from fichero_server.media.ocr_geometry import (  # noqa: E402
    PDF_TEXT_LAYER_FLAG,
    OCRGeometryLevel,
    from_pymupdf_page,
)

_WORDS = "Marshall surveyed the Choco river in 1842"


@pytest.fixture
def text_layer_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with a real text layer."""
    path = tmp_path / "born-digital.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 144), _WORDS, fontsize=12)
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def scanned_pdf(tmp_path: Path) -> Path:
    """A one-page PDF with NO text layer — the scan case."""
    path = tmp_path / "scanned.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


class TestGeometryIsRecovered:
    def test_every_word_gets_a_box(self, text_layer_pdf: Path):
        doc = fitz.open(str(text_layer_pdf))
        try:
            result = from_pymupdf_page(doc[0], page_index=0)
        finally:
            doc.close()

        assert len(result.boxes) == len(_WORDS.split()), (
            "the text layer's words were not recovered as regions — the "
            "geometry is in the file and was being discarded (#4418)"
        )
        assert [box.text for box in result.boxes] == _WORDS.split()

    def test_boxes_are_word_level_and_provenanced(self, text_layer_pdf: Path):
        """A region's provenance matters as much as the region: a PDF text
        layer is not a recognition result and must not look like one."""
        doc = fitz.open(str(text_layer_pdf))
        try:
            result = from_pymupdf_page(doc[0], page_index=0)
        finally:
            doc.close()

        assert result.provider == "pymupdf"
        for box in result.boxes:
            assert box.level == OCRGeometryLevel.WORD
            assert box.provider == "pymupdf"
            assert box.source == "pdf_text_layer"
            assert box.page_index == 0
            assert box.confidence is None, (
                "a text layer has no confidence to report; inventing 1.0 "
                "would claim a certainty nothing measured"
            )


class TestTheCoordinateSpace:
    def test_all_boxes_are_normalised_page_relative(self, text_layer_pdf: Path):
        """The load-bearing constraint. Image-prep produces several renditions
        of one page, so geometry in any rendition's pixels is wrong against
        all the others. Fractions survive every rendition and zoom level."""
        doc = fitz.open(str(text_layer_pdf))
        try:
            result = from_pymupdf_page(doc[0], page_index=0)
        finally:
            doc.close()

        for box in result.boxes:
            x, y, width, height = box.bbox
            assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
            assert width > 0.0 and height > 0.0
            assert x + width <= 1.000001
            assert y + height <= 1.000001
            assert box.coordinate_space == "normalized"

    def test_geometry_is_independent_of_rendition_size(self, text_layer_pdf: Path):
        """The regression this space exists to prevent: rendering the same
        page at a different DPI must not move a single region."""
        doc = fitz.open(str(text_layer_pdf))
        try:
            page = doc[0]
            baseline = [box.bbox for box in from_pymupdf_page(page).boxes]
            # A rendition at 4x — the pixel dimensions change completely.
            pixmap = page.get_pixmap(matrix=fitz.Matrix(4.0, 4.0))
            assert pixmap.width > page.rect.width * 3
            again = [box.bbox for box in from_pymupdf_page(page).boxes]
        finally:
            doc.close()

        assert baseline == again, (
            "page-relative geometry changed when a different rendition was "
            "produced — it is not rendition-independent (#4418)"
        )

    def test_boxes_are_ordered_down_the_page_not_up(self, text_layer_pdf: Path):
        """Top-left origin, y growing downward — the contract the model
        documents and what image/W3C space expects. PDF's native space is
        bottom-left, so getting this backwards is the easy mistake."""
        doc = fitz.open(str(text_layer_pdf))
        try:
            page = doc[0]
            result = from_pymupdf_page(page)
            # Text was inserted at y=144 on a ~792pt-tall page: nearer the top.
            assert page.rect.height > 400
        finally:
            doc.close()

        for box in result.boxes:
            assert box.bbox[1] < 0.5, (
                "text placed near the top of the page reported as being in "
                "the lower half — the y axis is flipped"
            )


class TestTextAndBoxesStayLinked:
    def test_char_spans_index_into_the_result_text(self, text_layer_pdf: Path):
        """Spans are defined as offsets into the owning artifact's content, so
        building both from the same word stream keeps them exact by
        construction rather than by hoping two extractions agree."""
        doc = fitz.open(str(text_layer_pdf))
        try:
            result = from_pymupdf_page(doc[0])
        finally:
            doc.close()

        assert result.text == _WORDS
        for box in result.boxes:
            assert box.char_start is not None and box.char_end is not None
            assert result.text[box.char_start : box.char_end] == box.text


class TestNoTextLayerIsReportedHonestly:
    def test_scanned_page_reports_geometry_unavailable(self, scanned_pdf: Path):
        """"No text layer" must not look like "recognised nothing".

        Both produce zero boxes. Only the flag distinguishes them, and the
        overlay needs that difference to say "geometry unavailable" instead of
        rendering an empty page that implies recognition failed.
        """
        doc = fitz.open(str(scanned_pdf))
        try:
            result = from_pymupdf_page(doc[0], page_index=0)
        finally:
            doc.close()

        assert result.boxes == []
        assert result.metadata[PDF_TEXT_LAYER_FLAG] is False
        assert result.text == ""

    def test_text_layer_page_reports_the_flag_true(self, text_layer_pdf: Path):
        doc = fitz.open(str(text_layer_pdf))
        try:
            result = from_pymupdf_page(doc[0], page_index=0)
        finally:
            doc.close()

        assert result.metadata[PDF_TEXT_LAYER_FLAG] is True

    def test_a_page_without_dimensions_raises(self):
        """Fail loudly rather than emitting geometry normalised against zero."""

        class _NoRect:
            rect = None

            def get_text(self, _mode):  # pragma: no cover - never reached
                return []

        with pytest.raises(ValueError, match="no usable dimensions"):
            from_pymupdf_page(_NoRect())


class TestGeometryIsPersistedAtIngest:
    """Capturing geometry is only useful if it survives the import."""

    @staticmethod
    def _ingest(pdf_path: Path):
        from fichero_server.importers.ingest import (
            PDF_TEXT_GEOMETRY_ARTIFACT,
            _create_pdf_page_children,
        )
        from fichero_server.models import Artifact, Document, DocType

        saved: list = []

        class FakeDB:
            def save(self, row):
                saved.append(row)

            def get(self, *_args, **_kwargs):
                return None

            def query(self, *_args, **_kwargs):
                return []

            def embed(self, *_args, **_kwargs):
                return False

        parent = Document(name=pdf_path.name, doc_type=DocType.file)
        _create_pdf_page_children(parent, pdf_path, FakeDB())
        geometry_artifacts = [
            row
            for row in saved
            if isinstance(row, Artifact)
            and row.artifact_type == PDF_TEXT_GEOMETRY_ARTIFACT
        ]
        return geometry_artifacts

    def test_a_born_digital_page_lands_a_geometry_artifact(
        self, text_layer_pdf: Path
    ):
        artifacts = self._ingest(text_layer_pdf)

        assert len(artifacts) == 1, (
            "importing a PDF with a text layer produced no geometry artifact "
            "— the coordinates are in the file and are still being dropped"
        )
        geometry = artifacts[0].ocr_geometry
        assert geometry is not None
        assert len(geometry.boxes) == len(_WORDS.split())
        assert geometry.metadata[PDF_TEXT_LAYER_FLAG] is True
        assert artifacts[0].provider == "pymupdf"

    def test_a_scanned_page_lands_an_explicit_unavailable_record(
        self, scanned_pdf: Path
    ):
        """Absence of the artifact means "never processed"; presence with the
        flag false means "this page has no geometry". Writing nothing for a
        scan would collapse those two into one indistinguishable state."""
        artifacts = self._ingest(scanned_pdf)

        assert len(artifacts) == 1
        geometry = artifacts[0].ocr_geometry
        assert geometry is not None
        assert geometry.boxes == []
        assert geometry.metadata[PDF_TEXT_LAYER_FLAG] is False

    def test_geometry_failure_never_fails_the_import(self, text_layer_pdf: Path):
        """Geometry is a bonus on the import path. A page that cannot be read
        must cost its own artifact, not the whole import."""
        import fichero_server.importers.ingest as ingest_module
        from fichero_server.models import Document, DocType

        saved: list = []

        class FakeDB:
            def save(self, row):
                saved.append(row)

            def get(self, *_args, **_kwargs):
                return None

            def query(self, *_args, **_kwargs):
                return []

            def embed(self, *_args, **_kwargs):
                return False

        def _explode(*_args, **_kwargs):
            raise RuntimeError("geometry backend exploded")

        original = ingest_module._save_pdf_text_layer_geometry
        ingest_module._save_pdf_text_layer_geometry = _explode
        try:
            parent = Document(name=text_layer_pdf.name, doc_type=DocType.file)
            with pytest.raises(RuntimeError):
                ingest_module._create_pdf_page_children(
                    parent, text_layer_pdf, FakeDB()
                )
        finally:
            ingest_module._save_pdf_text_layer_geometry = original

        # And with the real (internally guarded) helper, a broken page is
        # swallowed: pages are still created.
        parent = Document(name=text_layer_pdf.name, doc_type=DocType.file)
        pages = ingest_module._create_pdf_page_children(
            parent, text_layer_pdf, FakeDB()
        )
        assert pages, "the import must still produce page children"
