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

from fichero import mcp_server
from fichero.cli import FicheroClient, FicheroError

# Every tool the server is expected to expose. Each wraps one FicheroClient
# call — the read/drive surface plus the Mind Palace arrangement tools (#1269).
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
    # mind palace — arrangement (#1269)
    "fichero_mp_list_rooms",
    "fichero_mp_get_room",
    "fichero_mp_create_room",
    "fichero_mp_scene_summary",
    "fichero_mp_create_note",
    "fichero_mp_list_notes",
    "fichero_mp_get_note",
    "fichero_mp_update_note",
    "fichero_mp_delete_note",
    "fichero_mp_list_nodes",
    "fichero_mp_get_node",
    "fichero_mp_place_node",
    "fichero_mp_move_node",
    "fichero_mp_remove_node",
    "fichero_mp_list_connections",
    "fichero_mp_create_connection",
    "fichero_mp_remove_connection",
    "fichero_mp_list_stacks",
    "fichero_mp_get_stack",
    "fichero_mp_create_stack",
    "fichero_mp_add_to_stack",
    "fichero_mp_remove_from_stack",
    "fichero_mp_get_viewport",
    "fichero_mp_save_viewport",
    "fichero_mp_focus",
    "fichero_mp_suggest_arrangement",
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


def test_mp_create_note_hits_note_endpoint(monkeypatch):
    note_body = {
        "id": "note-1",
        "content": "A note",
        "room_id": "room-1",
        "note_type": "user",
        "author_id": "user",
        "status": "draft",
        "linked_claim_ids": [],
        "linked_source_ids": [],
        "linked_entity_ids": [],
        "metadata": {},
    }
    with _mock_client(monkeypatch, body=note_body) as seen:
        note = mcp_server.fichero_mp_create_note(
            "A note",
            room_id="room-1",
            linked_entity_ids=["entity-1"],
        )
    assert seen[0].url.path == "/api/mind-palace/notes"
    assert json.loads(seen[0].content) == {
        "room_id": "room-1",
        "content": "A note",
        "note_type": "user",
        "author_id": "user",
        "linked_claim_ids": [],
        "linked_source_ids": [],
        "linked_entity_ids": ["entity-1"],
        "metadata": {},
    }
    assert note.id == "note-1"


def test_mp_list_notes_passes_filters(monkeypatch):
    note_body = {
        "id": "note-2",
        "content": "A note",
        "room_id": "room-1",
        "note_type": "ai_workspace",
        "author_id": "ai",
        "status": "draft",
        "linked_claim_ids": [],
        "linked_source_ids": [],
        "linked_entity_ids": [],
        "metadata": {},
    }
    with _mock_client(monkeypatch, body={"items": [note_body], "count": 1}) as seen:
        notes = mcp_server.fichero_mp_list_notes(
            room_id="room-1",
            note_type="ai_workspace",
            author_id="ai",
        )
    assert dict(seen[0].url.params) == {
        "room_id": "room-1",
        "note_type": "ai_workspace",
        "author_id": "ai",
    }
    assert len(notes) == 1
    assert notes[0].id == "note-2"


def test_mp_get_update_delete_note_hit_expected_paths(monkeypatch):
    note_body = {
        "id": "note-3",
        "content": "Old content",
        "room_id": "room-1",
        "note_type": "user",
        "author_id": "user",
        "status": "draft",
        "linked_claim_ids": [],
        "linked_source_ids": [],
        "linked_entity_ids": [],
        "metadata": {},
    }

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "PATCH":
            return httpx.Response(200, json={**note_body, "content": "Updated"})
        if request.method == "DELETE":
            return httpx.Response(200, json={"status": "deleted"})
        return httpx.Response(200, json=note_body)

    with _mock_client(monkeypatch, handler=handler):
        got = mcp_server.fichero_mp_get_note("note-3")
        updated = mcp_server.fichero_mp_update_note(
            "note-3", content="Updated", status="surfaced"
        )
        deleted = mcp_server.fichero_mp_delete_note("note-3")

    assert [req.method for req in seen] == ["GET", "PATCH", "DELETE"]
    assert seen[0].url.path == "/api/mind-palace/notes/note-3"
    assert json.loads(seen[1].content) == {
        "content": "Updated",
        "status": "surfaced",
    }
    assert seen[2].url.path == "/api/mind-palace/notes/note-3"
    assert got.id == "note-3"
    assert updated.content == "Updated"
    assert deleted.status == "deleted"


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


# -- mind palace tools (#1269) ---------------------------------------------
def test_mp_list_rooms_hits_rooms_endpoint(monkeypatch):
    with _mock_client(monkeypatch, body={"items": [], "count": 0}) as seen:
        mcp_server.fichero_mp_list_rooms(room_type="research")
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/mind-palace/rooms"
    assert dict(seen[0].url.params)["room_type"] == "research"


def test_mp_create_room_builds_post_body(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=_recording(reqs, {"id": "room-1"})):
        mcp_server.fichero_mp_create_room("Ideas", room_type="synthesis")
    assert reqs[0].url.path == "/api/mind-palace/rooms"
    sent = json.loads(reqs[0].content)
    assert sent["name"] == "Ideas"
    assert sent["room_type"] == "synthesis"
    assert sent["owner_id"] == "user"


def test_mp_place_node_builds_post_body(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=_recording(reqs, {"id": "node-1"})):
        mcp_server.fichero_mp_place_node(
            "room-1", "claim", source_id="claim-9", position_x=1.5, position_z=-2.0
        )
    assert reqs[0].url.path == "/api/mind-palace/nodes"
    sent = json.loads(reqs[0].content)
    assert sent["room_id"] == "room-1"
    assert sent["node_type"] == "claim"
    assert sent["source_id"] == "claim-9"
    assert sent["position_x"] == 1.5
    assert sent["position_z"] == -2.0
    assert sent["created_by"] == "agent"


def test_mp_move_node_patches_with_position(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=_recording(reqs, {"id": "node-1"})):
        mcp_server.fichero_mp_move_node("node-1", 3.0, 4.0, 0.0, scale=2.0)
    assert reqs[0].method == "PATCH"
    assert reqs[0].url.path == "/api/mind-palace/nodes/node-1"
    assert json.loads(reqs[0].content) == {
        "position_x": 3.0,
        "position_y": 4.0,
        "position_z": 0.0,
        "scale": 2.0,
    }


def test_mp_move_node_omits_scale_when_none(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=_recording(reqs, {"id": "node-1"})):
        mcp_server.fichero_mp_move_node("node-1", 1.0, 2.0, 3.0)
    assert "scale" not in json.loads(reqs[0].content)


def test_mp_add_to_stack_builds_nested_path(monkeypatch):
    with _mock_client(monkeypatch, body={"id": "stack-1", "node_ids": ["n1"]}) as seen:
        mcp_server.fichero_mp_add_to_stack("stack-1", "n1")
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/mind-palace/stacks/stack-1/nodes/n1"


def test_mp_focus_uses_query_params(monkeypatch):
    body = {"room_id": "room-1", "user_id": "user", "focus_node_id": "n5"}
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_mp_focus("room-1", "n5")
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/mind-palace/rooms/room-1/focus"
    params = dict(seen[0].url.params)
    assert params["node_id"] == "n5"
    assert params["user_id"] == "user"


def test_mp_suggest_arrangement_builds_body(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(monkeypatch, handler=_recording(reqs, {"items": [], "count": 0})):
        mcp_server.fichero_mp_suggest_arrangement(
            "room-1", ["n1", "n2"], arrangement_type="chronological"
        )
    assert reqs[0].url.path == "/api/mind-palace/rooms/room-1/suggest-arrangement"
    assert json.loads(reqs[0].content) == {
        "node_ids": ["n1", "n2"],
        "arrangement_type": "chronological",
    }


def test_mp_save_viewport_builds_path_and_body(monkeypatch):
    reqs: list[httpx.Request] = []
    with _mock_client(
        monkeypatch, handler=_recording(reqs, {"room_id": "room-1", "user_id": "user"})
    ):
        mcp_server.fichero_mp_save_viewport(
            "room-1", camera_z=5.0, bookmark_name="overview"
        )
    assert reqs[0].url.path == "/api/mind-palace/rooms/room-1/viewport/user"
    sent = json.loads(reqs[0].content)
    assert sent["camera_z"] == 5.0
    assert sent["bookmark_name"] == "overview"


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
