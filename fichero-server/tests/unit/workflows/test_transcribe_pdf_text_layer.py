"""Regression tests for #1033 — Transcribe must not re-OCR a born-digital
PDF that already has a selectable text layer.

`_try_pdf_text_layer` (added for #957) was nested inside the
`vision_mode == "apple"` branch of `process_vision`, so any run using an
LLM vision provider re-OCR'd every digital PDF — wasted time and noisier
output than the embedded text. The check is now hoisted above the
vision-mode branch so it fires regardless of provider; `force_ocr`
overrides it.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision

# process_vision renders PDF pages to images via Quartz (macOS-only); on Linux
# CI the render fails ("No module named 'Quartz'") before the mocked vision call
# is reached. Use a built-in skipif (always honored at collection) rather than a
# custom marker, so the whole module is skipped off-macOS regardless of hooks.
pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="process_vision renders PDFs via Quartz (macOS-only); skipped on Linux CI",
)


def _make_pdf_with_text(path: Path, pages: list[str]) -> None:
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 72), body, fontsize=11)
    doc.save(str(path))
    doc.close()


def _llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


def _apple_llm_config() -> LLMConfig:
    return LLMConfig(provider="apple", model="apple-intelligence")


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


@pytest.mark.asyncio
async def test_born_digital_pdf_uses_text_layer_in_apple_mode(tmp_path: Path) -> None:
    """The #1033 fix: a born-digital PDF in vision_mode='apple' must use the
    embedded text layer rather than running Apple Vision OCR on the images."""
    pdf = tmp_path / "born_digital.pdf"
    _make_pdf_with_text(pdf, [
        "Davidson signed the deed on the third of March nineteen thirty one.",
        "Antonio Asprilla filed the complaint with the alcalde mayor.",
    ])

    vision_mock = AsyncMock(side_effect=AssertionError("vision OCR must not run"))
    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="apple",
        )

    assert "Davidson" in result["text"]
    assert "Asprilla" in result["text"]
    vision_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_scanned_pdf_page_llm_mode_calls_llm_not_text_layer(tmp_path: Path) -> None:
    """#2222 regression: a PDF page with no embedded text (is_blank=True at ingest)
    must always call the LLM vision path in vision_mode='llm', even when
    _try_pdf_text_layer returns a non-None list (e.g. thin OCR artifacts from
    the PDF scanner). Before the fix, a non-None layer set pdf_layer_used=True
    and silently returned empty text instead of calling the LLM."""
    pdf = tmp_path / "scan_with_thin_ocr.pdf"
    # Simulate a scanned PDF that PyMuPDF finds has a thin OCR layer — just
    # enough text to pass the non-empty check in _try_pdf_text_layer but not
    # the actual handwritten content.
    pdf.write_bytes(b"%PDF-stub")

    llm_result = "El alcalde mayor Antonio García firmó el acta."
    vision_mock = AsyncMock(return_value=llm_result)

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        # Simulate _try_pdf_text_layer returning non-None (thin OCR layer)
        # which is the bug trigger: before the fix this set pdf_layer_used=True
        # and skipped the LLM call, returning empty text for the blank page.
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=[""],  # non-None but empty content per page
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value="data:image/png;base64,STUB",
        ),
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[{
                "id": "page-1",
                "path": None,
                "parent_id": "parent-pdf-id",
                "sequence": 1,
                "page_content": None,
                "metadata": {"is_blank": True, "text_extracted": False},
            }],
            prompt="Transcribe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    # LLM must be called — not silently skipped by the text-layer shortcut.
    vision_mock.assert_awaited()
    assert llm_result in result["text"]


@pytest.mark.asyncio
async def test_force_ocr_bypasses_text_layer(tmp_path: Path) -> None:
    """force_ocr=True must skip the text-layer short-circuit and run the
    vision path even for a born-digital PDF (text layer itself garbage)."""
    pdf = tmp_path / "force.pdf"
    _make_pdf_with_text(pdf, ["Some genuine selectable text on the page."])

    vision_mock = AsyncMock(return_value="OCR OUTPUT")
    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,AAAA",
        ),
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
            force_ocr=True,
        )

    vision_mock.assert_awaited()
    assert "OCR OUTPUT" in result["text"]


def test_force_ocr_in_vision_config_schema() -> None:
    from fichero_server.workflows.tools.vision_base import VISION_CONFIG_SCHEMA

    assert "force_ocr" in VISION_CONFIG_SCHEMA
    assert VISION_CONFIG_SCHEMA["force_ocr"]["default"] is False


@pytest.mark.asyncio
async def test_born_digital_pdf_beats_stale_cached_artifact(tmp_path: Path) -> None:
    """#1064: a born-digital PDF must use its fresh text layer even when a
    stale (garbage) transcription artifact is already cached.

    Pre-fix, the skip-if-artifact cache check ran *before* the #1033
    text-layer short-circuit, so a pre-#1033 Apple Vision artifact full of
    OCR garbage shielded the short-circuit and got served on every run.
    The cache check is now gated on `not pdf_layer_used` — for a
    born-digital PDF it must be bypassed entirely.
    """
    pdf = tmp_path / "born_digital.pdf"
    _make_pdf_with_text(pdf, [
        "Davidson signed the deed on the third of March nineteen thirty one.",
    ])

    # A stale, garbage cached artifact — what a pre-#1033 OCR run left behind.
    stale = Mock(content="xvi ⍰⍰,⍰⍰⍰ -1— 0— +1—", id="stale-artifact-1")
    find_existing_mock = Mock(return_value=stale)
    vision_mock = AsyncMock(side_effect=AssertionError("vision OCR must not run"))

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.find_existing_artifact",
            new=find_existing_mock,
        ),
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_apple_llm_config(),
            library_path="/tmp/fichero-test-lib-1064",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="apple",
        )

    # The fresh text layer wins — not the stale garbage artifact.
    assert "Davidson" in result["text"]
    assert "⍰" not in result["text"]
    # The skip-if-artifact cache must be bypassed entirely for a born-digital
    # PDF — find_existing_artifact should never even be consulted.
    find_existing_mock.assert_not_called()
    vision_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_image_only_pdf_page_child_routes_to_apple_vision_page(
    tmp_path: Path,
) -> None:
    """#1274: in Catalogue per-page fan-out, a page child with no embedded
    text must OCR that page with Apple Vision instead of skipping or OCRing
    the whole parent PDF for every page branch."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF stub")
    documents = [{
        "id": "page-2",
        "path": None,
        "parent_id": "pdf-1",
        "sequence": 2,
        "page_content": None,
    }]

    from fichero_server.workflows.tools.vision_base import VisionOCRResult

    save_mock = AsyncMock(return_value="artifact-page-2")
    # #4309: the per-page apple branch fetches text + geometry in one pass.
    page_ocr_mock = AsyncMock(
        return_value=VisionOCRResult(
            text="OCR text from page 2", line_boxes=[], word_boxes=[]
        )
    )
    all_pages_mock = AsyncMock(
        side_effect=AssertionError("page-child branch must not OCR whole PDF")
    )

    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=save_mock),
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=None),
        patch(
            "fichero_server.workflows.tools.vision_base.apple_vision_ocr_pdf_page_geometry_async",
            new=page_ocr_mock,
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.apple_vision_ocr_pages_geometry_async",
            new=all_pages_mock,
        ),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_apple_llm_config(),
            library_path="/tmp/fichero-test-lib-1274",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="auto",
        )

    page_ocr_mock.assert_awaited_once_with(str(pdf), 1, "en-US")
    all_pages_mock.assert_not_awaited()
    assert result["text"] == "OCR text from page 2"
    assert result["artifacts"] == ["artifact-page-2"]
    assert result["page_records"] == [
        {"doc_id": "page-2", "text": "OCR text from page 2"}
    ]
    save_kwargs = save_mock.await_args.kwargs
    assert save_kwargs["document_id"] == "page-2"
    assert save_kwargs["llm_config"].provider == "apple"
    assert save_kwargs["llm_config"].model == "apple-vision"


@pytest.mark.asyncio
async def test_pdf_text_layer_page_child_uses_only_that_page(
    tmp_path: Path,
) -> None:
    """Per-page Catalogue routing should not turn one page child into the
    full parent PDF transcript when a text layer is available."""
    pdf = tmp_path / "born_digital.pdf"
    pdf.write_bytes(b"%PDF stub")
    documents = [{
        "id": "page-2",
        "path": None,
        "parent_id": "pdf-1",
        "sequence": 2,
        "page_content": "",
    }]

    page_ocr_mock = AsyncMock(
        side_effect=AssertionError("text-layer page must not OCR")
    )

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value="artifact-page-2"),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=["Text from page 1", "Text from page 2"],
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.apple_vision_ocr_pdf_page_async",
            new=page_ocr_mock,
        ),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_apple_llm_config(),
            library_path="/tmp/fichero-test-lib-1274",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="auto",
        )

    page_ocr_mock.assert_not_awaited()
    assert result["text"] == "Text from page 2"
    assert "Text from page 1" not in result["text"]
    assert result["page_records"] == [
        {"doc_id": "page-2", "text": "Text from page 2"}
    ]


@pytest.mark.asyncio
async def test_llm_vision_multipage_pdf_processes_all_pages(tmp_path: Path) -> None:
    """#2215 regression: LLM vision on a whole PDF (no per-page fan-out) must
    process every page separately and populate per_page_texts so
    _propagate_to_page_children distributes each page's transcript to its
    child document. Before the fix, only page 0 was rendered (hard-coded
    `page_index=0`) and _propagate_to_page_children never fired."""
    pdf = tmp_path / "multipage.pdf"
    _make_pdf_with_text(pdf, ["Page one body.", "Page two body."])

    page_transcripts = ["Transcription of page one.", "Transcription of page two."]
    llm_call_count = 0

    # `language` is passed by the caller (#2092). A mock that does not accept
    # it raises TypeError inside the per-page loop, which the loop logs and
    # swallows as a page failure — so this test failed with "got 0 LLM calls"
    # while looking like a fan-out regression. The mock had drifted from the
    # signature it stands in for.
    async def _mock_vision(images, prompt, config, language=None):
        nonlocal llm_call_count
        text = page_transcripts[llm_call_count % len(page_transcripts)]
        llm_call_count += 1
        return text

    save_mock = AsyncMock(return_value="artifact-parent")
    propagate_mock = AsyncMock(
        return_value=["artifact-page-1", "artifact-page-2"]
    )

    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=save_mock),
        # Force LLM path: pretend this is a scanned PDF with no text layer
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=None),
        # Avoid Quartz rendering in CI
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value="data:image/png;base64,STUB",
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._propagate_to_page_children",
            new=propagate_mock,
        ),
        patch("fichero_server.llm.vision", new=_mock_vision),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[{"id": "parent-pdf", "path": str(pdf)}],
            prompt="Transcribe.",
            llm_config=_llm_config(),
            library_path="/tmp/fichero-test-2215",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    # LLM must be called once per page (2), not just once for page 0
    assert llm_call_count == 2, (
        f"Expected 2 LLM calls (one per page), got {llm_call_count}. "
        "Fix: LLM path must iterate all pages, not hard-code page_index=0."
    )
    # Both page transcriptions appear in the combined output
    assert "page one" in result["text"]
    assert "page two" in result["text"]
    # _propagate_to_page_children must be triggered with all per-page texts
    propagate_mock.assert_awaited_once()
    propagated_parent_id, propagated_texts = propagate_mock.await_args.args[:2]
    assert propagated_parent_id == "parent-pdf"
    assert propagated_texts == page_transcripts
    assert result["artifacts"] == ["artifact-page-1", "artifact-page-2"]
