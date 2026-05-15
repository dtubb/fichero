"""Unit tests for fichero.cli.client.FicheroClient.

The HTTP layer is mocked with httpx.MockTransport — no live backend required.
"""

from __future__ import annotations

import httpx
import pytest

from fichero.cli import DEFAULT_BASE_URL, FicheroClient, FicheroError
from fichero.cli import client as client_module


def _client(handler, **kwargs) -> FicheroClient:
    """Build a FicheroClient wired to a MockTransport handler."""
    kwargs.setdefault("token", "test-token")
    kwargs.setdefault("library_path", "/tmp/Lib.fichero")
    return FicheroClient(
        base_url="http://test", transport=httpx.MockTransport(handler), **kwargs
    )


def _capture(response: object = None):
    """Return (handler, requests) where requests accumulates seen requests.

    ``response`` overrides what the mock returns. Default is a generic ``{"ok":
    True}`` — fine for tests of untyped methods that only check request
    construction. Tests that exercise typed methods (``list_documents``,
    ``list_workflows`` …) should pass ``response=[]`` (or a realistic shape)
    so Pydantic validation succeeds at the boundary.
    """
    if response is None:
        response = {"ok": True}
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response)

    return handler, seen


# -- headers ---------------------------------------------------------------
def test_auth_header_is_set():
    handler, seen = _capture()
    _client(handler).health()
    assert seen[0].headers["authorization"] == "Bearer test-token"


def test_library_path_header_is_set():
    handler, seen = _capture(response=[])
    _client(handler, library_path="/tmp/My.fichero").list_documents()
    assert seen[0].headers["x-fichero-library-path"] == "/tmp/My.fichero"


def test_empty_token_omits_auth_header():
    handler, seen = _capture()
    _client(handler, token="").health()
    assert "authorization" not in seen[0].headers


def test_missing_library_path_omits_header():
    handler, seen = _capture()
    _client(handler, library_path="").health()
    assert "x-fichero-library-path" not in seen[0].headers


# -- request construction --------------------------------------------------
def test_none_query_params_are_dropped():
    handler, seen = _capture(response=[])
    _client(handler).list_documents(limit=5)
    # Only the non-None filters survive: limit + the offset default.
    assert dict(seen[0].url.params) == {"limit": "5", "offset": "0"}


def test_health_hits_health_endpoint():
    handler, seen = _capture()
    _client(handler).health()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/health"


def test_run_workflow_builds_execute_body():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json

        seen.append(json.loads(request.content))
        return httpx.Response(
            202,
            json={
                "thread_id": "t1",
                "workflow_id": "wf-1",
                "workflow_name": "Test",
                "status": "accepted",
                "stream_url": "/api/workflow-execution/stream/t1",
            },
        )

    _client(handler).run_workflow("wf-1", {"files": ["doc-9"]}, skip_cache=True)
    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"files": ["doc-9"]},
        "force_new": False,
        "skip_cache": True,
    }


def test_kg_search_passes_query_param():
    handler, seen = _capture(
        response={"query": "migration", "hits": [], "counts": {}}
    )
    _client(handler).kg_search("migration", limit=10)
    assert dict(seen[0].url.params) == {"q": "migration", "limit": "10"}


def test_import_file_sends_multipart(tmp_path):
    sample = tmp_path / "note.txt"
    sample.write_text("hello")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"id": "doc-1"})

    _client(handler).import_file(sample, parent_id="folder-1")
    assert seen[0].url.path == "/api/documents/import"
    assert dict(seen[0].url.params) == {"parent_id": "folder-1"}
    assert "multipart/form-data" in seen[0].headers["content-type"]
    assert b"note.txt" in seen[0].content


# -- responses & errors ----------------------------------------------------
def test_error_status_raises_ficheroerror():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="missing or invalid Authorization header")

    with pytest.raises(FicheroError, match="401") as excinfo:
        _client(handler).health()
    assert excinfo.value.status_code == 401


def test_error_404_carries_status_code():
    """404 from a polling endpoint needs to be distinguishable from 5xx errors."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="No checkpoint found")

    with pytest.raises(FicheroError) as excinfo:
        _client(handler).execution_status("thread-x")
    assert excinfo.value.status_code == 404


def test_connect_failure_raises_friendly_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(FicheroError, match="Is the engine running") as excinfo:
        _client(handler).health()
    # Transport-level failures have no status code.
    assert excinfo.value.status_code is None


def test_list_documents_loud_on_wrong_shape():
    """Typed methods must fail loudly when the backend returns a non-list —
    the whole point of the typing is to surface shape drift at the boundary,
    not let it slip through as "zero results" via a falsy-coercion shortcut.
    """
    handler, _ = _capture(response={"error": "library not found"})
    with pytest.raises(FicheroError, match="expected a list"):
        _client(handler).list_documents()


def test_list_documents_returns_typed_documents():
    """Validate the typing-at-the-boundary contract: list_documents returns
    list[Document], so callers see attribute access, and a wrong-shape response
    surfaces as a loud ValidationError rather than a deferred KeyError."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[
            {"id": "doc-1", "name": "Test PDF", "doc_type": "file"},
            {"id": "doc-2", "name": "Page 1", "doc_type": "page",
             "parent_id": "doc-1"},
        ])

    docs = _client(handler).list_documents()
    assert len(docs) == 2
    # Attribute access, not dict access — the typing is real.
    assert docs[0].id == "doc-1"
    assert docs[0].name == "Test PDF"
    assert docs[1].parent_id == "doc-1"


def test_document_inspector_hits_expected_path():
    seen: list[httpx.Request] = []

    inspector_payload = {
        "document_id": "doc-42",
        "document": None,
        "source_metadata": None,
        "claim_count": 0,
        "claims": [],
        "entities": [],
        "annotations": [],
        "notes": [],
        "citations_outbound": [],
        "citations_inbound": [],
        "interpretations": [],
        "projects": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=inspector_payload)

    result = _client(handler).document_inspector("doc-42")
    assert result.document_id == "doc-42"
    assert result.entities == []
    assert seen[0].url.path == "/api/documents/doc-42/inspector"


def test_empty_response_body_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert _client(handler).health() is None


# -- token / config discovery ---------------------------------------------
def test_token_read_from_env(monkeypatch):
    monkeypatch.setenv("FICHERO_API_KEY", "env-token")
    assert client_module._read_token() == "env-token"


def test_token_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / "absent")
    assert client_module._read_token() is None


def test_base_url_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("FICHERO_API_URL", raising=False)
    c = FicheroClient(token="x")
    assert c.base_url == DEFAULT_BASE_URL
    c.close()


def test_context_manager_closes(monkeypatch):
    handler, _ = _capture()
    with _client(handler) as c:
        c.health()
    assert c._client.is_closed
