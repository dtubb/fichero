"""Tests for the text-format passthrough in process_vision (#884).

Locks the behaviour: when Transcribe (or any vision tool) receives a
.md/.txt/etc. file, it reads the file directly instead of sending the
bytes to the vision LLM. Without this, Catalogue (Mixed) on a folder
containing .md crashes the vision API with 'cannot identify image file'.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import (
    VisionToolConfig,
    _is_non_retriable_provider_error,
    process_vision,
)


def _make_llm_config() -> LLMConfig:
    return LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


@pytest.mark.asyncio
async def test_markdown_file_returns_its_text_without_vision_call(tmp_path: Path) -> None:
    """A .md file should round-trip its content via the fast path.

    If the fast path didn't fire the function would try to lazy-import
    `vision` and POST the file bytes to a vision LLM — which is exactly
    the #884 crash we're locking out.
    """
    md_file = tmp_path / "notes.md"
    md_file.write_text("# Heading\n\nBody content.\n", encoding="utf-8")

    with patch(
        "fichero_server.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value=None),
    ):
        result = await process_vision(
            files=[str(md_file)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert "Heading" in result["text"]
    assert "Body content" in result["text"]
    assert result["texts"] == [result["text"]]


@pytest.mark.asyncio
async def test_all_text_format_suffixes_passthrough(tmp_path: Path) -> None:
    """Every suffix in TEXT_FORMATS hits the fast path with non-empty output."""
    suffixes = [".txt", ".md", ".markdown", ".rst", ".html", ".htm", ".xml", ".csv"]
    with patch(
        "fichero_server.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value=None),
    ):
        for suffix in suffixes:
            file = tmp_path / f"sample{suffix}"
            file.write_text(f"content-{suffix}", encoding="utf-8")
            result = await process_vision(
                files=[str(file)],
                documents=[],
                prompt="x",
                llm_config=_make_llm_config(),
                library_path="",
                task_id=None,
                tool_config=_tool_config(),
                vision_mode="llm",
            )
            assert f"content-{suffix}" in result["text"], suffix


@pytest.mark.asyncio
async def test_pdf_with_existing_page_content_skips_vision(tmp_path: Path) -> None:
    """When the document record already has page_content (e.g. a digital
    PDF whose text layer was extracted by Kreuzberg at ingest), Transcribe
    must use that text directly instead of re-OCRing.
    """
    pdf = tmp_path / "book.pdf"
    # Bytes don't matter — the fast path uses page_content, never opens the file.
    pdf.write_bytes(b"")

    documents = [{
        "id": "doc-1",
        "path": str(pdf),
        "page_content": "Chapter 1\n\nThe rains came in late March.",
    }]

    with patch(
        "fichero_server.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value="artifact-1"),
    ) as mock_save:
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="/tmp/lib",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert "Chapter 1" in result["text"]
    assert result["texts"] == [result["text"]]
    # The artifact write fires once (text persists)
    assert mock_save.await_count == 1


@pytest.mark.asyncio
async def test_force_ocr_bypasses_existing_page_content(tmp_path: Path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"image")
    documents = [{
        "id": "doc-1",
        "path": str(image),
        "page_content": "stale transcription",
    }]

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,IMAGE",
        ),
        patch(
            "fichero_server.llm.vision",
            new=AsyncMock(return_value="fresh image result"),
        ) as vision,
    ):
        result = await process_vision(
            files=[str(image)],
            documents=documents,
            prompt="Review the image.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
            force_ocr=True,
            save_to_db=False,
        )

    vision.assert_awaited_once()
    assert result["text"] == "fresh image result"


@pytest.mark.asyncio
async def test_specialist_vision_tools_force_image_processing() -> None:
    from importlib import import_module

    for module_name, tool_name in (
        ("classify_script", "classify_script"),
        ("handwriting", "handwriting"),
        ("transcribe_review", "transcribe_review"),
    ):
        module = import_module(f"fichero_server.workflows.tools.{module_name}")
        process_result = {
            "text": "{}" if tool_name == "classify_script" else "result",
            "results": [],
        }
        with patch.object(
            module,
            "process_vision",
            new=AsyncMock(return_value=process_result),
        ) as process_vision:
            await getattr(module, tool_name)(
                {"files": ["page.png"]},
                {"library_path": "/library.fichero"},
                _make_llm_config(),
            )

        assert process_vision.await_args.kwargs["force_ocr"] is True


@pytest.mark.asyncio
async def test_transcribe_review_can_disable_prior_artifact_reuse() -> None:
    from fichero_server.workflows.tools import transcribe_review as review_module

    with patch.object(
        review_module,
        "process_vision",
        new=AsyncMock(return_value={"text": "final review"}),
    ) as process_vision:
        await review_module.transcribe_review(
            {
                "files": ["page.png"],
                "skip_if_artifact_exists": False,
            },
            {"library_path": "/library.fichero"},
            _make_llm_config(),
        )

    tool_config = process_vision.await_args.kwargs["tool_config"]
    assert tool_config.skip_if_artifact_exists is False


@pytest.mark.asyncio
async def test_transcribe_review_aligns_ensemble_drafts_by_page() -> None:
    from fichero_server.workflows.tools import transcribe_review as review_module

    with patch.object(
        review_module,
        "process_vision",
        new=AsyncMock(return_value={"texts": ["review 1", "review 2"]}),
    ) as process_vision:
        await review_module.transcribe_review(
            {
                "files": ["page-1.png", "page-2.png"],
                "context": [
                    [{"text": "model-a page 1"}, {"text": "model-a page 2"}],
                    [{"text": "model-b page 1"}, {"text": "model-b page 2"}],
                ],
            },
            {"library_path": "/library.fichero"},
            _make_llm_config(),
        )

    assert process_vision.await_args.kwargs["context"] == [
        "model-a page 1\n\n---\n\nmodel-b page 1",
        "model-a page 2\n\n---\n\nmodel-b page 2",
    ]


@pytest.mark.asyncio
async def test_process_vision_uses_page_aligned_context(tmp_path: Path) -> None:
    files = [tmp_path / "page-1.png", tmp_path / "page-2.png"]
    for file in files:
        file.write_bytes(b"image")

    async def review(images, prompt, config):
        del images, config
        assert not ({"draft page 1", "draft page 2"} <= set(prompt.splitlines()))
        return "review 1" if "draft page 1" in prompt else "review 2"

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,IMAGE",
        ),
        patch("fichero_server.llm.vision", new=review),
    ):
        result = await process_vision(
            files=[str(file) for file in files],
            documents=[],
            prompt="Review.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            context=["draft page 1", "draft page 2"],
            force_ocr=True,
            save_to_db=False,
        )

    assert result["texts"] == ["review 1", "review 2"]


def test_non_retriable_provider_error_detection() -> None:
    assert _is_non_retriable_provider_error("Error code: 403 - key limit exceeded")
    assert _is_non_retriable_provider_error("401 Unauthorized")
    assert not _is_non_retriable_provider_error("timed out waiting for response")


@pytest.mark.asyncio
async def test_pdf_with_empty_page_content_falls_through_to_vision(tmp_path: Path) -> None:
    """A document record with empty/missing page_content shouldn't trigger
    the pre-extracted fast path — fall through to the normal vision path
    (which here would crash on empty bytes, but we just assert the fast
    path didn't fire instead)."""
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"")
    documents = [{
        "id": "doc-1",
        "path": str(pdf),
        "page_content": "",  # empty — no text
    }]

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value="x"),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,",
        ),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="x",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )
    # If the fast path had fired, result["text"] would be "" but texts
    # would have one entry. With fall-through, results structure still
    # exists but the fast-path bookkeeping didn't add to texts.
    assert "results" in result


@pytest.mark.asyncio
async def test_whitespace_only_page_content_does_not_short_circuit(tmp_path: Path) -> None:
    """page_content of just whitespace should NOT count as pre-extracted
    text (\\.strip() check), so it falls through to vision."""
    pdf = tmp_path / "x.pdf"
    pdf.write_bytes(b"")
    documents = [{
        "id": "doc-1",
        "path": str(pdf),
        "page_content": "   \n\n  ",
    }]
    with (
        patch(
            "fichero_server.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value="x"),
        ),
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,",
        ),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="x",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )
    assert "results" in result


@pytest.mark.asyncio
async def test_per_page_fan_out_uses_page_content_when_path_is_nil(tmp_path: Path) -> None:
    """The per-page fan-out (#891) gives Transcribe one branch per page
    child. Each page child has its OWN page_content but path=None (it
    shares the parent PDF's path via files[i]). The fast-path lookup
    must therefore key by INDEX, not by doc.path — otherwise it never
    matches and falls through to vision OCR on the parent path N times
    (which is what broke Daniel's 252-page Catalogue run).
    """
    pdf = tmp_path / "book.pdf"
    pdf.write_bytes(b"")

    # Simulates one fan-out branch: 1 file path (parent), 1 document
    # (the page child, path=None, has page_content).
    documents = [{
        "id": "page-14",
        "path": None,  # page children have no path of their own
        "page_content": "Page 14 of the book.",
        "sequence": 14,
    }]

    with patch(
        "fichero_server.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value="artifact-14"),
    ) as mock_save:
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="/tmp/lib",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert "Page 14" in result["text"]
    # Verify save_artifact got the page child's id, not the parent's
    assert mock_save.await_count == 1
    save_kwargs = mock_save.await_args.kwargs
    assert save_kwargs["document_id"] == "page-14"


@pytest.mark.asyncio
async def test_save_to_db_false_skips_artifact_persistence(tmp_path: Path) -> None:
    """When save_to_db=False, the artifact write is not attempted."""
    md_file = tmp_path / "n.md"
    md_file.write_text("hello", encoding="utf-8")

    with patch(
        "fichero_server.workflows.tools.vision_base.save_artifact",
        new=AsyncMock(return_value="artifact-id"),
    ) as mock_save:
        result = await process_vision(
            files=[str(md_file)],
            documents=[],
            prompt="x",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
            save_to_db=False,
        )

    assert mock_save.await_count == 0
    assert result["text"] == "hello"


# ---------------------------------------------------------------------------
# Truncated / absent page transcription fallback (#1170)
# ---------------------------------------------------------------------------

_PDF_LAYER_FULL = "Full text of page one — " + "word " * 50  # 250+ chars


@pytest.mark.asyncio
async def test_truncated_transcription_falls_back_to_pdf_text_layer(tmp_path: Path) -> None:
    """When metadata.transcription is shorter than metadata.text_length by >50 chars,
    process_vision replaces it with the PDF text layer for that page."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF stub")

    documents = [{
        "id": "page-1",
        "path": str(pdf),
        "page_content": "short stub",
        "sequence": 1,
        "metadata": {
            "transcription": "truncated short",  # 15 chars
            "text_length": 300,                  # expected 300 chars
        },
    }]

    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=[_PDF_LAYER_FULL]),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert _PDF_LAYER_FULL in result["text"], "expected PDF text layer to replace truncated metadata"


@pytest.mark.asyncio
async def test_absent_transcription_falls_back_to_pdf_text_layer(tmp_path: Path) -> None:
    """When metadata.transcription is None but text_length > 50, use PDF text layer."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF stub")

    documents = [{
        "id": "page-1",
        "path": str(pdf),
        "page_content": "",
        "sequence": 1,
        "metadata": {
            # No "transcription" key — None after dict.get()
            "text_length": 300,
        },
    }]

    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=[_PDF_LAYER_FULL]),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    assert _PDF_LAYER_FULL in result["text"], "expected PDF text layer for page with no stored transcription"


@pytest.mark.asyncio
async def test_matching_transcription_not_replaced(tmp_path: Path) -> None:
    """When stored transcription matches text_length, PDF layer is not consulted."""
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(b"%PDF stub")
    full_text = "word " * 60  # 300 chars

    documents = [{
        "id": "page-1",
        "path": str(pdf),
        "page_content": full_text,
        "sequence": 1,
        "metadata": {
            "transcription": full_text,
            "text_length": len(full_text),
        },
    }]

    mock_layer = patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer")
    with (
        patch("fichero_server.workflows.tools.vision_base.save_artifact", new=AsyncMock(return_value=None)),
        mock_layer as ml,
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_make_llm_config(),
            library_path="",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    ml.assert_not_called()
    assert full_text.strip() in result["text"]
