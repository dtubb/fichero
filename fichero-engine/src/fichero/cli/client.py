"""FicheroClient — a thin synchronous HTTP wrapper around the Fichero backend.

The backend binds to 127.0.0.1:8765 and requires two things on most requests:

* ``Authorization: Bearer <token>`` — a per-launch shared secret the engine
  writes to ``~/Library/Application Support/Fichero/.api-key`` (mode 0600).
  See ``fichero/api/auth.py`` for the writer side.
* ``X-Fichero-Library-Path`` — the ``.fichero`` package the request operates on.

This client discovers the token automatically and attaches both headers. Where
a backend response shape is captured by an existing Pydantic model in
``fichero.models``, the method imports it and returns the validated typed
instance — so callers see ``Document`` / ``Workflow`` / ``Artifact`` rather
than ``Any``, and shape drift becomes a loud ``ValidationError`` at the
boundary instead of a silent ``KeyError`` deep in the formatter. The CLI and
the backend share the source-of-truth Pydantic types by direct import (no
codegen, no possibility of drift). Endpoints that return custom shapes still
return ``Any`` for now — they'll get typed in follow-up commits.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

from fichero.models import Artifact, Document, Workflow

DEFAULT_BASE_URL = "http://127.0.0.1:8765"

# Matches fichero/api/auth.py::_token_file_path — the engine owns the writer,
# this is the reader.
_TOKEN_PATH = Path.home() / "Library" / "Application Support" / "Fichero" / ".api-key"


class FicheroError(RuntimeError):
    """The backend was unreachable or returned a non-2xx response.

    ``status_code`` is the HTTP status when the failure came from a response;
    ``None`` for transport errors (connection refused, DNS, etc.). Callers that
    want to differentiate "not ready yet" (404) from "real error" should check
    this rather than parsing the message string.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _read_token() -> str | None:
    """Read the per-launch auth token, or None if the engine hasn't written it."""
    env = os.environ.get("FICHERO_API_KEY")
    if env:
        return env.strip()
    try:
        return _TOKEN_PATH.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop None-valued entries so optional query params are simply omitted."""
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


def _expect_list(raw: Any, path: str) -> list[Any]:
    """Assert a typed-list method's response really is a list.

    The whole point of typing at the boundary is to make a wrong-shape
    response loud, not silent. Without this guard, ``raw or []`` would swallow
    ``None`` (204 / empty body) as "zero results" and treat ``{"error": ...}``
    as a dict to iterate (yielding string keys that then fail Pydantic
    validation with a confusing message). This raises a clear error instead.
    """
    if not isinstance(raw, list):
        raise FicheroError(
            f"GET {path} returned {type(raw).__name__}, expected a list"
        )
    return raw


class FicheroClient:
    """Synchronous HTTP client for the Fichero backend.

    Pass ``transport`` (an ``httpx.MockTransport``) in tests to exercise request
    construction without a live backend.
    """

    def __init__(
        self,
        base_url: str | None = None,
        library_path: str | None = None,
        token: str | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("FICHERO_API_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self.library_path = library_path or os.environ.get("FICHERO_LIBRARY_PATH")
        # token="" is honoured (explicit "no token"); token=None means discover.
        self.token = token if token is not None else _read_token()
        self._client = httpx.Client(
            base_url=self.base_url, timeout=timeout, transport=transport
        )

    # -- lifecycle ---------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FicheroClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- core --------------------------------------------------------------
    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.library_path:
            headers["X-Fichero-Library-Path"] = self.library_path
        return headers

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        files: Any = None,
    ) -> Any:
        """Issue a request and return parsed JSON (or None for empty responses).

        Raises FicheroError on connection failure or any non-2xx status.
        """
        try:
            response = self._client.request(
                method,
                path,
                params=_clean(params),
                json=json,
                files=files,
                headers=self._headers(),
            )
        except httpx.ConnectError as exc:
            raise FicheroError(
                f"Cannot connect to the Fichero backend at {self.base_url}. "
                "Is the engine running?"
            ) from exc
        except httpx.HTTPError as exc:
            raise FicheroError(f"{method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            raise FicheroError(
                f"{method} {path} -> {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    # -- health ------------------------------------------------------------
    def health(self) -> Any:
        return self.request("GET", "/api/health")

    # -- documents ---------------------------------------------------------
    def list_documents(
        self,
        *,
        parent_id: str | None = None,
        doc_type: str | None = None,
        file_type: str | None = None,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Document]:
        raw = self.request(
            "GET",
            "/api/documents",
            params={
                "parent_id": parent_id,
                "doc_type": doc_type,
                "file_type": file_type,
                "status": status,
                "limit": limit,
                "offset": offset,
            },
        )
        return [Document.model_validate(d) for d in _expect_list(raw, "/api/documents")]

    def get_document(self, doc_id: str) -> Document:
        return Document.model_validate(
            self.request("GET", f"/api/documents/{doc_id}")
        )

    def document_inspector(self, doc_id: str) -> Any:
        """Aggregate view of a document's entities, claims, and artifacts."""
        return self.request("GET", f"/api/documents/{doc_id}/inspector")

    def import_file(self, path: str | Path, parent_id: str | None = None) -> Any:
        """Upload a single file to the library (multipart/form-data)."""
        file_path = Path(path).expanduser()
        with file_path.open("rb") as handle:
            return self.request(
                "POST",
                "/api/documents/import",
                params={"parent_id": parent_id},
                files={"file": (file_path.name, handle)},
            )

    # -- workflows ---------------------------------------------------------
    def list_workflows(self) -> list[Workflow]:
        raw = self.request("GET", "/api/workflows")
        return [Workflow.model_validate(w) for w in _expect_list(raw, "/api/workflows")]

    def run_workflow(
        self,
        workflow_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        force_new: bool = False,
        skip_cache: bool = False,
    ) -> Any:
        return self.request(
            "POST",
            "/api/workflow-execution/execute",
            json={
                "workflow_id": workflow_id,
                "inputs": inputs or {},
                "force_new": force_new,
                "skip_cache": skip_cache,
            },
        )

    def execution_status(self, thread_id: str) -> Any:
        return self.request(
            "GET", f"/api/workflow-execution/threads/{thread_id}/status"
        )

    # -- artifacts ---------------------------------------------------------
    def list_artifacts(
        self,
        doc_id: str,
        *,
        artifact_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_descendants: bool = True,
    ) -> list[Artifact]:
        path = f"/api/artifacts/document/{doc_id}"
        raw = self.request(
            "GET",
            path,
            params={
                "artifact_type": artifact_type,
                "limit": limit,
                "offset": offset,
                "include_descendants": include_descendants,
            },
        )
        return [Artifact.model_validate(a) for a in _expect_list(raw, path)]

    # -- knowledge graph ---------------------------------------------------
    def list_entities(
        self,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> Any:
        return self.request(
            "GET",
            "/api/entities",
            params={"q": query, "entity_type": entity_type, "limit": limit},
        )

    def list_claims(
        self,
        *,
        query: str | None = None,
        source_document_id: str | None = None,
        entity_id: str | None = None,
        claim_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Any:
        return self.request(
            "GET",
            "/api/claims",
            params={
                "q": query,
                "source_document_id": source_document_id,
                "entity_id": entity_id,
                "claim_type": claim_type,
                "limit": limit,
                "offset": offset,
            },
        )

    def kg_search(self, query: str, *, limit: int = 50) -> Any:
        return self.request(
            "GET", "/api/kg/search", params={"q": query, "limit": limit}
        )

    # -- search ------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        search_type: str = "hybrid",
        min_score: float = 0.3,
    ) -> Any:
        return self.request(
            "POST",
            "/api/search",
            json={
                "query": query,
                "limit": limit,
                "search_type": search_type,
                "min_score": min_score,
            },
        )

    # -- activity ----------------------------------------------------------
    def recent_activity(self, *, limit: int = 50) -> Any:
        return self.request("GET", "/api/activity/recent", params={"limit": limit})
