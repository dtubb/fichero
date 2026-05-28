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
        return httpx.Response(200, json={
            "id": "doc-1",
            "name": "note.txt",
            "path": "/path/to/note.txt",
            "doc_type": "file",
            "description": "",
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-01T00:00:00",
        })

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
    """Typed methods must fail loudly when the backend returns a genuinely
    wrong shape — the whole point of the typing is to surface shape drift at
    the boundary, not let it slip through as "zero results" via a
    falsy-coercion shortcut.

    A dict WITHOUT an ``items`` list is not the standardized
    ``{items, count}`` envelope, so the CLI must raise rather than treat the
    error payload as iterable.
    """
    handler, _ = _capture(response={"error": "library not found"})
    with pytest.raises(FicheroError, match="envelope or a list"):
        _client(handler).list_documents()


def test_list_documents_unwraps_envelope():
    """The standardized ``{items, count}`` envelope is unwrapped to its
    items — callers see a list of typed Documents, not the envelope dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "items": [
                {"id": "doc-1", "name": "Test PDF", "doc_type": "file"},
                {"id": "doc-2", "name": "Page 1", "doc_type": "page",
                 "parent_id": "doc-1"},
            ],
            "count": 2,
        })

    docs = _client(handler).list_documents()
    assert len(docs) == 2
    assert docs[0].id == "doc-1"
    assert docs[1].parent_id == "doc-1"


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


# -- mind palace (spatial) -------------------------------------------------
# Verify the #1269 MCP-facing client methods construct the right
# path/method/body so an agent can drive a room.
def test_palace_scene_path():
    handler, seen = _capture()
    _client(handler).palace_scene("room-1")
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/mind-palace/rooms/room-1/scene"


def test_palace_place_node_posts_body():
    import json as _json

    handler, seen = _capture()
    _client(handler).palace_place_node(
        "room-1", "source", source_id="doc-9", label="Letter", position_x=1.0
    )
    req = seen[0]
    assert req.method == "POST"
    assert req.url.path == "/api/mind-palace/nodes"
    body = _json.loads(req.content)
    assert body["room_id"] == "room-1"
    assert body["node_type"] == "source"
    assert body["source_id"] == "doc-9"
    assert body["position_x"] == 1.0
    assert body["created_by"] == "ai"


def test_palace_move_node_patches():
    import json as _json

    handler, seen = _capture()
    _client(handler).palace_move_node(
        "node-1", position_x=2.0, position_y=3.0, scale=1.5
    )
    req = seen[0]
    assert req.method == "PATCH"
    assert req.url.path == "/api/mind-palace/nodes/node-1"
    body = _json.loads(req.content)
    assert body["position_x"] == 2.0
    assert body["scale"] == 1.5


def test_palace_connect_posts_body():
    import json as _json

    handler, seen = _capture()
    _client(handler).palace_connect("room-1", "n-a", "n-b")
    body = _json.loads(seen[0].content)
    assert seen[0].url.path == "/api/mind-palace/connections"
    assert body["source_node_id"] == "n-a"
    assert body["target_node_id"] == "n-b"
    assert body["connection_type"] == "semantic"


def test_palace_arrange_posts_node_ids():
    import json as _json

    handler, seen = _capture()
    _client(handler).palace_arrange("room-1", ["n-a", "n-b"], arrangement_type="thematic")
    assert seen[0].url.path == "/api/mind-palace/rooms/room-1/suggest-arrangement"
    body = _json.loads(seen[0].content)
    assert body["node_ids"] == ["n-a", "n-b"]
    assert body["arrangement_type"] == "thematic"


def test_palace_focus_uses_query_params():
    handler, seen = _capture()
    _client(handler).palace_focus("room-1", "node-7")
    assert seen[0].url.path == "/api/mind-palace/rooms/room-1/focus"
    assert seen[0].url.params["node_id"] == "node-7"
    assert seen[0].url.params["user_id"] == "user"
