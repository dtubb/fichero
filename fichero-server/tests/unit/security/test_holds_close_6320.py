# ruff: noqa: F811  (a fixture imported from another test module and taken by name: the pattern test_share_scope_5967 uses)
"""The holds of review 3 (#6320), each through the real HTTP stack with multi-user on, on a scratch library. Four callers:
alice (project editor, a deny on folder B), bob (project viewer, a deny on B), carla (editor of folder A, a decoy `?x_id=A` in the
query) and dana (viewer of A, the same decoy). Each test fails on the code before its fix."""

import re

import pytest

from fichero_server.db.manager import db_manager
from fichero_server.models import Conversation, DocType, Document
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
    assert by["carla"][0].post("/api/chat", json={"message": "hi"}).status_code == 403  # an unscoped chat reads the whole library: not a folder person's (#6325 H5)
    for name in ("alice",):
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


#: One route of each family: a caller whose reads differ page by page (alice, bob: a deny on B) is refused a route that sums,
#: walks or rewrites the whole library's knowledge rows, because it cannot be filtered after the fact.
_WHOLE_LIBRARY_FAMILIES = [
    ("GET", "/api/kg/predictions", None), ("GET", "/api/kg/pykeen/stored", None), ("GET", "/api/kg/review/summary", None),
    ("GET", "/api/kg/mutations", None), ("GET", "/api/kg/inclusion", None), ("GET", "/api/kg/entities/x/readable", None),
    ("GET", "/api/kg/curation-rules/claim-rules", None), ("GET", "/api/kg/entity-curation/audit", None),
    ("GET", "/api/kg/export/rdf", None), ("GET", "/api/kg/triangulation", None), ("GET", "/api/claims/x/links", None),
    ("GET", "/api/entities/x/inspector", None), ("GET", "/api/claims/queues/unreviewed", None),
    ("POST", "/api/claims", {"text": "t"}), ("PATCH", "/api/entities/x", {"canonical_name": "n"}),
    ("POST", "/api/kg/claims/merge", {}), ("POST", "/api/kg/rebuild", {}), ("POST", "/api/kg/review/pairs", {}),
]


def test_n5_every_whole_library_knowledge_family_is_refused_to_a_caller_with_a_deny(project, four):
    for method, path, body in _WHOLE_LIBRARY_FAMILIES:
        for name, client, decoy in four:
            if name in ("alice", "bob"):
                got = client.request(method, path, json=body)
                assert got.status_code == 403, (name, method, path, got.status_code, got.text[:120])


def test_a_new_knowledge_route_must_filter_its_rows_or_refuse_a_caller_with_a_deny():
    """The sweep's list: every route under the entity, claim and KG prefixes depends on `whole_library_reader_only`, or is one of
    the few that filter their own rows (named here). A new route of this kind fails until it does one or the other."""
    import os

    os.environ.setdefault("FICHERO_FEATURE_TIER", "dev")
    from fichero_server.api import main
    from tests.route_inventory import served_routes

    filters = {("GET", "/api/entities"), ("GET", "/api/entities/{entity_id}"), ("GET", "/api/claims"), ("GET", "/api/claims/{claim_id}"),
               ("GET", "/api/kg/search"), ("GET", "/api/kg/graph/neighborhood/{entity_id}"), ("GET", "/api/claim-links/{link_id}")}

    def deps(d):
        for x in d.dependencies:
            yield getattr(x.call, "__name__", "")
            yield from deps(x)

    bare = []
    for route in served_routes(main.app):
        if not route.path.startswith(("/api/kg", "/api/claims", "/api/claim-links", "/api/entities")):
            continue
        for method in route.methods - {"HEAD"}:
            if (method, route.path) not in filters and "whole_library_reader_only" not in set(deps(route.dependant)):
                bare.append((method, route.path))
    assert not bare, f"these routes neither filter their rows nor refuse a caller with a deny (`whole_library_reader_only`): {sorted(bare)}"


def test_o1_one_restricted_page_does_not_turn_off_the_knowledge_views_for_someone_named_on_it(project):
    from fichero_server.models.rights import RightsRecord

    alice, bob = _as(project.harness, "alice"), _as(project.harness, "bob")
    views = ("/api/entities/top", "/api/entities/claim-counts", "/api/kg/graph/centrality", "/api/claims/queues/unreviewed")
    for client in (alice, bob):
        assert all(client.get(v).status_code == 200 for v in views)  # nothing restricted yet
    db = db_manager.get_database(project.harness.library)
    db.save(RightsRecord(target_kind="document", target_id=project.ids["b1"], restricted=True, readers=[project.users["alice"].id]))
    assert [alice.get(v).status_code for v in views] == [200] * 4  # a named reader keeps them
    assert [bob.get(v).status_code for v in views] == [403] * 4  # someone not named cannot be shown a count that includes it


def test_h5_a_query_name_no_route_declares_is_not_a_target(project, four):
    """#6325 H5: `?x_id=<A>` opened the library level to a person shared folder A. It names no id the route reads, so it changes nothing."""
    for method, path in (("POST", "/api/workflows"), ("POST", "/api/projects"), ("POST", "/api/search/reindex"), ("POST", "/api/storage/regenerate-missing"),
                         ("GET", "/api/actions"), ("GET", "/api/claims")):
        for name, client, decoy in four:
            if name in ("carla", "dana"):
                plain = client.request(method, path, json={} if method == "POST" else None)
                with_decoy = client.request(method, path + decoy, json={} if method == "POST" else None)
                assert with_decoy.status_code == plain.status_code, (name, method, path, plain.status_code, with_decoy.status_code)
    # a name the route DOES declare still counts: carla reads her own folder by `parent_id`
    own = next(c for n, c, _ in four if n == "carla").get(f"/api/documents?parent_id={project.ids['A']}")
    assert own.status_code == 200, own.text[:200]


def test_h7_the_write_check_reads_ids_and_items(project, four):
    """#6325 H7: `document.copy_into_project` carries its pages in `ids`, `document.transfer` in `items`; neither was a target."""
    assert authz.target_ids_from_params({"ids": ["a"], "items": ["b", {"document_id": "c"}], "name": "d"}) == ["a", "b", "c"]
    b1 = project.ids["b1"]
    assert _all_refused(four, "POST", "/api/actions/invoke", {"name": "document.copy_into_project", "params": {"ids": [b1], "project_id": project.ids["A"]}})
    assert _all_refused(four, "POST", "/api/actions/invoke", {"name": "document.transfer", "params": {"items": [b1], "source": project.library}})


def test_h9_the_machines_own_routes_are_the_owners(project, four):
    """#6325 H9: the MLX runtime, local models, paired machines, the registry of libraries and the chain preset change the owner's Mac.
    Every such write depends on the owner check (looked at, not fired: the runtime delete really deletes; the route sweep fires them in scratch);
    the harmless ones are also fired."""
    from fastapi.routing import APIRoute
    from fichero_server.api.routes.auth.accounts import _require_owner_for_writes
    from tests.route_inventory import served_routes

    machine = re.compile(r"^/api/(local-inference|local-models|machines|registry|chains/presets)\b")
    writes = [r for r in served_routes(project.harness.app) if isinstance(r, APIRoute) and machine.match(r.path) and set(r.methods) - {"GET", "HEAD", "OPTIONS"}]
    assert len(writes) >= 15
    open_routes = [f"{sorted(r.methods)} {r.path}" for r in writes if _require_owner_for_writes not in {d.call for d in _all_dependencies(r.dependant)}]
    assert not open_routes, open_routes
    erin = _person(project.harness, "erin")
    project.harness.app_db.set_library_role(user_id=erin.id, library_path=authz.normalize_library_path(project.library), role=authz.ROLE_EDITOR)
    for who, client in [(n, c) for n, c, _ in four] + [("erin", _as(project.harness, "erin"))]:
        for method, path in (("DELETE", "/api/machines/x"), ("POST", "/api/registry/add"), ("POST", "/api/registry/update-access"), ("POST", "/api/chains/presets/paleography")):
            got = client.request(method, path, json={})
            assert got.status_code == 403, (who, method, path, got.status_code, got.text[:120])
    assert _as(project.harness, "erin").get("/api/local-models").status_code == 200  # a read stays anyone's


def _all_dependencies(dependant):
    for dep in dependant.dependencies:
        yield dep
        yield from _all_dependencies(dep)


def test_h2_read_routes_outside_the_walked_families_leave_out_a_denied_page(project, four):
    """#6325 H2: search explain, the global KG view, cross-language entity search (refused to a caller whose reads differ page by page);
    the roots list, the sample pages and the KG note hits leave out what rests on a denied page."""
    from fichero_server.models.knowledge import Note

    db = db_manager.get_database(project.harness.library)
    leaf = Document(name="leaf", doc_type=DocType.page, parent_id=project.ids["b1"])
    db.save(leaf)
    db.save(Note(page_id=leaf.id, body="zzsecretnote"))
    for name, client, decoy in four:
        for path in ("/api/search/explain/SECRET", "/view/kg/global"):
            assert client.get(path + decoy).status_code == 403, (name, path)
        assert client.post("/api/search/explain" + decoy, json={"query": "SECRET"}).status_code == 403, name
        assert client.post("/api/multilingual/entities/search" + decoy, json={"query": "SECRET", "target_languages": ["en"]}).status_code == 403, name
        if name in ("alice", "bob"):
            assert "Folder B" not in client.get("/api/documents/collections").text, name
            assert "zzsecretnote" not in client.get("/api/kg/search?q=zzsec").text, name
            assert project.ids["b1"] not in client.get("/api/recipes/samples").text, name
    assert "Folder B" in _as(project.harness, "owner").get("/api/documents/collections").text
    assert "zzsecretnote" in _as(project.harness, "owner").get("/api/kg/search?q=zzsec").text
