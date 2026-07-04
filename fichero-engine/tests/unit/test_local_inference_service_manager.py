"""Unit tests for app-managed local MLX/oMLX service contracts."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
import signal
import socket
import sys
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

import fichero.local_inference as local_inference
from fichero.local_inference import (
    LocalInferenceRuntimeMissingError,
    ManagedLocalInferenceProcess,
    LocalInferenceServiceManager,
    LocalProviderProfile,
    LocalServiceState,
    is_loopback_url,
)


class FakeProcess:
    def __init__(self) -> None:
        self.pid: int | None = None
        self.last_error: str | None = None
        self.start_calls = 0
        self.stop_calls = 0
        self.running = False

    async def start(self) -> None:
        self.start_calls += 1
        self.last_error = None
        self.running = True
        self.pid = 1200 + self.start_calls

    async def stop(self) -> None:
        self.stop_calls += 1
        self.running = False
        self.pid = None

    def is_running(self) -> bool:
        return self.running

    def crash(self) -> None:
        self.running = False
        self.pid = None


def write_fake_managed_server(tmp_path: Path) -> Path:
    script = tmp_path / "fake_mlx_server.py"
    script.write_text(
        """import argparse
import http.server
import json
import os
import signal
import socketserver
import sys
import time

shutdown = False

def handle_signal(signum, frame):
    global shutdown
    shutdown = True

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--host", required=True)
parser.add_argument("--port", required=True, type=int)
args = parser.parse_args()

mode = os.environ.get("FICHERO_FAKE_MLX_MODE", "serve")
if mode == "exit":
    sys.stderr.write(os.environ.get("FICHERO_FAKE_MLX_STDERR", "boom\\n"))
    sys.stderr.flush()
    raise SystemExit(int(os.environ.get("FICHERO_FAKE_MLX_EXIT_CODE", "7")))

class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in {"/health", "/v1/health"}:
            self.send_response(404)
            self.end_headers()
            return
        payload = {
            "reachable": True,
            "model_loaded": True,
            "configured_model_id": args.model,
            "warm": True,
        }
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

class ReusableTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

with ReusableTCPServer((args.host, args.port), Handler) as server:
    server.daemon_threads = True
    server.timeout = 0.1
    while not shutdown:
        server.handle_request()
""",
        encoding="utf-8",
    )
    return script


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeHealthClient:
    def __init__(self, responses: list[dict[str, Any] | BaseException]) -> None:
        self.responses = list(responses)
        self.urls: list[str] = []

    async def get_json(self, url: str, timeout_seconds: float) -> dict[str, Any]:
        self.urls.append(url)
        if not self.responses:
            raise TimeoutError("no fake health response queued")
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def profile(**overrides: Any) -> LocalProviderProfile:
    data: dict[str, Any] = {
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


def healthy_payload() -> dict[str, Any]:
    return {
        "reachable": True,
        "model_loaded": True,
        "configured_model_id": "mlx-community/Qwen3-VL-8B",
        "warm": True,
    }


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://127.0.0.1:8766/v1", True),
        ("http://[::1]:8766/v1", True),
        ("http://localhost:8766/v1", True),
        ("https://api.openai.com/v1", False),
        ("http://192.168.1.10:8766/v1", False),
    ],
)
def test_loopback_url_detection(url: str, expected: bool) -> None:
    assert is_loopback_url(url) is expected


@pytest.mark.asyncio
async def test_success_health_marks_service_healthy() -> None:
    process = FakeProcess()
    client = FakeHealthClient([healthy_payload()])
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        client,
        poll_interval_seconds=0,
    )

    status = await manager.start()

    assert status.state == LocalServiceState.healthy
    assert status.healthy is True
    assert status.restart_count == 0
    assert status.pid == 1201
    assert status.uptime_seconds is not None
    assert client.urls == ["http://127.0.0.1:8766/v1/health"]


@pytest.mark.asyncio
async def test_cold_start_polls_until_model_loaded() -> None:
    process = FakeProcess()
    client = FakeHealthClient(
        [
            {"reachable": True, "model_loading": True, "model_loaded": False},
            healthy_payload(),
        ]
    )
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        client,
        poll_interval_seconds=0,
    )

    status = await manager.start(timeout_seconds=1)

    assert status.state == LocalServiceState.healthy
    assert len(client.urls) == 2
    assert process.start_calls == 1


@pytest.mark.asyncio
async def test_cold_start_retries_reachable_unloaded_without_loading_flag() -> None:
    process = FakeProcess()
    client = FakeHealthClient(
        [
            {"reachable": True, "model_loaded": False},
            healthy_payload(),
        ]
    )
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        client,
        poll_interval_seconds=0,
    )

    status = await manager.start(timeout_seconds=1)

    assert status.state == LocalServiceState.healthy
    assert status.healthy is True
    assert len(client.urls) == 2
    assert process.start_calls == 1


@pytest.mark.asyncio
async def test_start_retries_transient_health_transport_failure() -> None:
    process = FakeProcess()
    client = FakeHealthClient([ConnectionError("connection refused"), healthy_payload()])
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        client,
        poll_interval_seconds=0,
    )

    status = await manager.start(timeout_seconds=1)

    assert status.state == LocalServiceState.healthy
    assert status.healthy is True
    assert len(client.urls) == 2


@pytest.mark.asyncio
async def test_timeout_health_failure_is_failed_with_error() -> None:
    process = FakeProcess()
    client = FakeHealthClient([TimeoutError("connect timed out"), TimeoutError("still unavailable")])
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        client,
        poll_interval_seconds=0,
    )

    status = await manager.start(timeout_seconds=0)

    assert status.state == LocalServiceState.failed
    assert status.healthy is False
    assert "timed out" in (status.last_error or "")


@pytest.mark.asyncio
async def test_malformed_health_response_fails_closed() -> None:
    process = FakeProcess()
    client = FakeHealthClient([{"reachable": "yes", "model_loaded": "true", "memory_warning": "low memory"}])
    manager = LocalInferenceServiceManager(profile(), process, client)

    status = await manager.start()

    assert status.state == LocalServiceState.failed
    assert "malformed health response" in (status.last_error or "")
    assert "reachable" in (status.last_error or "")
    assert "model_loaded" in (status.last_error or "")


@pytest.mark.asyncio
async def test_crash_restart_accounting(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeDateTime:
        calls = 0
        values = [
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 1, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 2, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 3, tzinfo=UTC),
            datetime(2026, 1, 1, 12, 0, 4, tzinfo=UTC),
        ]

        @classmethod
        def now(cls, tz: object) -> datetime:
            value = cls.values[min(cls.calls, len(cls.values) - 1)]
            cls.calls += 1
            return value

    monkeypatch.setattr(local_inference, "datetime", FakeDateTime)
    process = FakeProcess()
    client = FakeHealthClient([healthy_payload(), healthy_payload()])
    manager = LocalInferenceServiceManager(profile(), process, client)

    first = await manager.start()
    process.crash()
    crashed = await manager.health()
    restarted = await manager.restart_after_crash()

    assert first.state == LocalServiceState.healthy
    assert crashed.state == LocalServiceState.failed
    assert "not running" in (crashed.last_error or "")
    assert restarted.state == LocalServiceState.healthy
    assert restarted.restart_count == 1
    assert first.started_at is not None
    assert restarted.started_at is not None
    assert restarted.started_at > first.started_at
    assert process.start_calls == 2


@pytest.mark.asyncio
async def test_stop_resets_state() -> None:
    process = FakeProcess()
    manager = LocalInferenceServiceManager(
        profile(),
        process,
        FakeHealthClient([healthy_payload()]),
    )

    await manager.start()
    status = await manager.stop()

    assert status.state == LocalServiceState.stopped
    assert status.healthy is False
    assert status.started_at is None
    assert process.stop_calls == 1


@pytest.mark.asyncio
async def test_managed_process_starts_and_stops_real_sidecar(tmp_path: Path) -> None:
    script = write_fake_managed_server(tmp_path)
    port = free_loopback_port()
    process = ManagedLocalInferenceProcess(
        profile(
            python_executable=sys.executable,
            command=[str(script)],
            base_url=f"http://127.0.0.1:{port}/v1",
        )
    )
    manager = LocalInferenceServiceManager(
        profile(
            python_executable=sys.executable,
            command=[str(script)],
            base_url=f"http://127.0.0.1:{port}/v1",
        ),
        process,
        poll_interval_seconds=0.01,
    )

    status = await manager.start(timeout_seconds=2)

    assert status.state == LocalServiceState.healthy
    assert status.pid is not None
    pid = status.pid
    assert process.is_running() is True
    os.kill(pid, 0)

    stopped = await manager.stop()

    assert stopped.state == LocalServiceState.stopped
    assert process.pid is None
    assert process.is_running() is False
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.asyncio
async def test_managed_process_surfaces_crash_error_and_allows_restart(tmp_path: Path) -> None:
    script = write_fake_managed_server(tmp_path)
    port = free_loopback_port()
    managed_profile = profile(
        python_executable=sys.executable,
        command=[str(script)],
        base_url=f"http://127.0.0.1:{port}/v1",
    )
    process = ManagedLocalInferenceProcess(managed_profile)
    manager = LocalInferenceServiceManager(
        managed_profile,
        process,
        poll_interval_seconds=0.01,
    )

    first = await manager.start(timeout_seconds=2)
    assert first.state == LocalServiceState.healthy
    assert process.pid is not None
    os.kill(process.pid, signal.SIGKILL)
    deadline = datetime.now(UTC).timestamp() + 2
    while process.is_running() and datetime.now(UTC).timestamp() < deadline:
        await asyncio.sleep(0.01)

    crashed = await manager.health()

    assert crashed.state == LocalServiceState.failed
    assert "exited" in (crashed.last_error or "")

    restarted = await manager.restart_after_crash(timeout_seconds=2)

    assert restarted.state == LocalServiceState.healthy
    assert restarted.restart_count == 1
    await manager.stop()


@pytest.mark.asyncio
async def test_managed_process_missing_runtime_raises_typed_error() -> None:
    managed_profile = profile(
        python_executable="/does/not/exist/python",
        command=["-m", "mlx_lm", "server"],
    )
    process = ManagedLocalInferenceProcess(managed_profile)

    with pytest.raises(LocalInferenceRuntimeMissingError):
        await process.start()

    assert process.last_error is not None
    assert "runtime not found" in process.last_error


@pytest.mark.asyncio
async def test_managed_process_stderr_excerpt_surfaces_in_status(tmp_path: Path) -> None:
    script = write_fake_managed_server(tmp_path)
    port = free_loopback_port()
    managed_profile = profile(
        python_executable=sys.executable,
        command=[str(script)],
        base_url=f"http://127.0.0.1:{port}/v1",
    )
    process = ManagedLocalInferenceProcess(managed_profile)
    manager = LocalInferenceServiceManager(
        managed_profile,
        process,
        poll_interval_seconds=0.01,
    )
    previous_mode = os.environ.get("FICHERO_FAKE_MLX_MODE")
    previous_stderr = os.environ.get("FICHERO_FAKE_MLX_STDERR")
    previous_exit = os.environ.get("FICHERO_FAKE_MLX_EXIT_CODE")
    os.environ["FICHERO_FAKE_MLX_MODE"] = "exit"
    os.environ["FICHERO_FAKE_MLX_STDERR"] = "mlx runtime missing"
    os.environ["FICHERO_FAKE_MLX_EXIT_CODE"] = "9"
    try:
        status = await manager.start(timeout_seconds=0.2)
    finally:
        if previous_mode is None:
            os.environ.pop("FICHERO_FAKE_MLX_MODE", None)
        else:
            os.environ["FICHERO_FAKE_MLX_MODE"] = previous_mode
        if previous_stderr is None:
            os.environ.pop("FICHERO_FAKE_MLX_STDERR", None)
        else:
            os.environ["FICHERO_FAKE_MLX_STDERR"] = previous_stderr
        if previous_exit is None:
            os.environ.pop("FICHERO_FAKE_MLX_EXIT_CODE", None)
        else:
            os.environ["FICHERO_FAKE_MLX_EXIT_CODE"] = previous_exit

    assert status.state == LocalServiceState.failed
    assert "mlx runtime missing" in (status.last_error or "")


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "https://api.openai.com/v1"},
        {"provider_type": "openai"},
        {"allows_paid_fallbacks": True},
        {"healthcheck_path": "health"},
    ],
)
def test_profile_validation_rejects_cloud_non_loopback_fallbacks(overrides: dict[str, Any]) -> None:
    with pytest.raises((ValidationError, ValueError)):
        profile(**overrides)
