"""#4309 — OCR geometry is captured on the FIRST vision pass, never dropped.

Every pass that reads text off a page must persist the word/line boxes the
engine already computed alongside the text:

  * Apple Vision (image + PDF, whole-file and per-page fan-out) — Vision
    localizes everything it recognizes; the boxes ride into
    ``Artifact.ocr_geometry`` instead of being thrown away.
  * Born-digital PDF text layer — PyMuPDF localizes every word it extracts;
    the pdf_text passthrough now carries those boxes too.
  * The box↔text link (char spans into the page's own text) is stored so a
    later content edit can re-map its segment instead of orphaning geometry.

The Vision/PyMuPDF engines are stubbed at the module seams — no macOS Vision
call, no model call — and artifacts are read back through the typed DB layer,
which also pins the JSON round-trip of the nested ``OCRGeometryResult``.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from fichero_server.workflows.tools.vision_base import (
    VisionOCRBox,
    VisionOCRResult,
    _apple_geometry_result,
    _vision_flip_bbox_to_top_left,
)


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

def _make_pdf(path: Path, n_pages: int, *, with_text: bool = False) -> None:
    import fitz

    doc = fitz.open()
    try:
        for i in range(n_pages):
            page = doc.new_page()
            if with_text:
                page.insert_text(
                    (72, 72),
                    f"This is page {i + 1} with a proper embedded text layer.",
                )
        doc.save(str(path))
    finally:
        doc.close()


def _make_png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (16, 16), (255, 255, 255)).save(str(path), format="PNG")


@pytest.fixture
def temp_library(tmp_path, monkeypatch):
    monkeypatch.setenv("FICHERO_SKIP_DEFAULT_WORKFLOWS", "1")
    from fichero_server.db.manager import db_manager

    lib = tmp_path / "Geometry.fichero"
    lib.mkdir(parents=True, exist_ok=True)
    yield str(lib), db_manager
    try:
        db_manager.close_all()
    except Exception:
        pass


def _llm_config():
    from fichero_server.llm import LLMConfig

    return LLMConfig(provider="openai", model="gpt-4o")


def _vision_result(page_index: int | None = None) -> VisionOCRResult:
    """A fake Apple Vision result with one line + two word boxes and spans."""
    text = "Hello world"
    return VisionOCRResult(
        text=text,
        line_boxes=[
            VisionOCRBox(
                text=text,
                bbox=[0.1, 0.8, 0.6, 0.1],
                confidence=0.97,
                page_index=page_index,
                char_start=0,
                char_end=len(text),
            )
        ],
        word_boxes=[
            VisionOCRBox(
                text="Hello",
                bbox=[0.1, 0.8, 0.25, 0.1],
                confidence=0.97,
                page_index=page_index,
                char_start=0,
                char_end=5,
            ),
            VisionOCRBox(
                text="world",
                bbox=[0.4, 0.8, 0.3, 0.1],
                confidence=0.97,
                page_index=page_index,
                char_start=6,
                char_end=11,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# A. Pure helpers
# ---------------------------------------------------------------------------

class TestGeometryHelpers:

    def test_flip_bbox_converts_bottom_left_to_top_left(self):
        # Vision: y=0.7 from the bottom, height 0.1 → top-left y = 0.2.
        assert _vision_flip_bbox_to_top_left([0.1, 0.7, 0.5, 0.1]) == pytest.approx(
            [0.1, 0.2, 0.5, 0.1]
        )

    def test_flip_bbox_clamps_epsilon_overhang(self):
        x, y, w, h = _vision_flip_bbox_to_top_left([0.95, -0.0000001, 0.0500001, 1.0000002])
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
        assert x + w <= 1.0 + 1e-9 and y + h <= 1.0 + 1e-9

    def test_apple_geometry_result_maps_levels_spans_and_provider(self):
        geometry = _apple_geometry_result(_vision_result(page_index=2))
        assert geometry is not None
        assert geometry.provider == "apple_vision"
        assert geometry.text == "Hello world"
        levels = {box.level.value for box in geometry.boxes}
        assert levels == {"line", "word"}
        word = next(b for b in geometry.boxes if b.text == "world")
        assert (word.char_start, word.char_end) == (6, 11)
        assert word.page_index == 2
        # A region must record the KIND of evidence it came from, not only the
        # engine: recognised-from-ink and read-from-a-text-layer have different
        # trustworthiness (#4309).
        assert geometry.source == "apple_vision_ocr"
        assert all(box.source == "apple_vision_ocr" for box in geometry.boxes)

    def test_apple_geometry_result_says_produced_nothing_not_nothing_at_all(self):
        """A blank page is a fact about the PAGE, not about the engine.

        Vision can localize, so zero boxes means it looked and found nothing —
        which must not be recorded the same way as "geometry was never
        attempted". Returning None conflated the two.
        """
        from fichero_server.media.ocr_geometry import (
            OCRGeometryStatus,
            geometry_status,
        )

        empty = VisionOCRResult(text="", line_boxes=[], word_boxes=[])
        geometry = _apple_geometry_result(empty)
        assert geometry is not None
        assert geometry.boxes == []
        assert geometry_status(geometry) is OCRGeometryStatus.PRODUCED_NOTHING
        # and "nothing recorded at all" still reads as not_run
        assert geometry_status(None) is OCRGeometryStatus.NOT_RUN

    def test_vision_geometry_from_results_flips_and_links_spans(self):
        """Fake Vision observations → flipped boxes + char spans per line."""
        from fichero_server.workflows.tools.vision_base import (
            _vision_geometry_from_results,
        )

        class FakeCandidate:
            def __init__(self, text):
                self._text = text

            def string(self):
                return self._text

            def confidence(self):
                return 0.9

        class FakeObservation:
            def __init__(self, text, bbox):
                self._candidate = FakeCandidate(text)
                self._bbox = bbox

            def topCandidates_(self, _n):
                return [self._candidate]

            def boundingBox(self):
                return self._bbox

        results = [
            FakeObservation("First line", {"x": 0.1, "y": 0.8, "width": 0.5, "height": 0.1}),
            FakeObservation("Second", {"x": 0.1, "y": 0.6, "width": 0.3, "height": 0.1}),
        ]
        geometry = _vision_geometry_from_results(results, page_index=0)
        assert geometry.text == "First line\nSecond"
        first, second = geometry.line_boxes
        # Bottom-left 0.8 + h 0.1 → top-left y 0.1 (first line is at the top).
        assert first.bbox == pytest.approx([0.1, 0.1, 0.5, 0.1])
        assert (first.char_start, first.char_end) == (0, 10)
        # "Second" starts after "First line\n".
        assert (second.char_start, second.char_end) == (11, 17)


# ---------------------------------------------------------------------------
# B. Apple Vision passes persist geometry on the saved artifact
# ---------------------------------------------------------------------------

class TestAppleVisionGeometryPersisted:

    @pytest.mark.asyncio
    async def test_image_pass_saves_geometry(self, temp_library, tmp_path):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        png = tmp_path / "page.png"
        _make_png(png)

        doc = Document(
            name="page.png",
            doc_type=DocType.file,
            file_type=FileType.image,
            path=str(png),
        )
        db.save(doc)

        src = await files_tool(
            inputs={},
            state={"selected_doc_ids": [doc.id], "library_path": library_path},
            llm_config=_llm_config(),
        )

        with patch(
            "fichero_server.workflows.tools.vision_base.apple_vision_ocr_with_geometry",
            return_value=_vision_result(),
        ):
            result = await transcribe(
                inputs={
                    "files": src["files"],
                    "documents": src["documents"],
                    "vision_mode": "apple",
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )

        assert not result.get("error")
        arts = db.query(Artifact, document_id=doc.id, artifact_type="transcription")
        assert len(arts) == 1
        geometry = arts[0].ocr_geometry
        assert geometry is not None, "#4309: Apple Vision image pass dropped geometry"
        assert geometry.provider == "apple_vision"
        assert arts[0].provider == "apple"
        word = next(b for b in geometry.boxes if b.text == "Hello")
        assert (word.char_start, word.char_end) == (0, 5)
        assert word.bbox == pytest.approx([0.1, 0.8, 0.25, 0.1])

    @pytest.mark.asyncio
    async def test_whole_pdf_pass_saves_geometry_per_page_child(
        self, temp_library, tmp_path
    ):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "scan.pdf"
        _make_pdf(pdf, 3)  # scanned: no text layer → real OCR path

        parent = Document(
            name="scan.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        src = await files_tool(
            inputs={},
            state={"selected_doc_ids": [parent.id], "library_path": library_path},
            llm_config=_llm_config(),
        )

        pages = [_vision_result(page_index=i) for i in range(3)]
        seen_pages: list[int] = []

        def _fake_page_geometry(path, page_index, language="en"):
            seen_pages.append(page_index)
            return pages[page_index]

        with patch(
            "fichero_server.workflows.tools.vision_base._apple_ocr_pdf_page_geometry",
            side_effect=_fake_page_geometry,
        ), patch(
            "fichero_server.workflows.tools.vision_base._apple_ocr_pdf_pages_geometry",
            return_value=pages,
        ):
            result = await transcribe(
                inputs={
                    "files": src["files"],
                    "documents": src["documents"],
                    "vision_mode": "apple",
                    "force_ocr": True,
                },
                state={"library_path": library_path, "task_id": None},
                llm_config=_llm_config(),
            )

        assert not result.get("error")
        assert db.query(Artifact, document_id=parent.id, artifact_type="transcription") == []
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 3
        for child in children:
            arts = db.query(Artifact, document_id=child.id, artifact_type="transcription")
            assert len(arts) == 1, f"page {child.sequence} missing transcription artifact"
            geometry = arts[0].ocr_geometry
            assert geometry is not None, (
                f"#4309: page {child.sequence} Apple Vision pass dropped geometry"
            )
            assert geometry.provider == "apple_vision"
            assert {b.level.value for b in geometry.boxes} == {"line", "word"}
            assert all(b.page_index == child.sequence - 1 for b in geometry.boxes)


# ---------------------------------------------------------------------------
# C. Born-digital PDF text layer carries PyMuPDF word geometry
# ---------------------------------------------------------------------------

class TestPdfTextLayerGeometry:

    def test_layer_geometry_words_normalized_with_spans(self, tmp_path):
        from fichero_server.workflows.tools.vision_base import _pdf_text_layer_geometry

        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, 2, with_text=True)

        geoms = _pdf_text_layer_geometry(str(pdf))
        assert geoms is not None and len(geoms) == 2
        for page_index, geometry in enumerate(geoms):
            assert geometry is not None
            assert geometry.provider == "pymupdf"
            assert geometry.boxes, "text layer produced no word boxes"
            for box in geometry.boxes:
                assert box.level.value == "word"
                assert box.page_index == page_index
                x, y, w, h = box.bbox
                assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
                assert w > 0 and h > 0
                # box↔text link: the span slices the page's own text.
                assert box.char_start is not None and box.char_end is not None
                assert geometry.text[box.char_start:box.char_end] == box.text

    @pytest.mark.asyncio
    async def test_text_layer_pass_saves_geometry_per_page_child(
        self, temp_library, tmp_path
    ):
        from fichero_server.models import Artifact, Document, DocType, FileType
        from fichero_server.workflows.tools.sources import files_tool
        from fichero_server.workflows.tools.transcribe import transcribe

        library_path, db_manager = temp_library
        db = db_manager.get_database(library_path)
        pdf = tmp_path / "digital.pdf"
        _make_pdf(pdf, 2, with_text=True)

        parent = Document(
            name="digital.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            path=str(pdf),
        )
        db.save(parent)

        src = await files_tool(
            inputs={},
            state={"selected_doc_ids": [parent.id], "library_path": library_path},
            llm_config=_llm_config(),
        )

        result = await transcribe(
            inputs={
                "files": src["files"],
                "documents": src["documents"],
                "vision_mode": "apple",
            },
            state={"library_path": library_path, "task_id": None},
            llm_config=_llm_config(),
        )

        assert not result.get("error")
        children = db.query(Document, parent_id=parent.id, doc_type=DocType.page)
        assert len(children) == 2
        for child in children:
            arts = db.query(Artifact, document_id=child.id, artifact_type="transcription")
            assert len(arts) == 1
            # (Provider label comes from the passthrough/pdf_text path the run
            # took; the geometry provenance below is the #4309 contract.)
            geometry = arts[0].ocr_geometry
            assert geometry is not None, (
                f"#4309: page {child.sequence} pdf_text pass dropped geometry"
            )
            assert geometry.provider == "pymupdf"
            assert all(b.page_index == child.sequence - 1 for b in geometry.boxes)


# ---------------------------------------------------------------------------
# D. API surface — geometry rides the single-artifact GET only
# ---------------------------------------------------------------------------

class TestArtifactResponseGeometry:

    def _artifact(self):
        from fichero_server.models import Artifact

        return Artifact(
            document_id="doc-1",
            artifact_type="transcription",
            content="Hello world",
            ocr_geometry=_apple_geometry_result(_vision_result()),
            provider="apple",
            model="apple-vision",
        )

    def test_single_get_includes_geometry(self):
        from fichero_server.api.routes.document.artifacts import _artifact_response

        response = _artifact_response(self._artifact(), include_geometry=True)
        assert response.ocr_geometry is not None
        assert response.ocr_geometry.provider == "apple_vision"
        assert len(response.ocr_geometry.boxes) == 3

    def test_list_shape_omits_geometry(self):
        from fichero_server.api.routes.document.artifacts import _artifact_response

        response = _artifact_response(self._artifact())
        assert response.ocr_geometry is None
