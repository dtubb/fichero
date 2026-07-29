from __future__ import annotations

import ipaddress
import shutil
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

DEFAULT_API_BASE = "http://127.0.0.1:8765/api"
DEFAULT_TOKEN_FILE = Path(
    "~/Library/Application Support/Fichero/.api-key"
).expanduser()


class ManifestApiClient(Protocol):
    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any: ...


class ImporterHttpClient(Protocol):
    base_url: str

    def create_library(self, path: str) -> Any: ...

    def import_file(self, path: str | Path, parent_id: str | None = None) -> Any: ...

    def list_documents(self, *, parent_id: str | None = None, **kwargs: Any) -> list[Any]: ...

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
    ) -> Any: ...


class HttpManifestClient:
    """Shared CLI transport for importers that talk to a running engine."""

    def __init__(
        self, api_base: str, token: str, library_path: str, timeout: int = 120
    ) -> None:
        from fichero_server.cli.client import FicheroClient

        self._client = FicheroClient(
            base_url=api_base.removesuffix("/api"),
            token=token,
            library_path=library_path,
            timeout=timeout,
        )

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        return self._client.request(method, f"/api{path}", json=body)


def resolve_http_token(
    token_file: Path = DEFAULT_TOKEN_FILE,
    *,
    api_base: str | None = None,
) -> str:
    if token_file == DEFAULT_TOKEN_FILE:
        from fichero_server.cli.client import _read_token

        token = _read_token(base_url=api_base.removesuffix("/api") if api_base else None)
        if token:
            return token
    return token_file.read_text(encoding="utf-8").strip()


def ensure_remote_document(
    client: ImporterHttpClient,
    *,
    name: str,
    path: str,
    doc_type: str,
    parent_id: str | None,
    status: str = "completed",
    file_type: str | None = None,
    page_content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "path": path,
        "doc_type": doc_type,
        "parent_id": parent_id,
        "status": status,
    }
    if file_type is not None:
        payload["file_type"] = file_type
    if page_content is not None:
        payload["page_content"] = page_content
    if metadata is not None:
        payload["metadata"] = metadata

    for existing in client.list_documents(parent_id=parent_id):
        existing_path = getattr(existing, "path", None)
        existing_type = getattr(getattr(existing, "doc_type", None), "value", None) or getattr(existing, "doc_type", None)
        if existing_path == path and existing_type == doc_type:
            return client.request("PUT", f"/api/documents/{existing.id}", json=payload)
    return client.request("POST", "/api/documents", json=payload)


def reset_local_library_if_loopback(
    client: ImporterHttpClient, library_path: Path, *, reset: bool
) -> None:
    if not reset or not library_path.exists():
        return
    if not _client_uses_loopback(client):
        return
    shutil.rmtree(library_path)


def _client_uses_loopback(client: ImporterHttpClient) -> bool:
    host = urlparse(getattr(client, "base_url", "")).hostname
    if not host:
        return False
    if host in {"localhost", "::1"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


__all__ = [
    "DEFAULT_API_BASE",
    "DEFAULT_TOKEN_FILE",
    "HttpManifestClient",
    "ImporterHttpClient",
    "ManifestApiClient",
    "ensure_remote_document",
    "reset_local_library_if_loopback",
    "resolve_http_token",
]
