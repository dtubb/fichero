"""MLX runs inside the app's engine (#4973, ruled 2026-10-09: everything the app needs ships inside it).

The sandboxed app could not build its MLX runtime after install ("Operation not permitted"), so MLX is
bundled at build time and its servers run on a thread in the engine. What breaks without these: the app's
local vision, OCR, text and Whisper models refuse with "provision the runtime", which the app can't do.
"""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from fichero_server.llm import mlx_in_process, mlx_runtime
from fichero_server.llm.local_inference import LocalProviderProfile, ManagedLocalInferenceProcess


@pytest.fixture
def bundled(monkeypatch):
    monkeypatch.setattr(mlx_in_process, "runs_in_process", lambda: True)
    versions = {"mlx-lm": "0.31.3", "mlx-vlm": "0.6.17", "mlx-whisper": "0.4.3"}
    from importlib import metadata

    real = metadata.version
    monkeypatch.setattr(metadata, "version", lambda name: versions.get(name) or real(name))


def test_a_dev_engine_starts_its_own_python_and_the_app_runs_mlx_inside(monkeypatch):
    monkeypatch.delenv("FICHERO_MLX_IN_PROCESS", raising=False)
    monkeypatch.setattr(mlx_in_process, "bundled_mlx_available", lambda: True)
    monkeypatch.setattr(mlx_in_process.sys, "executable", "/usr/bin/python3.12")
    assert not mlx_in_process.runs_in_process(), "a dev engine (a real Python) keeps the separate process"
    monkeypatch.setattr(mlx_in_process.sys, "executable", "/Applications/Fichero.app/…/MacOS/Fichero Server")
    assert mlx_in_process.runs_in_process()
    monkeypatch.setattr(mlx_in_process, "bundled_mlx_available", lambda: False)
    assert not mlx_in_process.runs_in_process(), "nothing bundled: nothing runs inside"


def test_bundled_mlx_reports_itself_ready_with_nothing_to_provision(bundled, tmp_path):
    runtime = mlx_runtime.MLXRuntime(tmp_path / "mlx-runtime") if hasattr(mlx_runtime, "MLXRuntime") else \
        mlx_runtime.get_mlx_runtime()
    assert runtime.is_provisioned() and runtime.has_audio()
    assert runtime.versions() == {"mlx_lm_version": "0.31.3", "mlx_vlm_version": "0.6.17",
                                  "mlx_whisper_version": "0.4.3"}


def test_the_app_engine_picks_the_in_process_server(bundled):
    from fichero_server.api.routes.ai import local_inference as route

    profile = LocalProviderProfile(id="omlx-test", name="MLX test", provider_type="omlx", model_id="m", base_url="http://127.0.0.1:18431/v1",
                                   managed_by_app=True)
    manager = route._new_manager(profile)
    try:
        assert isinstance(manager.process, mlx_in_process.InProcessLocalInferenceProcess)
    finally:
        route._MANAGERS.pop(profile.id, None)


def test_start_runs_the_server_on_a_thread_and_stop_frees_it(monkeypatch):
    profile = LocalProviderProfile(id="omlx-test", name="MLX test", provider_type="omlx", model_id="m", base_url="http://127.0.0.1:18432/v1",
                                   managed_by_app=True)
    process = mlx_in_process.InProcessLocalInferenceProcess(profile)
    monkeypatch.setattr(process, "_model_spec", lambda: "/models/m")
    monkeypatch.setattr(process, "_refuse_if_memory_is_short", lambda: None)
    monkeypatch.setattr(process, "_model_is_vision", lambda: True)
    stopped, unloaded = threading.Event(), []

    def fake_vision(model_spec: str, port: int) -> None:
        assert (model_spec, port) == ("/models/m", 18432)
        process._stop_server, process._unload = stopped.set, lambda: unloaded.append(True)
        process._run_on_thread(lambda: stopped.wait(5), "fake")

    monkeypatch.setattr(process, "_start_vision", fake_vision)
    asyncio.run(process.start())
    assert process.is_running() and process.pid is not None
    asyncio.run(process.stop())
    assert not process.is_running() and unloaded == [True] and process.pid is None


def test_a_server_that_dies_says_why(monkeypatch):
    profile = LocalProviderProfile(id="omlx-test", name="MLX test", provider_type="omlx", model_id="m", base_url="http://127.0.0.1:18433/v1",
                                   managed_by_app=True)
    process = mlx_in_process.InProcessLocalInferenceProcess(profile)

    def boom() -> None:
        raise OSError("[Errno 48] Address already in use")

    process._run_on_thread(boom, "boom")
    deadline = time.monotonic() + 5
    while process.is_running() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert "Address already in use" in (process.last_error or "")
    assert isinstance(process, ManagedLocalInferenceProcess)


GB = 1024**3


def test_the_kv_cache_is_quantized_only_past_a_page_and_harder_when_the_model_is_tight(monkeypatch):
    """#5641: a page read stays at full precision; a long answer (a thinking model's reasoning) is
    compressed; a model that barely fits gets a smaller cache rather than crashing the Mac."""
    for key in ("KV_BITS", "QUANTIZED_KV_START", "KV_QUANT_SCHEME", "MLX_VLM_MAX_NUM_SEQS"):
        monkeypatch.delenv(f"FICHERO_{key}", raising=False)
    roomy = mlx_in_process.kv_settings(3 * GB, 16 * GB)
    assert (roomy["KV_BITS"], roomy["QUANTIZED_KV_START"], roomy["MLX_VLM_MAX_NUM_SEQS"]) == ("8", "5000", "1")
    tight = mlx_in_process.kv_settings(5 * GB, 8 * GB)
    assert (tight["KV_BITS"], tight["QUANTIZED_KV_START"]) == ("4", "1024")
    assert mlx_in_process.kv_settings(3 * GB, 64 * GB)["MLX_VLM_MAX_NUM_SEQS"] == "4", "a big Mac reads 4 pages at once"
    monkeypatch.setenv("FICHERO_KV_BITS", "6")
    assert mlx_in_process.kv_settings(3 * GB, 16 * GB)["KV_BITS"] == "6", "a setting can be tried without a build"


def test_the_runtime_status_says_audio_and_settings_offers_no_provision_when_bundled(bundled):
    """The status route dropped audio_ready and the Whisper version (so audio always read as missing),
    and Settings offered Provision for a runtime the app already carries (found live, 2026-10-09)."""
    from fichero_server.api.routes.ai import local_inference as route
    from fichero_server.api.routes.ai import provider_models

    from fichero_server.llm.mlx_runtime import get_mlx_runtime

    old_python = get_mlx_runtime().python_path()  # a runtime provisioned before MLX was bundled, still on disk
    old_python.parent.mkdir(parents=True, exist_ok=True)
    old_python.write_text("#!/bin/sh\n")
    status = route._runtime_status_response()
    assert status.audio_ready and status.mlx_whisper_version == "0.4.3"
    assert status.python_path is None and status.disk_usage_bytes == 0, "no separate Python is reported in the app"
    row = provider_models._mlx_runtime_row() if hasattr(provider_models, "_mlx_runtime_row") else None
    if row is not None:
        assert row.install_action is None and "bundled" in row.size_note


# ---- The guard: in the app, no MLX path may reach for a separate Python (2026-10-09) ----------------
# Found one at a time in the running app: provisioning, the Whisper download, the MLX weights download.
# Each failed only in the sandbox. Here every path runs in "app mode" with the separate Python made to
# fail if touched, and each must still do its job in the engine.

import sys
import types


@pytest.fixture
def no_separate_python(bundled, monkeypatch):
    def refuse(*_a, **_k):
        raise AssertionError("an MLX path reached for a separate Python in the app")

    monkeypatch.setattr(mlx_runtime.MLXRuntime, "python_path", refuse)
    import asyncio as _asyncio

    real_exec = _asyncio.create_subprocess_exec

    async def no_exec(program, *args, **kw):
        if "python" in str(program).lower():
            refuse()
        return await real_exec(program, *args, **kw)

    monkeypatch.setattr(_asyncio, "create_subprocess_exec", no_exec)


def test_in_the_app_the_separate_python_refuses_loudly(bundled):
    with pytest.raises(mlx_runtime.MLXRuntimeInTheAppError, match="bug in Fichero"):
        mlx_runtime.get_mlx_runtime().require_python_path()
    status = asyncio.run(mlx_runtime.get_mlx_runtime().start_provision())
    assert status["provisioned"] and status["job"] is None, "provisioning is a no-op: MLX is built in"


def test_mlx_weights_download_in_the_engine(no_separate_python, monkeypatch, tmp_path):
    from fichero_server.llm import mlx_model_store

    calls = {}
    fake_hub = types.SimpleNamespace(snapshot_download=lambda **kw: calls.update(kw))
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    store = mlx_model_store.get_mlx_model_store()
    monkeypatch.setattr(type(store), "root", property(lambda self: tmp_path / "mlx"), raising=False)
    monkeypatch.setattr(type(store), "cache_dir", property(lambda self: tmp_path / "mlx" / "hub"), raising=False)
    spec = store.spec("Qwen2.5-VL-3B")
    job = mlx_model_store.ManagedModelDownloadJob(job_id="j", model_id=spec.model_id, state="queued",
                                                  current=0, total=1, message="")
    asyncio.run(store._run_download(job, spec))
    assert job.state == "completed", job.error
    assert calls["repo_id"] == spec.repo_id


def test_whisper_downloads_and_transcribes_in_the_engine(no_separate_python, monkeypatch, tmp_path):
    from fichero_server.llm import whisper_runtime

    monkeypatch.setitem(sys.modules, "huggingface_hub",
                        types.SimpleNamespace(snapshot_download=lambda **kw: None))
    spec = whisper_runtime.spec("tiny")
    target = whisper_runtime.snapshot_path(spec, tmp_path)
    monkeypatch.setattr(whisper_runtime, "snapshot_path", lambda s, h=None: target)
    whisper_runtime.download_whisper_model("tiny", tmp_path)
    target.mkdir(parents=True, exist_ok=True)
    import numpy as np

    monkeypatch.setitem(sys.modules, "miniaudio", types.SimpleNamespace(
        SampleFormat=types.SimpleNamespace(FLOAT32="f32"),
        decode_file=lambda *a, **k: types.SimpleNamespace(samples=np.zeros(16000, np.float32).tobytes())))
    monkeypatch.setitem(sys.modules, "mlx_whisper", types.SimpleNamespace(
        transcribe=lambda audio, **k: {"text": " hello "}))
    assert whisper_runtime.transcribe_sync("a.mp3", "tiny", "en", tmp_path) == "hello"


def test_a_trained_model_lands_in_the_engine(no_separate_python, monkeypatch, tmp_path):
    from fichero_server.training import mlx_landing

    def convert(hf_path, mlx_path, **kw):
        out = tmp_path / "out"
        out.mkdir(exist_ok=True)
        (out / "model.safetensors").write_bytes(b"x")

    monkeypatch.setitem(sys.modules, "mlx_vlm", types.ModuleType("mlx_vlm"))
    monkeypatch.setitem(sys.modules, "mlx_vlm.convert", types.SimpleNamespace(convert=convert))
    mlx_landing.convert_for_mlx(tmp_path / "merged", tmp_path / "out")
    assert any((tmp_path / "out").glob("*.safetensors"))



def test_the_app_removes_the_python_environments_it_no_longer_uses(bundled, tmp_path, monkeypatch):
    """Earlier builds provisioned MLX and Kraken environments at run time; in the app they are dead weight and
    read as if a second Python were needed (two found in the maintainer's container, 2026-10-10). Only a folder
    that is an environment goes; the models stay."""
    from fichero_server.llm.mlx_runtime import remove_runtimes_the_app_no_longer_uses

    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path))
    for name in ("mlx-runtime", "kraken-runtime"):
        (tmp_path / name / "bin").mkdir(parents=True)
        (tmp_path / name / "pyvenv.cfg").write_text("home = /old/app\n")
    (tmp_path / "models" / "mlx").mkdir(parents=True)
    removed = remove_runtimes_the_app_no_longer_uses()
    assert sorted(removed) == sorted(str(tmp_path / n) for n in ("mlx-runtime", "kraken-runtime"))
    assert not (tmp_path / "mlx-runtime").exists() and not (tmp_path / "kraken-runtime").exists()
    assert (tmp_path / "models" / "mlx").is_dir()


def test_outside_the_app_the_runtime_environments_are_kept(tmp_path, monkeypatch):
    from fichero_server.llm import mlx_runtime

    monkeypatch.setattr(mlx_runtime, "bundled_versions", lambda: None)
    monkeypatch.setenv("FICHERO_MODEL_STORE_ROOT", str(tmp_path))
    (tmp_path / "mlx-runtime").mkdir()
    (tmp_path / "mlx-runtime" / "pyvenv.cfg").write_text("")
    assert mlx_runtime.remove_runtimes_the_app_no_longer_uses() == []
    assert (tmp_path / "mlx-runtime").is_dir()
