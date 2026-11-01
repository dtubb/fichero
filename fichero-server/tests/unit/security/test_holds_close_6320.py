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
