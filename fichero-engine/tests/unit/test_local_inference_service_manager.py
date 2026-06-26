"""Unit tests for app-managed local MLX/oMLX service contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

import fichero.local_inference as local_inference
from fichero.local_inference import (
    LocalInferenceServiceManager,
    LocalProviderProfile,
    LocalServiceState,
    is_loopback_url,
)


class FakeProcess:
    def __init__(self) -> None:
        self.pid: int | None = None
        self.start_calls = 0
        self.stop_calls = 0
        self.running = False

    async def start(self) -> None:
        self.start_calls += 1
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
