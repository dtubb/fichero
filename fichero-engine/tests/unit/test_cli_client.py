"""Unit tests for fichero.cli.client.FicheroClient.

The HTTP layer is mocked with httpx.MockTransport — no live backend required.
"""

from __future__ import annotations

import json
from urllib.parse import quote

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
    assert seen[0].headers["x-fichero-library-path"] == quote(
        "/tmp/My.fichero", safe="/"
    )


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


def test_compare_workflow_builds_request_body():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "prompt": "[Workflow: wf-1]",
                "models_compared": ["openai/gpt-4o"],
                "results": [],
                "fastest_model": None,
                "cheapest_model": None,
                "total_cost_usd": 0.0,
                "total_latency_ms": 0.0,
                "comparison_id": "cmp-1",
                "timestamp": "2026-05-15T00:00:00",
            },
        )

    _client(handler).compare_workflow(
        workflow_id="wf-1",
        doc_id="doc-9",
        models=[{"provider": "openai", "model": "gpt-4o"}],
    )
    assert seen[0] == {
        "workflow_id": "wf-1",
        "doc_id": "doc-9",
        "models": [{"provider": "openai", "model": "gpt-4o"}],
        "inputs": {},
        "timeout_seconds": 300,
    }


def test_compare_vision_builds_request_body():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "prompt": "Describe",
                "models_compared": ["openai/gpt-4o"],
                "results": [],
                "fastest_model": None,
                "cheapest_model": None,
                "total_cost_usd": 0.0,
                "total_latency_ms": 0.0,
                "comparison_id": "cmp-2",
                "timestamp": "2026-05-15T00:00:00",
            },
        )

    _client(handler).compare_vision(
        images=["data:image/png;base64,AAAA"],
        models=[{"provider": "openai", "model": "gpt-4o"}],
        prompt="Describe",
        detail="high",
    )
    assert seen[0] == {
        "images": ["data:image/png;base64,AAAA"],
        "prompt": "Describe",
        "models": [{"provider": "openai", "model": "gpt-4o"}],
        "detail": "high",
        "timeout_seconds": 120,
    }


def test_translate_document_runs_translate_workflow():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/api/workflows":
            return httpx.Response(
                200,
                json=[{"id": "wf-t", "name": "Translate"}],
            )
        if request.method == "POST" and request.url.path == "/api/workflow-execution/execute":
            payload = json.loads(request.content)
            assert payload["workflow_id"] == "wf-t"
            assert payload["inputs"]["selected_doc_ids"] == ["doc-7"]
            assert payload["inputs"]["target_lang"] == "en"
            assert payload["inputs"]["source_lang"] == "nl"
            return httpx.Response(
                202,
                json={
                    "thread_id": "t1",
                    "workflow_id": "wf-t",
                    "workflow_name": "Translate",
                    "status": "accepted",
                    "stream_url": "/api/workflow-execution/stream/t1",
                },
            )
        return httpx.Response(404, text="not found")

    response = _client(handler).translate_document("doc-7", target_lang="en", source_lang="nl")
    assert response.workflow_name == "Translate"


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


def test_create_note_returns_typed_note_and_posts_payload():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "id": "note-z1",
                "title": "Field note",
                "body": "Remember this",
                "kind": "zettel",
                "tags": ["field"],
                "linked_note_ids": [],
                "linked_entity_ids": [],
                "linked_claim_ids": [],
                "linked_document_ids": ["doc-1"],
            },
        )

    note = _client(handler).create_note(
        title="Field note",
        body="Remember this",
        tags=["field"],
        linked_document_ids=["doc-1"],
    )
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/notes"
    assert json.loads(seen[0].content)["linked_document_ids"] == ["doc-1"]
    assert note.id == "note-z1"
    assert note.body == "Remember this"


def test_list_notes_unwraps_envelope_and_returns_typed_notes():
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"kind": "reference", "q": "archive"}
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": "note-z2",
                        "title": "Reading note",
                        "body": "Archive note",
                        "kind": "reference",
                        "tags": [],
                        "linked_note_ids": [],
                        "linked_entity_ids": [],
                        "linked_claim_ids": [],
                        "linked_document_ids": [],
                    }
                ],
                "count": 1,
            },
        )

    notes = _client(handler).list_notes(kind="reference", query="archive")
    assert len(notes) == 1
    assert notes[0].title == "Reading note"


def test_get_note_returns_typed_note():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/notes/note-z3"
        return httpx.Response(
            200,
            json={
                "id": "note-z3",
                "title": None,
                "body": "Plain note",
                "kind": "zettel",
                "tags": [],
                "linked_note_ids": [],
                "linked_entity_ids": [],
                "linked_claim_ids": [],
                "linked_document_ids": [],
            },
        )

    note = _client(handler).get_note("note-z3")
    assert note.id == "note-z3"
    assert note.body == "Plain note"


def test_empty_response_body_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    assert _client(handler).health() is None


# -- token / config discovery ---------------------------------------------
def test_token_read_from_env(monkeypatch):
    monkeypatch.setenv("FICHERO_SESSION_TOKEN", "session-token")
    monkeypatch.setenv("FICHERO_API_KEY", "bootstrap-token")
    assert client_module._read_token() == "session-token"


def test_token_read_from_bootstrap_env(monkeypatch):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("FICHERO_API_KEY", "env-token")
    assert client_module._read_token() == "env-token"


def test_token_missing_file_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / "absent")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")
    assert client_module._read_token() is None


def test_token_read_from_cli_session_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text('{"session_token": "file-token"}', encoding="utf-8")
    session_path.chmod(0o600)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / ".api-key")
    assert client_module._read_token() == "file-token"


def test_loopback_base_url_prefers_bootstrap_token_over_cli_session(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text('{"session_token": "remote-session-token"}', encoding="utf-8")
    session_path.chmod(0o600)
    bootstrap_path = tmp_path / ".api-key"
    bootstrap_path.write_text("bootstrap-token", encoding="utf-8")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", bootstrap_path)

    assert client_module._read_token(base_url="http://127.0.0.1:8765") == "bootstrap-token"


def test_remote_base_url_ignores_bootstrap_token_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text('{"session_token": "remote-session-token"}', encoding="utf-8")
    session_path.chmod(0o600)
    bootstrap_path = tmp_path / ".api-key"
    bootstrap_path.write_text("bootstrap-token", encoding="utf-8")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", bootstrap_path)

    assert client_module._read_token(base_url="https://pairing.example.com") == "remote-session-token"


def test_remote_base_url_without_session_does_not_fall_back_to_bootstrap_file(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "missing-session.json")
    bootstrap_path = tmp_path / ".api-key"
    bootstrap_path.write_text("bootstrap-token", encoding="utf-8")
    monkeypatch.setattr(client_module, "_TOKEN_PATH", bootstrap_path)

    assert client_module._read_token(base_url="https://pairing.example.com") is None


def test_token_read_from_selected_cli_user_session(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text(
        json.dumps(
            {
                "current_user": "alice",
                "sessions": {
                    "alice": {"session_token": "alice-token", "user": {"username": "alice"}},
                    "bob": {"session_token": "bob-token", "user": {"username": "bob"}},
                },
            }
        ),
        encoding="utf-8",
    )
    session_path.chmod(0o600)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / ".api-key")
    assert client_module._read_token(as_user="bob") == "bob-token"


def test_token_ignores_bad_cli_session_file_and_falls_back_to_bootstrap(
    monkeypatch, tmp_path
):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text("{not json", encoding="utf-8")
    session_path.chmod(0o600)
    bootstrap_path = tmp_path / ".api-key"
    bootstrap_path.write_text("bootstrap-token", encoding="utf-8")
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", bootstrap_path)
    assert client_module._read_token() == "bootstrap-token"


def test_token_ignores_cli_session_file_without_0600(monkeypatch, tmp_path):
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    session_path = tmp_path / "cli-session.json"
    session_path.write_text('{"session_token": "file-token"}', encoding="utf-8")
    session_path.chmod(0o644)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", session_path)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", tmp_path / ".api-key")
    assert client_module._read_token() is None


def test_request_picks_up_token_after_startup_gap(monkeypatch, tmp_path):
    """A client constructed before the token file exists should recover once
    the engine writes the shared secret, rather than leaking a startup 403."""

    token_path = tmp_path / ".api-key"
    monkeypatch.delenv("FICHERO_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    monkeypatch.setattr(client_module, "_TOKEN_PATH", token_path)
    monkeypatch.setattr(client_module, "_CLI_SESSION_PATH", tmp_path / "cli-session.json")

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        auth = request.headers.get("authorization")
        if auth != "Bearer fresh-token":
            return httpx.Response(403, text="missing or invalid Authorization header")
        return httpx.Response(200, json=[])

    client = FicheroClient(
        base_url="http://test",
        library_path="/tmp/Lib.fichero",
        transport=httpx.MockTransport(handler),
    )
    try:
        token_path.write_text("fresh-token", encoding="utf-8")
        docs = client.list_documents()
    finally:
        client.close()

    assert docs == []
    assert len(seen) == 1
    assert seen[0].headers["authorization"] == "Bearer fresh-token"


def test_request_picks_up_library_path_after_startup_gap(monkeypatch):
    """A client created before the active library path is available should
    attach it once the window sets FICHERO_LIBRARY_PATH."""

    monkeypatch.delenv("FICHERO_API_KEY", raising=False)
    monkeypatch.delenv("FICHERO_LIBRARY_PATH", raising=False)

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        library_path = request.headers.get("x-fichero-library-path")
        if library_path != quote("/tmp/Lib.fichero", safe="/"):
            return httpx.Response(403, text="missing or invalid X-Fichero-Library-Path")
        return httpx.Response(200, json=[])

    client = FicheroClient(
        base_url="http://test",
        transport=httpx.MockTransport(handler),
    )
    try:
        monkeypatch.setenv("FICHERO_LIBRARY_PATH", "/tmp/Lib.fichero")
        docs = client.list_documents()
    finally:
        client.close()

    assert docs == []
    assert len(seen) == 1
    assert seen[0].headers["x-fichero-library-path"] == quote(
        "/tmp/Lib.fichero", safe="/"
    )


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
