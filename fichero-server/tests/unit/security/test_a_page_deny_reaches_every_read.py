"""A deny on a page reaches every READ of what is on it, whichever id the request names (#5180).

WHY: #5177 closed the write side. On the read side the library dependency checked only the FIRST
id a request named, so `/api/source-settings/resolve?document_id=<allowed>&segment_id=<denied>`
answered the denied segment's settings. Lists and aggregates were worse: a bibliography export of
`document_ids=<denied>`, a sign's instances, a hand's attributions and a bookmark's target handed
over a denied page's text or segments because none of them names the page in its URL at all.

The product answers a denied read with 403 (`LibraryAccessDeniedError`), and a LIST leaves out what
the caller may not read and counts it (`withheld`, #5135), rather than refusing the whole list.

The guard walks every GET route: each single id it takes must be one the sweep can put on a denied
page (and so is proven 403 there, not-403 on an allowed page, through the real route), or be
declared not-on-a-page with why. A `*_ids` list must be declared filtered with the test that
proves it. So the next GET route with an id cannot reopen this quietly.
"""

from __future__ import annotations

import re

import pytest
from fastapi.routing import APIRoute

import fichero_server.api.main as api_main
from fichero_server.models import Artifact, ContentRepresentation, DocType, Document, Rendition
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.hands import Hand, HandAttribution
from fichero_server.models.knowledge import Annotation, Note, ProvenanceKind, SourceMetadata
from fichero_server.models.reading_orders import ReadingOrder
from fichero_server.models.signs import DeclaredSign
from fichero_server.models.typed_links import TypedLink
from tests.unit.api.test_segments_multiuser_access import (  # noqa: F401  (fixtures)
    _grant_role,
    _make_doc,
    _make_pass,
    _make_segment,
    _override,
    multiuser_client,
    users,
)

#: Ids the sweep puts on the page (`_page_records`): a route taking one is swept.
ON_A_PAGE = {"doc_id", "document_id", "folder_id", "item_id", "source_id", "segment_id", "id", "end_id",
             "target_id", "pass_id", "representation_id", "order_id", "annotation_id", "note_id", "link_id",
             "rendition_id", "artifact_id", "bookmark_id", "interpretation_id"}

#: Ids of things that are not on a page, with why. A read through one is not a page read.
NOT_ON_A_PAGE = {
    # The engine's own jobs, settings and machines -- no library, no page.
    "task_id": "an engine task", "job_id": "a model download", "profile_id": "a model profile",
    "cluster_id": "a compute cluster", "snapshot_id": "a storage snapshot", "rule_id": "an orchestration rule",
    "record_id": "an agent-write audit row", "run_id": "a migration run", "action_id": "an action-log row",
    # Library-level records. Their aggregates over pages are the knowledge-graph scope (a ruling
    # pending with the maintainer), except hands and signs, which are filtered here.
    "entity_id": "a KG entity", "claim_id": "a KG claim", "project_id": "a project",
    "reference_id": "a bibliography reference",
    "framework_id": "an interpretive framework (library-level)", "pattern_id": "an interpretive pattern",
    "state_id": "a hermeneutic-circle state", "plan_id": "a research plan",
    # Workflows, chat and the engine's integrations: runs and threads, not page records.
    "batch_id": "a workflow batch", "thread_id": "a workflow thread", "workflow_id": "a workflow",
    "chain_id": "a workflow chain", "execution_id": "a chain execution", "schedule_id": "a schedule",
    "trigger_id": "a trigger", "workspace_id": "a chat workspace", "conversation_id": "a chat conversation",
    "comparison_id": "a model comparison", "model_id": "a model", "prediction_id": "a PyKEEN prediction",
    "provider_id": "a model provider", "server_id": "an MCP server", "external_id": "another app's item",
    "hand_id": "a hand; its attributions are filtered (test_a_hand_lists_only_what_the_caller_may_read)",
    "sign_id": "a sign; its instances are filtered (test_a_signs_instances_leave_out_a_denied_page)",
    # Query-only ids that name no library record, or filter a list the caller already may read.
    "actor_id": "an agent", "agent_id": "an agent", "allograph_id": "an allograph",
    "linked_entity_id": "a KG entity", "linked_claim_id": "a KG claim",
    "linked_structure_node_id": "a structure node",
    "mask_id": "a segment, checked like any single id", "parent_entry_id": "an entry of the checked order",
    "parent_id": "a document, checked like any single id", "page_id": "a document, checked like any single id",
    "linked_document_id": "a document, checked like any single id",
    "source_document_id": "a document, checked like any single id",
    "target_document_id": "a document, checked like any single id",
    "topic_id": "a topic of the engine's built-in help text (recipes/seed/topics.yaml), not library content",
}

#: `*_ids` lists: a list route filters and counts; it is never a blanket 403.
FILTERED_LISTS = {
    "document_ids": "test_a_list_of_documents_leaves_out_the_denied_one",
    "ids": "test_every_listing_of_documents_leaves_out_a_denied_one",
    "scope_ids": "test_a_training_set_preview_leaves_out_a_denied_page",
    "held_out_ids": "test_a_training_set_preview_leaves_out_a_denied_page",
}

#: GET routes that take an id and do not read the library through the library dependency, with why.
APP_LEVEL = {
    **{path: "the engine's own jobs and settings" for path in (
        "/api/ingest/status/{task_id}", "/api/hpc/clusters/{cluster_id}", "/api/settings/model-profiles/{profile_id}",
        "/api/storage/snapshots/{snapshot_id}", "/api/tasks/{task_id}", "/api/tasks/{task_id}/result",
        "/api/tasks/reindex/{task_id}/progress", "/api/tasks/metrics/{task_id}/data",
        "/api/tasks/vector-repair/{task_id}/progress", "/api/tasks/kg-metrics/{task_id}/data",
        "/api/local-inference/profiles/{profile_id}/status", "/api/local-inference/models/downloads/{job_id}",
        "/api/policies/orchestration/{rule_id}", "/api/providers/{provider_id}", "/api/providers/{provider_id}/models",
        "/api/models/huggingface/{model_id:path}", "/api/model-comparison/comparison/{comparison_id}",
        "/api/mcp-servers/{server_id}")},
    **{path: "an engine-wide store, not one library's (not page-gated: reported with #5180)" for path in (
        "/api/agents/write/audit", "/api/agents/write/audit/{record_id}", "/api/kg/pykeen/training-jobs/{model_id}",
        "/api/kg/pykeen/stored", "/api/kg/pykeen/stored/{prediction_id}", "/api/batches/{batch_id}",
        "/api/batches/{batch_id}/progress", "/api/workflow-execution/stream/{thread_id}",
        "/api/chains/{chain_id}", "/api/chains/executions/{execution_id}")},
    **{path: "another app's item (Bookends, Tinderbox)" for path in (
        "/api/integrations/{app_name}/items/{external_id}", "/api/integrations/bookends/citation/{external_id}",
        "/api/integrations/tinderbox/notes/{external_id}/attributes")},
    "/api/authz/library": "the caller's own ACL snapshot; `target_id` is what it asks about",
    "/api/topics/{topic_id}": "the engine's built-in help text (recipes/seed/topics.yaml); reads no library",
}


def _is_id(name: str) -> bool:
    # `ids` too: `GET /api/documents?ids=` is a list of documents by a name `*_ids` does not match,
    # and it was missed by this guard until #5180's follow-up.
    return name in ("id", "ids") or name.endswith("_id") or name.endswith("_ids")


def _depends_on(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def walk(dependant) -> None:
        for sub in dependant.dependencies:
            names.add(getattr(sub.call, "__name__", ""))
            walk(sub)

    walk(route.dependant)
    return names


def get_routes() -> list[tuple[str, list[str], list[str], bool]]:
    """(path, path ids, query ids, checked by the library dependency) for every GET route."""
    out = []
    for route in api_main.app.routes:
        if isinstance(route, APIRoute) and "GET" in route.methods:
            path_ids = [p.name for p in route.dependant.path_params if _is_id(p.name)]
            query_ids = [p.name for p in route.dependant.query_params if _is_id(p.name)]
            checked = bool({"get_library_database", "get_library_database_for_write"} & _depends_on(route))
            if path_ids or query_ids:
                out.append((route.path, path_ids, query_ids, checked))
    return out


def problems(routes, on_a_page, not_on_a_page, filtered_lists, app_level) -> list[str]:
    found = []
    for path, path_ids, query_ids, checked in routes:
        if path not in app_level and not checked:
            found.append(f"{path} takes an id but never reaches the library read check")
        for name in path_ids + query_ids:
            if name == "ids" or name.endswith("_ids"):
                if name not in filtered_lists:
                    found.append(f"{path} takes the list {name!r}: filter it (readable_documents) and declare it")
            elif name not in on_a_page and name not in not_on_a_page:
                found.append(f"{path} takes {name!r}: sweep it (ON_A_PAGE) or say why it is not on a page")
    return found


def test_every_get_route_id_is_swept_or_declared():
    found = problems(get_routes(), ON_A_PAGE, NOT_ON_A_PAGE, FILTERED_LISTS, APP_LEVEL)
    assert found == [], "\n".join(found)


class TestTheGuardFires:
    def test_an_unchecked_route_is_reported(self):
        assert problems([("/x/{doc_id}", ["doc_id"], [], False)], {"doc_id"}, {}, {}, set()) == [
            "/x/{doc_id} takes an id but never reaches the library read check"]

    def test_an_undeclared_id_and_list_are_reported(self):
        found = problems([("/x/{widget_id}", ["widget_id"], ["page_ids"], True)], set(), {}, {}, set())
        assert len(found) == 2 and "'widget_id'" in found[0] and "'page_ids'" in found[1]

    def test_declared_is_clean(self):
        assert problems([("/x/{doc_id}", ["doc_id"], ["ids_ids"], True)], {"doc_id"}, {}, {"ids_ids": "t"}, set()) == []


def _page_records(db, doc) -> dict[str, str]:
    """One record of every kind the sweep fills, all on `doc`."""
    run = _make_pass(db, doc.id)
    seg = _make_segment(db, document_id=doc.id, pass_id=run.id, rect=[0.1, 0.1, 0.2, 0.05])
    other = _make_segment(db, document_id=doc.id, pass_id=run.id, rect=[0.3, 0.1, 0.2, 0.05])
    reading = ContentRepresentation(document_id=doc.id, kind="transcription", content="x",
                                    source_anchor=SourceAnchor(document_id=doc.id))
    order = ReadingOrder(document_id=doc.id, pass_id=run.id, provenance_kind=ProvenanceKind.human, name="m")
    annotation = Annotation(kind="highlight", document_id=doc.id)
    page = Document(name=f"{doc.name} p1", doc_type=DocType.page, parent_id=doc.id)
    link = TypedLink(from_id=seg.id, to_id=other.id, link_type="glosses", provenance_kind=ProvenanceKind.human)
    rendition = Rendition(document_id=doc.id, role="original", path="x.jpg")
    artifact = Artifact(document_id=doc.id, artifact_type="transcription", content="x")
    bookmark = Document(name=f"to {doc.name}", doc_type=DocType.file, node_kind="alias", alias_target_id=doc.id,
                        prototype_key="bookmark")
    for row in (reading, order, annotation, page, link, rendition, artifact, bookmark):
        db.save(row)
    note = Note(page_id=page.id, body="n")
    db.save(note)
    from fichero_server.models.hermeneutics import Interpretation, InterpretiveFramework

    framework = InterpretiveFramework(name="a lens", framework_type="thematic", description="a lens")
    db.save(framework)
    interpretation = Interpretation(framework_id=framework.id, interpretation_text="read so", act="reading",
                                    document_id=doc.id)
    db.save(interpretation)
    return {"doc_id": doc.id, "document_id": doc.id, "folder_id": doc.id, "item_id": doc.id, "source_id": doc.id,
            "segment_id": seg.id, "id": seg.id, "end_id": seg.id, "target_id": seg.id, "pass_id": run.id,
            "representation_id": reading.id, "order_id": order.id, "annotation_id": annotation.id,
            "note_id": note.id, "link_id": link.id, "rendition_id": rendition.id, "artifact_id": artifact.id,
            "bookmark_id": bookmark.id, "interpretation_id": interpretation.id}


def _swept_routes() -> list[str]:
    return sorted(path for path, path_ids, _q, _c in get_routes()
                  if path_ids and all(name in ON_A_PAGE for name in path_ids))


def _url(path: str, ids: dict[str, str]) -> str:
    return re.sub(r"{(\w+)(?::\w+)?}", lambda m: ids.get(m.group(1), "1"), path)


@pytest.fixture
def denied_and_allowed(multiuser_client, app_db, users, db):
    """A VIEWER denied one page; the same viewer on another page. Returns (client, headers, denied, allowed)."""
    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "viewer")
    denied, allowed = _make_doc(db, "denied.jpg"), _make_doc(db, "allowed.jpg")
    _override(app_db, users.editor, library_path, denied.id, "deny")
    return client, login("editor"), denied, allowed


def test_every_get_route_on_a_denied_page_refuses_and_on_an_allowed_one_does_not(denied_and_allowed, db):
    client, headers, denied, allowed = denied_and_allowed
    on_denied, on_allowed = _page_records(db, denied), _page_records(db, allowed)
    routes = _swept_routes()
    assert len(routes) > 60, routes                              # not vacuous: the whole read surface
    leaked, broken = [], []
    for path in routes:
        if client.get(_url(path, on_denied), headers=headers).status_code != 403:
            leaked.append(path)
        if client.get(_url(path, on_allowed), headers=headers).status_code == 403:
            broken.append(path)
    assert leaked == [], f"a denied page's record was read: {leaked}"
    assert broken == [], f"refused on an ALLOWED page, so the 403 is not the deny: {broken}"


def test_a_second_id_on_a_denied_page_is_refused_after_an_allowed_first(denied_and_allowed, db):
    """The bug: only the first id was checked."""
    client, headers, denied, allowed = denied_and_allowed
    bad, good = _page_records(db, denied), _page_records(db, allowed)
    for url in (f"/api/source-settings/resolve?document_id={allowed.id}&segment_id={bad['segment_id']}",
                f"/api/reading-orders/{good['order_id']}/neighbours?segment_id={bad['segment_id']}",
                f"/api/segments/document/{allowed.id}?pass_id={bad['pass_id']}"):
        assert client.get(url, headers=headers).status_code == 403, url
    fine = client.get(f"/api/source-settings/resolve?document_id={allowed.id}&segment_id={good['segment_id']}",
                      headers=headers)
    assert fine.status_code == 200, fine.text[:200]


def test_a_list_of_documents_leaves_out_the_denied_one(denied_and_allowed, db):
    client, headers, denied, allowed = denied_and_allowed
    _cite(db, denied, "A Secret Letter"), _cite(db, allowed, "An Open Letter")
    bib = client.get("/api/citations/export", params={"document_ids": [denied.id, allowed.id]}, headers=headers)
    assert bib.status_code == 200
    assert "Secret" not in bib.text and "Open Letter" in bib.text
    assert bib.headers["X-Fichero-Withheld-Documents"] == "1"
    segments = client.get("/api/segments", params={"document_ids": f"{denied.id},{allowed.id}"}, headers=headers)
    assert segments.status_code == 200 and segments.json()["withheld_documents"] == 1


def test_a_signs_instances_leave_out_a_denied_page(denied_and_allowed, db):
    client, headers, denied, allowed = denied_and_allowed
    seg = _make_segment(db, document_id=allowed.id, pass_id=_make_pass(db, allowed.id).id, rect=[0.1, 0.1, 0.2, 0.05])
    sign = DeclaredSign(name="a ligature", picture_segment_id=seg.id, code_point="U+F1AC")
    db.save(sign)
    for doc in (denied, allowed):
        db.save(ContentRepresentation(document_id=doc.id, kind="transcription", content="ab",
                                      source_anchor=SourceAnchor(document_id=doc.id)))
    body = client.get(f"/api/signs/{sign.id}/instances", headers=headers).json()
    assert [item["document_id"] for item in body["items"]] == [allowed.id]
    assert body["withheld"] == 1 and body["total"] == 1


def test_a_hand_lists_only_what_the_caller_may_read(denied_and_allowed, db):
    client, headers, denied, allowed = denied_and_allowed
    hand = Hand(label="hand B")
    db.save(hand)
    for doc in (denied, allowed):
        seg = _make_segment(db, document_id=doc.id, pass_id=_make_pass(db, doc.id).id, rect=[0.1, 0.1, 0.2, 0.05])
        db.save(HandAttribution(hand_id=hand.id, segment_id=seg.id))
    body = client.get(f"/api/hands/{hand.id}/attributions", headers=headers).json()
    assert len(body["items"]) == 1 and body["withheld"] == 1


def test_a_bookmark_to_a_denied_page_does_not_hand_it_over(denied_and_allowed, db):
    client, headers, denied, allowed = denied_and_allowed
    for doc, expected in ((denied, 403), (allowed, 200)):
        bookmark = Document(name=f"to {doc.name}", doc_type=DocType.file, node_kind="alias", alias_target_id=doc.id,
                        prototype_key="bookmark")
        db.save(bookmark)
        assert client.get(f"/api/bookmarks/{bookmark.id}/resolve", headers=headers).status_code == expected


def _cite(db, doc, title):
    doc.source_metadata = SourceMetadata(title=title).model_dump(mode="json")   # the field stores a dict
    db.save(doc)


def test_the_bibtex_download_of_one_document_answers(denied_and_allowed, db):
    """`/document/{id}.bib` was registered after `/document/{id}`, which took `<id>.bib` as an id:
    every download answered 404. It answers now -- and a denied page's is refused like any read."""
    client, headers, denied, allowed = denied_and_allowed
    _cite(db, denied, "A Secret Letter"), _cite(db, allowed, "An Open Letter")
    bib = client.get(f"/api/citations/document/{allowed.id}.bib", headers=headers)
    assert bib.status_code == 200 and "Open Letter" in bib.text and bib.text.lstrip().startswith("@")
    assert client.get(f"/api/citations/document/{denied.id}.bib", headers=headers).status_code == 403
    styled = client.get(f"/api/citations/document/{allowed.id}", headers=headers)   # its neighbour still answers
    assert styled.status_code == 200 and styled.json()["document_id"] == allowed.id


def test_every_listing_of_documents_leaves_out_a_denied_one(denied_and_allowed, multiuser_client, app_db, users, db):
    """`GET /api/documents` listed a denied document (#5180 follow-up), and so did every list of
    document rows: roots, a folder's children, a page's ancestors, bookmarks, trash."""
    client, headers, denied, allowed = denied_and_allowed
    folder = Document(name="letters", doc_type=DocType.folder)
    db.save(folder)
    inside_denied = Document(name="secret child", doc_type=DocType.file, parent_id=folder.id)
    inside_allowed = Document(name="open child", doc_type=DocType.file, parent_id=folder.id)
    db.save(inside_denied), db.save(inside_allowed)
    _override(app_db, users.editor, multiuser_client[2], inside_denied.id, "deny")

    def names(url, **params):
        response = client.get(url, params=params, headers=headers)
        assert response.status_code == 200, (url, response.text[:200])
        body = response.json()
        return {item["name"] for item in body["items"]}, body["withheld"]

    listed, withheld = names("/api/documents")
    assert "denied.jpg" not in listed and "secret child" not in listed and "allowed.jpg" in listed
    assert withheld == 2
    assert names("/api/documents", ids=f"{denied.id},{allowed.id}") == ({"allowed.jpg"}, 1)
    roots, withheld = names("/api/documents/roots")
    assert "denied.jpg" not in roots and "allowed.jpg" in roots and withheld == 1
    assert names(f"/api/documents/{folder.id}/children") == ({"open child"}, 1)


def test_a_training_set_preview_leaves_out_a_denied_page(denied_and_allowed, multiuser_client, app_db, users, db):
    """WHY: `GET /api/training/set` takes LISTS (`scope_ids`, `held_out_ids`), which the read check never
    sees, and a scope folder expands to its pages. Unfiltered, a viewer denied a page got its name and id
    back in the preview's held-out and missing lists, and a training set built on their say-so would
    hold it. With Multi-user on, a page the caller may not read is in no part of the preview -- named
    directly, under a folder they may read, or held out."""
    client, headers, denied, allowed = denied_and_allowed
    folder = Document(name="letters", doc_type=DocType.folder)
    db.save(folder)
    secret = Document(name="secret page", doc_type=DocType.page, parent_id=folder.id, path="/secret.jpg")
    shown = Document(name="open page", doc_type=DocType.page, parent_id=folder.id, path="/open.jpg")
    db.save(secret), db.save(shown)
    _override(app_db, users.editor, multiuser_client[2], secret.id, "deny")

    response = client.get("/api/training/set", headers=headers, params={
        "teacher": "nobody", "scope_ids": [folder.id, denied.id, allowed.id],
        "held_out_ids": [secret.id, denied.id, shown.id]})
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert secret.id not in response.text and denied.id not in response.text, body
    assert [h["document_id"] for h in body["held_out"]] == [shown.id]
    assert [m["document_id"] for m in body["missing"]] == [allowed.id]   # no teacher pass: missing, still named


def test_a_reading_at_scale_over_a_folder_with_a_denied_page_is_refused(multiuser_client, app_db, users, db,
                                                                        monkeypatch):
    """WHY (#5475): a reading run SENDS every page under its `scope_ids` to Hugging Face, but the action
    layer checks only the ids the request names. A folder the caller may read can hold a page denied on
    its own; unchecked, an editor could ship that page's image off the Mac by naming its folder. Under
    Multi-user the run is refused, nothing queued -- the same rule as training, check and evaluation
    starts (`authz.assert_can_read_every`). A folder holding only readable pages still starts, and the
    owner's request over the very same folder is unchanged. The far side is a fake: nothing is sent."""
    from fichero_server.remote_read import job as read_job

    client, login, library_path = multiuser_client
    _grant_role(app_db, users.editor, library_path, "editor")
    letters = Document(name="letters", doc_type=DocType.folder)
    open_folder = Document(name="open", doc_type=DocType.folder)
    db.save(letters), db.save(open_folder)
    secret = Document(name="secret page", doc_type=DocType.page, parent_id=letters.id, path="/secret.jpg")
    shown = Document(name="open page", doc_type=DocType.page, parent_id=open_folder.id, path="/open.jpg")
    db.save(secret), db.save(shown)
    _override(app_db, users.editor, library_path, secret.id, "deny")
    started = []
    monkeypatch.setattr(read_job, "start", lambda db, request, *, started_by, **kw: started.append(
        request.scope_ids) or {"job_id": f"job-{len(started)}", "flavor": request.flavor})

    def start(headers, scope_ids):
        return client.post("/api/reading-at-scale", headers=headers, json={
            "scope_ids": scope_ids, "card": "k", "pages_may_leave": True})

    editor = login("editor")
    refused = start(editor, [letters.id])
    assert refused.status_code == 403, refused.text[:300]
    refused_by_page = start(editor, [secret.id])
    assert refused_by_page.status_code == 403, refused_by_page.text[:300]
    assert started == []                                   # nothing queued, nothing sent

    ok = start(editor, [open_folder.id])
    assert ok.status_code == 200, ok.text[:300]
    # The owner (bootstrap) reads everything: the same folder starts, the request unchanged.
    from fichero_server.actions.registry import ActionContext, registry
    from fichero_server.remote_read.job import ReadAtScaleRequest

    owner = registry.invoke(db, "reading.start_at_scale", ReadAtScaleRequest(
        scope_ids=[letters.id], card="k", pages_may_leave=True).model_dump(),
        ActionContext(actor="owner", library_path=library_path, is_bootstrap=True))
    assert owner.result["job_id"] == "job-2"
    assert started == [[open_folder.id], [letters.id]]
