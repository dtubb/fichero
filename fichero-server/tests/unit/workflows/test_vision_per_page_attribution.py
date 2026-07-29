"""Regression tests for per-page attribution in process_vision.

#2250 — one LLM call per page child + correct doc_id in page_records.
#2241 — no NameError/UnboundLocalError when a blank page child is processed
         by a cloud LLM provider (image_uri must be initialised before retry).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision


_TOOL_CFG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    skip_if_artifact_exists=False,
)

_LLM_CFG = LLMConfig(provider="openai", model="gpt-4o", api_key="test-key")


@pytest.mark.asyncio
async def test_per_page_fanout_calls_llm_once_per_page_and_attributes_doc_ids(
    tmp_path,
):
    """#2250: process_vision called with 2 per-page fan-out docs must call the
    LLM exactly once per page and return page_records keyed on the correct
    page-child doc_id.

    Goes RED when the caller batches both pages into a single call (pre-#2236
    builder behaviour): only one page_records entry would appear.
    """
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    documents = [
        {
            "id": "page-1",
            "path": None,
            "parent_id": "parent-pdf",
            "sequence": 1,
            "page_content": None,
        },
        {
            "id": "page-2",
            "path": None,
            "parent_id": "parent-pdf",
            "sequence": 2,
            "page_content": None,
        },
    ]

    call_log: list[dict] = []

    async def _vision(images, prompt, config):
        call_log.append({"images": list(images)})
        return f"Transcribed page {len(call_log)}"

    with (
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=None),
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            side_effect=lambda path, page_index=0, **kw: f"data:image/png;base64,PAGE{page_index}",
        ),
        patch("fichero_server.llm.vision", new=_vision),
    ):
        result = await process_vision(
            files=[str(pdf), str(pdf)],
            documents=documents,
            prompt="Transcribe this page.",
            llm_config=_LLM_CFG,
            library_path="",
            task_id=None,
            tool_config=_TOOL_CFG,
            vision_mode="llm",
        )

    assert len(call_log) == 2, (
        f"#2250/#2236: expected 2 LLM calls (one per page child), got {len(call_log)}"
    )
    # Each call used a distinct page-rendered URI (different page_index)
    assert call_log[0]["images"] != call_log[1]["images"], (
        "#2250: each page child must render its own page, not the same image twice"
    )
    # page_records carries both page-child doc_ids
    pr_ids = {r["doc_id"] for r in result["page_records"]}
    assert pr_ids == {"page-1", "page-2"}, (
        f"#2250: page_records must attribute to both page children; got {pr_ids}"
    )


@pytest.mark.asyncio
async def test_blank_page_in_per_page_fanout_cloud_provider_no_crash(tmp_path):
    """#2241: A blank page child processed via a cloud/LLM provider must not
    raise NameError / UnboundLocalError for `image_uri`.

    image_uri is only assigned inside the LLM single-page branch; the
    empty-response retry block must not reference it when that assignment
    was skipped (e.g. a rare edge-case code path that hits the retry guard
    without having gone through the normal single-page LLM path).
    """
    pdf = tmp_path / "blank.pdf"
    pdf.write_bytes(b"%PDF-1.4 stub")

    documents = [
        {
            "id": "blank-page",
            "path": None,
            "parent_id": "parent-pdf",
            "sequence": 1,
            "page_content": None,
            "metadata": {"is_blank": True},
        },
    ]

    call_count = 0

    async def _blank_vision(images, prompt, config):
        nonlocal call_count
        call_count += 1
        return ""  # simulate blank page — LLM returns nothing

    with (
        patch("fichero_server.workflows.tools.vision_base._try_pdf_text_layer", return_value=None),
        patch(
            "fichero_server.workflows.tools.vision_base._pdf_page_to_data_uri",
            return_value="data:image/png;base64,BLANK",
        ),
        patch("fichero_server.llm.vision", new=_blank_vision),
    ):
        # Must not raise NameError/UnboundLocalError
        result = await process_vision(
            files=[str(pdf)],
            documents=documents,
            prompt="Transcribe.",
            llm_config=_LLM_CFG,
            library_path="",
            task_id=None,
            tool_config=_TOOL_CFG,
            vision_mode="llm",
        )

    assert result is not None, "#2241: must not crash with NameError"
    assert len(result["results"]) == 1
    entry = result["results"][0]
    assert entry["text"] == "", "blank page must produce empty text, not crash"
    # The retry fires once (initial call) + up to once (retry) — both return ""; result is an error entry
    assert "error" in entry, "#2241: blank page should produce an error entry"
