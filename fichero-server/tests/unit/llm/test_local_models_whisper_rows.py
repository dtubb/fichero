"""The Whisper rows in Settings must describe a surface that can act.

Before this, six rows each offered a Download button wired to
``whisper.load_model`` in an env with no openai-whisper: the POST returned
200, the background task raised into the void, and the row sat there
unchanged forever. These tests pin the replacement contract -- the row says
whether it can act, and why not when it cannot.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fichero_server.llm import local_models, whisper_runtime
from fichero_server.llm.local_models import LocalModelManager, WHISPER_MODELS


def _fake_status(ready: bool) -> dict[str, object]:
    return {
        "ready": ready,
        "mlx_whisper_version": "0.4.3" if ready else None,
        "reason": None if ready else "The MLX runtime has no transcriber yet. Provision it in Settings.",
    }


@pytest.fixture
def empty_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the whisper rows at an empty store, not the developer's real one."""
    monkeypatch.setattr(
        local_models,
        "_whisper_snapshot_path",
        lambda spec: whisper_runtime.snapshot_path(spec, tmp_path),
    )
    monkeypatch.setattr(local_models, "_whisper_installed_bytes", lambda name: 0)
    return tmp_path


def test_whisper_rows_are_inert_and_say_why_when_no_transcriber_exists(
    empty_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_models, "audio_runtime_status", lambda: _fake_status(False))

    rows = LocalModelManager().list_whisper_models()

    assert rows, "the catalog still lists what could be downloaded"
    for row in rows:
        assert row.available is False
        assert "Provision" in str(row.unavailable_reason)
        assert row.note, "each row says what the model is for"
        assert row.model_type == "whisper"


def test_whisper_rows_are_actionable_once_the_runtime_can_transcribe(
    empty_store: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(local_models, "audio_runtime_status", lambda: _fake_status(True))

    rows = LocalModelManager().list_whisper_models()

    assert all(row.available for row in rows)
    assert all(row.unavailable_reason is None for row in rows)


def test_a_downloaded_model_stays_deletable_even_with_no_transcriber(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Weights on disk are the user's to remove regardless of runtime state."""
    monkeypatch.setattr(local_models, "audio_runtime_status", lambda: _fake_status(False))
    snapshot = whisper_runtime.snapshot_path(whisper_runtime.spec("tiny"), tmp_path)
    snapshot.mkdir(parents=True)
    (snapshot / "weights.npz").write_bytes(b"x" * 8)
    monkeypatch.setattr(
        local_models,
        "_whisper_snapshot_path",
        lambda spec: whisper_runtime.snapshot_path(spec, tmp_path),
    )
    monkeypatch.setattr(local_models, "_whisper_installed_bytes", lambda name: 8)

    rows = {row.model_id: row for row in LocalModelManager().list_whisper_models()}

    assert rows["tiny"].is_downloaded is True
    assert rows["tiny"].available is True
    assert rows["tiny"].download_state == "installed"
    assert rows["base"].available is False


def test_the_legacy_catalog_mapping_is_derived_not_a_second_source_of_truth() -> None:
    assert set(WHISPER_MODELS) == set(whisper_runtime.WHISPER_MLX_MODELS)
    for model_id, info in WHISPER_MODELS.items():
        spec = whisper_runtime.WHISPER_MLX_MODELS[model_id]
        assert info["repo_id"] == spec.repo_id
        assert info["runtime"] == "mlx-whisper"
        assert info["disk_mb"] == round(spec.download_size_bytes / 1_000_000)
