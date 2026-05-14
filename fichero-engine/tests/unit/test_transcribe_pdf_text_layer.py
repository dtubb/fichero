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

from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from fichero.llm import LLMConfig
from fichero.workflows.tools.vision_base import VisionToolConfig, process_vision


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


def _tool_config() -> VisionToolConfig:
    return VisionToolConfig(
        artifact_type="transcription",
        update_page_content=True,
        trigger_embedding=False,
        supports_apple_vision=True,
    )


@pytest.mark.asyncio
async def test_born_digital_pdf_uses_text_layer_in_llm_mode(tmp_path: Path) -> None:
    """The #1033 fix: a born-digital PDF, vision_mode='llm', no document
    records passed — the text-layer short-circuit must still fire and the
    LLM vision call must NOT happen."""
    pdf = tmp_path / "born_digital.pdf"
    _make_pdf_with_text(pdf, [
        "Davidson signed the deed on the third of March nineteen thirty one.",
        "Antonio Asprilla filed the complaint with the alcalde mayor.",
    ])

    vision_mock = AsyncMock(side_effect=AssertionError("vision OCR must not run"))
    with (
        patch(
            "fichero.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch("fichero.llm.vision", new=vision_mock),
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
        )

    assert "Davidson" in result["text"]
    assert "Asprilla" in result["text"]
    vision_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_force_ocr_bypasses_text_layer(tmp_path: Path) -> None:
    """force_ocr=True must skip the text-layer short-circuit and run the
    vision path even for a born-digital PDF (text layer itself garbage)."""
    pdf = tmp_path / "force.pdf"
    _make_pdf_with_text(pdf, ["Some genuine selectable text on the page."])

    vision_mock = AsyncMock(return_value="OCR OUTPUT")
    with (
        patch(
            "fichero.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero.workflows.tools.vision_base.file_to_data_uri",
            return_value="data:image/png;base64,AAAA",
        ),
        patch("fichero.llm.vision", new=vision_mock),
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
    from fichero.workflows.tools.vision_base import VISION_CONFIG_SCHEMA

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
            "fichero.workflows.tools.vision_base.save_artifact",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "fichero.workflows.tools.vision_base.find_existing_artifact",
            new=find_existing_mock,
        ),
        patch("fichero.llm.vision", new=vision_mock),
    ):
        result = await process_vision(
            files=[str(pdf)],
            documents=[],
            prompt="Transcribe.",
            llm_config=_llm_config(),
            library_path="/tmp/fichero-test-lib-1064",
            task_id=None,
            tool_config=_tool_config(),
            vision_mode="llm",
        )

    # The fresh text layer wins — not the stale garbage artifact.
    assert "Davidson" in result["text"]
    assert "⍰" not in result["text"]
    # The skip-if-artifact cache must be bypassed entirely for a born-digital
    # PDF — find_existing_artifact should never even be consulted.
    find_existing_mock.assert_not_called()
    vision_mock.assert_not_awaited()
