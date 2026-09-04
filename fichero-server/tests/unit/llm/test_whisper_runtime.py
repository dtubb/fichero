"""Whisper served from the managed MLX runtime instead of a missing import.

The behaviour under test is the one that was broken: every Whisper button in
the Downloads tab called ``whisper.load_model`` inside an engine env that has
no openai-whisper, so downloads failed in a background task and workflow runs
died with an ImportError. These tests pin the replacement -- the transcriber
lives in the MLX runtime venv -- and, just as importantly, pin the HONESTY:
a runtime that cannot transcribe says so before anything is clicked.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from fichero_server.llm import whisper_runtime
from fichero_server.llm.mlx_runtime import MLXAudioRuntimeMissingError, MLXRuntime
from fichero_server.llm.whisper_runtime import (
    WHISPER_MLX_MODELS,
    UnknownWhisperModelError,
    WhisperModelNotInstalledError,
    WhisperTranscriptionError,
)


@pytest.fixture(autouse=True)
def _clean_download_state() -> None:
    whisper_runtime._DOWNLOAD_STATE.clear()


def _runtime(tmp_path: Path, *, with_whisper: bool) -> MLXRuntime:
    runtime = MLXRuntime(tmp_path / "mlx-runtime")
    python_path = runtime.python_path()
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    metadata = '{"mlx_lm_version": "0.31.3", "mlx_vlm_version": "0.6.17"'
    metadata += ', "mlx_whisper_version": "0.4.3"}' if with_whisper else "}"
    (runtime.runtime_dir / "runtime.json").write_text(metadata, encoding="utf-8")
    return runtime


def _install_snapshot(model_id: str, home: Path, *, size: int = 32) -> Path:
    snapshot = whisper_runtime.snapshot_path(whisper_runtime.spec(model_id), home)
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "weights.npz").write_bytes(b"x" * size)
    return snapshot


# --- catalog ---------------------------------------------------------------


def test_every_catalogued_model_carries_a_pinned_revision_and_a_reason() -> None:
    """A curated list, not a dump: each entry says what it is for and costs."""
    assert set(WHISPER_MLX_MODELS) == {"tiny", "base", "small", "medium", "large-v3", "turbo"}
    for model_id, spec in WHISPER_MLX_MODELS.items():
        assert spec.model_id == model_id
        assert spec.repo_id.startswith("mlx-community/")
        # A 40-char commit sha, never "main": the store's delete guard keys on
        # the revision, and an unpinned model changes weights under the user.
        assert len(spec.revision) == 40
        assert spec.download_size_bytes > 0
        assert spec.note.strip()
        assert spec.speed.strip()


def test_the_retired_large_config_value_still_resolves() -> None:
    """Saved workflows carry whisper_model_size="large"; OpenAI retired it."""
    assert whisper_runtime.resolve_model_id("large") == "large-v3"
    assert whisper_runtime.spec("large").repo_id == "mlx-community/whisper-large-v3-mlx"


def test_an_unknown_model_is_named_in_the_refusal() -> None:
    with pytest.raises(UnknownWhisperModelError, match="tiny"):
        whisper_runtime.spec("enormous")


# --- honesty about the runtime ---------------------------------------------


def test_a_runtime_without_a_transcriber_says_so_instead_of_failing_later(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=False))

    status = whisper_runtime.audio_runtime_status()

    assert status["ready"] is False
    assert "Provision" in str(status["reason"])
    with pytest.raises(MLXAudioRuntimeMissingError):
        whisper_runtime.download_whisper_model("tiny", home=tmp_path)
    # The caller is a BackgroundTask: the raise reaches nobody, so the row
    # state has to carry the reason.
    state, error = whisper_runtime.download_state("tiny")
    assert state == "failed"
    assert "Provision" in str(error)


def test_a_provisioned_runtime_reports_its_transcriber_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))

    status = whisper_runtime.audio_runtime_status()

    assert status["ready"] is True
    assert status["mlx_whisper_version"] == "0.4.3"
    assert status["reason"] is None


# --- download / delete ------------------------------------------------------


def test_a_failed_download_is_remembered_rather_than_vanishing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The download runs in a BackgroundTask; the POST has already returned 200.

    Without a recorded state the tab showed a model that would never appear
    and gave no reason -- the exact silent failure this surface had.
    """
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))

    def explode(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(1, "python", stderr="RepositoryNotFoundError: nope")

    monkeypatch.setattr(whisper_runtime.subprocess, "run", explode)

    with pytest.raises(subprocess.CalledProcessError):
        whisper_runtime.download_whisper_model("tiny", home=tmp_path)

    state, error = whisper_runtime.download_state("tiny")
    assert state == "failed"
    assert "RepositoryNotFoundError" in str(error)


def test_an_already_installed_model_is_not_downloaded_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))
    _install_snapshot("tiny", tmp_path)
    calls: list[object] = []
    monkeypatch.setattr(whisper_runtime.subprocess, "run", lambda *a, **k: calls.append(a))

    whisper_runtime.download_whisper_model("tiny", home=tmp_path)

    assert calls == []
    assert whisper_runtime.download_state("tiny") == ("installed", None)


def test_delete_frees_only_the_pinned_snapshot(tmp_path: Path) -> None:
    snapshot = _install_snapshot("tiny", tmp_path, size=100)
    sibling = whisper_runtime.whisper_store_dir(tmp_path) / "keep-me"
    sibling.mkdir(parents=True)
    (sibling / "note.txt").write_text("keep", encoding="utf-8")

    freed = whisper_runtime.delete_whisper_model("tiny", home=tmp_path)

    assert freed == 100
    assert snapshot.exists() is False
    assert sibling.exists() is True
    assert whisper_runtime.delete_whisper_model("tiny", home=tmp_path) == 0


# --- transcription ----------------------------------------------------------


def test_transcription_refuses_a_model_that_is_not_downloaded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))

    with pytest.raises(WhisperModelNotInstalledError, match="Whisper tiny"):
        whisper_runtime.transcribe_sync("/tmp/audio.wav", "tiny", "en", home=tmp_path)


def test_transcription_reads_the_payload_past_any_progress_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))
    _install_snapshot("tiny", tmp_path)
    captured: dict[str, object] = {}

    class Completed:
        stdout = 'Detected language: en\n__FICHERO_WHISPER__{"text": "  hello there  ", "language": "en"}'
        stderr = ""

    def fake_run(argv: list[str], **kwargs: object) -> Completed:
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return Completed()

    monkeypatch.setattr(whisper_runtime.subprocess, "run", fake_run)

    text = whisper_runtime.transcribe_sync("/tmp/audio.wav", "tiny", "en", home=tmp_path)

    assert text == "hello there"
    argv = captured["argv"]
    assert argv[0] == str(tmp_path / "mlx-runtime" / "bin" / "python")
    assert str(whisper_runtime.snapshot_path(whisper_runtime.spec("tiny"), tmp_path)) in argv
    # Nothing may reach the network at transcription time: the weights are on
    # disk and the repo id is never resolved again.
    assert captured["env"]["HF_HUB_OFFLINE"] == "1"


def test_a_missing_ffmpeg_is_reported_as_the_fixable_thing_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))
    _install_snapshot("tiny", tmp_path)

    def explode(*args: object, **kwargs: object) -> None:
        raise subprocess.CalledProcessError(
            1, "python", stderr="FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'"
        )

    monkeypatch.setattr(whisper_runtime.subprocess, "run", explode)

    with pytest.raises(WhisperTranscriptionError, match="brew install ffmpeg"):
        whisper_runtime.transcribe_sync("/tmp/audio.wav", "tiny", "en", home=tmp_path)


def test_a_transcriber_that_printed_nothing_is_an_error_not_an_empty_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty transcript would be indistinguishable from silent audio."""
    monkeypatch.setattr(whisper_runtime, "get_mlx_runtime", lambda: _runtime(tmp_path, with_whisper=True))
    _install_snapshot("tiny", tmp_path)

    class Completed:
        stdout = ""
        stderr = "zsh: killed"

    monkeypatch.setattr(whisper_runtime.subprocess, "run", lambda *a, **k: Completed())

    with pytest.raises(WhisperTranscriptionError, match="no result payload"):
        whisper_runtime.transcribe_sync("/tmp/audio.wav", "tiny", "en", home=tmp_path)
