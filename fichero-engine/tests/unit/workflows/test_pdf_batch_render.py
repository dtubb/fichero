"""Unit tests for PDF batch-render optimisation. (#2247)

Before the fix, _apple_ocr_pdf_pages called _render_pdf_page_to_cgimage once
per page — O(N) CGPDFDocumentCreateWithURL opens for an N-page PDF.

After the fix, a new _batch_render_pdf_pages_to_cgimages helper opens the
document exactly once and yields all CGImages in one pass. This test verifies
the 1-open invariant at the _apple_ocr_pdf_pages call boundary by patching
_batch_render_pdf_pages_to_cgimages directly.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.parametrize("num_pages", [1, 3, 10])
def test_apple_ocr_opens_pdf_exactly_once(num_pages: int):
    """#2247: _apple_ocr_pdf_pages must call _batch_render_pdf_pages_to_cgimages exactly once.

    Previously _render_pdf_page_to_cgimage was called num_pages times (one full
    CGPDFDocumentCreateWithURL parse per page). After the fix the batch helper
    is called once; its output is iterated in-process without re-opening the doc.
    """
    fake_images = [MagicMock(name=f"cg_image_{i}") for i in range(num_pages)]

    def fake_ocr(cg_image, language):
        idx = fake_images.index(cg_image)
        return f"page {idx} text"

    with (
        patch(
            "fichero.workflows.tools.vision_base._batch_render_pdf_pages_to_cgimages",
            return_value=(fake_images, num_pages),
        ) as mock_batch,
        patch(
            "fichero.workflows.tools.vision_base._vision_ocr_cgimage",
            side_effect=fake_ocr,
        ),
    ):
        from fichero.workflows.tools.vision_base import _apple_ocr_pdf_pages

        result = _apple_ocr_pdf_pages("/fake/path/doc.pdf", language="en")

    # The document must be opened exactly once, regardless of page count.
    assert mock_batch.call_count == 1, (
        f"#2247: _batch_render_pdf_pages_to_cgimages must be called exactly "
        f"once for a {num_pages}-page PDF, got {mock_batch.call_count}"
    )
    assert len(result) == num_pages, (
        f"Expected {num_pages} page results, got {len(result)}"
    )
    assert result == [f"page {i} text" for i in range(num_pages)], (
        "OCR text must match per-page fake_ocr output in order"
    )


def test_apple_ocr_none_image_returns_empty_string():
    """#2247: a None CGImage (failed render for one page) must yield '' not crash."""
    images = [MagicMock(name="good"), None, MagicMock(name="good2")]

    call_log: list[str] = []

    def fake_ocr(cg_image, language):
        call_log.append("called")
        return "text"

    with (
        patch(
            "fichero.workflows.tools.vision_base._batch_render_pdf_pages_to_cgimages",
            return_value=(images, 3),
        ),
        patch(
            "fichero.workflows.tools.vision_base._vision_ocr_cgimage",
            side_effect=fake_ocr,
        ),
    ):
        from fichero.workflows.tools.vision_base import _apple_ocr_pdf_pages

        result = _apple_ocr_pdf_pages("/fake/path/doc.pdf")

    assert result[1] == "", "None CGImage must produce an empty page string"
    assert result[0] == "text"
    assert result[2] == "text"
    # OCR must not be called for the None page
    assert len(call_log) == 2, "OCR must be skipped for the None-image page"


def test_apple_ocr_batch_render_error_returns_empty_list():
    """#2247: if _batch_render_pdf_pages_to_cgimages raises, return []."""
    with patch(
        "fichero.workflows.tools.vision_base._batch_render_pdf_pages_to_cgimages",
        side_effect=ValueError("Cannot open PDF"),
    ):
        from fichero.workflows.tools.vision_base import _apple_ocr_pdf_pages

        result = _apple_ocr_pdf_pages("/bad/path.pdf")

    assert result == [], "A failed batch render must return an empty list, not raise"
