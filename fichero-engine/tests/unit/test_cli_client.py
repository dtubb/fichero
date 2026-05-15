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


def _capture():
    """Return (handler, requests) where requests accumulates seen requests."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True})

    return handler, seen


# -- headers ---------------------------------------------------------------
def test_auth_header_is_set():
    handler, seen = _capture()
    _client(handler).health()
    assert seen[0].headers["authorization"] == "Bearer test-token"


def test_library_path_header_is_set():
    handler, seen = _capture()
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
    handler, seen = _capture()
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
        return httpx.Response(202, json={"thread_id": "t1"})

    _client(handler).run_workflow("wf-1", {"files": ["doc-9"]}, skip_cache=True)
    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"files": ["doc-9"]},
        "force_new": False,
        "skip_cache": True,
    }


def test_kg_search_passes_query_param():
    handler, seen = _capture()
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


def test_document_inspector_hits_expected_path():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"entities": [], "claims": []})

    result = _client(handler).document_inspector("doc-42")
    assert result == {"entities": [], "claims": []}
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
