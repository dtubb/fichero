from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from fichero.local_inference import (
    LocalInferenceCapabilities,
    LocalModelHardwareError,
    LocalModelNotInstalledError,
    ManagedLocalInferenceProcess,
    LocalProviderProfile,
)
from fichero.mlx_model_store import MLXModelStore, MANAGED_MLX_MODELS


def _write_snapshot(root: Path, repo_id: str, revision: str, *, size: int = 4) -> Path:
    snapshot = root / "hub" / f"models--{repo_id.replace('/', '--')}" / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "config.json").write_bytes(b"x" * size)
    return snapshot


def _profile(**overrides: object) -> LocalProviderProfile:
    data: dict[str, object] = {
        "id": "local-omlx",
        "name": "Local oMLX",
        "provider_type": "omlx",
        "model_id": "mlx-community/Qwen3-VL-8B",
        "base_url": "http://127.0.0.1:8766/v1",
        "local_only": True,
        "allows_paid_fallbacks": False,
        "managed_by_app": True,
        "healthcheck_path": "/health",
        "timeout_seconds": 0.01,
    }
    data.update(overrides)
    return LocalProviderProfile(**data)


def test_catalog_install_state_from_store_layout(tmp_path: Path) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    qwen = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
    _write_snapshot(store.root, qwen.repo_id, qwen.revision, size=8)
    _write_snapshot(store.root, "user/custom-model", "abc123", size=5)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "fichero.local_inference.get_local_inference_capabilities",
            lambda: LocalInferenceCapabilities(
                system="Darwin",
                machine="arm64",
                is_apple_silicon=True,
                physical_memory_bytes=16 * 1024**3,
                macos_version="26.0",
            ),
        )
        entries = {entry.model_id: entry for entry in store.list_catalog_entries()}

    assert entries["mlx-community/Qwen3-VL-8B"].installed is True
    assert entries["mlx-community/Qwen3-VL-8B"].disk_usage_bytes == 8
    assert entries["mlx-community/Qwen3-VL-8B"].source == "app_cache"
    assert entries["mlx-community/Qwen3-VL-8B"].supported is True
    assert entries["user/custom-model"].installed is True
    assert entries["user/custom-model"].source == "user_configured"


@pytest.mark.asyncio
async def test_download_job_progress_and_cancel(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    gate = asyncio.Event()

    async def fake_run_download(job, spec):
        job.state = "running"
        job.current = 2
        job.message = f"Downloading {spec.display_name}"
        await gate.wait()

    monkeypatch.setattr(store, "_run_download", fake_run_download)

    job = await store.start_download("mlx-community/Qwen3-VL-8B")
    assert job.state in {"queued", "running"}

    cancelled = await store.cancel(job.job_id)

    assert cancelled.state == "cancelled"
    assert cancelled.message == "Download cancelled"


def test_delete_never_escapes_store_root(tmp_path: Path) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    spec = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
    outside = tmp_path / "outside" / spec.revision
    outside.mkdir(parents=True, exist_ok=True)
    (outside / "file.bin").write_bytes(b"x")
    store.snapshot_path = lambda _spec: outside  # type: ignore[method-assign]

    with pytest.raises(ValueError):
        store.delete("mlx-community/Qwen3-VL-8B")


@pytest.mark.asyncio
async def test_download_command_pins_revision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    calls: list[tuple[tuple[str, ...], dict[str, str] | None]] = []

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(*argv, **kwargs):
        calls.append((tuple(argv), kwargs.get("env")))
        return FakeProcess()

    class FakeRuntime:
        def require_python_path(self) -> Path:
            return Path("/tmp/mlx-runtime/bin/python")

    monkeypatch.setattr("fichero.mlx_model_store.get_mlx_runtime", lambda: FakeRuntime())
    monkeypatch.setattr("fichero.mlx_model_store.asyncio.create_subprocess_exec", fake_exec)

    job = await store.start_download("mlx-community/Qwen3-VL-8B")
    await store._job_tasks[job.job_id]

    argv, env = calls[0]
    assert argv[0] == "/tmp/mlx-runtime/bin/python"
    assert MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"].revision in argv
    assert env is not None
    assert env["HF_HOME"] == str(store.root)
    assert env["HUGGINGFACE_HUB_CACHE"] == str(store.cache_dir)


def test_spawn_with_uninstalled_model_raises_typed_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr("fichero.mlx_model_store.get_mlx_model_store", lambda: store)
    monkeypatch.setattr(
        "fichero.local_inference.get_local_inference_capabilities",
        lambda: LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            physical_memory_bytes=32 * 1024**3,
            macos_version="26.0",
        ),
    )
    process = ManagedLocalInferenceProcess(_profile())

    with pytest.raises(LocalModelNotInstalledError):
        process._model_spec()


def test_spawn_refuses_underpowered_mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    spec = MANAGED_MLX_MODELS["mlx-community/Qwen3-VL-8B"]
    _write_snapshot(store.root, spec.repo_id, spec.revision, size=8)
    monkeypatch.setattr("fichero.mlx_model_store.get_mlx_model_store", lambda: store)
    monkeypatch.setattr(
        "fichero.local_inference.get_local_inference_capabilities",
        lambda: LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            physical_memory_bytes=8 * 1024**3,
            macos_version="26.0",
        ),
    )
    process = ManagedLocalInferenceProcess(_profile())

    with pytest.raises(LocalModelHardwareError, match="16 GB unified memory"):
        process._model_spec()


@pytest.mark.asyncio
async def test_download_refuses_underpowered_mac(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr(
        "fichero.local_inference.get_local_inference_capabilities",
        lambda: LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            physical_memory_bytes=8 * 1024**3,
            macos_version="26.0",
        ),
    )

    with pytest.raises(LocalModelHardwareError, match="needs 16 GB unified memory"):
        await store.start_download("mlx-community/Qwen3-VL-8B")


def test_catalog_marks_unsupported_when_memory_floor_is_missed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = MLXModelStore(tmp_path / "mlx")
    monkeypatch.setattr(
        "fichero.local_inference.get_local_inference_capabilities",
        lambda: LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            physical_memory_bytes=8 * 1024**3,
            macos_version="26.0",
        ),
    )

    entries = {entry.model_id: entry for entry in store.list_catalog_entries()}

    assert entries["mlx-community/Qwen3-VL-8B"].supported is False
    assert "16 GB unified memory" in entries["mlx-community/Qwen3-VL-8B"].unsupported_reason
