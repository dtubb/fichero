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
