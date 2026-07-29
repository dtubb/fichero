"""Tests for app-managed local inference API routes."""

from __future__ import annotations

from typing import Any

import pytest

from fichero_server.api.routes import local_inference as routes
from fichero_server.llm.local_inference import LocalInferenceServiceManager, ManagedLocalInferenceProcess


class FakeProcess:
    def __init__(self) -> None:
        self.pid: int | None = None
        self.last_error: str | None = None
        self.running = False
        self.start_calls = 0
        self.stop_calls = 0

    async def start(self) -> None:
        self.start_calls += 1
        self.last_error = None
        self.running = True
        self.pid = 9000 + self.start_calls

    async def stop(self) -> None:
        self.stop_calls += 1
        self.running = False
        self.pid = None

    def is_running(self) -> bool:
        return self.running


class FakeHealthClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    async def get_json(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        self.urls.append(url)
        if not self.responses:
            raise TimeoutError("no fake health response queued")
        return self.responses.pop(0)


@pytest.fixture(autouse=True)
def clear_local_inference_managers() -> None:
    routes._MANAGERS.clear()
    yield
    routes._MANAGERS.clear()


def test_list_local_inference_profiles_returns_typed_omlx_profile(client) -> None:
    response = client.get("/api/local-inference/profiles")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    profile = data["items"][0]
    assert profile["id"] == routes.DEFAULT_OMLX_PROFILE_ID
    assert profile["provider_type"] == "omlx"
    assert profile["local_only"] is True
    assert profile["allows_paid_fallbacks"] is False
    assert profile["managed_by_app"] is True
    assert profile["base_url"].startswith("http://localhost:8000")
    assert profile["supported"] is True


def test_local_inference_catalog_exposes_configured_model(client) -> None:
    class StubStore:
        def list_catalog_entries(self):
            return [
                {
                    "provider_type": "omlx",
                    "model_id": routes.DEFAULT_OMLX_MODEL_ID,
                    "display_name": "Qwen3-VL 8B",
                    "capabilities": ["text", "vision"],
                    "installed": True,
                    "download_size_bytes": 123,
                    "disk_usage_bytes": 456,
                    "min_memory_bytes": 17179869184,
                    "memory_class": "needs 16 GB unified memory",
                    "supported": True,
                    "unsupported_reason": None,
                    "license_label": "user-managed",
                    "source": "app_cache",
                }
            ]

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(routes, "get_mlx_model_store", lambda: StubStore())
        response = client.get("/api/local-inference/catalog")

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 1
    entry = data["items"][0]
    assert entry["provider_type"] == "omlx"
    assert entry["model_id"] == routes.DEFAULT_OMLX_MODEL_ID
    assert entry["capabilities"] == ["text", "vision"]
    assert entry["installed"] is True
    assert entry["supported"] is True


def test_local_inference_catalog_surfaces_hardware_unsupported_reason(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubStore:
        def list_catalog_entries(self):
            return [
                {
                    "provider_type": "omlx",
                    "model_id": routes.DEFAULT_OMLX_MODEL_ID,
                    "display_name": "Qwen3-VL 8B",
                    "capabilities": ["text", "vision"],
                    "installed": False,
                    "download_size_bytes": 123,
                    "disk_usage_bytes": 0,
                    "min_memory_bytes": 17179869184,
                    "memory_class": "needs 16 GB unified memory",
                    "supported": False,
                    "unsupported_reason": "Qwen3-VL 8B needs 16 GB unified memory; this Mac has 8 GB",
                    "license_label": "user-managed",
                    "source": "app_cache",
                }
            ]

    monkeypatch.setattr(routes, "get_mlx_model_store", lambda: StubStore())

    response = client.get("/api/local-inference/catalog")

    assert response.status_code == 200
    entry = response.json()["items"][0]
    assert entry["supported"] is False
    assert "16 GB unified memory" in entry["unsupported_reason"]


def test_local_inference_capabilities_exposes_machine_probe(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_local_inference_capabilities",
        lambda: routes.LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            subprocess_capable=True,
            physical_memory_bytes=16 * 1024**3,
            macos_version="26.0",
        ),
    )

    response = client.get("/api/local-inference/capabilities")

    assert response.status_code == 200
    assert response.json()["is_apple_silicon"] is True
    assert response.json()["subprocess_capable"] is True
    assert response.json()["physical_memory_bytes"] == 16 * 1024**3


def test_profiles_report_unavailable_when_subprocesses_are_disabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        routes,
        "get_local_inference_capabilities",
        lambda: routes.LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            subprocess_capable=False,
            physical_memory_bytes=16 * 1024**3,
            macos_version="26.0",
        ),
    )

    response = client.get("/api/local-inference/profiles")

    assert response.status_code == 200
    profile = response.json()["items"][0]
    assert profile["supported"] is False
    assert profile["unsupported_reason"] == "not available on this device"


def test_manager_for_managed_profile_uses_managed_process() -> None:
    manager = routes._manager_for_profile(routes.DEFAULT_OMLX_PROFILE_ID)

    assert isinstance(manager, LocalInferenceServiceManager)
    assert isinstance(manager.process, ManagedLocalInferenceProcess)


def test_validate_local_profile_rejects_cloud_escape(client) -> None:
    response = client.post(
        "/api/local-inference/profiles/validate",
        json={
            "id": "bad-cloud",
            "name": "Bad Cloud",
            "provider_type": "openai",
            "model_id": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "local_only": True,
            "allows_paid_fallbacks": False,
            "managed_by_app": True,
        },
    )

    assert response.status_code == 422
    assert "Local profile cannot target cloud provider" in response.text


def test_status_start_health_stop_lifecycle_uses_manager_contract(client) -> None:
    process = FakeProcess()
    health_client = FakeHealthClient(
        [
            {
                "reachable": True,
                "model_loaded": True,
                "configured_model_id": routes.DEFAULT_OMLX_MODEL_ID,
                "warm": True,
            }
        ]
    )
    manager = LocalInferenceServiceManager(
        routes._configured_omlx_profile(),
        process,
        health_client,
        poll_interval_seconds=0,
    )
    routes._MANAGERS[routes.DEFAULT_OMLX_PROFILE_ID] = manager

    initial = client.get(f"/api/local-inference/profiles/{routes.DEFAULT_OMLX_PROFILE_ID}/status")
    assert initial.status_code == 200
    assert initial.json()["state"] == "stopped"

    started = client.post(
        f"/api/local-inference/profiles/{routes.DEFAULT_OMLX_PROFILE_ID}/start",
        json={"timeout_seconds": 1},
    )
    assert started.status_code == 200
    assert started.json()["state"] == "healthy"
    assert started.json()["healthy"] is True
    assert started.json()["pid"] == 9001
    assert health_client.urls == ["http://localhost:8000/v1/health"]

    stopped = client.post(f"/api/local-inference/profiles/{routes.DEFAULT_OMLX_PROFILE_ID}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "stopped"
    assert process.stop_calls == 1


def test_unknown_profile_returns_404(client) -> None:
    response = client.get("/api/local-inference/profiles/does-not-exist/status")

    assert response.status_code == 404
    assert "Local inference profile not found" in response.text


def test_runtime_status_provision_and_remove_routes(client, monkeypatch: pytest.MonkeyPatch) -> None:
    class StubRuntime:
        def __init__(self) -> None:
            self.provisioned = False
            self.started = 0
            self.removed = 0

        def status(self) -> dict[str, Any]:
            return {
                "provisioned": self.provisioned,
                "mlx_lm_version": "0.31.3" if self.provisioned else None,
                "disk_usage_bytes": 1024 if self.provisioned else 0,
                "python_path": "/tmp/mlx-runtime/bin/python" if self.provisioned else None,
                "runtime_dir": "/tmp/mlx-runtime",
                "job": {
                    "job_id": "job-1",
                    "state": "completed" if self.provisioned else "running",
                    "current": 3 if self.provisioned else 1,
                    "total": 3,
                    "percent": 100.0 if self.provisioned else 33.3,
                    "message": "ready" if self.provisioned else "creating",
                    "error": None,
                },
            }

        async def start_provision(self) -> dict[str, Any]:
            self.started += 1
            self.provisioned = True
            return self.status()

        def remove(self) -> dict[str, Any]:
            self.removed += 1
            self.provisioned = False
            return self.status()

    runtime = StubRuntime()
    monkeypatch.setattr(routes, "get_mlx_runtime", lambda: runtime)

    status = client.get("/api/local-inference/runtime")
    assert status.status_code == 200
    assert status.json()["provisioned"] is False

    provisioned = client.post("/api/local-inference/runtime/provision")
    assert provisioned.status_code == 200
    assert provisioned.json()["provisioned"] is True
    assert runtime.started == 1

    removed = client.delete("/api/local-inference/runtime")
    assert removed.status_code == 200
    assert removed.json()["provisioned"] is False
    assert runtime.removed == 1


def test_model_download_and_delete_routes(client, monkeypatch: pytest.MonkeyPatch) -> None:
    class StubJob:
        state = "running"

        def to_dict(self) -> dict[str, Any]:
            return {
                "job_id": "job-1",
                "model_id": routes.DEFAULT_OMLX_MODEL_ID,
                "state": "running",
                "current": 1,
                "total": 3,
                "percent": 33.3,
                "message": "Downloading",
                "error": None,
            }

    class StubStore:
        def __init__(self) -> None:
            self.deleted: list[str] = []
            self.job_value = StubJob()

        async def start_download(self, model_id: str):
            return self.job_value

        def job(self, job_id: str):
            return self.job_value if job_id == "job-1" else None

        async def cancel(self, job_id: str):
            return self.job_value

        def delete(self, model_id: str) -> int:
            self.deleted.append(model_id)
            return 123

    store = StubStore()
    monkeypatch.setattr(routes, "get_mlx_model_store", lambda: store)

    started = client.post(f"/api/local-inference/models/{routes.DEFAULT_OMLX_MODEL_ID}/download")
    assert started.status_code == 200
    assert started.json()["job_id"] == "job-1"

    status = client.get("/api/local-inference/models/downloads/job-1")
    assert status.status_code == 200
    assert status.json()["model_id"] == routes.DEFAULT_OMLX_MODEL_ID

    cancelled = client.post("/api/local-inference/models/downloads/job-1/cancel")
    assert cancelled.status_code == 200

    deleted = client.delete(f"/api/local-inference/models/{routes.DEFAULT_OMLX_MODEL_ID}")
    assert deleted.status_code == 200
    assert deleted.json()["freed_bytes"] == 123


def test_model_download_refuses_unsupported_hardware(client, monkeypatch: pytest.MonkeyPatch) -> None:
    class StubStore:
        async def start_download(self, model_id: str):
            raise routes.LocalModelHardwareError(
                "Qwen3-VL 8B needs 16 GB unified memory; this Mac has 8 GB"
            )

    monkeypatch.setattr(routes, "get_mlx_model_store", lambda: StubStore())

    response = client.post(f"/api/local-inference/models/{routes.DEFAULT_OMLX_MODEL_ID}/download")

    assert response.status_code == 409
    assert "16 GB unified memory" in response.text


def test_start_refuses_when_subprocesses_are_disabled(client, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fichero_server.llm.local_inference.get_local_inference_capabilities",
        lambda: routes.LocalInferenceCapabilities(
            system="Darwin",
            machine="arm64",
            is_apple_silicon=True,
            subprocess_capable=False,
            physical_memory_bytes=16 * 1024**3,
            macos_version="26.0",
        ),
    )

    response = client.post(
        f"/api/local-inference/profiles/{routes.DEFAULT_OMLX_PROFILE_ID}/start",
        json={"timeout_seconds": 0.1},
    )

    assert response.status_code == 409
    assert "not available on this device" in response.text
