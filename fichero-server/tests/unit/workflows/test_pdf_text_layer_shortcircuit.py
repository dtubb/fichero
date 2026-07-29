"""Regression tests for #957 — skip Apple Vision OCR when the PDF
already has an embedded text layer.

`_try_pdf_text_layer` extracts per-page text via PyMuPDF and returns
the list when every non-empty page clears the threshold, or None
when the PDF is scanned (no text) or mixed (some text pages, some
scanned). Callers fall through to OCR when None is returned.
"""

from __future__ import annotations

import pytest

from fichero_server.workflows.tools.vision_base import _try_pdf_text_layer


def _make_pdf_with_text(path, pages: list[str]) -> None:
    """Build a PDF where each entry in `pages` becomes one page of
    body text. Uses PyMuPDF since it's how the production code path
    reads as well — round-trip is meaningful.
    """
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    doc.save(str(path))
    doc.close()


def _make_blank_pdf(path, num_pages: int) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    doc.save(str(path))
    doc.close()


class TestPdfTextLayerShortCircuit:
    def test_born_digital_pdf_returns_text_per_page(self, tmp_path):
        pdf = tmp_path / "born_digital.pdf"
        _make_pdf_with_text(pdf, [
            "Davidson signed the deed on the third of March nineteen thirty one.",
            "Antonio Asprilla filed the complaint with the alcalde mayor.",
            "The Court of First Instance heard the matter on the fifth.",
        ])
        result = _try_pdf_text_layer(str(pdf))
        assert result is not None, "Born-digital PDF should return text layer"
        assert len(result) == 3
        assert "Davidson" in result[0]
        assert "Asprilla" in result[1]
        assert "Court" in result[2]

    def test_blank_pdf_returns_none(self, tmp_path):
        # All pages empty → no usable text layer → caller should OCR
        pdf = tmp_path / "blank.pdf"
        _make_blank_pdf(pdf, 3)
        result = _try_pdf_text_layer(str(pdf))
        assert result is None, "Blank PDF should fall through to OCR"

    def test_mixed_pdf_returns_none(self, tmp_path):
        # First page has real text, second is too short (looks scanned)
        # → bail to OCR for uniformity rather than process pages
        # differently. The threshold is 20 non-space chars.
        pdf = tmp_path / "mixed.pdf"
        _make_pdf_with_text(pdf, [
            "Davidson signed the deed on the third of March nineteen thirty one.",
            "x",  # Way under the 20-char threshold
        ])
        result = _try_pdf_text_layer(str(pdf))
        assert result is None, "Mixed-quality PDF should fall through to OCR"

    def test_blank_page_inside_text_pdf_is_fine(self, tmp_path):
        # Pages with NO text at all (blank verso) are skipped from the
        # threshold check — only pages with SOME text need to clear it.
        # A 3-page PDF where page 2 is genuinely blank should still
        # be recognised as having a text layer.
        pdf = tmp_path / "with_blank_verso.pdf"
        _make_pdf_with_text(pdf, [
            "Davidson signed the deed on the third of March nineteen thirty one.",
            "",  # Genuinely blank — no text at all
            "Antonio Asprilla filed the complaint with the alcalde mayor.",
        ])
        result = _try_pdf_text_layer(str(pdf))
        assert result is not None
        assert len(result) == 3
        assert "Davidson" in result[0]
        assert result[1].strip() == ""
        assert "Asprilla" in result[2]

    def test_corrupt_pdf_returns_none(self, tmp_path):
        # PyMuPDF can't open a non-PDF file → helper returns None and
        # the caller falls through to OCR (which will itself fail
        # cleanly, but that's the existing behaviour).
        bad = tmp_path / "not_a_pdf.pdf"
        bad.write_bytes(b"this is not a PDF")
        result = _try_pdf_text_layer(str(bad))
        assert result is None
