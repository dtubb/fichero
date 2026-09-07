"""Detect Regions (VLM) must never report success with zero regions.

Daniel, 2026-09-07: a "Detect Regions (VLM)" run on a Gemini model COMPLETED
with no error — one model call, ~1704 output tokens, ~$0.05 billed — and saved
ZERO regions. The model replied, the node parsed no boxes out of the reply, and
the run reported ``processed_count`` with no error. A paid call that produced
nothing is the worst outcome, because the user cannot tell it from a page that
genuinely has no localizable text.

Two things had to change and both are exercised here:

1. The parser (``parse_vlm_geometry``) now tolerates the shapes Gemini actually
   returns — a ```json fence, a bare top-level array of ``box_2d`` items — so a
   compliant reply is no longer thrown away before it reaches the box parser.
2. When boxes are the POINT of the run — Detect Regions VLM passes
   ``force_return_boxes=True`` — and not one box parsed, ``process_vision``
   fails LOUD: a per-file error carrying the reply length, the rejection
   reason, and a snippet of what the model returned, with
   ``error_kind='no_boxes'``. Nothing boxless is saved.

A plain Transcribe with ``return_boxes`` does NOT set ``force_return_boxes``;
its salvaged transcript stays intact — that contract is guarded in
``test_return_boxes_never_loses_transcription.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.vision_base import (
    VISION_ERROR_NO_BOXES,
    VisionToolConfig,
    process_vision,
)

# Mirrors the real detect_regions TOOL_CONFIG: regions artifact, Apple Vision
# supported (its local branch is the default), boxes come from the LLM path.
_REGIONS_CFG = VisionToolConfig(
    artifact_type="regions",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=True,
    skip_if_artifact_exists=False,
)

_GEMINI = LLMConfig(provider="google", model="gemini-2.0-flash", api_key="k")

_TRANSCRIPT = "El presente documento dice lo siguiente."


@pytest.fixture
def image(tmp_path: Path) -> str:
    path = tmp_path / "page.png"
    path.write_bytes(b"stub")
    return str(path)


async def _run(image_path: str, reply: str) -> dict:
    """Drive the real process_vision as Detect Regions (VLM) would."""

    async def _vision(images, prompt, config, *, language=None, **kwargs):
        return reply

    with (
        patch(
            "fichero_server.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,stub",
        ),
        patch("fichero_server.llm.vision", new=_vision),
    ):
        return await process_vision(
            files=[image_path],
            documents=[],
            prompt="Find the regions.",
            llm_config=_GEMINI,
            library_path="",
            task_id=None,
            tool_config=_REGIONS_CFG,
            vision_mode="llm",
            return_boxes=True,
            force_return_boxes=True,
        )


@pytest.mark.asyncio
async def test_prose_reply_with_no_boxes_fails_loud(image):
    """RED before the fix: the run completed with no error and no regions."""
    result = await _run(image, "The handwriting was too faint for me to read.")

    err = result["results"][0].get("error")
    assert err, "a paid VLM call that produced no regions must surface an error"
    assert result["results"][0].get("error_kind") == VISION_ERROR_NO_BOXES
    # The run's aggregate error is set too, so the node/Activity shows failure
    # rather than a clean "completed".
    assert result["error"]
    # No boxless regions artifact was written.
    assert result["artifacts"] == []
    # The message names what came back so the user can see it, not just "0".
    assert "no parseable" in err.lower() or "no parseable regions" in err.lower()


@pytest.mark.asyncio
async def test_empty_boxes_list_fails_loud(image):
    """A well-formed reply that simply carries an empty boxes list is the same
    failure — boxes were the point and none arrived."""
    reply = json.dumps({"text": _TRANSCRIPT, "boxes": []})
    result = await _run(image, reply)

    assert result["results"][0].get("error_kind") == VISION_ERROR_NO_BOXES
    assert result["artifacts"] == []


@pytest.mark.asyncio
async def test_fenced_gemini_reply_now_produces_regions(image):
    """The parser fix end-to-end: a reply wrapped in a ```json fence (Gemini's
    default) used to reach the box parser as unparseable and produce zero
    regions. It must now yield the boxes and NOT trip the fail-loud guard."""
    reply = (
        "```json\n"
        + json.dumps(
            {
                "text": "presente documento",
                "boxes": [
                    {"text": "presente", "bbox": [0.1, 0.1, 0.2, 0.05],
                     "level": "word"},
                    {"text": "documento", "bbox": [0.32, 0.1, 0.25, 0.05],
                     "level": "word"},
                ],
            }
        )
        + "\n```"
    )
    result = await _run(image, reply)

    assert result["results"][0].get("error") is None
    assert result["results"][0].get("error_kind") is None


@pytest.mark.asyncio
async def test_bare_gemini_box_array_now_produces_regions(image):
    """Gemini's own native output — a bare array of {box_2d, label} on the
    0..1000 grid — must reach the parser and count as regions, not zero."""
    reply = json.dumps(
        [
            {"box_2d": [100, 50, 200, 400], "label": "presente"},
            {"box_2d": [250, 50, 350, 400], "label": "documento"},
        ]
    )
    result = await _run(image, reply)

    assert result["results"][0].get("error") is None
    assert result["results"][0].get("error_kind") is None
