from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import fichero.api.main as api_main
import fichero.security.remote_backend as remote_backend


def _health_remote_backend(monkeypatch: pytest.MonkeyPatch, **env: str) -> dict[str, object]:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    response = TestClient(api_main.app).get("/api/health")
    assert response.status_code == 200
    return response.json()["remote_backend"]


def test_tailnet_detection_reports_not_configured_without_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout="{}")

    monkeypatch.setattr(remote_backend.subprocess, "run", fake_run)

    remote_status = _health_remote_backend(monkeypatch)

    assert remote_status["tailnet_status"] == "not_configured"
    assert calls == []


def test_tailnet_detection_reports_reachable_when_serve_targets_configured_ts_net(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "Web": {
            "example.ts.net:443": {
                "Handlers": {"/": "http://127.0.0.1:8765"}
            }
        }
    }

    monkeypatch.setattr(
        remote_backend.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    remote_status = _health_remote_backend(
        monkeypatch,
        FICHERO_TAILNET_URL="https://example.ts.net",
    )

    assert remote_status["tailnet_status"] == "reachable"


def test_tailnet_detection_reports_serve_not_running_when_status_lacks_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        remote_backend.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps({})),
    )

    remote_status = _health_remote_backend(
        monkeypatch,
        FICHERO_TAILNET_URL="https://example.ts.net",
    )

    assert remote_status["tailnet_status"] == "serve_not_running"


def test_tailnet_detection_reports_cli_missing_loudly(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def raise_missing(*args, **kwargs):
        raise FileNotFoundError("tailscale")

    monkeypatch.setattr(remote_backend.subprocess, "run", raise_missing)

    remote_status = _health_remote_backend(
        monkeypatch,
        FICHERO_TAILNET_URL="https://example.ts.net",
    )

    assert remote_status["tailnet_status"] == "not_installed"
    assert "tailscale CLI not installed" in caplog.text
