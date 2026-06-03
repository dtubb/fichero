"""Remote backend configuration helpers.

Fichero's supported remote-backend model is SSH loopback forwarding: the
engine still binds to 127.0.0.1 on the remote host, and the client reaches it
through a local tunnel. This module keeps that contract explicit and testable.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from os import environ
from typing import Mapping
from urllib.parse import urlparse


_TRUE_VALUES = {"1", "true", "yes", "on"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}
SUPPORTED_CONNECTION_MODEL = "ssh-loopback"


@dataclass(frozen=True)
class RemoteBackendStatus:
    """Remote-backend startup status exposed through health diagnostics."""

    enabled: bool
    connection_model: str
    api_url: str | None
    library_path_configured: bool
    token_configured: bool
    warnings: list[str]

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in _TRUE_VALUES


def _host_from_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    return parsed.hostname


def build_remote_backend_status(
    env: Mapping[str, str] | None = None,
) -> RemoteBackendStatus:
    """Validate and summarize the configured remote-backend mode.

    ``FICHERO_REMOTE_BACKEND=1`` opts into remote mode. Remote mode supports
    only SSH loopback forwarding; a public bind host is rejected because auth is
    designed as a local shared-secret, not an internet-facing API boundary.
    """

    source = env if env is not None else environ
    enabled = _is_truthy(source.get("FICHERO_REMOTE_BACKEND"))
    model = source.get("FICHERO_REMOTE_BACKEND_MODEL", SUPPORTED_CONNECTION_MODEL)
    model = model.strip() or SUPPORTED_CONNECTION_MODEL
    api_url = source.get("FICHERO_API_URL")
    library_path = source.get("FICHERO_LIBRARY_PATH")
    token = source.get("FICHERO_API_KEY")
    bind_host = source.get("FICHERO_REMOTE_BACKEND_BIND_HOST")
    warnings: list[str] = []

    if not enabled:
        return RemoteBackendStatus(
            enabled=False,
            connection_model=SUPPORTED_CONNECTION_MODEL,
            api_url=api_url,
            library_path_configured=bool(library_path),
            token_configured=bool(token),
            warnings=[],
        )

    if model != SUPPORTED_CONNECTION_MODEL:
        raise ValueError(
            "Unsupported FICHERO_REMOTE_BACKEND_MODEL. "
            f"Expected {SUPPORTED_CONNECTION_MODEL!r}; got {model!r}."
        )

    if bind_host and bind_host not in _LOOPBACK_HOSTS:
        raise ValueError(
            "Remote backend mode requires loopback binding. "
            "Start the engine on 127.0.0.1 and use SSH -L forwarding; "
            f"got FICHERO_REMOTE_BACKEND_BIND_HOST={bind_host!r}."
        )

    api_host = _host_from_url(api_url)
    if api_host and api_host not in _LOOPBACK_HOSTS:
        warnings.append(
            "FICHERO_API_URL is not loopback. Prefer an SSH tunnel such as "
            "http://127.0.0.1:18765 rather than exposing the backend host."
        )
    if not token:
        warnings.append("FICHERO_API_KEY is not set; protected endpoints will return 401.")
    if not library_path:
        warnings.append(
            "FICHERO_LIBRARY_PATH is not set; library-specific endpoints need a "
            "remote .fichero path."
        )

    return RemoteBackendStatus(
        enabled=True,
        connection_model=model,
        api_url=api_url,
        library_path_configured=bool(library_path),
        token_configured=bool(token),
        warnings=warnings,
    )
