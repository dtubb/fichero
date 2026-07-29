"""Unit tests for the Fichero MCP server.

The MCP server is a thin wrapper over ``FicheroClient``; these tests cover tool
registration and argument passthrough with the HTTP layer mocked
(``httpx.MockTransport``) — no live backend required.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from urllib.parse import quote

import httpx
import pytest

from fichero_mcp import server as mcp_server
from fichero_cli import FicheroClient, FicheroError

# Every tool the server is expected to expose. Each wraps one FicheroClient
# call — the read/drive surface only.
EXPECTED_TOOLS = {
    # core read / drive
    "fichero_health",
    "fichero_import",
    "fichero_docs_list",
    "fichero_docs_get",
    "fichero_create_note",
    "fichero_list_notes",
    "fichero_get_note",
    "fichero_workflow_list",
    "fichero_workflow_run",
    "fichero_workflow_status",
    "fichero_artifacts",
    "fichero_kg_entities",
    "fichero_kg_claims",
    "fichero_kg_search",
    "fichero_kg_neighborhood",
    "fichero_document_inspector",
    "fichero_document_kg",
    "fichero_artifact_get",
    "fichero_search",
    "fichero_activity",
    "fichero_workspace_add_source",
    "fichero_workspace_remove_source",
    "fichero_workspace_surface_claim",
    "fichero_workspace_add_note",
    "fichero_reveal_location",
}


def _list_tools() -> list:
    return asyncio.run(mcp_server.mcp.list_tools())


@contextmanager
def _mock_client(monkeypatch, *, handler=None, status=200, body=None):
    """Patch mcp_server._client to return a MockTransport-backed FicheroClient.

    Yields the list of seen httpx.Request objects.
    """
    seen: list[httpx.Request] = []

    def _default_handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"ok": True} if body is None else body)

    transport = httpx.MockTransport(handler or _default_handler)

    def _build() -> FicheroClient:
        return FicheroClient(
            base_url="http://test",
            library_path="/tmp/Lib.fichero",
            token="test-token",
            transport=transport,
        )

    monkeypatch.setattr(mcp_server, "_client", _build)
    yield seen


# -- tool registration -----------------------------------------------------
def test_all_expected_tools_are_registered():
    names = {tool.name for tool in _list_tools()}
    assert names == EXPECTED_TOOLS


def test_no_stale_tools_remain():
    """Surfaces with no FicheroClient backing stay gone (hermeneutics, research,
    chains). Mind Palace is back (#1269) because the client now wraps its routes."""
    names = {tool.name for tool in _list_tools()}
    for stale in (
        "fichero_hm_list_frameworks",
        "fichero_rs_list_agents",
        "fichero_run_chain",
    ):
        assert stale not in names


def test_tools_have_descriptions_and_schemas():
    for tool in _list_tools():
        assert tool.description, f"{tool.name} has no description"
        assert tool.inputSchema is not None


# -- argument passthrough --------------------------------------------------
def test_health_hits_health_endpoint(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_health()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/health"


def test_workflow_list_hits_workflows_endpoint(monkeypatch):
    # list_workflows() returns list[Workflow]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_workflow_list()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/workflows"


def test_docs_get_builds_path(monkeypatch):
    # get_document() returns Document; mock serves a dict that validates.
    with _mock_client(monkeypatch, body={"id": "doc-42", "name": "doc-42"}) as seen:
        mcp_server.fichero_docs_get("doc-42")
    assert seen[0].url.path == "/api/documents/doc-42"


def test_docs_list_passes_filters(monkeypatch):
    # list_documents() returns list[Document]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_docs_list(doc_type="pdf", limit=5)
    params = dict(seen[0].url.params)
    assert params == {"doc_type": "pdf", "limit": "5", "offset": "0"}


def test_workflow_run_builds_execute_body(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
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

    with _mock_client(monkeypatch, handler=handler):
        mcp_server.fichero_workflow_run("wf-1", "doc-9", skip_cache=True)
    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"files": ["doc-9"]},
        "force_new": False,
        "skip_cache": True,
    }


def test_workflow_status_builds_path(monkeypatch):
    status_body = {
        "thread_id": "thread-7",
        "workflow_id": "wf-1",
        "workflow_name": "Test",
        "status": "completed",
    }
    with _mock_client(monkeypatch, body=status_body) as seen:
        mcp_server.fichero_workflow_status("thread-7")
    assert seen[0].url.path == "/api/workflow-execution/threads/thread-7/status"


def test_artifacts_builds_path_and_params(monkeypatch):
    # /api/artifacts/document/{id} returns the standard {items, count} envelope.
    with _mock_client(monkeypatch, body={"items": [], "count": 0}) as seen:
        mcp_server.fichero_artifacts("doc-3", artifact_type="catalogue", limit=10)
    assert seen[0].url.path == "/api/artifacts/document/doc-3"
    assert dict(seen[0].url.params)["artifact_type"] == "catalogue"


def test_kg_search_passes_query_param(monkeypatch):
    body = {"query": "migration", "hits": [], "counts": {}}
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_kg_search("migration", limit=10)
    assert dict(seen[0].url.params) == {"q": "migration", "limit": "10"}


def test_search_builds_post_body(monkeypatch):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={
            "query": "ledgers", "results": [], "count": 0,
            "total_results": 0, "search_type": "hybrid",
            "execution_time_ms": 0.0,
        })

    with _mock_client(monkeypatch, handler=handler):
        mcp_server.fichero_search("ledgers", limit=3)
    assert seen[0]["query"] == "ledgers"
    assert seen[0]["limit"] == 3
    assert seen[0]["search_type"] == "hybrid"
    assert seen[0]["min_score"] == 0.3


def test_import_sends_multipart(monkeypatch, tmp_path):
    sample = tmp_path / "note.txt"
    sample.write_text("hello")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={
            "name": "note.txt",
            "expected_thumbnail_path": "",
            "expected_display_path": "",
        })

    with _mock_client(monkeypatch, handler=handler) as seen:
        mcp_server.fichero_import(str(sample), parent_id="folder-1")
    assert seen[0].url.path == "/api/documents/import"
    assert dict(seen[0].url.params) == {"parent_id": "folder-1"}
    assert "multipart/form-data" in seen[0].headers["content-type"]


def test_auth_and_library_headers_are_set(monkeypatch):
    # recent_activity returns list[ActivityResponse]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_activity()
    assert seen[0].headers["authorization"] == "Bearer test-token"
    assert seen[0].headers["x-fichero-library-path"] == quote(
        "/tmp/Lib.fichero", safe="/"
    )


def test_reveal_location_hits_typed_resolver(monkeypatch):
    with _mock_client(monkeypatch) as seen:
        mcp_server.fichero_reveal_location("page-1", page=2, bbox=[0, 0, 1, 1])
    assert seen[0].url.path == "/api/locations/resolve"
    assert json.loads(seen[0].content) == {
        "documentId": "page-1", "page": 2, "bbox": [0, 0, 1, 1], "surface": "both"
    }


@pytest.mark.parametrize(
    ("tool", "params", "action", "action_params"),
    [
        (
            mcp_server.fichero_workspace_add_source,
            ("workspace-1", "doc-1"),
            "workspace.add_source",
            {"workspace_id": "workspace-1", "document_id": "doc-1"},
        ),
        (
            mcp_server.fichero_workspace_remove_source,
            ("workspace-1", "doc-1"),
            "workspace.remove_source",
            {"workspace_id": "workspace-1", "document_id": "doc-1"},
        ),
        (
            mcp_server.fichero_workspace_surface_claim,
            ("workspace-1", "claim-1"),
            "workspace.surface_claim",
            {"workspace_id": "workspace-1", "claim_id": "claim-1"},
        ),
        (
            mcp_server.fichero_workspace_add_note,
            ("workspace-1", "Remember this"),
            "workspace.add_note",
            {"workspace_id": "workspace-1", "text": "Remember this"},
        ),
    ],
)
def test_workspace_tools_invoke_audited_action(
    monkeypatch, tool, params, action, action_params
):
    with _mock_client(monkeypatch) as seen:
        monkeypatch.setattr(mcp_server, "_agent_client", mcp_server._client)
        tool(*params)
    assert seen[0].url.path == "/api/actions/invoke"
    assert json.loads(seen[0].content) == {"name": action, "params": action_params}


def test_create_note_hits_core_notes_endpoint(monkeypatch):
    note_body = {
        "id": "note-z1",
        "title": "Field note",
        "body": "Remember this",
        "kind": "zettel",
        "tags": ["field"],
        "linked_note_ids": [],
        "linked_entity_ids": ["entity-1"],
        "linked_claim_ids": [],
        "linked_document_ids": ["doc-1"],
    }
    with _mock_client(monkeypatch, body=note_body) as seen:
        note = mcp_server.fichero_create_note(
            "Remember this",
            title="Field note",
            tags=["field"],
            linked_entity_ids=["entity-1"],
            linked_document_ids=["doc-1"],
        )
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/notes"
    assert json.loads(seen[0].content) == {
        "title": "Field note",
        "body": "Remember this",
        "kind": "zettel",
        "tags": ["field"],
        "linked_note_ids": [],
        "linked_entity_ids": ["entity-1"],
        "linked_claim_ids": [],
        "linked_document_ids": ["doc-1"],
        "address": None,
        "parent_address": None,
    }
    assert note.id == "note-z1"
    assert note.body == "Remember this"


def test_list_and_get_notes_are_typed(monkeypatch):
    note_body = {
        "id": "note-z2",
        "title": "Reading note",
        "body": "A linked note",
        "kind": "reference",
        "tags": ["reading"],
        "linked_note_ids": [],
        "linked_entity_ids": [],
        "linked_claim_ids": ["claim-1"],
        "linked_document_ids": [],
    }
    with _mock_client(monkeypatch, body={"items": [note_body], "count": 1}) as seen:
        notes = mcp_server.fichero_list_notes(kind="reference", linked_claim_id="claim-1")
    assert seen[0].url.path == "/api/notes"
    assert dict(seen[0].url.params) == {"kind": "reference", "linked_claim_id": "claim-1"}
    assert notes[0].title == "Reading note"

    with _mock_client(monkeypatch, body=note_body) as seen:
        note = mcp_server.fichero_get_note("note-z2")
    assert seen[0].url.path == "/api/notes/note-z2"
    assert note.id == "note-z2"


# A handler that records each httpx.Request (so URL/path/body can be asserted)
# and replies with a caller-supplied body. Needed because _mock_client only
# records requests for its *default* handler, not a custom one.
def _recording(reqs: list, body) -> "callable":
    def handler(request: httpx.Request) -> httpx.Response:
        reqs.append(request)
        return httpx.Response(200, json=body)

    return handler


# -- core read tools -------------------------------------------------------
def test_kg_neighborhood_builds_path_and_params(monkeypatch):
    # entity_neighborhood() validates into NeighborhoodResponse.
    body = {
        "focus_entity_id": "e1",
        "focus_canonical_name": "Entity One",
        "neighbors": [],
        "edges": [],
        "truncated": False,
    }
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_kg_neighborhood("e1", hops=2, limit=10)
    assert seen[0].url.path == "/api/kg/graph/neighborhood/e1"
    params = dict(seen[0].url.params)
    assert params["hops"] == "2"
    assert params["limit"] == "10"


def test_document_kg_builds_path(monkeypatch):
    # document_knowledge_graph() validates into DocumentKnowledgeGraphResponse.
    body = {
        "document_id": "doc-1",
        "include_children": True,
        "groups": [],
        "claims": [],
        "entity_count": 0,
        "claim_count": 0,
        "catalogue": [],
    }
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_document_kg("doc-1", include_children=True)
    assert seen[0].url.path == "/api/documents/doc-1/knowledge-graph"
    assert dict(seen[0].url.params)["include_children"] == "true"


def test_artifact_get_builds_path(monkeypatch):
    # get_artifact() validates into Artifact (needs document_id + artifact_type).
    body = {"document_id": "doc-1", "artifact_type": "transcription"}
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_artifact_get("art-9")
    assert seen[0].url.path == "/api/artifacts/art-9"


# -- error propagation -----------------------------------------------------
def test_backend_error_propagates_not_swallowed(monkeypatch):
    """A non-2xx response must raise, not return a silent {"error": ...} dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with _mock_client(monkeypatch, handler=handler):
        with pytest.raises(FicheroError, match="500"):
            mcp_server.fichero_health()


def test_connect_failure_propagates(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with _mock_client(monkeypatch, handler=handler):
        with pytest.raises(FicheroError, match="Is the engine running"):
            mcp_server.fichero_health()


# -- config wiring ---------------------------------------------------------
def test_client_uses_config_base_url(monkeypatch):
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", "http://configured:9000")
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", "/cfg/Lib.fichero")
    client = mcp_server._client()
    try:
        assert client.base_url == "http://configured:9000"
        assert client.library_path == "/cfg/Lib.fichero"
    finally:
        client.close()


def test_main_populates_config_from_args(monkeypatch):
    # This test only checks arg -> _CONFIG wiring. main() also runs a no-token
    # startup probe; a test asserting that warning must patch _TOKEN_PATH and
    # FICHERO_API_KEY (see test_mcp_warns_without_token in test_integration_security).
    captured: dict = {}
    monkeypatch.setattr(
        mcp_server.mcp, "run", lambda *a, **k: captured.setdefault("ran", True)
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "fichero-mcp",
            "--api-url",
            "http://cli:1234",
            "--library-path",
            "/cli/L.fichero",
        ],
    )
    monkeypatch.setitem(mcp_server._CONFIG, "base_url", None)
    monkeypatch.setitem(mcp_server._CONFIG, "library_path", None)
    mcp_server.main()
    assert captured["ran"] is True
    assert mcp_server._CONFIG["base_url"] == "http://cli:1234"
    assert mcp_server._CONFIG["library_path"] == "/cli/L.fichero"
