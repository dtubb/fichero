# ruff: noqa: F811  (a fixture imported from another test module and taken by name: the pattern test_share_scope_5967 uses)
"""The holds of review 3 (#6320), each through the real HTTP stack with multi-user on, on a scratch library. Four callers:
alice (project editor, a deny on folder B), bob (project viewer, a deny on B), carla (editor of folder A, a decoy `?x_id=A` in the
query) and dana (viewer of A, the same decoy). Each test fails on the code before its fix."""

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import Conversation, Document
from fichero_server.security import authz
from tests.unit.security.test_sharing_probe_2026_10_01 import _multiuser_on, harness  # noqa: F401
from tests.unit.transport.test_person_bound_invite_5910 import _as
from tests.unit.transport.test_share_scope_5967 import _person, project  # noqa: F401


@pytest.fixture
def four(project):
    lib = authz.normalize_library_path(project.library)
    for name in ("alice", "bob"):
        project.harness.app_db.set_library_acl_override(user_id=project.users[name].id, library_path=lib, target_id=project.ids["B"], effect="deny")
    for name, role in (("carla", "editor"), ("dana", "viewer")):
        _person(project.harness, name)
        authz.grant_folder(actor=project.users["owner"], library=lib, user=name, folder_id=project.ids["A"], role=role)
    decoy = f"?x_id={project.ids['A']}"
    return [(n, _as(project.harness, n), decoy if n in ("carla", "dana") else "") for n in ("alice", "bob", "carla", "dana")]


def _all_refused(four, method, path, body, who=("alice", "bob", "carla", "dana")):
    for name, client, decoy in four:
        if name in who:
            got = client.request(method, path + decoy, json=body)
            assert got.status_code == 403, (name, method, path, got.status_code, got.text[:200])
    return True


def test_h1_execute_with_a_typed_selection_is_checked_like_its_inputs(project, four):
    b1, folder = project.ids["b1"], project.ids["B"]
    assert _all_refused(four, "POST", "/api/workflow-execution/execute", {"workflow_id": "x", "selection": {"kind": "documents", "ids": [b1]}})
    assert _all_refused(four, "POST", "/api/workflow-execution/execute", {"workflow_id": "x", "selection": {"kind": "folder", "ids": [folder]}})


def _spy_chat(monkeypatch, project):
    """The real route and retriever; the model and the search are fakes. Returns what the retriever was asked."""
    from types import SimpleNamespace

    from fichero_server.api.routes.system import chat
    from fichero_server.retrieval import graph_rag

    seen = []

    def retrieve(self, **kw):
        seen.append(kw)
        return graph_rag.RetrievalPayload()

    async def ask(*a, **k):
        return SimpleNamespace(content="ok", tool_calls=[])

    monkeypatch.setattr(graph_rag.GraphAwareRetriever, "retrieve", retrieve)
    monkeypatch.setattr(chat, "_get_langchain_llm", lambda *a, **k: object())
    monkeypatch.setattr(chat, "_chat_config", lambda *a, **k: None)
    monkeypatch.setattr(chat, "_ask", ask)
    monkeypatch.setattr(chat, "_chat_tools_enabled", lambda: False)
    return seen


def test_h2_chat_scope_document_id_and_a_conversations_own_scope_are_checked(project, four, monkeypatch):
    _spy_chat(monkeypatch, project)
    b = project.ids["B"]
    assert _all_refused(four, "POST", "/api/chat", {"message": "hi", "scope_document_id": b})
    db = db_manager.get_database(project.harness.library)
    conv = Conversation(title="b", messages=[], scope_document_id=b, document_ids=[])
    db.save(conv)
    assert _all_refused(four, "POST", "/api/chat", {"message": "hi", "conversation_id": conv.id})


def test_h2_an_unscoped_chat_retrieves_only_what_the_caller_may_read(project, four, monkeypatch):
    seen = _spy_chat(monkeypatch, project)
    by = {name: (client, decoy) for name, client, decoy in four}
    for name in ("alice", "carla"):
        client, decoy = by[name]
        seen.clear()
        got = client.post("/api/chat" + decoy, json={"message": "hi"})
        assert got.status_code == 200, (name, got.text[:200])
        may_read = seen[0].get("may_read")
        assert may_read is not None and may_read(project.ids["b1"]) is False, name
        assert may_read(project.ids["a1"]) is True, name
    seen.clear()  # a person whose reads cannot differ page by page pays nothing
    owner = _as(project.harness, "owner")
    assert owner.post("/api/chat", json={"message": "hi"}).status_code == 200 and seen[0].get("may_read") is None


def test_h2_the_retriever_leaves_out_a_denied_page_found_by_search_scope_or_a_hop_of_the_graph(project):
    from types import SimpleNamespace

    from fichero_server.models import KnowledgeClaim
    from fichero_server.retrieval.graph_rag import GraphAwareRetriever

    db = db_manager.get_database(project.harness.library)
    for key in ("a1", "b1"):
        doc = db.get(Document, project.ids[key])
        doc.page_content = f"SECRET{key}"
        db.save(doc)
    claim = KnowledgeClaim(text="SECRET claim", source_document_id=project.ids["b1"], subject_canonical="Ann", predicate_verb="owned", object_phrase="x",
                           source_excerpt="SECRET claim")
    db.save(claim)
    hits = [SimpleNamespace(document_id=project.ids["b1"], score=0.9), SimpleNamespace(document_id=project.ids["a1"], score=0.8)]
    db.search = lambda **kw: (hits, len(hits), None)
    allowed = {project.ids["a1"]}
    payload = GraphAwareRetriever(db).retrieve(query="q", max_sources=5, may_read=lambda d: d in allowed)
    text = " ".join(str(d) for d in payload.context_docs) + str(payload.sources)
    assert "SECRETa1" in text and "SECRETb1" not in text and "SECRET claim" not in text
    scoped = GraphAwareRetriever(db).retrieve(query="q", max_sources=5, document_ids=[project.ids["b1"], project.ids["a1"]], may_read=lambda d: d in allowed)
    assert "SECRETb1" not in str(scoped.context_docs)


def test_h2_the_agents_search_tool_returns_only_pages_the_caller_may_read(project, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.actions.chat_tools import dispatch_tool_call
    from fichero_server.api.routes.search import core

    db = db_manager.get_database(project.harness.library)
    rows = [SimpleNamespace(document_id=project.ids["b1"]), SimpleNamespace(document_id=project.ids["a1"])]
    monkeypatch.setattr(core, "_run_content_search_sync", lambda db_, req, q: (rows, 2, None))
    monkeypatch.setattr(core, "asdict", lambda r: {"document_id": r.document_id})
    result = dispatch_tool_call(db, "search.query", {"query": "x"}, library_path=project.library, is_bootstrap=True, may_read=lambda d: d != project.ids["b1"])
    assert [r["document_id"] for r in result.result["results"]] == [project.ids["a1"]]


def test_h2_the_chat_tool_loop_is_given_the_callers_reader(project, four, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.api.routes.system import chat

    seen = _spy_chat(monkeypatch, project)
    got = {}

    async def loop(llm, messages, **kw):
        got.update(kw)
        return "ok", []

    monkeypatch.setattr(chat, "_chat_tools_enabled", lambda: True)
    monkeypatch.setattr(chat, "_run_chat_tools_loop", loop)
    alice = [c for n, c, _ in four if n == "alice"][0]
    assert alice.post("/api/chat", json={"message": "hi"}).status_code == 200
    assert got["may_read"] is not None and got["may_read"](project.ids["b1"]) is False
    assert SimpleNamespace and seen


def _schedule(inputs):
    return {"name": "n", "workflow_id": "w", "config": {"schedule_type": "interval", "interval_seconds": 86400}, "inputs": inputs}


def test_h3_a_viewer_cannot_make_a_schedule_and_nobody_schedules_a_run_on_a_denied_page(project, four):
    assert _all_refused(four, "POST", "/api/schedules", _schedule({}), who=("bob", "dana"))
    assert _all_refused(four, "POST", "/api/schedules", _schedule({"doc_id": project.ids["b1"]}), who=("alice", "carla"))


def test_h3_a_viewer_cannot_trigger_pause_or_delete_a_schedule(project, four):
    for method, tail in (("POST", "/s1/trigger"), ("POST", "/s1/pause"), ("POST", "/s1/resume"), ("DELETE", "/s1"), ("PUT", "/s1")):
        assert _all_refused(four, method, "/api/schedules" + tail, {} if method != "DELETE" else None, who=("bob", "dana")), tail


def test_h3_a_trigger_watches_a_folder_on_the_owners_mac_so_only_the_owner_makes_one(project, four, tmp_path):
    body = {"name": "t", "workflow_id": "w", "config": {"watch_path": str(tmp_path)}, "inputs_template": {}}
    assert _all_refused(four, "POST", "/api/triggers", body)
    assert _all_refused(four, "POST", "/api/triggers", {**body, "inputs_template": {"doc_id": project.ids["b1"]}})


def test_h4_migrations_are_the_owners(project, four):
    assert _all_refused(four, "POST", "/api/migrations/rollback", {"run_id": "r1"})
    assert _all_refused(four, "POST", "/api/migrations/run", {"command": "repair_orphaned_claim_links", "dry_run": True})
    assert _all_refused(four, "POST", "/api/migrations/validate", {"command": "repair_orphaned_claim_links"})


def test_g1_samples_names_only_pages_the_caller_reads(project, four):
    assert _all_refused(four, "PUT", "/api/recipes/samples", {"ids": [project.ids["b1"]]}, who=("alice", "carla"))


def test_g1_document_fetch_saves_a_top_level_document_so_a_folder_scoped_person_cannot(project, four):
    assert _all_refused(four, "POST", "/api/research/tools/document-fetch", {"url": "https://example.org/a.pdf", "project_id": "p"}, who=("bob", "carla", "dana"))


def test_g1_an_action_is_made_and_imported_only_by_someone_who_can_write(project, four):
    assert _all_refused(four, "POST", "/api/actions/import", {"json_data": "{}", "new_id": True}, who=("bob", "dana"))
    assert _all_refused(four, "POST", "/api/actions", {"name": "a"}, who=("bob", "dana"))


def test_g1_bibtex_export_names_only_pages_the_caller_reads(project, four):
    assert _all_refused(four, "POST", "/api/bibliography/export.bib", {"document_ids": [project.ids["b1"]]}, who=("alice", "bob", "carla", "dana"))


def test_g1_compare_tool_and_compare_workflow_inputs_are_checked(project, four):
    b1 = project.ids["b1"]
    assert _all_refused(four, "POST", "/api/model-comparison/compare-tool", {"tool_name": "describe", "inputs": {"selected_doc_ids": [b1]}, "models": []},
                        who=("alice", "carla"))
    assert _all_refused(four, "POST", "/api/model-comparison/compare-workflow",
                        {"doc_id": project.ids["a1"], "workflow_id": "x", "models": [], "inputs": {"selected_doc_ids": [b1]}}, who=("alice", "carla"))


def test_g1_the_integrations_move_files_on_the_owners_mac_so_they_are_the_owners(project, four):
    assert _all_refused(four, "POST", "/api/integrations/notes/import", {"external_id": "1"})
    assert _all_refused(four, "POST", "/api/integrations/notes/export", {"file_path": "/tmp/x"})


def test_m1_a_top_level_save_by_an_editor_with_a_deny_is_not_refused_for_the_deny(project, four):
    """`[None]` walked the whole project though the save only needs the project's top level."""
    alice = [c for n, c, _ in four if n == "alice"][0]
    got = alice.post("/api/research/tools/browser-save", json={"url": "ftp://x/a.pdf", "project_id": "p"})
    assert got.status_code != 403, got.text[:200]


def test_p2_a_signed_in_owner_or_plain_editor_pays_no_walk_but_a_denied_editor_still_walks(project, monkeypatch):
    calls = []
    real = authz._allowed
    monkeypatch.setattr(authz, "_allowed", lambda *a, **k: calls.append(a[2]) or real(*a, **k))
    pages = 7
    for name in ("owner", "alice", "bob"):  # no deny yet: one answer for the named id, no lookup per page
        calls.clear()
        assert _as(project.harness, name).post("/api/documents/dataset/query", json={}).status_code == 200, name
        assert len(calls) < pages, (name, len(calls))
    lib = authz.normalize_library_path(project.library)
    project.harness.app_db.set_library_acl_override(user_id=project.users["alice"].id, library_path=lib, target_id=project.ids["B"], effect="deny")
    calls.clear()
    assert _as(project.harness, "alice").post("/api/documents/dataset/query", json={}).status_code == 403
    assert len(calls) > 2  # the walk went past the named id, and found the denied folder


def test_g3_running_a_chain_on_a_denied_page_is_refused(project, four):
    """A chain's steps are runs: `inputs` names the pages they read and write, like /execute."""
    assert _all_refused(four, "POST", "/api/chains/c1/execute-steps", {"inputs": {"selected_doc_ids": [project.ids["b1"]]}})


def test_n1_a_snapshot_is_restored_pinned_and_deleted_only_by_the_owner(project, four):
    """Anyone signed in could restore one over the owner's whole project. The check comes before the snapshot is looked up."""
    assert _all_refused(four, "POST", "/api/storage/snapshots/s1/restore", None)
    assert _all_refused(four, "DELETE", "/api/storage/snapshots/s1", None)
    assert _all_refused(four, "PATCH", "/api/storage/snapshots/s1/pin", None)
    assert _all_refused(four, "POST", f"/api/storage/snapshots?library_path={project.library}", None)


def test_n2_a_library_is_taken_off_the_list_only_by_the_owner(project, four):
    from urllib.parse import quote

    assert _all_refused(four, "DELETE", "/api/registry/" + quote(project.library, safe=""), None)


def test_n8_tasks_and_policies_are_the_owners(project, four):
    for path in ("/api/tasks/reindex", "/api/tasks/reanchor", "/api/tasks/vector-repair", "/api/tasks/metrics", "/api/tasks/kg-metrics"):
        assert _all_refused(four, "POST", path, {}), path
    assert _all_refused(four, "POST", "/api/policies/orchestration", {"name": "n", "entity_type": "claim", "action": "allow"})


def _chain(project, static_inputs):
    return {"name": "c", "steps": [{"id": "s1", "workflow_id": "w", "static_inputs": static_inputs}]}


def test_n3_a_chain_is_made_changed_and_deleted_only_by_someone_who_can_write_there(project, four):
    assert _all_refused(four, "POST", "/api/chains", _chain(project, {}), who=("bob", "carla", "dana"))
    assert _all_refused(four, "POST", "/api/chains", _chain(project, {"selected_doc_ids": [project.ids["b1"]]}), who=("alice",))
    assert _all_refused(four, "PUT", "/api/chains/c1", {"steps": _chain(project, {"doc_id": project.ids["b1"]})["steps"]}, who=("alice",))
    assert _all_refused(four, "DELETE", "/api/chains/c1", None, who=("bob", "carla", "dana"))


def test_n3_a_chain_whose_step_names_a_denied_page_is_not_run_and_a_viewer_does_not_run_one(project, four):
    owner = _as(project.harness, "owner")
    made = owner.post("/api/chains", json=_chain(project, {"selected_doc_ids": [project.ids["b1"]]}))
    assert made.status_code == 200, made.text
    cid = made.json()["id"]
    assert _all_refused(four, "POST", f"/api/chains/{cid}/execute-steps", {"inputs": {}})  # the step's static_inputs, not the request, name b1
    assert _all_refused(four, "POST", f"/api/chains/{cid}/execute", {"inputs": {}})
    assert _all_refused(four, "POST", f"/api/chains/{cid}/execute", {"inputs": {"selected_doc_ids": [project.ids["b1"]]}}, who=("bob", "dana"))


def _seed_secret_records(project):
    from fichero_server.models import AgentNote, AgentNoteActor, AgentNoteSourceAnchor, KnowledgeClaim

    db = db_manager.get_database(project.harness.library)
    claim = KnowledgeClaim(text="SECRET claim", source_document_id=project.ids["b1"], subject_canonical="Ann", predicate_verb="owned", object_phrase="x")
    ok_claim = KnowledgeClaim(text="PLAIN claim", source_document_id=project.ids["a1"], subject_canonical="Ann", predicate_verb="owned", object_phrase="y")
    note = AgentNote(body="SECRET note", source_anchor=AgentNoteSourceAnchor(document_id=project.ids["b1"]), actor=AgentNoteActor(actor_id="agent"))
    conv = Conversation(title="SECRET chat", messages=[], scope_document_id=project.ids["b1"], document_ids=[])
    for row in (claim, ok_claim, note, conv):
        db.save(row)
    return claim, ok_claim, note, conv


def test_n4_plain_reads_of_claims_agent_memory_and_conversations_leave_out_what_rests_on_a_denied_page(project, four):
    claim, ok_claim, note, conv = _seed_secret_records(project)
    for name, client, decoy in four:
        for path in ("/api/claims", "/api/agent-memory", "/api/chat/conversations"):
            got = client.get(path + decoy)
            assert got.status_code in (200, 403), (name, path, got.status_code)
            assert "SECRET" not in got.text, (name, path, got.text[:200])
        for path in (f"/api/claims/{claim.id}", f"/api/agent-memory/{note.id}", f"/api/chat/conversations/{conv.id}"):
            assert client.get(path + decoy).status_code == 403, (name, path)
    alice = {n: c for n, c, _ in four}["alice"]
    assert ok_claim.id in alice.get("/api/claims").text  # what she may read is still there


def test_n5_the_action_route_reads_through_the_callers_reader_and_search_counts_what_it_returns(project, four, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.actions.chat_tools import dispatch_tool_call
    from fichero_server.api.routes.search import core
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity

    claim, ok_claim, _note, _conv = _seed_secret_records(project)
    db = db_manager.get_database(project.harness.library)
    db.save(KnowledgeEntity(canonical_name="SECRET entity", entity_type=EntityType.person, source_document_ids=[project.ids["b1"]]))
    alice = {n: c for n, c, _ in four}["alice"]

    def invoke(name, params):
        return alice.post("/api/actions/invoke", json={"name": name, "params": params})

    listed = invoke("claim.list", {})
    assert listed.status_code == 200 and "SECRET" not in listed.text and ok_claim.id in listed.text
    assert invoke("claim.get", {"claim_id": claim.id}).status_code == 403
    entities = invoke("entity.list", {})
    assert entities.status_code == 200 and "SECRET" not in entities.text
    rows = [SimpleNamespace(document_id=project.ids["b1"]), SimpleNamespace(document_id=project.ids["a1"])]
    monkeypatch.setattr(core, "_run_content_search_sync", lambda db_, req, q: (rows, 2, None))
    monkeypatch.setattr(core, "asdict", lambda r: {"document_id": r.document_id})
    got = dispatch_tool_call(db, "search.query", {"query": "x"}, library_path=project.library, is_bootstrap=True, may_read=lambda d: d != project.ids["b1"])
    assert got.result["total_results"] is None and got.result["has_more"] is False  # no exact total for a caller who reads only some pages
    owner = dispatch_tool_call(db, "search.query", {"query": "x"}, library_path=project.library, is_bootstrap=True)
    assert owner.result["total_results"] == 2


def test_n6_a_run_is_resumed_only_by_someone_who_can_write_the_pages_it_works_on(project, four, monkeypatch):
    from types import SimpleNamespace

    from fichero_server.api.routes.workflow_execution import core
    from fichero_server.workflows import checkpointer

    ck = SimpleNamespace(checkpoint={"id": "c1", "channel_values": {"workflow_id": "w", "selected_doc_ids": [project.ids["b1"]]}}, metadata={})

    class Saver:
        async def aget_tuple(self, config):
            return ck

    monkeypatch.setattr(checkpointer.AsyncDuckDBCheckpointer, "from_db_path", classmethod(lambda cls, path: Saver()))
    monkeypatch.setattr(core.WorkflowStore, "get", lambda self, wid: SimpleNamespace(name="w", id="w", nodes=[], edges=[]))
    assert _all_refused(four, "POST", "/api/workflow-execution/threads/thread-x/resume", {})
    # a continuation naming a denied page of its own is refused too
    ck.checkpoint["channel_values"].pop("selected_doc_ids")
    assert _all_refused(four, "POST", "/api/workflow-execution/threads/thread-x/resume", {"inputs": {"doc_id": project.ids["b1"]}})


def test_n7_a_person_shared_one_folder_opens_the_table_on_it_and_nowhere_else(project, four):
    by = {name: client for name, client, _ in four}
    for name in ("carla", "dana"):
        got = by[name].post("/api/documents/dataset/query", json={"parent_id": project.ids["A"]})
        assert got.status_code == 200, (name, got.status_code, got.text[:200])
        for refused in ({"parent_id": project.ids["B"]}, {}, {"parent_id": None}):
            assert by[name].post("/api/documents/dataset/query", json=refused).status_code == 403, (name, refused)


def test_n5_the_entity_and_kg_routes_hide_what_rests_on_a_denied_page_and_aggregates_are_refused(project, four):
    from fichero_server.models.knowledge import EntityType, KnowledgeEntity

    db = db_manager.get_database(project.harness.library)
    secret = KnowledgeEntity(canonical_name="SECRET entity", entity_type=EntityType.person, source_document_ids=[project.ids["b1"]])
    plain = KnowledgeEntity(canonical_name="PLAIN entity", entity_type=EntityType.person, source_document_ids=[project.ids["a1"]])
    db.save(secret), db.save(plain)
    _seed_secret_records(project)
    by = {name: (client, decoy) for name, client, decoy in four}
    for name in ("alice", "bob", "carla", "dana"):
        client, decoy = by[name]
        for path in ("/api/entities", f"/api/entities/{secret.id}", f"/api/kg/graph/neighborhood/{secret.id}", "/api/kg/search?q=entity"):
            sep = "&" if "?" in path else "?"
            got = client.get(path + (decoy.replace("?", sep, 1) if decoy else ""))
            assert got.status_code in (200, 403), (name, path, got.status_code)
            assert "SECRET" not in got.text, (name, path, got.text[:200])
        for path in ("/api/entities/top", "/api/entities/claim-counts", "/api/kg/graph/centrality", "/api/kg/graph/pagerank", f"/api/entities/{plain.id}/co-occurrence"):
            got = client.get(path + decoy)
            assert got.status_code == 403, (name, path, got.status_code)
    alice, _ = by["alice"]
    assert "PLAIN entity" in alice.get("/api/kg/search?q=entity").text and "PLAIN entity" in alice.get("/api/entities").text  # what she may read is still there
