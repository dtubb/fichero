"""Whisper weights live in the ONE shared models folder, loaded out-of-process.

This file used to pin a process-global cache around an in-process
``whisper.load_model`` — a cache for a model that could never load, because
openai-whisper is not in the engine env. The transcriber now runs in the
managed MLX runtime venv as a subprocess, so there is no Python object in this
process to cache. What still matters, and is what these tests keep, is WHERE
the weights land: the one shared models folder (#2269), never ~/.cache and
never a per-library or stale-bundle-id path.
"""

from __future__ import annotations

from fichero_server.db.paths import server_state_dir
from fichero_server.llm import whisper_runtime
from fichero_server.workflows.tools import audio_base


def test_models_base_is_the_shared_folder():
    assert audio_base.MODELS_BASE == server_state_dir() / "models"
    # No stale bundle id, no ~/.cache, no per-library scattering.
    assert "com.fichero.fichero" not in str(audio_base.MODELS_BASE)
    assert ".cache" not in str(audio_base.MODELS_BASE)


def test_whisper_weights_land_under_the_shared_models_folder():
    store = whisper_runtime.whisper_store_dir()

    assert store == server_state_dir() / "models" / "whisper"
    assert whisper_runtime.whisper_cache_dir().is_relative_to(store)
    assert ".cache" not in str(whisper_runtime.whisper_cache_dir())


def test_each_model_gets_its_own_pinned_snapshot_directory(tmp_path):
    """Two models must never share a directory: delete has to free exactly one."""
    paths = {
        model_id: whisper_runtime.snapshot_path(spec, tmp_path)
        for model_id, spec in whisper_runtime.WHISPER_MLX_MODELS.items()
    }

    assert len(set(paths.values())) == len(paths)
    for model_id, path in paths.items():
        assert path.name == whisper_runtime.WHISPER_MLX_MODELS[model_id].revision


def test_the_engine_process_holds_no_whisper_model_cache():
    """The subprocess boundary is the point: no 1.5 GB object lives here."""
    assert not hasattr(audio_base, "_WHISPER_MODEL_CACHE")
    assert not hasattr(audio_base, "_get_shared_whisper_model")
