from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Protocol

DEFAULT_API_BASE = "http://127.0.0.1:8765/api"
DEFAULT_TOKEN_FILE = Path(
    "~/Library/Application Support/Fichero/.api-key"
).expanduser()


class ManifestApiClient(Protocol):
    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any: ...


class ImporterHttpClient(Protocol):
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
    """urllib-based transport for importers that talk to a running engine."""

    def __init__(
        self, api_base: str, token: str, library_path: str, timeout: int = 120
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.library_path = library_path
        self.timeout = timeout

    def request(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> Any:
        url = f"{self.api_base}{path}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "X-Fichero-Library-Path": urllib.parse.quote(self.library_path, safe="/"),
        }
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                if "application/json" not in resp.headers.get("Content-Type", ""):
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"{method} {url} failed: HTTP {exc.code}: {detail}"
            ) from exc


def resolve_http_token(token_file: Path = DEFAULT_TOKEN_FILE) -> str:
    if token_file == DEFAULT_TOKEN_FILE:
        from fichero.cli.client import _read_token

        token = _read_token()
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


__all__ = [
    "DEFAULT_API_BASE",
    "DEFAULT_TOKEN_FILE",
    "HttpManifestClient",
    "ImporterHttpClient",
    "ManifestApiClient",
    "ensure_remote_document",
    "resolve_http_token",
]
