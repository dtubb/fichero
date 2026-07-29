"""Regression tests for #670 — LLM vision path must render PDF pages to PNG
data URIs rather than passing the raw PDF bytes through file_to_data_uri.

Root cause: the ``else`` (LLM vision) branch of ``process_vision`` called
``file_to_data_uri(file_path, ...)`` unconditionally.  ``file_to_data_uri``
only handles raster image formats (jpg/png/gif/…); it has no PDF support.
Opening a PDF with Pillow produces either a crash, a mis-labeled MIME type
(``image/jpeg``), or an unreadable blob — all of which silently send the
wrong data to the vision LLM.

The fix introduces ``_pdf_page_to_data_uri(file_path, page_index,
max_dimension)`` that calls the already-existing
``_render_pdf_page_to_cgimage`` and converts the result to a PNG data URI.
The LLM branch now calls this helper for ``.pdf`` files instead of the
image-only ``file_to_data_uri``.

These tests cover:
 1. Single-page PDF (no page selection) → page 0 is rendered, NOT file_to_data_uri.
 2. Multi-page PDF with a page selection (page index = 1) → page 1 is
    rendered, NOT page 0 or the whole PDF.
 3. A plain image file still goes through the original file_to_data_uri path
    (regression guard — the fix must not break image handling).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=False,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


_FAKE_PAGE0_URI = "data:image/png;base64,PAGE0FAKE"
_FAKE_PAGE1_URI = "data:image/png;base64,PAGE1FAKE"


# ---------------------------------------------------------------------------
# Test 1: single-page PDF with no explicit page selection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_vision_pdf_uses_rendered_page_not_file_to_data_uri(
    tmp_path: Path,
) -> None:
    """LLM vision path must NOT call file_to_data_uri for a PDF.

    It must call _pdf_page_to_data_uri (or equivalent) and pass the
    rendered page URI to the vision LLM.  Prior to the fix, file_to_data_uri
    was called unconditionally, which passed PIL-mishandled PDF bytes to the
    LLM.
    """
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    vision_mock = AsyncMock(return_value="page 0 result")

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=None,
        ),
        # The bug: file_to_data_uri should NOT be called for a PDF.
        # We assert it's not called after the fix.
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            side_effect=AssertionError(
                "#670: file_to_data_uri must not be called for PDFs — "
                "use _pdf_page_to_data_uri instead"
            ),
        ) as file_to_data_uri_mock,
        # The fix: _pdf_page_to_data_uri renders the correct page.
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value=_FAKE_PAGE0_URI,
        ) as pdf_page_mock,
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[],
            prompt="Describe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    # file_to_data_uri must never be called for a PDF
    file_to_data_uri_mock.assert_not_called()

    # _pdf_page_to_data_uri must be called with page 0 (no selection → first page)
    pdf_page_mock.assert_called_once()
    call_args = pdf_page_mock.call_args
    assert call_args[0][0] == str(pdf) or call_args.kwargs.get("file_path") == str(pdf), \
        "pdf_page_to_data_uri must receive the PDF path"
    page_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("page_index", 0)
    assert page_arg == 0, f"Expected page_index=0 for no-selection PDF, got {page_arg}"

    # The rendered URI must be passed to the vision LLM
    vision_call_images = vision_mock.await_args[1].get(
        "images", vision_mock.await_args[0][0] if vision_mock.await_args[0] else []
    )
    assert _FAKE_PAGE0_URI in vision_call_images, \
        "The page-0 rendered PNG URI must be sent to the vision LLM"

    assert result["text"] == "page 0 result"


# ---------------------------------------------------------------------------
# Test 2: multi-page PDF with explicit page selection (page index = 1)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_vision_pdf_page_selection_renders_correct_page(
    tmp_path: Path,
) -> None:
    """When a per-page fan-out document (page_index=1) is provided, the LLM
    vision path must render page 1, not page 0, and must NOT call
    file_to_data_uri.

    This is the core of the #670 bug: even if page selection was honoured for
    Apple Vision (#891), the LLM path always sent the raw PDF / page 0.
    """
    pdf = tmp_path / "multipage.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub multipage")

    # Simulate Catalogue per-page fan-out: documents[0] is the page-2 child
    # (sequence=2 → 0-based page_index=1).
    documents = [
        {
            "id": "page-child-2",
            "path": None,
            "parent_id": "pdf-root",
            "sequence": 2,       # 1-based → page_index = 1
            "page_content": None,
        }
    ]

    vision_mock = AsyncMock(return_value="page 1 result")

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=None,
        ),
        # Must NOT be called — the bug path
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            side_effect=AssertionError(
                "#670: file_to_data_uri must not be called for PDFs"
            ),
        ) as file_to_data_uri_mock,
        # The fix — must be called with page_index=1
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value=_FAKE_PAGE1_URI,
        ) as pdf_page_mock,
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Describe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    file_to_data_uri_mock.assert_not_called()

    pdf_page_mock.assert_called_once()
    call_args = pdf_page_mock.call_args
    page_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args.kwargs.get("page_index", 0)
    assert page_arg == 1, (
        f"#670: PDF page selection broken — expected page_index=1 for sequence=2, got {page_arg}. "
        "The LLM vision path must honour per-page fan-out selection."
    )

    vision_call_images = vision_mock.await_args[1].get(
        "images", vision_mock.await_args[0][0] if vision_mock.await_args[0] else []
    )
    assert _FAKE_PAGE1_URI in vision_call_images, \
        "The page-1 rendered PNG URI must be sent to the vision LLM, not page 0"

    assert result["text"] == "page 1 result"


@pytest.mark.asyncio
async def test_llm_vision_pdf_zero_sequence_selection_does_not_process_whole_pdf(
    tmp_path: Path,
) -> None:
    """Legacy sequence=0 page docs still mean page 0, not whole-PDF mode."""
    pdf = tmp_path / "multipage.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub multipage")

    fake_doc = MagicMock()
    fake_doc.__len__.return_value = 3
    fitz_mock = MagicMock()
    fitz_mock.open.return_value = fake_doc
    vision_mock = AsyncMock(return_value="first page only")

    with (
        patch.dict("sys.modules", {"fitz": fitz_mock}),
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._try_pdf_text_layer",
            return_value=None,
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            side_effect=AssertionError(
                "file_to_data_uri must not be called for PDFs"
            ),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value=_FAKE_PAGE0_URI,
        ) as pdf_page_mock,
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[{
                "id": "legacy-page-0",
                "path": None,
                "parent_id": "pdf-root",
                "sequence": 0,
                "page_content": None,
            }],
            prompt="Describe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    pdf_page_mock.assert_called_once_with(
        str(pdf),
        page_index=0,
        max_dimension=2048,
    )
    assert result["text"] == "first page only"


# ---------------------------------------------------------------------------
# Test 3: plain image file still goes through file_to_data_uri (regression)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_llm_vision_image_still_uses_file_to_data_uri(
    tmp_path: Path,
) -> None:
    """The PDF fix must not break plain image handling.  A .png file must
    still be processed by the original file_to_data_uri path, not the new
    PDF renderer.
    """
    # Minimal 1x1 white PNG
    import struct
    import zlib

    def _minimal_png() -> bytes:
        def chunk(name: bytes, data: bytes) -> bytes:
            c = struct.pack(">I", len(data)) + name + data
            return c + struct.pack(">I", zlib.crc32(name + data) & 0xFFFFFFFF)
        idat = zlib.compress(b"\x00\xFF\xFF\xFF")
        return (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", idat)
            + chunk(b"IEND", b"")
        )

    img = tmp_path / "photo.png"
    img.write_bytes(_minimal_png())

    vision_mock = AsyncMock(return_value="image result")
    _FAKE_IMG_URI = "data:image/png;base64,IMGFAKE"

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        # The PDF helper must NOT be called for a .png
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            side_effect=AssertionError(
                "_pdf_page_to_data_uri must not be called for plain images"
            ),
        ) as pdf_page_mock,
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value=_FAKE_IMG_URI,
        ) as file_to_data_uri_mock,
        patch("fichero_server.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(img)],
            documents=[],
            prompt="Describe.",
            llm_config=_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    pdf_page_mock.assert_not_called()
    file_to_data_uri_mock.assert_called_once()
    assert result["text"] == "image result"
