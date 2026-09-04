"""Coverage for shared audio/Whisper helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm import LLMConfig

from fichero_server.workflows.tools import audio_base


def test_local_transcription_runs_in_the_managed_mlx_runtime(monkeypatch):
    """The transcriber is no longer imported into the engine process.

    ``import whisper`` here always failed: openai-whisper is undeclared in the
    engine env and torch is deliberately kept out of it, so every
    ``local_whisper`` run died at the import. The audio path now delegates to
    the mlx-whisper transcriber inside the managed MLX runtime venv, and the
    engine process loads no model of its own.
    """
    calls = []

    def fake_transcribe(file_path, model_id, language):
        calls.append((file_path, model_id, language))
        return "hello world"

    monkeypatch.setattr(
        audio_base,
        "transcribe_sync",
        lambda file_path, model_id, language: fake_transcribe(file_path, model_id, language),
    )

    assert audio_base.transcribe_with_whisper_sync("clip.wav", "tiny", "auto") == "hello world"

    assert calls == [("clip.wav", "tiny", "auto")]


def test_the_engine_process_never_imports_openai_whisper():
    """A regression guard with teeth: the import is the bug, not the symptom."""
    lines = [
        line.strip()
        for line in Path(audio_base.__file__).read_text(encoding="utf-8").splitlines()
    ]

    # Statements only -- the module's prose explains the old import on purpose.
    assert not [line for line in lines if line.startswith(("import whisper", "from whisper"))]


@pytest.mark.asyncio
async def test_remote_audio_uses_canonical_llm_boundary(monkeypatch):
    captured = {}

    async def transcribe(file_path, prompt, config, *, language):
        captured.update(
            file_path=file_path,
            prompt=prompt,
            config=config,
            language=language,
        )
        return "  remote transcript  "

    monkeypatch.setattr(audio_base, "audio_transcription", transcribe)
    config = LLMConfig(provider="openai", model="whisper-1")

    result = await audio_base.transcribe_with_llm(
        "clip.wav", config, "Be exact", "es"
    )

    assert result == "remote transcript"
    assert captured == {
        "file_path": "clip.wav",
        "prompt": "Be exact",
        "config": config,
        "language": "es",
    }
