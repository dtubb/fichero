"""Reasoning-only output retries once WITHOUT the thinking preamble.

Ann's paleography run (2026-08-24): gemini-3.1-flash-lite with
``thinking_mode: medium`` put everything inside an unclosed ``<think>`` block
on 11 of 12 files. ``sanitize_transcription`` rightly refused each one — but
the run died with no recovery, when the same model transcribes fine if simply
not asked to delimit its reasoning. The seam in ``process_vision`` now retries
exactly once with the preamble stripped from the prompt; still-commentary
output keeps the original loud failure.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from PIL import Image

import fichero_server.llm as llm_module
from fichero_server.llm import LLMConfig
from fichero_server.workflows.tools.transcription_output import sanitize_transcription
from fichero_server.workflows.tools.vision_base import VisionToolConfig, process_vision

GOLD = "En la villa de Madrid a veinte dias"
REASONING_ONLY = "<think>I can see an old manuscript, let me work line by line…"


def _run(tmp_path: Path, monkeypatch, responses: list[str]) -> tuple[dict, list[str]]:
    image = tmp_path / "page.png"
    Image.new("RGB", (24, 24), "white").save(image)

    prompts_seen: list[str] = []

    async def fake_vision(*, images, prompt, config, language=None, **kwargs):
        prompts_seen.append(prompt)
        return responses[min(len(prompts_seen), len(responses)) - 1]

    # `process_vision` imports `vision` from fichero_server.llm at call time,
    # so the patch lands on the llm module.
    monkeypatch.setattr(llm_module, "vision", fake_vision)

    result = asyncio.run(process_vision(
        files=[str(image)],
        documents=[{"id": "doc-1", "name": "page.png"}],
        prompt="Transcribe the page. Output ONLY the transcription.",
        llm_config=LLMConfig(provider="openrouter", model="google/gemini-3.1-flash-lite"),
        library_path=str(tmp_path),
        task_id=None,
        tool_config=VisionToolConfig(artifact_type="transcription"),
        thinking_mode="medium",
        save_to_db=False,
        postprocess_text=sanitize_transcription,
    ))
    return result, prompts_seen


def test_reasoning_only_first_answer_recovers_without_preamble(tmp_path, monkeypatch):
    result, prompts = _run(tmp_path, monkeypatch, [REASONING_ONLY, GOLD])

    assert result["texts"] == [GOLD]
    assert len(prompts) == 2
    assert "<think>" in prompts[0]
    # The retry prompt is the SAME prompt minus the thinking preamble.
    assert "<think>" not in prompts[1]
    assert "Output ONLY the transcription." in prompts[1]
    assert not result["results"][0].get("error")


def test_still_commentary_after_retry_keeps_the_loud_failure(tmp_path, monkeypatch):
    result, prompts = _run(tmp_path, monkeypatch, [REASONING_ONLY, REASONING_ONLY])

    assert len(prompts) == 2
    assert "reasoning" in (result["results"][0].get("error") or "").lower()
    assert result["texts"] == [""]


def test_clean_answer_never_triggers_a_second_call(tmp_path, monkeypatch):
    result, prompts = _run(tmp_path, monkeypatch, [GOLD])

    assert len(prompts) == 1
    assert result["texts"] == [GOLD]
