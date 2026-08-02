"""FicheroClient — a thin synchronous HTTP wrapper around the Fichero backend.

The backend binds to 127.0.0.1:8765 and requires two things on most requests:

* ``Authorization: Bearer <token>`` — a per-launch shared secret the engine
  writes to ``~/Library/Application Support/Fichero/.api-key`` (mode 0600).
  See ``fichero/api/auth.py`` for the writer side.
* ``X-Fichero-Library-Path`` — the ``.fichero`` package the request operates on.

This client discovers the token automatically and attaches both headers. Where
a backend response shape is captured by an existing Pydantic model in
``fichero_server.models``, the method imports it and returns the validated typed
instance — so callers see ``Document`` / ``Workflow`` / ``Artifact`` rather
than ``Any``, and shape drift becomes a loud ``ValidationError`` at the
boundary instead of a silent ``KeyError`` deep in the formatter. The CLI and
the backend share the source-of-truth Pydantic types by direct import (no
codegen, no possibility of drift). Endpoints that return custom shapes still
return ``Any`` for now — they'll get typed in follow-up commits.
"""

from __future__ import annotations

import json
import ipaddress
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote
from urllib.parse import urlparse

import httpx

from fichero_server.api.routes.system.activity import ActivityResponse
from fichero_server.api.routes.document.artifacts import ArtifactResponse
from fichero_server.api.routes.document.inspector import (
    DocumentInspectorResponse,
    DocumentKnowledgeGraphResponse,
)
from fichero_server.api.routes.entity.entities import (
    EntityAuditResponse,
    EntityCoOccurrence,
    EntityDocumentLink,
    EntityDrillDownResponse,
    EntityResolutionResponse,
    TopEntityRow,
)
from fichero_server.api.routes.entity.inspector import EntityInspectorResponse
from fichero_server.api.routes.kg_graph import NeighborhoodResponse
from fichero_server.api.routes.kg_rebuild import KGResetResponse, RebuildResponse
from fichero_server.api.routes.kg_search import KGSearchResponse
from fichero_server.api.routes.ai.model_comparison import ComparisonResultResponse
from fichero_server.api.routes.ai.provider_models import ProviderResponse
from fichero_server.models.hermeneutics import Interpretation
from fichero_server.api.routes.search import SearchResponse
from fichero_server.api.routes.system.settings import AIDefaults
from fichero_server.api.routes.workflow_execution.schemas import (
    ExecuteAcceptedResponse,
    ExecutionStatusResponse,
    ThreadListResponse,
)
from fichero_server.api.routes.workflow_execution.threads import (
    CancelResponse,
    ThreadDeletedResponse,
)
from fichero_server.models.knowledge import KnowledgeClaim, KnowledgeEntity, Note, NoteKind
from fichero_server.models import (
    Artifact,
    ClaimListResponse,
    Document,
    KnownLibrary,
    LibraryCreateResponse,
    LibraryRegistryResponse,
    LibrarySnapshot,
    Workflow,
)

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
SPLIT_CHAPTERS_WORKFLOW_NAME = "Split Chapters"
TRANSLATE_WORKFLOW_NAME = "Translate"

# Matches fichero/api/auth.py::_token_file_path — the engine owns the writer,
# this is the reader.
_TOKEN_PATH = Path.home() / "Library" / "Application Support" / "Fichero" / ".api-key"
_CLI_SESSION_PATH = _TOKEN_PATH.with_name("cli-session.json")


def _is_loopback_base_url(base_url: str | None) -> bool | None:
    if not base_url:
        return None
    host = urlparse(base_url).hostname
    if not host:
        return None
    if host in {"localhost", "::1", "test", "testserver", "testclient"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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


def _read_cli_session_payload(as_user: str | None = None) -> dict[str, Any]:
    """Read the selected CLI session payload from disk, if present."""
    try:
        if (_CLI_SESSION_PATH.stat().st_mode & 0o777) != 0o600:
            return {}
        payload = json.loads(_CLI_SESSION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, AttributeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    if "session_token" in payload:
        return payload
    sessions = payload.get("sessions")
    if not isinstance(sessions, dict) or not sessions:
        return {}
    selected_user = (as_user or payload.get("current_user") or "").strip()
    if selected_user:
        selected = sessions.get(selected_user)
        return selected if isinstance(selected, dict) else {}
    first_session = next(iter(sessions.values()), {})
    return first_session if isinstance(first_session, dict) else {}


def _read_token(base_url: str | None = None, as_user: str | None = None) -> str | None:
    """Read the selected auth token, scoped to the actual backend host."""
    # An explicitly selected account must never fall back to the loopback
    # bootstrap credential: that would attribute an agent MCP action to owner.
    if as_user:
        payload = _read_cli_session_payload(as_user=as_user)
        token = payload.get("session_token")
        return token.strip() if isinstance(token, str) and token.strip() else None

    env = os.environ.get("FICHERO_SESSION_TOKEN")
    if env:
        return env.strip()

    loopback = _is_loopback_base_url(base_url)
    if loopback is False:
        payload = _read_cli_session_payload(as_user=as_user)
        token = payload.get("session_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        env = os.environ.get("FICHERO_API_KEY")
        if env:
            return env.strip()
        return None

    if loopback is None:
        payload = _read_cli_session_payload(as_user=as_user)
        token = payload.get("session_token")
        if isinstance(token, str) and token.strip():
            return token.strip()

    env = os.environ.get("FICHERO_API_KEY")
    if env:
        return env.strip()

    try:
        return _TOKEN_PATH.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None



def _connect_error(base_url: str, exc: httpx.ConnectError) -> "FicheroError":
    """Say what actually failed: TLS trust and connection-refused are different
    diagnoses (#4468). Reporting a certificate failure as "is the engine
    running?" sends the caller to check a process that is up.
    """
    text = f"{exc} {exc.__cause__ or ''}".lower()
    if "certificate" in text or "ssl" in text or "tls" in text:
        return FicheroError(
            f"TLS certificate verification failed for {base_url}. The engine is "
            "likely RUNNING; its loopback certificate is self-signed. Trust it "
            "by pointing SSL_CERT_FILE at the engine's server.crt (under "
            "~/Library/Application Support/Fichero/Remote Access/<host-port-...>/)."
        )
    return FicheroError(
        f"Cannot connect to the Fichero backend at {base_url}. Is the engine running?"
    )


def _clean(params: dict[str, Any] | None) -> dict[str, Any] | None:
    """Drop None-valued entries so optional query params are simply omitted."""
    if not params:
        return None
    cleaned = {k: v for k, v in params.items() if v is not None}
    return cleaned or None


def _expect_list(raw: Any, path: str) -> list[Any]:
    """Unwrap a list endpoint's ``{items, count}`` envelope to its items.

    Every list endpoint returns the standardized envelope (#1075/#1149), so
    the single uniform rule for the CLI is "take ``.items``". A bare list is
    still accepted for any endpoint not yet migrated, so this stays correct
    mid-sweep.

    The guard keeps wrong-shape responses loud rather than silent: without it,
    ``raw or []`` would swallow ``None`` (204 / empty body) as "zero results"
    and treat ``{"error": ...}`` as a dict to iterate.
    """
    if isinstance(raw, dict) and isinstance(raw.get("items"), list):
        return raw["items"]
    if not isinstance(raw, list):
        raise FicheroError(
            f"GET {path} returned {type(raw).__name__}, expected a "
            "{items, count} envelope or a list"
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
        as_user: str | None = None,
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        client_name: str | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("FICHERO_API_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        # token="" is honoured (explicit "no token"); token=None means discover
        # from disk on demand so the client can survive startup ordering races.
        self._discover_token = token is None
        self._as_user = as_user.strip() if isinstance(as_user, str) and as_user.strip() else None
        self.token = token if token is not None else _read_token(
            base_url=self.base_url,
            as_user=self._as_user,
        )
        # library_path="" is honoured (explicit "no library"); library_path=None
        # means discover from the environment on demand so a late-bound window
        # can still recover without reconstructing the client.
        self._discover_library_path = library_path is None
        self.library_path = library_path or os.environ.get("FICHERO_LIBRARY_PATH")
        # Which client surface is speaking (e.g. "fichero-cli", "fichero-mcp").
        # Sent as X-Fichero-Client and recorded on ActionAudit rows so an audit
        # entry says WHICH surface used a credential, not just whose credential
        # it was (#4469). Attribution metadata only — never used for authz.
        self.client_name = client_name
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
    def _refresh_auth_context(self) -> bool:
        """Refresh lazily discovered auth headers from their live sources.

        The shared-secret token is written by the engine at startup and the
        library path may not be available until the active document/window has
        finished restoring. A client that snapshots either value too early can
        emit a burst of unauthenticated requests during startup and then work
        moments later. Re-reading the live sources keeps the first protected
        request from being permanently stale.
        """
        changed = False
        if self._discover_token:
            refreshed = _read_token(base_url=self.base_url, as_user=self._as_user)
            if refreshed and refreshed != self.token:
                self.token = refreshed
                changed = True
        if self._discover_library_path:
            refreshed_path = os.environ.get("FICHERO_LIBRARY_PATH")
            if refreshed_path and refreshed_path != self.library_path:
                self.library_path = refreshed_path
                changed = True
        return changed

    def _headers(self) -> dict[str, str]:
        self._refresh_auth_context()
        headers: dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.library_path:
            headers["X-Fichero-Library-Path"] = quote(self.library_path, safe="/")
        if self.client_name:
            headers["X-Fichero-Client"] = self.client_name
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
        self._refresh_auth_context()
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
            raise _connect_error(self.base_url, exc) from exc
        except httpx.HTTPError as exc:
            raise FicheroError(f"{method} {path} failed: {exc}") from exc

        if response.status_code in {401, 403} and self._refresh_auth_context():
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
                raise _connect_error(self.base_url, exc) from exc
            except httpx.HTTPError as exc:
                raise FicheroError(f"{method} {path} failed: {exc}") from exc

        if response.status_code >= 400:
            raise FicheroError(
                f"{method} {path} -> {response.status_code}: {response.text}",
                status_code=response.status_code,
            )
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            content_type = response.headers.get("content-type", "")
            if content_type.startswith("text/"):
                return response.text
            return {
                "content_type": content_type or "application/octet-stream",
                "bytes": len(response.content),
            }

    def request_stream(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[str]:
        """Issue a request and return SSE/text lines without buffering JSON."""
        self._refresh_auth_context()
        try:
            with self._client.stream(
                method,
                path,
                params=_clean(params),
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    raise FicheroError(
                        f"{method} {path} -> {response.status_code}: {response.text}",
                        status_code=response.status_code,
                    )
                return [line for line in response.iter_lines() if line]
        except httpx.ConnectError as exc:
            raise _connect_error(self.base_url, exc) from exc
        except httpx.HTTPError as exc:
            raise FicheroError(f"{method} {path} failed: {exc}") from exc

    # -- health ------------------------------------------------------------
    def health(self) -> Any:
        return self.request("GET", "/api/health")

    # -- devices -----------------------------------------------------------
    def list_devices(self) -> Any:
        return self.request("GET", "/api/pair/devices")

    def revoke_device(self, device_id: str) -> Any:
        return self.request("POST", f"/api/pair/devices/{device_id}/revoke")

    # -- notes -------------------------------------------------------------
    def create_note(
        self,
        *,
        title: str | None = None,
        body: str = "",
        kind: str | NoteKind = NoteKind.zettel,
        tags: list[str] | None = None,
        linked_note_ids: list[str] | None = None,
        linked_entity_ids: list[str] | None = None,
        linked_claim_ids: list[str] | None = None,
        linked_document_ids: list[str] | None = None,
        page_id: str | None = None,
        folder_id: str | None = None,
        address: str | None = None,
        parent_address: str | None = None,
    ) -> Note:
        """Create a Zettelkasten note."""
        payload = {
            "title": title,
            "body": body,
            "kind": kind.value if isinstance(kind, NoteKind) else kind,
            "tags": tags or [],
            "linked_note_ids": linked_note_ids or [],
            "linked_entity_ids": linked_entity_ids or [],
            "linked_claim_ids": linked_claim_ids or [],
            "linked_document_ids": linked_document_ids or [],
            "address": address,
            "parent_address": parent_address,
        }
        if page_id is not None:
            payload["page_id"] = page_id
        if folder_id is not None:
            payload["folder_id"] = folder_id
        raw = self.request(
            "POST",
            "/api/notes",
            json=payload,
        )
        return Note.model_validate(raw)

    def list_notes(
        self,
        *,
        kind: str | NoteKind | None = None,
        tag: str | None = None,
        linked_entity_id: str | None = None,
        linked_claim_id: str | None = None,
        linked_document_id: str | None = None,
        page_id: str | None = None,
        folder_id: str | None = None,
        query: str | None = None,
    ) -> list[Note]:
        """List Zettelkasten notes, optionally filtered."""
        params = {
            "kind": kind.value if isinstance(kind, NoteKind) else kind,
            "tag": tag,
            "linked_entity_id": linked_entity_id,
            "linked_claim_id": linked_claim_id,
            "linked_document_id": linked_document_id,
            "q": query,
        }
        if page_id is not None:
            params["page_id"] = page_id
        if folder_id is not None:
            params["folder_id"] = folder_id
        raw = self.request(
            "GET",
            "/api/notes",
            params=params,
        )
        return [Note.model_validate(item) for item in _expect_list(raw, "/api/notes")]

    def get_note(self, note_id: str) -> Note:
        """Fetch a Zettelkasten note by ID."""
        raw = self.request("GET", f"/api/notes/{note_id}")
        return Note.model_validate(raw)

    # -- library bootstrap ------------------------------------------------
    def create_library(self, path: str) -> LibraryCreateResponse:
        """Create a fresh ``.fichero`` package and initialize its tables.

        The library-create endpoint does NOT require an
        ``X-Fichero-Library-Path`` header — the path goes in the body —
        so this works before any library exists.
        """
        raw = self.request("POST", "/api/library", json={"path": path})
        return LibraryCreateResponse.model_validate(raw)

    def create_library_snapshot(
        self,
        path: str,
        *,
        reason: str = "",
        initiator: str = "user",
    ) -> LibrarySnapshot:
        """Create a database/vector snapshot for a library package."""
        raw = self.request(
            "POST",
            "/api/storage/snapshots",
            params={
                "library_path": path,
                "reason": reason,
                "initiator": initiator,
            },
        )
        return LibrarySnapshot.model_validate(raw)

    def list_library_snapshots(
        self,
        *,
        library_name: str | None = None,
        include_expired: bool = False,
    ) -> dict[str, Any]:
        """List library snapshots from the backend."""
        return self.request(
            "GET",
            "/api/storage/snapshots",
            params={
                "library_name": library_name,
                "include_expired": include_expired,
            },
        )

    def restore_library_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """Restore a database/vector snapshot into its library package."""
        return self.request("POST", f"/api/storage/snapshots/{snapshot_id}/restore")

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
        # Extract items from envelope format
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        return [Document.model_validate(d) for d in _expect_list(items, "/api/documents")]

    def get_document(self, doc_id: str) -> Document:
        return Document.model_validate(
            self.request("GET", f"/api/documents/{doc_id}")
        )

    def document_inspector(self, doc_id: str) -> DocumentInspectorResponse:
        """Aggregate view of a document's entities, claims, and artifacts."""
        return DocumentInspectorResponse.model_validate(
            self.request("GET", f"/api/documents/{doc_id}/inspector")
        )

    def document_knowledge_graph(
        self, doc_id: str, *, include_children: bool = False
    ) -> DocumentKnowledgeGraphResponse:
        """Canonical KG grouping for a document — deduped, merge-resolved (#1068)."""
        return DocumentKnowledgeGraphResponse.model_validate(
            self.request(
                "GET",
                f"/api/documents/{doc_id}/knowledge-graph",
                params={"include_children": include_children},
            )
        )

    EXPORT_FORMATS = (
        "parquet",
        "jsonl",
        "markdown-folder",
        "word",
        "excel",
        "eleventy-site",
    )

    def export_library(self, export_format: str, output_path: str) -> Any:
        """Run a server-side library export (#4471).

        Thin wrapper over ``POST /api/export/{format}`` — the ONE export
        implementation (the server's ``iter_export_records()`` stream); the
        CLI adds no second path. All formats take ``output_path``.
        """
        if export_format not in self.EXPORT_FORMATS:
            raise FicheroError(
                f"Unknown export format {export_format!r}; supported: "
                + ", ".join(self.EXPORT_FORMATS)
            )
        return self.request(
            "POST",
            f"/api/export/{export_format}",
            json={"output_path": output_path},
        )

    def import_file(self, path: str | Path, parent_id: str | None = None) -> Document:
        """Upload a single file to the library (multipart/form-data)."""
        file_path = Path(path).expanduser()
        with file_path.open("rb") as handle:
            raw = self.request(
                "POST",
                "/api/documents/import",
                params={"parent_id": parent_id},
                files={"file": (file_path.name, handle)},
            )
            return Document.model_validate(raw)

    # -- workflows ---------------------------------------------------------
    def list_workflows(self) -> list[Workflow]:
        raw = self.request("GET", "/api/workflows")
        # Extract items from envelope format
        items = raw.get("items", raw) if isinstance(raw, dict) else raw
        return [Workflow.model_validate(w) for w in _expect_list(items, "/api/workflows")]

    def run_workflow(
        self,
        workflow_id: str,
        inputs: dict[str, Any] | None = None,
        *,
        force_new: bool = False,
        skip_cache: bool = False,
    ) -> ExecuteAcceptedResponse:
        return ExecuteAcceptedResponse.model_validate(
            self.request(
                "POST",
                "/api/workflow-execution/execute",
                json={
                    "workflow_id": workflow_id,
                    "inputs": inputs or {},
                    "force_new": force_new,
                    "skip_cache": skip_cache,
                },
            )
        )

    def split_chapters(self, doc_id: str) -> ExecuteAcceptedResponse:
        """Run the built-in Split Chapters workflow on ``doc_id``."""
        workflows = self.list_workflows()
        workflow_id: str | None = None
        for workflow in workflows:
            if (workflow.name or "").lower() == SPLIT_CHAPTERS_WORKFLOW_NAME.lower():
                workflow_id = workflow.id
                break
        if workflow_id is None:
            raise FicheroError(
                "No workflow named 'Split Chapters'. Reinstall default workflows "
                "or run `fichero workflow list` to inspect available workflows."
            )
        return self.run_workflow(workflow_id, {"selected_doc_ids": [doc_id]})

    def translate_document(
        self,
        doc_id: str,
        *,
        target_lang: str = "en",
        source_lang: str = "auto",
    ) -> ExecuteAcceptedResponse:
        """Run the built-in Translate workflow on ``doc_id``."""
        workflows = self.list_workflows()
        workflow_id: str | None = None
        for workflow in workflows:
            if (workflow.name or "").lower() == TRANSLATE_WORKFLOW_NAME.lower():
                workflow_id = workflow.id
                break
        if workflow_id is None:
            raise FicheroError(
                "No workflow named 'Translate'. Reinstall default workflows "
                "or run `fichero workflow list` to inspect available workflows."
            )
        return self.run_workflow(
            workflow_id,
            {
                "selected_doc_ids": [doc_id],
                "source_lang": source_lang,
                "target_lang": target_lang,
                # Back-compat aliases for older translate nodes.
                "source_language": source_lang,
                "target_language": target_lang,
            },
        )

    def execution_status(self, thread_id: str) -> ExecutionStatusResponse:
        return ExecutionStatusResponse.model_validate(
            self.request(
                "GET", f"/api/workflow-execution/threads/{thread_id}/status"
            )
        )

    def compare_models(
        self,
        *,
        prompt: str,
        models: list[dict[str, Any]],
        system_prompt: str | None = None,
        timeout_seconds: int = 120,
    ) -> ComparisonResultResponse:
        return ComparisonResultResponse.model_validate(
            self.request(
                "POST",
                "/api/model-comparison/compare",
                json={
                    "prompt": prompt,
                    "models": models,
                    "system_prompt": system_prompt,
                    "timeout_seconds": timeout_seconds,
                },
            )
        )

    def compare_vision(
        self,
        *,
        images: list[str],
        models: list[dict[str, Any]],
        prompt: str = "Describe this image in detail",
        detail: str = "auto",
        timeout_seconds: int = 120,
    ) -> ComparisonResultResponse:
        return ComparisonResultResponse.model_validate(
            self.request(
                "POST",
                "/api/model-comparison/compare-vision",
                json={
                    "images": images,
                    "prompt": prompt,
                    "models": models,
                    "detail": detail,
                    "timeout_seconds": timeout_seconds,
                },
            )
        )

    def compare_tool(
        self,
        *,
        tool_name: str,
        inputs: dict[str, Any],
        models: list[dict[str, Any]],
        tool_config: dict[str, Any] | None = None,
        timeout_seconds: int = 120,
    ) -> ComparisonResultResponse:
        return ComparisonResultResponse.model_validate(
            self.request(
                "POST",
                "/api/model-comparison/compare-tool",
                json={
                    "tool_name": tool_name,
                    "inputs": inputs,
                    "models": models,
                    "tool_config": tool_config,
                    "timeout_seconds": timeout_seconds,
                },
            )
        )

    def compare_workflow(
        self,
        *,
        workflow_id: str,
        doc_id: str,
        models: list[dict[str, Any]],
        inputs: dict[str, Any] | None = None,
        timeout_seconds: int = 300,
    ) -> ComparisonResultResponse:
        return ComparisonResultResponse.model_validate(
            self.request(
                "POST",
                "/api/model-comparison/compare-workflow",
                json={
                    "workflow_id": workflow_id,
                    "doc_id": doc_id,
                    "models": models,
                    "inputs": inputs or {},
                    "timeout_seconds": timeout_seconds,
                },
            )
        )

    # -- artifacts ---------------------------------------------------------
    def get_artifact(self, artifact_id: str) -> Artifact:
        """Fetch a single artifact by ID.

        Backed by ``GET /api/artifacts/{artifact_id}`` (see
        ``fichero/api/routes/artifacts.py::get_artifact``). The route returns
        the same shape as items in the document-scoped list, so we validate
        into the existing ``Artifact`` model — same drift-loud contract as
        ``list_artifacts``.
        """
        return Artifact.model_validate(
            self.request("GET", f"/api/artifacts/{artifact_id}")
        )

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
        return [
            Artifact.model_validate(a)
            for a in _expect_list(raw, path)
        ]

    # -- knowledge graph ---------------------------------------------------
    def list_entities(
        self,
        *,
        query: str | None = None,
        entity_type: str | None = None,
        limit: int = 50,
    ) -> list[KnowledgeEntity]:
        raw = self.request(
            "GET",
            "/api/entities",
            params={"q": query, "entity_type": entity_type, "limit": limit},
        )
        return [
            KnowledgeEntity.model_validate(e)
            for e in _expect_list(raw, "/api/entities")
        ]

    def create_entity(
        self,
        canonical_name: str,
        entity_type: str = "other",
        *,
        description: str | None = None,
        aliases: list[str] | None = None,
    ) -> KnowledgeEntity:
        return KnowledgeEntity.model_validate(
            self.request("POST", "/api/entities", json={
                "canonical_name": canonical_name,
                "entity_type": entity_type,
                "description": description,
                "aliases": aliases or [],
            })
        )

    def create_claim(
        self,
        text: str,
        *,
        source_document_id: str | None = None,
        entity_ids: list[str] | None = None,
        predicate_verb: str | None = None,
        subject_canonical: str | None = None,
        object_phrase: str | None = None,
        confidence: float = 1.0,
    ) -> KnowledgeClaim:
        raw = self.request("POST", "/api/claims", json={
            "text": text,
            "source_document_id": source_document_id,
            "entity_ids": entity_ids or [],
            "predicate_verb": predicate_verb,
            "subject_canonical": subject_canonical,
            "object_phrase": object_phrase,
            "confidence": confidence,
            "created_by": "human",
        })
        return KnowledgeClaim.model_validate(raw)

    def list_claims(
        self,
        *,
        query: str | None = None,
        source_document_id: str | None = None,
        entity_id: str | None = None,
        claim_type: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[KnowledgeClaim]:
        raw = self.request(
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
        return [
            KnowledgeClaim.model_validate(c)
            for c in _expect_list(raw, "/api/claims")
        ]

    def citations_at_doc(self, doc_id: str) -> list[KnowledgeEntity]:
        """Citation entities mentioned by this doc or its page children.

        There is no dedicated backend citation-inspector endpoint yet; this
        mirrors the SwiftUI inspector path by reading document-scoped claims
        and resolving citation-typed entity IDs through ``GET /api/entities``.
        """
        claims = self.claims_at_doc(doc_id)
        seen: set[str] = set()
        citations: list[KnowledgeEntity] = []
        for claim in claims:
            for entity_id in claim.entity_ids or []:
                if entity_id in seen:
                    continue
                seen.add(entity_id)
                try:
                    entity = self.get_entity(entity_id)
                except Exception:
                    continue
                entity_type = (
                    entity.entity_type.value
                    if hasattr(entity.entity_type, "value")
                    else str(entity.entity_type)
                )
                if entity_type == "citation":
                    citations.append(entity)
        citations.sort(key=lambda entity: entity.canonical_name.lower())
        return citations

    # -- scoped KG exploration (#1125) ---------------------------------
    # These compose existing endpoints (list_claims, list_documents,
    # entity_documents) to answer "all entities at this scope" and
    # "all claims at this scope mentioning entity X" without new
    # backend routes. Folder-scope recursively walks the doc tree.

    def entities_at_doc(
        self, doc_id: str, *, entity_type: str | None = None,
    ) -> list[KnowledgeEntity]:
        """All entities mentioned by any claim sourced from this doc
        (or any of its page children). For a page doc this is just
        that page's entities; for a multi-page PDF this is the union
        across all pages.

        Resolves entities through the claim's entity_ids[] union so
        secondary mentions (#1119) are included, not just claim
        subjects.
        """
        # First the direct claims on this doc.
        direct = self.list_claims(source_document_id=doc_id, limit=1000)
        # Then claims on each child doc (pages of a PDF).
        children = self.list_documents(parent_id=doc_id, limit=1000)
        all_claims = list(direct)
        for child in children:
            all_claims.extend(
                self.list_claims(source_document_id=child.id, limit=1000)
            )
        # Collect unique entity_ids from every claim's entity_ids[].
        seen: set[str] = set()
        for c in all_claims:
            for eid in c.entity_ids or []:
                seen.add(eid)
        if not seen:
            return []
        # Resolve to KnowledgeEntity objects.
        results: list[KnowledgeEntity] = []
        for eid in seen:
            try:
                ent = self.get_entity(eid)
            except Exception:
                continue
            if entity_type and (
                (ent.entity_type.value if hasattr(ent.entity_type, "value") else str(ent.entity_type))
                != entity_type
            ):
                continue
            results.append(ent)
        results.sort(key=lambda e: e.canonical_name.lower())
        return results

    def entities_at_folder(
        self, folder_id: str, *,
        recursive: bool = True,
        entity_type: str | None = None,
    ) -> list[KnowledgeEntity]:
        """Entities mentioned anywhere under a folder. Recursive by
        default — walks every doc descendant.
        """
        doc_ids = self._collect_descendant_doc_ids(
            folder_id, recursive=recursive,
        )
        seen: set[str] = set()
        for did in doc_ids:
            for c in self.list_claims(source_document_id=did, limit=1000):
                for eid in c.entity_ids or []:
                    seen.add(eid)
        results: list[KnowledgeEntity] = []
        for eid in seen:
            try:
                ent = self.get_entity(eid)
            except Exception:
                continue
            if entity_type and (
                (ent.entity_type.value if hasattr(ent.entity_type, "value") else str(ent.entity_type))
                != entity_type
            ):
                continue
            results.append(ent)
        results.sort(key=lambda e: e.canonical_name.lower())
        return results

    def claims_at_doc(
        self, doc_id: str, *, entity_id: str | None = None,
    ) -> list[KnowledgeClaim]:
        """Claims sourced from this doc OR any of its page children,
        optionally filtered to those mentioning a specific entity.
        """
        direct = self.list_claims(
            source_document_id=doc_id, entity_id=entity_id, limit=1000,
        )
        children = self.list_documents(parent_id=doc_id, limit=1000)
        all_claims = list(direct)
        for child in children:
            all_claims.extend(self.list_claims(
                source_document_id=child.id, entity_id=entity_id, limit=1000,
            ))
        return all_claims

    def claims_at_folder(
        self, folder_id: str, *,
        entity_id: str | None = None,
        recursive: bool = True,
    ) -> list[KnowledgeClaim]:
        """Claims sourced from anywhere under a folder. Optionally
        filtered to those mentioning a specific entity."""
        doc_ids = self._collect_descendant_doc_ids(
            folder_id, recursive=recursive,
        )
        results: list[KnowledgeClaim] = []
        for did in doc_ids:
            results.extend(self.list_claims(
                source_document_id=did, entity_id=entity_id, limit=1000,
            ))
        return results

    def entity_context(self, entity_id: str) -> dict[str, Any]:
        """Cheap summary of where this entity appears.

        Returns counts of distinct pages / docs / folders the entity
        is mentioned in, plus the total claim count. Drives the
        ``fichero entity context <id>`` CLI command — "Pedro Pérez
        appears in: 12 pages across 3 docs in 1 folder, with 47
        claims."
        """
        docs = self.entity_documents(entity_id)
        # Page vs. doc distinguished by doc_type. Folder ancestors
        # gathered from the doc.parent_id chain.
        page_ids: set[str] = set()
        doc_ids: set[str] = set()
        folder_ids: set[str] = set()
        claim_total = 0
        for link in docs:
            full = self.get_document(link.document_id)
            doc_type_val = (
                full.doc_type.value
                if hasattr(full.doc_type, "value")
                else str(full.doc_type)
            )
            if doc_type_val == "page":
                page_ids.add(full.id)
                # Parent is the doc that contains the page.
                if full.parent_id:
                    doc_ids.add(full.parent_id)
            else:
                doc_ids.add(full.id)
            # Walk up to find the folder.
            parent_id = full.parent_id
            while parent_id:
                try:
                    parent = self.get_document(parent_id)
                except Exception:
                    break
                parent_type = (
                    parent.doc_type.value
                    if hasattr(parent.doc_type, "value")
                    else str(parent.doc_type)
                )
                if parent_type == "folder":
                    folder_ids.add(parent.id)
                    break
                parent_id = parent.parent_id
            claim_total += getattr(link, "claim_count", 0) or 0
        return {
            "entity_id": entity_id,
            "page_count": len(page_ids),
            "doc_count": len(doc_ids),
            "folder_count": len(folder_ids),
            "claim_count": claim_total,
        }

    def _collect_descendant_doc_ids(
        self, root_id: str, *, recursive: bool = True,
    ) -> list[str]:
        """Walk the doc tree under ``root_id`` and return every
        descendant's id (excluding the root itself).

        Non-recursive returns only direct children. Recursive walks
        the whole subtree breadth-first. Used by the scoped query
        helpers; left private because callers should prefer the
        public entities_at_/claims_at_ wrappers.
        """
        out: list[str] = []
        frontier: list[str] = [root_id]
        while frontier:
            current = frontier.pop(0)
            children = self.list_documents(parent_id=current, limit=1000)
            for child in children:
                out.append(child.id)
                if recursive:
                    frontier.append(child.id)
        return out

    def kg_search(self, query: str, *, limit: int = 50) -> KGSearchResponse:
        return KGSearchResponse.model_validate(
            self.request(
                "GET", "/api/kg/search", params={"q": query, "limit": limit}
            )
        )

    def kg_rebuild(self, *, vectors: bool = True, triples: bool = True) -> RebuildResponse:
        raw = self.request(
            "POST", "/api/kg/rebuild",
            json={"vectors": vectors, "triples": triples},
        )
        return RebuildResponse.model_validate(raw)

    def kg_reset(self) -> KGResetResponse:
        raw = self.request("POST", "/api/kg/reset")
        return KGResetResponse.model_validate(raw)

    def import_document(self, path: Path, parent_id: str | None = None) -> Document:
        with open(path, "rb") as fh:
            files = {"file": (path.name, fh, "application/octet-stream")}
            params = {}
            if parent_id:
                params["parent_id"] = parent_id
            raw = self.request("POST", "/api/documents/import", files=files, params=params)
            return Document.model_validate(raw)

    def entity_neighborhood(
        self,
        entity_id: str,
        *,
        hops: int = 1,
        limit: int = 50,
        rank: str = "edge_weight",
    ) -> NeighborhoodResponse:
        raw = self.request(
            "GET",
            f"/api/kg/graph/neighborhood/{entity_id}",
            params={"hops": hops, "limit": limit, "rank": rank},
        )
        return NeighborhoodResponse.model_validate(raw)

    # -- search ------------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        limit: int = 10,
        search_type: str = "hybrid",
        min_score: float = 0.3,
        include: list[str] | None = None,
        doc_id: str | None = None,
        folder_id: str | None = None,
    ) -> SearchResponse:
        body: dict = {
            "query": query,
            "limit": limit,
            "search_type": search_type,
            "min_score": min_score,
        }
        if include is not None:
            body["include"] = include
        filters: dict = {}
        if doc_id:
            filters["document_id"] = doc_id
        if folder_id:
            filters["folder_id"] = folder_id
        if filters:
            body["filters"] = filters
        raw = self.request(
            "POST",
            "/api/search",
            json=body,
        )
        return SearchResponse.model_validate(raw)

    # -- activity ----------------------------------------------------------
    def recent_activity(self, *, limit: int = 50) -> list[ActivityResponse]:
        raw = self.request("GET", "/api/activity/recent", params={"limit": limit})
        return [
            ActivityResponse.model_validate(a)
            for a in _expect_list(raw, "/api/activity/recent")
        ]

    def list_activities(
        self,
        *,
        thread_id: str | None = None,
        types: str | None = None,
        limit: int = 100,
    ) -> list[ActivityResponse]:
        """Query the durable activity log.

        Used by ``workflow run --wait`` because the checkpoint-based status
        endpoint reports ``completed`` whenever there are no pending writes —
        which is also true between nodes mid-run (see
        MEMORY: workflow_checkpoint_races_activity, #1088). The activity log,
        in contrast, only emits ``workflow_completed`` / ``workflow_failed`` /
        ``workflow_cancelled`` once the executor itself has finished.
        """
        raw = self.request(
            "GET",
            "/api/activity",
            params={"thread_id": thread_id, "types": types, "limit": limit},
        )
        return [
            ActivityResponse.model_validate(a)
            for a in _expect_list(raw, "/api/activity")
        ]

    # -- documents (extended) -----------------------------------------------
    def delete_document(self, doc_id: str) -> None:
        """Delete a document and cascade-delete its KG rows."""
        self.request("DELETE", f"/api/documents/{doc_id}")

    def update_document(self, doc_id: str, **fields: Any) -> Document:
        """PATCH a document's editable fields (name, parent_id, folder_path, …)."""
        return Document.model_validate(
            self.request("PUT", f"/api/documents/{doc_id}", json=fields)
        )

    # -- artifacts (extended) ----------------------------------------------
    def update_artifact(
        self,
        artifact_id: str,
        *,
        content: str | None = None,
        reviewed: bool | None = None,
    ) -> ArtifactResponse:
        """PATCH an artifact's content and/or reviewed flag."""
        body: dict[str, Any] = {}
        if content is not None:
            body["content"] = content
        if reviewed is not None:
            body["reviewed"] = reviewed
        return ArtifactResponse.model_validate(
            self.request("PUT", f"/api/artifacts/{artifact_id}", json=body)
        )

    def delete_artifact(self, artifact_id: str) -> None:
        """Delete an artifact (204 No Content)."""
        self.request("DELETE", f"/api/artifacts/{artifact_id}")

    # -- claims (extended) -------------------------------------------------
    def get_claim(self, claim_id: str) -> KnowledgeClaim:
        """Fetch a single knowledge claim by ID."""
        return KnowledgeClaim.model_validate(
            self.request("GET", f"/api/claims/{claim_id}")
        )

    def update_claim(self, claim_id: str, **fields: Any) -> KnowledgeClaim:
        """PATCH a claim's editable fields (text, curation_state, confidence, …)."""
        return KnowledgeClaim.model_validate(
            self.request("PATCH", f"/api/claims/{claim_id}", json=fields)
        )

    def delete_claim(self, claim_id: str) -> None:
        """Delete a knowledge claim (204 No Content)."""
        self.request("DELETE", f"/api/claims/{claim_id}")

    def review_claim(
        self, claim_id: str, *, status: str
    ) -> KnowledgeClaim:
        """Set the curation_state on a claim (approved / rejected / unreviewed)."""
        return KnowledgeClaim.model_validate(
            self.request(
                "PATCH",
                f"/api/claims/{claim_id}",
                json={"curation_state": status},
            )
        )

    # -- hermeneutics -----------------------------------------------------
    def create_interpretation(
        self,
        *,
        framework_id: str,
        interpretation_text: str,
        act: str,
        claim_id: str | None = None,
        document_id: str | None = None,
        passage_text: str | None = None,
        predicate: str | None = None,
        confidence: float = 0.5,
    ) -> Interpretation:
        return Interpretation.model_validate(
            self.request(
                "POST",
                "/api/hermeneutics/interpretations",
                json={
                    "framework_id": framework_id,
                    "claim_id": claim_id,
                    "document_id": document_id,
                    "passage_text": passage_text,
                    "interpretation_text": interpretation_text,
                    "act": act,
                    "predicate": predicate,
                    "confidence": confidence,
                },
            )
        )

    def list_interpretations(
        self,
        *,
        framework_id: str | None = None,
        claim_id: str | None = None,
        act: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Interpretation]:
        raw = self.request(
            "GET",
            "/api/hermeneutics/interpretations",
            params={
                "framework_id": framework_id,
                "claim_id": claim_id,
                "act": act,
                "limit": limit,
                "offset": offset,
            },
        )
        return [
            Interpretation.model_validate(i)
            for i in _expect_list(raw, "/api/hermeneutics/interpretations")
        ]

    def get_interpretation(self, interpretation_id: str) -> Interpretation:
        return Interpretation.model_validate(
            self.request("GET", f"/api/hermeneutics/interpretations/{interpretation_id}")
        )

    def update_interpretation(self, interpretation_id: str, **fields: Any) -> Interpretation:
        return Interpretation.model_validate(
            self.request(
                "PATCH",
                f"/api/hermeneutics/interpretations/{interpretation_id}",
                json=fields,
            )
        )

    # -- entities (extended) -----------------------------------------------
    def get_entity(self, entity_id: str) -> KnowledgeEntity:
        """Fetch a single knowledge entity by ID."""
        return KnowledgeEntity.model_validate(
            self.request("GET", f"/api/entities/{entity_id}")
        )

    def update_entity(self, entity_id: str, **fields: Any) -> KnowledgeEntity:
        """PATCH an entity's editable fields (canonical_name, aliases, …)."""
        return KnowledgeEntity.model_validate(
            self.request("PATCH", f"/api/entities/{entity_id}", json=fields)
        )

    def delete_entity(self, entity_id: str) -> None:
        """Delete a knowledge entity (204 No Content)."""
        self.request("DELETE", f"/api/entities/{entity_id}")

    def merge_entities(
        self,
        absorbing_id: str,
        absorbed_ids: list[str],
        *,
        merged_aliases: list[str] | None = None,
        merged_description: str | None = None,
    ) -> EntityAuditResponse:
        """Merge one or more entities into an absorbing entity, with audit."""
        return EntityAuditResponse.model_validate(
            self.request(
                "POST",
                "/api/kg/entity-curation/merge",
                json={
                    "absorbing_entity_id": absorbing_id,
                    "absorbed_entity_ids": absorbed_ids,
                    "merged_aliases": merged_aliases or [],
                    "merged_description": merged_description,
                },
            )
        )

    def split_entity(
        self,
        primary_id: str,
        split_off_ids: list[str],
        *,
        aliases_to_move: list[str] | None = None,
    ) -> EntityAuditResponse:
        """Split off sub-entities from a primary entity, with audit."""
        return EntityAuditResponse.model_validate(
            self.request(
                "POST",
                "/api/kg/entity-curation/split",
                json={
                    "primary_entity_id": primary_id,
                    "split_off_entity_ids": split_off_ids,
                    "aliases_to_move": aliases_to_move or [],
                },
            )
        )

    def top_entities(self, *, limit: int = 30) -> list[TopEntityRow]:
        """Top-N entities by claim count across the whole library."""
        raw = self.request(
            "GET", "/api/entities/top", params={"limit": limit}
        )
        return [
            TopEntityRow.model_validate(r)
            for r in _expect_list(raw, "/api/entities/top")
        ]

    def entity_documents(self, entity_id: str) -> list[EntityDocumentLink]:
        """Documents that mention this entity via knowledge claims."""
        path = f"/api/entities/{entity_id}/documents"
        raw = self.request("GET", path)
        return [
            EntityDocumentLink.model_validate(r)
            for r in _expect_list(raw, path)
        ]

    def entity_co_occurrence(self, entity_id: str) -> list[EntityCoOccurrence]:
        """Entities that co-occur with this entity in at least one claim."""
        path = f"/api/entities/{entity_id}/co-occurrence"
        raw = self.request("GET", path)
        return [
            EntityCoOccurrence.model_validate(r)
            for r in _expect_list(raw, path)
        ]

    def get_entity_claims(self, entity_id: str, *, limit: int = 200) -> ClaimListResponse:
        """Get all claims associated with an entity."""
        params = {"limit": limit, "entity_id": entity_id}
        raw = self.request("GET", "/api/claims", params=params)
        return ClaimListResponse.model_validate(raw)

    def get_entity_drill_down(self, entity_id: str) -> EntityDrillDownResponse:
        """Get the full drill-down information for an entity."""
        raw = self.request("GET", f"/api/entities/{entity_id}/drill-down")
        return EntityDrillDownResponse.model_validate(raw)

    def entity_inspector(self, entity_id: str) -> EntityInspectorResponse:
        """Full inspector data for an entity: claims, documents, annotations, notes."""
        return EntityInspectorResponse.model_validate(
            self.request("GET", f"/api/entities/{entity_id}/inspector")
        )

    def resolve_entity(self, name: str) -> EntityResolutionResponse:
        """Resolve a name/alias to a canonical entity."""
        return EntityResolutionResponse.model_validate(
            self.request("GET", f"/api/entities/resolve/{name}")
        )

    # -- audit -------------------------------------------------------------
    def list_audits(self, *, limit: int = 50) -> list[EntityAuditResponse]:
        """List entity merge/split audit records."""
        raw = self.request(
            "GET", "/api/kg/entity-curation/audit", params={"limit": limit}
        )
        return [
            EntityAuditResponse.model_validate(r)
            for r in _expect_list(raw, "/api/kg/entity-curation/audit")
        ]

    def undo_audit(self, audit_id: str) -> EntityAuditResponse:
        """Reverse a merge or split operation by audit ID."""
        return EntityAuditResponse.model_validate(
            self.request(
                "POST", f"/api/kg/entity-curation/audit/{audit_id}/undo"
            )
        )

    # -- workflow threads (extended) ----------------------------------------
    def list_threads(self, *, limit: int = 100) -> ThreadListResponse:
        """List recent workflow execution threads."""
        return ThreadListResponse.model_validate(
            self.request(
                "GET",
                "/api/workflow-execution/threads",
                params={"limit": limit},
            )
        )

    def delete_thread(self, thread_id: str) -> ThreadDeletedResponse:
        """Delete a workflow execution thread and its checkpoints (#1116)."""
        return ThreadDeletedResponse.model_validate(
            self.request(
                "DELETE",
                f"/api/workflow-execution/threads/{thread_id}",
            )
        )

    def cancel_workflow(self, thread_id: str) -> CancelResponse:
        """Cancel a running workflow (#1127).

        Returns the CancelResponse shape: ``thread_id``, ``status``
        (cancel_requested/not_running/already_terminal),
        ``partial_results_preserved`` (always True for now),
        ``message``. The endpoint is idempotent — calling it twice on
        an already-cancelled thread returns ``status=already_terminal``
        rather than raising.
        """
        raw = self.request(
            "POST",
            f"/api/workflow-execution/threads/{thread_id}/cancel",
        )
        return CancelResponse.model_validate(raw or {})

    # -- settings ----------------------------------------------------------
    def get_settings(self) -> AIDefaults:
        """Fetch the current AI-defaults settings block."""
        raw = self.request("GET", "/api/settings/ai-defaults")
        return AIDefaults.model_validate(raw or {})

    def set_settings(self, **fields: Any) -> AIDefaults:
        """PUT the full AI-defaults block (fetches current values, merges, saves)."""
        current = self.get_settings()
        current_dict = current.model_dump() if hasattr(current, 'model_dump') else current
        merged = {**current_dict, **fields}
        self.request("PUT", "/api/settings/ai-defaults", json=merged)
        return self.get_settings()

    # -- providers ---------------------------------------------------------
    def list_providers(self) -> list[ProviderResponse]:
        """List user-configured LLM providers."""
        raw = self.request("GET", "/api/providers")
        return [
            ProviderResponse.model_validate(p)
            for p in _expect_list(raw, "/api/providers")
        ]

    def get_provider(self, provider_id: str) -> ProviderResponse:
        """Fetch a single configured provider by ID."""
        return ProviderResponse.model_validate(
            self.request("GET", f"/api/providers/{provider_id}")
        )

    def add_provider(
        self,
        provider_type: str,
        *,
        name: str | None = None,
        api_base: str | None = None,
        api_key: str | None = None,
    ) -> ProviderResponse:
        """Create or upsert a provider configuration."""
        return ProviderResponse.model_validate(
            self.request(
                "POST",
                "/api/providers",
                json={
                    "provider_type": provider_type,
                    "name": name,
                    "api_base": api_base,
                    "api_key": api_key,
                },
            )
        )

    def delete_provider(self, provider_id: str) -> None:
        """Delete a provider configuration."""
        self.request("DELETE", f"/api/providers/{provider_id}")

    def list_known_libraries(self) -> LibraryRegistryResponse:
        """List all known libraries in the registry.

        Returns libraries sorted by last_accessed descending (most recent first).
        """
        raw = self.request("GET", "/api/registry")
        return LibraryRegistryResponse.model_validate(raw)

    def list_unicode_library_collisions(self):
        """Report Unicode-equivalent library path collisions."""
        from fichero_server.models import UnicodeLibraryCollisionResponse

        raw = self.request("GET", "/api/registry/unicode-collisions")
        return UnicodeLibraryCollisionResponse.model_validate(raw)

    def add_known_library(self, path: str, name: str | None = None) -> KnownLibrary:
        """Register an existing library path in the registry.

        Validates that the path exists and contains a .fichero package.

        Args:
            path: Absolute path to the .fichero package
            name: Optional display name (defaults to package basename)

        Returns:
            The KnownLibrary record that was created or updated.
        """
        params = {"path": path}
        if name is not None:
            params["name"] = name
        raw = self.request("POST", "/api/registry/add", params=params)
        return KnownLibrary.model_validate(raw)

    def remove_known_library(self, path: str) -> dict:
        """Remove a library from the known libraries registry.

        Args:
            path: Absolute path to the .fichero package

        Returns:
            Response dict with status confirmation.
        """
        from urllib.parse import quote

        encoded_path = quote(path, safe="")
        return self.request("DELETE", f"/api/registry/{encoded_path}")

    def update_library_access(self, path: str) -> KnownLibrary:
        """Mark a library as accessed (update last_accessed timestamp).

        Args:
            path: Absolute path to the .fichero package

        Returns:
            The updated KnownLibrary record.
        """
        raw = self.request("POST", "/api/registry/update-access", params={"path": path})
        return KnownLibrary.model_validate(raw)
