from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import fichero_server.api.main as api_main
import fichero_server.security.remote_backend as remote_backend


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
    """#2603, #5320: reachable means the tailnet port is Tailscale's HTTPS proxied to the
    engine's TLS listener -- the shape `tailscale serve --https=8765
    https+insecure://127.0.0.1:8765` writes (read on the Air 2026-10-01)."""
    payload = {
        "TCP": {"8765": {"HTTPS": True}},
        "Web": {"example.ts.net:8765": {"Handlers": {"/": {"Proxy": "https+insecure://127.0.0.1:8765"}}}},
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


def test_an_https_proxy_to_the_engine_port_is_not_reachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The older shape, still on the MBP 2026-10-01: Tailscale terminates HTTPS on 443 and
    proxies plain http:// to 8765. The engine's listener speaks TLS, so this cannot reach it --
    but the host name appears in the status, which the old substring check took as reachable.
    A `.ts.net` sharing address alone (no FICHERO_TAILNET_URL, as the app sets it) counts as
    configured."""
    payload = {
        "TCP": {"443": {"HTTPS": True}},
        "Web": {"example.ts.net:443": {"Handlers": {"/": {"Proxy": "http://127.0.0.1:8765"}}}},
    }

    monkeypatch.setattr(
        remote_backend.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=json.dumps(payload)),
    )

    remote_status = _health_remote_backend(
        monkeypatch,
        FICHERO_PUBLIC_BASE_URL="https://example.ts.net:8765",
    )

    assert remote_status["tailnet_status"] == "serve_not_running"


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
