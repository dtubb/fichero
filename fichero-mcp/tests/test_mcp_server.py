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
    "fichero_ingest_folder",
    "fichero_ingest_status",
    "fichero_docs_list",
    "fichero_docs_get",
    "fichero_create_note",
    "fichero_list_notes",
    "fichero_get_note",
    "fichero_workflow_list",
    "fichero_workflow_run",
    "fichero_workflow_status",
    "fichero_train_kraken",
    "fichero_train_vision_lora",
    "fichero_training_status",
    "fichero_training_cancel",
    "fichero_gather_reasons",
    "fichero_reasons_status",
    "fichero_reasons_cancel",
    "fichero_read_at_scale",
    "fichero_reading_status",
    "fichero_reading_resend_failed",
    "fichero_reading_cancel",
    "fichero_compare_readings",
    "fichero_artifacts",
    "fichero_kg_entities",
    "fichero_kg_claims",
    "fichero_kg_search",
    "fichero_kg_neighborhood",
    "fichero_document_inspector",
    "fichero_document_kg",
    "fichero_artifact_get",
    "fichero_page_export",
    # Both directions, not just out (`source.format.everywhere`: app, MCP and the
    # command line). An agent that can only export can read somebody else's work
    # out of the library and never bring any in.
    "fichero_page_import",
    "fichero_formats_list",
    "fichero_search",
    "fichero_activity",
    # Source-model slice 1/4/5 read-only segments seam (#4919/#4922/#4923;
    # this contract set had drifted behind fichero_segments's own addition,
    # caught while adding the other three for #4955 item C's MCP/CLI
    # parity).
    "fichero_segments",
    "fichero_segment",
    "fichero_segment_versions",
    "fichero_segment_reference",
    # The editor's verbs, for an agent (`source.editor.agent-parity`, #4941). Reads
    # alone made that behaviour false on the MCP half: an agent could look at a page
    # and change nothing, while the CLI half was true only because its surface is
    # generated from the contract.
    "fichero_segment_update",
    "fichero_segment_split",
    "fichero_segment_merge",
    "fichero_segment_delete",
    "fichero_segment_undelete",
    "fichero_segment_choose_reading",
    # Reading the text (#5139): without these an agent saw every shape on a page
    # and could read none of them.
    "fichero_segment_readings",
    "fichero_segments_naming_place",
    "fichero_place_as_of",
    "fichero_document_text",
    "fichero_segments_in_scope",
    "fichero_reading_orders",
    "fichero_reading_order_entries",
    # Library scoping + doc/workflow drive tools that were registered but had
    # gone missing from this contract set (S37762) — added here so the exact
    # set is truthful again.
    "fichero_list_libraries",
    "fichero_use_library",
    "fichero_document_move",
    "fichero_workflow_create",
    "fichero_workspace_add_source",
    "fichero_workspace_remove_source",
    "fichero_workspace_surface_claim",
    "fichero_workspace_add_note",
    "fichero_reveal_location",
    # Audited KG writes (#4469): these call /api/mcp/tools/knowledge/*, the
    # MutationLog-backed routes that record the request actor and previously
    # had zero callers.
    "fichero_kg_entity_upsert",
    "fichero_kg_claim_create",
    # AI providers & local model runtimes — same reach as the app's AI settings.
    "fichero_providers",
    "fichero_provider_catalog",
    "fichero_local_runtimes",
    "fichero_models_catalog",
    "fichero_model_download",
    "fichero_model_download_status",
    "fichero_model_download_cancel",
    "fichero_model_delete",
    "fichero_runtime_status",
    "fichero_runtime_provision",
    "fichero_local_models",
    "fichero_local_model_download",
    "fichero_kraken_status",
    "fichero_kraken_install",
    # HPC (Slurm) cluster connections — dry-run only on the backend.
    "fichero_hpc_clusters",
    "fichero_hpc_configure_cluster",
    "fichero_hpc_delete_cluster",
    "fichero_hpc_test_cluster",
    "fichero_hpc_dry_run_submit",
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
    # list_workflows() returns list[WorkflowResponse]; mock serves a list shape.
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_workflow_list()
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/workflows"


def _workflow_item(workflow_id: str, name: str, **overrides) -> dict:
    """One item as /api/workflows actually serves it."""
    item = {
        "id": workflow_id,
        "name": name,
        "description": "",
        "provider": "",
        "model": "",
        "format": "nodes",
        "nodes": [],
        "edges": [],
        "folder_path": "/",
        "sort_order": 0,
        "untested": False,
        "direct_runnable": True,
        "accepts_model_override": True,
        "requires_vision": False,
    }
    item.update(overrides)
    return item


def test_workflow_list_tells_the_agent_what_it_cannot_run(monkeypatch):
    """#3804: the engine refuses to run an internal component standalone. The
    list parsed items into the STORAGE model, which has no direct_runnable, so
    Pydantic dropped the refusal and an agent reading this tool saw only names
    — every one of which looked runnable. An agent cannot be expected to obey
    a rule it is never shown."""
    body = [
        _workflow_item("wf-parent", "Transcribe Spanish Script", requires_vision=True),
        _workflow_item("wf-child", "Spanish Script Passes", direct_runnable=False),
    ]
    with _mock_client(monkeypatch, body=body):
        workflows = mcp_server.fichero_workflow_list()

    assert len(workflows) == 2, "fixture must contain a runnable AND a component"
    # #4983-adjacent fix: `fichero_workflow_list` returns LEAN DICTS, not
    # model objects — deliberate since Aug 27 2026 (`e90907d0f`, "lean list
    # payloads"): the full node/edge dump was 450KB, the same reason
    # `fichero_docs_list` slims to dicts too (both tools are
    # JSON-serialisable summaries an agent reads, not typed objects). This
    # test predates that refactor (written for #3804, Aug 3) and was never
    # updated to the dict contract — the code is right, the test was stale.
    by_name = {w["name"]: w for w in workflows}
    assert by_name["Spanish Script Passes"]["direct_runnable"] is False
    assert by_name["Transcribe Spanish Script"]["direct_runnable"] is True
    assert by_name["Transcribe Spanish Script"]["requires_vision"] is True


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
    # `selected_doc_ids`, NOT `inputs: {"files": [...]}` (#4467). This
    # assertion previously pinned the BUG: the Files-source node, the CLI and
    # SwiftUI all read `selected_doc_ids`, nothing read `files`, so every MCP
    # workflow run resolved to zero documents and completed green. A test
    # asserting the shape the sender happened to send, rather than the shape
    # the receiver reads, cannot tell those apart. Duplicated copies of this
    # file are what let the stale assertion survive (#4480) — there is one now.
    assert seen[0] == {
        "workflow_id": "wf-1",
        "inputs": {"selected_doc_ids": ["doc-9"]},
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


def test_workflow_status_polls_the_summary_by_default(monkeypatch):
    """#5401: an agent polls this tool; the run's whole state was 526 KB, more than a tool result
    can hold. By default it must ask the engine for the summary, and the full state only on request."""
    status_body = {"thread_id": "t", "workflow_id": "w", "workflow_name": "T", "status": "running"}
    with _mock_client(monkeypatch, body=status_body) as seen:
        mcp_server.fichero_workflow_status("t")
        mcp_server.fichero_workflow_status("t", full_state=True)
    assert [r.url.params.get("view") for r in seen] == ["summary", "full"]


_COMPARE_BODY = {
    "measure": "agreement", "reference_label": "pass: DOCX", "hypothesis_label": "result: transcription",
    "definition": "edit distance / reference length",
    "scores": [{"policy": "layout-insensitive", "policy_description": "", "distance": 3,
                "reference_chars": 20, "hypothesis_chars": 21, "rate": 0.15}],
}


def test_compare_readings_is_on_the_default_surface(monkeypatch):
    """#5389 said the scorer was reachable 'from the API, CLI and MCP', but it was only on the
    `fichero_mcp.full` surface; the installed `fichero-mcp` serves this module, so an agent found
    no scorer at all. It must be here, and send the engine's own request shape."""
    import json

    with _mock_client(monkeypatch, body=_COMPARE_BODY) as seen:
        result = mcp_server.fichero_compare_readings(
            "page-1", reference_pass_id="pass-docx", hypothesis_artifact_id="art-gemini",
            policies=["layout-insensitive", "diplomatic"],
        )
    request = seen[0]
    assert request.method == "POST" and request.url.path == "/api/documents/page-1/readings/compare"
    assert json.loads(request.content) == {
        "reference": {"pass_id": "pass-docx"}, "hypothesis": {"artifact_id": "art-gemini"},
        "reference_checked_by": None, "policies": ["layout-insensitive", "diplomatic"],
    }
    assert result.measure == "agreement", "unchecked reference: agreement, never cer"


def test_compare_readings_refuses_an_ambiguous_side(monkeypatch):
    """WHY: a side naming both a pass and a result, or neither, has no single reading to score; the
    agent must hear that before a request is made, not get a number for the wrong reading."""
    with _mock_client(monkeypatch, body=_COMPARE_BODY) as seen:
        with pytest.raises(ValueError):
            mcp_server.fichero_compare_readings("p", reference_pass_id="a", reference_artifact_id="b",
                                                hypothesis_pass_id="c")
        with pytest.raises(ValueError):
            mcp_server.fichero_compare_readings("p", reference_pass_id="a")
    assert seen == []


def test_training_tools_send_the_engines_request(monkeypatch):
    """#5398: an agent can start, follow and stop a training job the one way the engine offers. The
    yes for the pages to leave is the agent's to pass on from the person, never a default."""
    import json

    with _mock_client(monkeypatch, body={"job_id": "j1"}) as seen:
        mcp_server.fichero_train_kraken(["folder-1"], "google/gemini-3-flash-preview", pages_may_leave=True,
                                        held_out_ids=["p4"], base="kraken-zenodo-21788410")
        mcp_server.fichero_training_status("j1")
        mcp_server.fichero_training_cancel("j1")
        mcp_server.fichero_train_vision_lora(["folder-1"], "google/gemini-3-flash-preview", pages_may_leave=True,
                                             language="Spanish")
    start, status, cancel, vision = seen
    assert (vision.method, vision.url.path) == ("POST", "/api/training/vision-lora")
    assert json.loads(vision.content)["base_repo"] == "Qwen/Qwen3-VL-8B-Instruct"
    assert json.loads(vision.content)["arm"] == "answer", "a reasons arm is chosen, never the default"
    assert (start.method, start.url.path) == ("POST", "/api/training/kraken")
    body = json.loads(start.content)
    assert body["pages_may_leave"] is True and body["held_out_ids"] == ["p4"] and body["timeout"] == "4h"
    assert (status.method, status.url.path) == ("GET", "/api/training/jobs/j1")
    assert (cancel.method, cancel.url.path) == ("POST", "/api/training/jobs/j1/cancel")


def test_reasons_tools_send_the_engines_request(monkeypatch):
    """#4642: an agent gathers a palaeographer's reasons the one way the engine offers."""
    import json

    with _mock_client(monkeypatch, body={"job_id": "g1"}) as seen:
        mcp_server.fichero_gather_reasons(["c01"], "fable-checked", "omlx", "Qwen3-VL-8B-Thinking",
                                          held_out_ids=["p9"])
        mcp_server.fichero_reasons_status("g1")
        mcp_server.fichero_reasons_cancel("g1")
    start, status, cancel = seen
    assert (start.method, start.url.path) == ("POST", "/api/training/reasons")
    body = json.loads(start.content)
    assert body["mode"] == "read" and body["checked"] == "fable-checked" and body["held_out_ids"] == ["p9"]
    assert (status.method, status.url.path) == ("GET", "/api/training/reasons/g1")
    assert (cancel.method, cancel.url.path) == ("POST", "/api/training/reasons/g1/cancel")


def test_reading_at_scale_tools_send_the_engines_request(monkeypatch):
    """#5398: an agent can start, follow, re-send and stop a reading run the one way the engine
    offers; the yes for the pages to leave is passed on from the person, never a default."""
    import json

    with _mock_client(monkeypatch, body={"job_id": "r1"}) as seen:
        mcp_server.fichero_read_at_scale(["eap-1"], "fichero-trained/sergio", pages_may_leave=True, reader="vlm")
        mcp_server.fichero_reading_status("r1")
        mcp_server.fichero_reading_resend_failed("r1")
        mcp_server.fichero_reading_cancel("r1")
    start, status, resend, cancel = seen
    assert (start.method, start.url.path) == ("POST", "/api/reading-at-scale")
    body = json.loads(start.content)
    assert body["pages_may_leave"] is True and body["reader"] == "vlm" and body["timeout"] == "2h"
    assert (status.method, status.url.path) == ("GET", "/api/reading-at-scale/jobs/r1")
    assert (resend.method, resend.url.path) == ("POST", "/api/reading-at-scale/jobs/r1/resend-failed")
    assert (cancel.method, cancel.url.path) == ("POST", "/api/reading-at-scale/jobs/r1/cancel")


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
        mcp_server.fichero_document_kg("doc-1", include_descendants=False)
        mcp_server.fichero_document_kg("doc-1")
    assert seen[0].url.path == "/api/documents/doc-1/knowledge-graph"
    # #5065: the flag is include_descendants, and recursion is the DEFAULT.
    assert dict(seen[0].url.params)["include_descendants"] == "false"
    assert dict(seen[1].url.params)["include_descendants"] == "true"
    assert "include_children" not in dict(seen[0].url.params)


def test_artifact_get_builds_path(monkeypatch):
    # get_artifact() validates into Artifact (needs document_id + artifact_type).
    body = {"document_id": "doc-1", "artifact_type": "transcription"}
    with _mock_client(monkeypatch, body=body) as seen:
        mcp_server.fichero_artifact_get("art-9")
    assert seen[0].url.path == "/api/artifacts/art-9"


def test_page_export_builds_the_route_and_returns_the_choices_and_losses(monkeypatch):
    body = {"format": "tei", "filename": "p.tei.xml", "content": "<TEI/>",
            "choices": {"order_name": "as-written"}, "losses": [{"what": "x", "count": 1, "why": "y"}]}
    with _mock_client(monkeypatch, body=body) as seen:
        out = mcp_server.fichero_page_export("d1", "tei", pass_id="p1", reading_kind="normalised")
    assert seen[0].url.path == "/api/documents/d1/export/tei"
    assert dict(seen[0].url.params) == {"pass_id": "p1", "reading_kind": "normalised"}
    assert out["losses"] and out["choices"], "the agent must be handed the losses, not just the file"


def test_page_import_posts_the_file_and_hands_back_what_landed(monkeypatch, tmp_path):
    """`source.format.everywhere`'s other direction. The agent is handed the RECOGNISED
    format and the repair count, not a success flag: a model told only that the import
    worked will describe a page as cleanly imported when forty of its boxes were
    repaired."""
    source = tmp_path / "folio.xml"
    source.write_text("<PcGts/>", encoding="utf-8")
    body = {"pass_id": "p9", "format": "pagexml", "segments": 812, "readings": 806,
            "order_entries": 812, "checksum": "abc123", "geometry_problems": 40}
    with _mock_client(monkeypatch, body=body) as seen:
        out = mcp_server.fichero_page_import("d1", str(source), format="pagexml", name="theirs")
    assert seen[0].url.path == "/api/documents/d1/import"
    assert dict(seen[0].url.params) == {"format": "pagexml", "name": "theirs"}
    assert seen[0].method == "POST"
    assert out["format"] == "pagexml" and out["geometry_problems"] == 40
    assert out["pass_id"] == "p9"


def test_formats_list_calls_the_route(monkeypatch):
    with _mock_client(monkeypatch, body={"items": []}) as seen:
        mcp_server.fichero_formats_list()
    assert seen[0].url.path == "/api/formats"


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


# -- AI providers / local runtimes / HPC passthrough (#tools-coverage) ------
#
# _mutating_client() would build a real agent client; in tests there is no
# stored agent token so it falls back to _client(). We patch _mutating_client
# to the same mock builder so mutation tools exercise the mock transport too.


def _mock_both(monkeypatch, *, body=None):
    """_mock_client but also point _mutating_client at the mocked _client."""
    cm = _mock_client(monkeypatch, body=body)
    seen = cm.__enter__()
    monkeypatch.setattr(mcp_server, "_mutating_client", mcp_server._client)
    return cm, seen


def test_providers_read_tools_hit_expected_paths(monkeypatch):
    for tool, path, body in [
        (mcp_server.fichero_providers, "/api/providers", []),
        (mcp_server.fichero_provider_catalog, "/api/providers/catalog", []),
        (mcp_server.fichero_local_runtimes, "/api/providers/local-runtimes", []),
        (mcp_server.fichero_models_catalog, "/api/local-inference/catalog", []),
        (mcp_server.fichero_runtime_status, "/api/local-inference/runtime", {}),
        (mcp_server.fichero_kraken_status, "/api/local-models/kraken/status", {}),
        (mcp_server.fichero_hpc_clusters, "/api/hpc/clusters", []),
    ]:
        with _mock_client(monkeypatch, body=body) as seen:
            tool()
        assert seen[0].method == "GET", tool.__name__
        assert seen[0].url.path == path, tool.__name__


def test_local_models_forwards_model_type_filter(monkeypatch):
    with _mock_client(monkeypatch, body=[]) as seen:
        mcp_server.fichero_local_models(model_type="kraken")
    assert seen[0].url.path == "/api/local-models"
    assert seen[0].url.params.get("model_type") == "kraken"


def test_model_download_lifecycle_paths(monkeypatch):
    cm, seen = _mock_both(monkeypatch, body={"job_id": "j1"})
    try:
        mcp_server.fichero_model_download("qwen2.5-vl")
        mcp_server.fichero_model_download_cancel("j1")
        mcp_server.fichero_model_delete("qwen2.5-vl")
        mcp_server.fichero_runtime_provision()
        mcp_server.fichero_kraken_install()
        mcp_server.fichero_local_model_download("kraken", "catmus-print")
    finally:
        cm.__exit__(None, None, None)
    calls = [(r.method, r.url.path) for r in seen]
    assert ("POST", "/api/local-inference/models/qwen2.5-vl/download") in calls
    assert ("POST", "/api/local-inference/models/downloads/j1/cancel") in calls
    assert ("DELETE", "/api/local-inference/models/qwen2.5-vl") in calls
    assert ("POST", "/api/local-inference/runtime/provision") in calls
    assert ("POST", "/api/local-models/kraken/install") in calls
    assert ("POST", "/api/local-models/download/kraken/catmus-print") in calls


def test_hpc_configure_forwards_body(monkeypatch):
    cm, seen = _mock_both(monkeypatch, body={"cluster_id": "c1"})
    try:
        mcp_server.fichero_hpc_configure_cluster(
            name="ACEnet",
            host_alias="acenet",
            username="researcher",
            remote_base_dir="/scratch/researcher",
            partition="gpu",
            account="def-lab",
        )
    finally:
        cm.__exit__(None, None, None)
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/hpc/clusters"
    sent = json.loads(seen[0].content)
    assert sent["host_alias"] == "acenet"
    assert sent["partition"] == "gpu"
    assert "cluster_id" not in sent  # omitted on create


def test_hpc_test_and_dry_run_submit_paths(monkeypatch):
    cm, seen = _mock_both(monkeypatch, body={"ok": True})
    try:
        mcp_server.fichero_hpc_test_cluster("c1")
        mcp_server.fichero_hpc_dry_run_submit(
            cluster_id="c1",
            workflow_id="wf-1",
            workflow_name="Transcribe",
            run_id="run-7",
            input_files=["/a.pdf", "/b.pdf"],
            throttle=2,
        )
        mcp_server.fichero_hpc_delete_cluster("c1")
    finally:
        cm.__exit__(None, None, None)
    calls = [(r.method, r.url.path) for r in seen]
    assert ("POST", "/api/hpc/clusters/c1/test") in calls
    assert ("POST", "/api/hpc/clusters/c1/dry-run-submit") in calls
    assert ("DELETE", "/api/hpc/clusters/c1") in calls
    submit = next(r for r in seen if r.url.path.endswith("/dry-run-submit"))
    body = json.loads(submit.content)
    assert body["input_files"] == ["/a.pdf", "/b.pdf"]
    assert body["throttle"] == 2


class TestSegmentWriteToolsCarryTheRoutesRefusals:
    """`source.editor.agent-parity` (#4941): the editor's verbs, over MCP.

    What these pin is the route each tool calls AND that the version checks reach it,
    because the failure mode is a tool that edits without the checks the editor obeys
    — an agent with a way around the one protection a concurrent human editor has.
    """

    def test_update_sends_the_expected_version_with_the_shape(self, monkeypatch):
        cm, seen = _mock_both(monkeypatch, body={"id": "seg-1", "version": 3})
        try:
            mcp_server.fichero_segment_update(
                "seg-1", expected_version=2, rect=[0.1, 0.2, 0.3, 0.05], kind="line"
            )
        finally:
            cm.__exit__(None, None, None)

        assert seen[0].method == "PUT"
        assert seen[0].url.path == "/api/segments/seg-1"
        body = json.loads(seen[0].content)
        assert body["expected_version"] == 2, "without this the route overwrites a newer row"
        assert body["anchor"] == {"rect": [0.1, 0.2, 0.3, 0.05]}
        assert body["kind"] == "line"

    def test_update_omits_what_the_caller_did_not_set(self, monkeypatch):
        """A field cannot be cleared by omission, so the tool must not send `null` for
        everything the caller left alone — that would blank a segment's language the
        moment somebody moved its box."""
        cm, seen = _mock_both(monkeypatch, body={"id": "seg-1"})
        try:
            mcp_server.fichero_segment_update("seg-1", expected_version=1, kind="word")
        finally:
            cm.__exit__(None, None, None)

        body = json.loads(seen[0].content)
        assert set(body) == {"segment_id", "expected_version", "kind"}, body

    def test_delete_sends_a_version_per_segment(self, monkeypatch):
        cm, seen = _mock_both(monkeypatch, body={"deleted": 2})
        try:
            mcp_server.fichero_segment_delete(
                ["seg-1", "seg-2"], {"seg-1": 3, "seg-2": 1}, reason="duplicate lines"
            )
        finally:
            cm.__exit__(None, None, None)

        assert seen[0].url.path == "/api/segments/delete"
        body = json.loads(seen[0].content)
        assert body["expected_versions"] == {"seg-1": 3, "seg-2": 1}
        assert body["reason"] == "duplicate lines"

    def test_merge_names_the_survivor(self, monkeypatch):
        cm, seen = _mock_both(monkeypatch, body={"keep_id": "seg-1"})
        try:
            mcp_server.fichero_segment_merge(["seg-1", "seg-2"], keep_id="seg-1")
        finally:
            cm.__exit__(None, None, None)

        body = json.loads(seen[0].content)
        assert seen[0].url.path == "/api/segments/merge"
        assert body == {"segment_ids": ["seg-1", "seg-2"], "keep_id": "seg-1"}

    def test_split_and_undelete_hit_their_own_routes(self, monkeypatch):
        cm, seen = _mock_both(monkeypatch, body={"new_segment_ids": ["seg-9"]})
        try:
            mcp_server.fichero_segment_split(
                "seg-1", [{"anchor": {"rect": [0, 0, 0.5, 0.1]}}]
            )
            mcp_server.fichero_segment_undelete(["seg-1"])
        finally:
            cm.__exit__(None, None, None)

        assert [r.url.path for r in seen] == [
            "/api/segments/split",
            "/api/segments/undelete",
        ]

    def test_a_refusal_propagates_rather_than_being_swallowed(self, monkeypatch):
        """A 409 means somebody else edited the row since the caller read it. The tool
        must raise so the agent re-reads and decides, not return a dict that reads like
        success — the shape that would let an agent loop overwriting a person's work."""
        cm = _mock_client(monkeypatch, status=409, body={"detail": "version 2 is stale"})
        cm.__enter__()
        monkeypatch.setattr(mcp_server, "_mutating_client", mcp_server._client)
        try:
            with pytest.raises(Exception) as raised:
                mcp_server.fichero_segment_update("seg-1", expected_version=2, kind="line")
        finally:
            cm.__exit__(None, None, None)
        assert "stale" in str(raised.value) or "409" in str(raised.value)

    def test_choosing_a_reading_is_offered_so_the_refusal_is_visible(self, monkeypatch):
        """Only a person may choose which reading counts, and an agent acting as itself
        is refused (403). The tool exists so that refusal is REPORTABLE rather than
        invisible for want of a surface offering it."""
        cm, seen = _mock_both(monkeypatch, body={"ok": True})
        try:
            mcp_server.fichero_segment_choose_reading("seg-1", "rep-1")
        finally:
            cm.__exit__(None, None, None)

        assert seen[0].url.path == "/api/segments/seg-1/readings/choice"
        assert json.loads(seen[0].content) == {"representation_id": "rep-1"}


class TestReadingTheText:
    """#5139: an agent can read the text it can already see the shapes of.

    WHY: the acceptance run (2026-09-27) listed 4,525 segments on one page over
    MCP and could read none of them -- the text lives in readings, and no tool
    reached a reading, the page's text, its reading orders, or a listing wider
    than one document. Each tool is ONE GET on the route the app and CLI use,
    returning the route's answer unchanged; if a tool drifts to another path
    or reshapes the answer, these fail. The route is mocked: the engine half
    (texts that are not null) is a separate fix, and these hold the contract.
    """

    def test_segment_readings_is_the_readings_route(self, monkeypatch):
        body = {"segment_id": "seg-1", "readings": [{"kind": "transcription", "text": "ܒܪܝܫܝܬ"}]}
        with _mock_client(monkeypatch, body=body) as seen:
            result = mcp_server.fichero_segment_readings("seg-1", kind="transcription")
        assert seen[0].method == "GET"
        assert seen[0].url.path == "/api/segments/seg-1/readings"
        assert dict(seen[0].url.params) == {"kind": "transcription"}
        assert result == body

    def test_document_text_is_the_page_text_route(self, monkeypatch):
        body = {"document_id": "doc-1", "text": "In principio", "blocks": [], "order": "ord-1"}
        with _mock_client(monkeypatch, body=body) as seen:
            result = mcp_server.fichero_document_text(
                "doc-1", order="ord-1", include_furniture=False
            )
        assert seen[0].url.path == "/api/segments/document/doc-1/text"
        # Unset options are not sent: the route's own defaults apply.
        assert dict(seen[0].url.params) == {"order": "ord-1", "include_furniture": "false"}
        assert result == body

    def test_segments_in_scope_joins_document_ids_the_way_the_route_reads_them(
        self, monkeypatch
    ):
        body = {"items": [{"id": "s1", "text": "a"}], "count": 1}
        with _mock_client(monkeypatch, body=body) as seen:
            result = mcp_server.fichero_segments_in_scope(
                document_ids=["d1", "d2"], kind="line", limit=1000, offset=1000
            )
        assert seen[0].url.path == "/api/segments"
        assert dict(seen[0].url.params) == {
            "document_ids": "d1,d2", "kind": "line", "limit": "1000", "offset": "1000",
        }
        assert result == body

    def test_segments_in_scope_by_folder(self, monkeypatch):
        with _mock_client(monkeypatch, body={"items": [], "count": 0}) as seen:
            mcp_server.fichero_segments_in_scope(parent_id="folder-1")
        assert dict(seen[0].url.params) == {"parent_id": "folder-1", "limit": "200", "offset": "0"}

    def test_reading_orders_and_their_entries(self, monkeypatch):
        with _mock_client(monkeypatch, body={"items": []}) as seen:
            mcp_server.fichero_reading_orders("doc-1")
            mcp_server.fichero_reading_order_entries("ord-1", parent_entry_id="e-1")
        assert [r.url.path for r in seen] == [
            "/api/reading-orders/document/doc-1",
            "/api/reading-orders/ord-1/entries",
        ]
        assert dict(seen[0].url.params) == {}
        assert dict(seen[1].url.params) == {"parent_entry_id": "e-1"}

    def test_a_refusal_propagates(self, monkeypatch):
        """A 404 for an unknown segment raises; it is not returned as if it were text."""
        with _mock_client(monkeypatch, status=404, body={"detail": "no such segment"}):
            with pytest.raises(FicheroError):
                mcp_server.fichero_segment_readings("missing")
