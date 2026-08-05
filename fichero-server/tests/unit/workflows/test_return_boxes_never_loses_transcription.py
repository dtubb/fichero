"""A geometry failure must never destroy the transcription (#4553 follow-up).

Geometry is a decoration on a transcription; the transcription is the archival
record. Three ways the decoration used to take the record down with it:

1. The model answers `return_boxes` in prose instead of JSON. `text` was
   reassigned from the parsed geometry, so the parse error propagated and the
   per-file handler recorded the file as FAILED with `text=""`. Measured
   against a Gemini config before the fix:
   `text=[''] error='Expecting value: line 1 column 1 (char 0)'`.
2. The user ticks `return_boxes` — a VISIBLE toggle on the transcribe node, it
   has no `x-hidden` in the config schema — while using any non-Gemini
   provider. That raised, failing every file in the run, for asking for a
   decoration the model cannot produce.
3. Nothing enforced the prompt's own rule that every box's text must appear in
   the transcription, so a model that invented coordinates for words it never
   read produced boxes that render authoritatively over the wrong part of the
   page — worse than no boxes, because a reader cannot tell them apart from
   real ones.

(1) and (2) now degrade to "transcription saved, geometry unavailable, here is
why". (3) is rejected loudly, and the rejection no longer costs the text.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from fichero_server.llm import LLMConfig
from fichero_server.media.ocr_geometry import (
    GEOMETRY_REASON_KEY,
    OCRGeometryStatus,
    geometry_status,
)
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision


def _parse(payload: str, *, llm_config: LLMConfig, page_index: int | None):
    """Imported lazily so this module still LOADS against code that predates
    the helper — otherwise an ImportError masks the end-to-end tests below,
    which must be able to fail RED on their own terms."""
    from fichero_server.workflows.tools.vision_base import (
        _return_boxes_text_and_geometry,
    )

    return _return_boxes_text_and_geometry(
        payload, llm_config=llm_config, page_index=page_index
    )


_TOOL_CFG = VisionToolConfig(
    artifact_type="transcription",
    update_page_content=False,
    trigger_embedding=False,
    supports_apple_vision=False,
    skip_if_artifact_exists=False,
)

_GEMINI = LLMConfig(provider="google", model="gemini-2.0-flash", api_key="k")
_OPENAI = LLMConfig(provider="openai", model="gpt-4o", api_key="k")

_TRANSCRIPT = "El presente documento dice lo siguiente."


def _boxes_reply(*boxes: dict) -> str:
    return json.dumps({"text": _TRANSCRIPT, "boxes": list(boxes)})


@pytest.fixture
def image(tmp_path: Path) -> str:
    path = tmp_path / "page.png"
    path.write_bytes(b"stub")
    return str(path)


async def _run(image_path: str, reply: str, llm_config: LLMConfig) -> dict:
    """Drive the real process_vision with `return_boxes=True`."""

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
            prompt="Transcribe.",
            llm_config=llm_config,
            library_path="",
            task_id=None,
            tool_config=_TOOL_CFG,
            vision_mode="llm",
            return_boxes=True,
        )


# --------------------------------------------------------------------------
# The transcription survives — end-to-end through process_vision.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prose_reply_keeps_the_transcription(image):
    """RED before the fix: texts == [''] and the file is recorded as failed."""
    result = await _run(image, _TRANSCRIPT, _GEMINI)

    assert result["texts"] == [_TRANSCRIPT], (
        "the model produced a usable transcription; a geometry parse failure "
        "must not discard it"
    )
    assert result["results"][0].get("error") is None


@pytest.mark.asyncio
async def test_rejected_boxes_keep_the_transcript_not_the_json_blob(image):
    """When the reply IS valid JSON and only the boxes are rejected, the
    transcript lives in its `text` field — storing the raw JSON blob instead
    would be a different data loss."""
    reply = _boxes_reply(
        {"text": "Wilmington", "bbox": [0.4, 0.1, 0.2, 0.05], "level": "word"},
    )
    result = await _run(image, reply, _GEMINI)

    assert result["texts"] == [_TRANSCRIPT]
    assert result["results"][0].get("error") is None


@pytest.mark.asyncio
async def test_non_gemini_provider_transcribes_instead_of_failing(image):
    """RED before the fix: every file fails with 'return_boxes requires
    provider=google with a Gemini model' and no transcription is saved."""
    result = await _run(image, _TRANSCRIPT, _OPENAI)

    assert result["texts"] == [_TRANSCRIPT]
    assert result["results"][0].get("error") is None


@pytest.mark.asyncio
async def test_well_formed_boxes_still_produce_their_text(image):
    """Guards against 'fixing' this by refusing every geometry."""
    result = await _run(
        image,
        _boxes_reply(
            {"text": "presente", "bbox": [0.1, 0.1, 0.2, 0.05], "level": "word"},
            {"text": "documento", "bbox": [0.32, 0.1, 0.25, 0.05], "level": "word"},
        ),
        _GEMINI,
    )

    assert result["texts"] == [_TRANSCRIPT]
    assert result["results"][0].get("error") is None


# --------------------------------------------------------------------------
# The geometry record says WHY — asserted at the layer that produces it.
# --------------------------------------------------------------------------


def test_prose_reply_records_geometry_as_malformed():
    text, geometry = _parse(
        _TRANSCRIPT, llm_config=_GEMINI, page_index=0
    )

    assert text == _TRANSCRIPT
    assert geometry_status(geometry) is OCRGeometryStatus.MALFORMED
    assert geometry.boxes == []
    assert "rejected" in geometry.metadata[GEOMETRY_REASON_KEY]


def test_box_text_absent_from_transcription_is_rejected():
    """The prompt demands 'every box's text must appear in the transcription'.
    Nothing enforced it until now.

    Rejects the WHOLE result rather than dropping the offending box: a model
    that fabricated one span cannot be trusted on the placement of the others.
    RED before the fix — the fabricated box is accepted and stored.
    """
    text, geometry = _parse(
        _boxes_reply(
            {"text": "presente", "bbox": [0.1, 0.1, 0.2, 0.05], "level": "word"},
            # never appears in _TRANSCRIPT
            {"text": "Wilmington", "bbox": [0.4, 0.1, 0.2, 0.05], "level": "word"},
        ),
        llm_config=_GEMINI,
        page_index=0,
    )

    assert text == _TRANSCRIPT, "the transcript survives the rejection"
    assert geometry_status(geometry) is OCRGeometryStatus.MALFORMED
    assert geometry.boxes == []
    assert "Wilmington" in geometry.metadata[GEOMETRY_REASON_KEY]


def test_out_of_range_coordinates_are_rejected_without_losing_text():
    text, geometry = _parse(
        _boxes_reply(
            # x + width > 1: off the page
            {"text": "presente", "bbox": [0.9, 0.1, 0.5, 0.05], "level": "word"},
        ),
        llm_config=_GEMINI,
        page_index=0,
    )

    assert text == _TRANSCRIPT
    assert geometry_status(geometry) is OCRGeometryStatus.MALFORMED
    assert geometry.boxes == []


def test_well_formed_word_boxes_are_kept():
    text, geometry = _parse(
        _boxes_reply(
            {"text": "presente", "bbox": [0.1, 0.1, 0.2, 0.05], "level": "word"},
            {"text": "documento", "bbox": [0.32, 0.1, 0.25, 0.05], "level": "word"},
        ),
        llm_config=_GEMINI,
        page_index=3,
    )

    assert text == _TRANSCRIPT
    assert geometry_status(geometry) is OCRGeometryStatus.CAPTURED
    assert [box.text for box in geometry.boxes] == ["presente", "documento"]
    assert all(str(box.level) == "word" for box in geometry.boxes)
    assert all(box.page_index == 3 for box in geometry.boxes), (
        "the page each box belongs to must be stamped from the fan-out's "
        "page index, not left null"
    )
    # #4309: the box<->text link must be established, or boxes can be drawn
    # but no span of the transcript resolves to one.
    assert all(box.char_start is not None for box in geometry.boxes)
