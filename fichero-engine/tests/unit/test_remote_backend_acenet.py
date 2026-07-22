from __future__ import annotations

import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

import fichero.api.main as api_main
from fichero.security.remote_backend import build_remote_backend_status


def test_remote_backend_status_defaults_to_disabled() -> None:
    status = build_remote_backend_status({})

    assert status.enabled is False
    assert status.connection_model == "ssh-loopback"
    assert status.warnings == []


def test_remote_backend_status_accepts_ssh_loopback_configuration() -> None:
    status = build_remote_backend_status(
        {
            "FICHERO_REMOTE_BACKEND": "1",
            "FICHERO_API_URL": "http://127.0.0.1:18765",
            "FICHERO_API_KEY": "remote-token",
            "FICHERO_LIBRARY_PATH": "/remote/project/Library.fichero",
            "FICHERO_REMOTE_BACKEND_BIND_HOST": "127.0.0.1",
        }
    )

    assert status.enabled is True
    assert status.connection_model == "ssh-loopback"
    assert status.api_url == "http://127.0.0.1:18765"
    assert status.token_configured is True
    assert status.library_path_configured is True
    assert status.warnings == []


def test_remote_backend_status_warns_when_token_or_library_path_missing() -> None:
    status = build_remote_backend_status(
        {
            "FICHERO_REMOTE_BACKEND": "true",
            "FICHERO_API_URL": "http://127.0.0.1:18765",
        }
    )

    assert status.enabled is True
    assert any("FICHERO_API_KEY is not set" in item for item in status.warnings)
    assert any("FICHERO_LIBRARY_PATH is not set" in item for item in status.warnings)


def test_remote_backend_status_rejects_public_bind_host() -> None:
    with pytest.raises(ValueError, match="requires loopback binding"):
        build_remote_backend_status(
            {
                "FICHERO_REMOTE_BACKEND": "1",
                "FICHERO_REMOTE_BACKEND_BIND_HOST": "0.0.0.0",
            }
        )


def test_remote_backend_status_rejects_tailnet_bind_host() -> None:
    with pytest.raises(ValueError, match="tailscale serve or SSH -L"):
        build_remote_backend_status(
            {
                "FICHERO_REMOTE_BACKEND": "1",
                "FICHERO_REMOTE_BACKEND_BIND_HOST": "100.64.12.34",
            }
        )


def test_health_reports_remote_backend_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FICHERO_REMOTE_BACKEND", "1")
    monkeypatch.setenv("FICHERO_API_URL", "http://127.0.0.1:18765")
    monkeypatch.setenv("FICHERO_API_KEY", "remote-token")
    monkeypatch.setenv("FICHERO_LIBRARY_PATH", "/remote/project/Library.fichero")

    response = TestClient(api_main.app).get("/api/health")

    assert response.status_code == 200
    remote_backend = response.json()["remote_backend"]
    assert remote_backend["enabled"] is True
    assert remote_backend["connection_model"] == "ssh-loopback"
    assert remote_backend["api_url"] == "http://127.0.0.1:18765"
    assert remote_backend["token_configured"] is True
    assert remote_backend["library_path_configured"] is True


def test_health_nonce_returns_bootstrap_secret_hmac(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main, "_api_token", "server-secret", raising=False)

    response = TestClient(api_main.app).get("/api/health?nonce=client-nonce")

    assert response.status_code == 200
    expected = hmac.new(
        b"server-secret",
        b"client-nonce",
        hashlib.sha256,
    ).hexdigest()
    assert response.json()["server_proof"] == expected
