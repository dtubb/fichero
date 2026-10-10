"""Find the Documents through its routes, tested to the spec (spec: docs/contributor_manual/specs/source/finding-documents.md).

`finddocs.job.any-box`, `finddocs.leaves-first`, `finddocs.accept-makes-groups`, `finddocs.corrections-teach`
(rejections kept), `finddocs.mcp-cli` (the routes the MCP and CLI are generated from). A project holds a folder of
photographs (PNG pages drawn here: written pages dark with text, blank versos with faint bleed-through, second shots
of one leaf moved a pixel) whose readings are transcription artifacts, as a reader leaves them. Everything goes
through `POST /api/find-documents/runs`, the job as the scheduler runs it, the proposal routes, accept and reject,
and `/api/actions/audit/{id}/undo`.
"""
from __future__ import annotations

import random

import pytest
from PIL import Image, ImageDraw

from fichero_server.execution import jobs
from fichero_server.models import Artifact, DocType, Document, FileType
from fichero_server.models.canvas import CanvasLayout
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from tests.unit.finddocs.boxes import correspondence_box, istmina_box


def _image(path, *, blank: bool, seed: str, shift: int = 0):
    image = Image.new("L", (240, 320), 232)
    draw = ImageDraw.Draw(image)
    rng = random.Random(seed)
    for row in range(24, 300, 12):
        x = 16
        while x < 220:
            width = rng.randint(6, 22)
            # Blank versos show only faint bleed-through, much lighter than ink.
            draw.rectangle([x + shift, row, x + width + shift, row + 4], fill=205 if blank else 40)
            x += width + rng.randint(4, 9)
        if blank and row > 120:
            break
    image.save(path)
    return path


def _project(db, tmp_path, pages):
    folder = Document(name="1948 Sentencias", doc_type=DocType.folder)
    db.save(folder)
    ids = {}
    for i, page in enumerate(pages):
        seed = page.repeats or page.id.replace("-again", "")
        path = _image(tmp_path / f"{page.id}.png", blank=page.blank, seed=seed, shift=1 if page.repeats else 0)
        doc = Document(name=f"IMG_{i:04d}.png", doc_type=DocType.file, file_type=FileType.image, path=str(path),
                       parent_id=folder.id, sort_order=i)
        db.save(doc)
        ids[page.id] = doc.id
        if page.text:
            db.save(Artifact(document_id=doc.id, artifact_type="transcription", content=page.text, model="teacher",
                             provider="openrouter"))
    return folder, ids


def _run(client, db, scope_ids, **extra):
    r = client.post("/api/find-documents/runs", json={"scope_ids": scope_ids, **extra})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    kind, subject = db.execute_fetchone("SELECT kind, subject FROM jobs WHERE id = ?", [job_id])
    assert kind == "find-documents-in-a-folder"
    db.execute("UPDATE jobs SET state = 'running' WHERE id = ? AND state = 'waiting'", [job_id])
    jobs.KINDS[kind].run(db, subject)
    status = client.get(f"/api/find-documents/runs/{job_id}")
    assert status.status_code == 200, status.text
    return status.json()


def _proposal(client, proposal_id):
    r = client.get(f"/api/find-documents/proposals/{proposal_id}")
    assert r.status_code == 200, r.text
    return r.json()


def _children(db, parent_id):
    return sorted((d for d in db.query(Document, parent_id=parent_id) if not d.deleted_at),
                  key=lambda d: (d.sort_order or 0, d.id))


@pytest.fixture
def istmina(db, tmp_path, jobs_run_by_the_test):
    pages, truth = istmina_box()
    folder, ids = _project(db, tmp_path, pages)
    return {"folder": folder, "ids": ids, "pages": pages, "truth": [[ids[p] for p in doc] for doc in truth]}


def test_finddocs_job_proposes_and_changes_nothing(client, db, istmina):
    """`finddocs.job.any-box` + `finddocs.leaves-first`: one job on the folder stores one proposal, reading the
    images' ink as well as the text; the folder and its pages are as they were."""
    folder = istmina["folder"]
    before = [(d.id, d.parent_id, d.sort_order, d.prototype_key) for d in _children(db, folder.id)]
    run = _run(client, db, [folder.id], accept_above=None)
    assert run["state"] in ("running", "done") and "8 documents proposed" in run["reason"]
    assert "waiting for you" in run["reason"]
    (proposal_id,) = run["proposal_ids"]
    proposal = _proposal(client, proposal_id)
    assert proposal["folder_id"] == folder.id
    assert [d["page_ids"] for d in proposal["documents"]] == istmina["truth"]
    assert {d["kind"] for d in proposal["documents"]} == {"Sentencia"}
    assert {d["state"] for d in proposal["documents"]} == {"proposed"}
    kinds = [f["kind"] for f in proposal["findings"]]
    assert kinds.count("blank-verso") == 34 and kinds.count("duplicate-shot") == 2
    ids = istmina["ids"]
    assert {(f["page_id"], f["of_page_id"]) for f in proposal["findings"] if f["kind"] == "duplicate-shot"} == {
        (ids[p.id], ids[p.repeats]) for p in istmina["pages"] if p.repeats}
    assert [(d.id, d.parent_id, d.sort_order, d.prototype_key) for d in _children(db, folder.id)] == before
    listed = client.get("/api/find-documents/proposals", params={"folder_id": folder.id}).json()
    assert [p["id"] for p in listed["items"]] == [proposal_id] and listed["count"] == 1
    # Stored as a hypothesis: a grouping artifact on the folder, never a change.
    (artifact,) = db.query(Artifact, document_id=folder.id, artifact_type="grouping")
    assert artifact.id == proposal_id


def test_finddocs_accept_makes_groups_with_prototypes_and_one_undo_restores(client, db, istmina):
    """`finddocs.accept-makes-groups`: accepting makes a group node of each document's pages in order, with its
    prototype (made, since the project had none), lays the canvas out, and one undo restores the folder."""
    folder = istmina["folder"]
    before = [(d.id, d.parent_id, d.sort_order) for d in _children(db, folder.id)]
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    assert not db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key="sentencia")
    r = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={})
    assert r.status_code == 200, r.text
    accepted = r.json()
    assert accepted["accepted"] == list(range(8)) and len(accepted["groups_made"]) == 8
    groups = _children(db, folder.id)
    assert [g.id for g in groups] == accepted["groups_made"]
    for group, pages in zip(groups, istmina["truth"]):
        assert group.doc_type == DocType.group and group.prototype_key == "sentencia"
        assert [c.id for c in db.query(Document, parent_id=group.id)] and \
            [m["id"] for m in group.metadata["group_members"]] == pages
    assert groups[0].name == "Sentencia 1948-01-12"
    assert db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key="sentencia")
    rows = {row.item_id: row for row in db.query(CanvasLayout, folder_id=folder.id)}
    assert set(rows) == {f"doc:{g}" for g in accepted["groups_made"]}
    states = [d["state"] for d in accepted["proposal"]["documents"]]
    assert states == ["accepted"] * 8
    # Accepting again accepts nothing: every document is already accepted.
    again = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={}).json()
    assert again["accepted"] == [] and again["groups_made"] == []

    undo = client.post(f"/api/actions/audit/{accepted['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    assert [(d.id, d.parent_id, d.sort_order) for d in _children(db, folder.id)] == before
    assert not [d for d in db.query(Document, doc_type=DocType.group) if not d.deleted_at]
    assert not db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key="sentencia")
    assert not db.query(CanvasLayout, folder_id=folder.id)
    assert {d["state"] for d in _proposal(client, proposal_id)["documents"]} == {"proposed"}
    # Redo (undoing the undo) accepts them again.
    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 200, redo.text
    assert len([d for d in _children(db, folder.id) if d.doc_type == DocType.group]) == 8


def test_finddocs_accept_above_a_confidence_and_reject_are_kept(client, db, tmp_path, jobs_run_by_the_test):
    """Accept All Above a Confidence, a one-page document, a proposed group of documents, and a rejection kept
    for learning (`finddocs.corrections-teach`), each undone as one."""
    pages, truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    proposal = _proposal(client, proposal_id)
    assert [d["page_ids"] for d in proposal["documents"]] == [[ids[p] for p in doc] for doc in truth]
    confidences = [d["confidence"] for d in proposal["documents"]]

    sure = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={"min_confidence": 0.9}).json()
    assert sure["accepted"] == [i for i, c in enumerate(confidences) if c >= 0.9]
    client.post(f"/api/actions/audit/{sure['audit_id']}/undo").raise_for_status()

    # The cable is one page: it stays that page, with its prototype.
    cable = client.post(f"/api/find-documents/proposals/{proposal_id}/accept",
                        json={"document_indexes": [1], "arrange": False}).json()
    assert cable["groups_made"] == []
    page = db.get(Document, ids["d2-p1"])
    assert page.prototype_key == "cable" and page.parent_id == folder.id
    client.post(f"/api/actions/audit/{cable['audit_id']}/undo").raise_for_status()
    assert db.get(Document, ids["d2-p1"]).prototype_key is None
    assert not db.query(ClassificationValue, dimension=ClassificationDimension.document_prototype, key="cable")

    # A letter and its reply, accepted together, become one group of the two documents, in order.
    pair = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={"document_indexes": [0, 2]}).json()
    letter, case = pair["groups_made"][0], pair["groups_made"][-1]
    assert len(pair["groups_made"]) == 2
    assert [m["id"] for m in db.get(Document, case).metadata["group_members"]] == [letter, ids["d3-p1"]]
    assert pair["proposal"]["groups"][0]["state"] == "accepted"
    client.post(f"/api/actions/audit/{pair['audit_id']}/undo").raise_for_status()
    assert [d.id for d in _children(db, folder.id)] == [ids[p.id] for p in pages]

    r = client.post(f"/api/find-documents/proposals/{proposal_id}/reject", json={"document_indexes": [4]})
    assert r.status_code == 200, r.text
    assert r.json()["documents"][4]["state"] == "rejected"
    assert client.post(f"/api/find-documents/proposals/{proposal_id}/accept",
                       json={"document_indexes": [4]}).json()["accepted"] == []
    assert client.post(f"/api/find-documents/proposals/{proposal_id}/reject",
                       json={"document_indexes": [99]}).status_code == 404


def test_finddocs_run_accepts_by_itself_above_its_setting(client, db, tmp_path, jobs_run_by_the_test):
    """A run with `accept_above` (the recipe step's setting) accepts the documents that sure and leaves the rest."""
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    run = _run(client, db, [folder.id], accept_above=0.8)
    proposal = _proposal(client, run["proposal_ids"][0])
    sure = [d["index"] for d in proposal["documents"] if d["confidence"] >= 0.8]
    assert sure
    assert [d["index"] for d in proposal["documents"] if d["state"] == "accepted"] == sure
    assert f"{len(sure)} accepted" in run["reason"]


def test_finddocs_proposes_only_by_default(client, db, tmp_path, jobs_run_by_the_test):
    """`finddocs.recipe-step` (ruled 2026-10-10, #5550): the auto-accept is off until a box a person broke down
    is scored, so left out a run proposes every document for a person -- the route (so the MCP and CLI generated
    from it) and the recipe step share the one setting, `finddocs.AUTO_ACCEPT_ABOVE`. A run given a level still
    accepts the documents at least that sure."""
    from fichero_server import finddocs
    from fichero_server.models.found_documents import FindDocumentsRequest

    assert finddocs.AUTO_ACCEPT_ABOVE is None
    assert FindDocumentsRequest(scope_ids=["x"]).accept_above is None
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    waiting = _run(client, db, [folder.id])  # no accept_above: the default
    assert {d["state"] for d in _proposal(client, waiting["proposal_ids"][0])["documents"]} == {"proposed"}
    assert "waiting for you" in waiting["reason"]
    again = tmp_path / "again"
    again.mkdir()
    folder2, _ = _project(db, again, pages)
    run = _run(client, db, [folder2.id], accept_above=0.95)
    proposal = _proposal(client, run["proposal_ids"][0])
    sure = [d["index"] for d in proposal["documents"] if d["confidence"] >= 0.95]
    assert sure and len(sure) < len(proposal["documents"]), "the box has documents on both sides of 95%"
    assert [d["index"] for d in proposal["documents"] if d["state"] == "accepted"] == sure
    assert f"{len(sure)} accepted (at least 95% sure)" in run["reason"]


def test_finddocs_selection_and_unknown_ids(client, db, istmina):
    """A selection of pages is found within its folder; an unknown id is refused before any job is queued."""
    ids = istmina["ids"]
    chosen = [ids[p.id] for p in istmina["pages"][:18]]  # the first two judgments
    run = _run(client, db, chosen, accept_above=None)
    proposal = _proposal(client, run["proposal_ids"][0])
    assert [d["page_ids"] for d in proposal["documents"]] == istmina["truth"][:2]
    assert client.post("/api/find-documents/runs", json={"scope_ids": ["nope"]}).status_code == 404
    assert client.get("/api/find-documents/proposals/nope").status_code == 404
    assert client.get("/api/find-documents/runs/nope").status_code == 404


def _kind_source(db, node_id):
    return ((db.get(Document, node_id).metadata or {}).get("attribute_sources") or {}).get("prototype")


def _accept_audit(db, run_id):
    from fichero_server.models import ActionAudit

    (audit,) = [a for a in db.query(ActionAudit, action_name="finddocs.accept") if a.run_id == run_id]
    return audit


def _proposed_kind(db, node_id):
    return ((db.get(Document, node_id).metadata or {}).get("proposed_attributes") or {}).get("prototype")


def test_finddocs_run_accept_is_boundaries_only(client, db, tmp_path, jobs_run_by_the_test):
    """Ruled 2026-10-10 (`finddocs.accept-makes-groups`, `finddocs.corrections-teach`): the run's own accept takes
    a document's boundaries only. Its kind is left as a proposed kind citing the run (machine: its proposal, its
    method), on a one-page document's page and on a group node alike, never assigned; a kind a person chose is left
    alone; cases stay proposals; each document says the run decided it; one undo restores it all."""
    from fichero_server.api.routes.document.classifications import ClassificationCreateRequest, create_value_impl
    from fichero_server.api.routes.document.documents import PrototypeAssignRequest, assign_document_prototype_impl

    pages, _truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    create_value_impl(db, ClassificationCreateRequest(dimension=ClassificationDimension.document_prototype,
                                                      key="factura", label="Factura"))
    assign_document_prototype_impl(db, ids["d7-p1"], PrototypeAssignRequest(prototype_key="factura"))
    run = _run(client, db, [folder.id], accept_above=0.8)
    job_id = run["job_id"]
    proposal = _proposal(client, run["proposal_ids"][0])
    accepted = [d for d in proposal["documents"] if d["state"] == "accepted"]
    one_page = [d for d in accepted if len(d["page_ids"]) == 1 and d["page_ids"][0] != ids["d7-p1"]]
    grouped = [d for d in accepted if len(d["page_ids"]) >= 2]
    assert one_page and grouped, "the box has one-page and longer documents above 80%"
    for document in accepted:
        assert document["decided_by"] == {"by": "run", "run_id": job_id, "actor": None}
    for document in one_page + grouped:
        node = document["accepted_as"]
        assert db.get(Document, node).prototype_key is None and _kind_source(db, node) is None
        proposed = _proposed_kind(db, node)
        assert proposed["value"] == document["prototype_key"] and proposed["state"] == "proposed"
        source = proposed["source"]
        assert source["by"] == "machine" and "accepted_by" not in source
        assert source["run_id"] == job_id and source["artifact_id"] == proposal["id"]
        assert source["model"] == "find-documents/rules-1" and source["tool"] == "find-documents"
    # The receipt's page had a person's kind: the run's accept left it, and who chose it, alone.
    assert [d for d in accepted if d["page_ids"] == [ids["d7-p1"]]], "the receipt is above 80%"
    assert db.get(Document, ids["d7-p1"]).prototype_key == "factura"
    assert _kind_source(db, ids["d7-p1"]) == {"by": "person"} and _proposed_kind(db, ids["d7-p1"]) is None
    assert {g["state"] for g in proposal["groups"]} <= {"proposed"}, "cases wait for a person"

    undo = client.post(f"/api/actions/audit/{_accept_audit(db, job_id).id}/undo")
    assert undo.status_code == 200, undo.text
    for document in one_page:
        page = db.get(Document, document["accepted_as"])
        assert page.prototype_key is None and _proposed_kind(db, page.id) is None
    assert _kind_source(db, ids["d7-p1"]) == {"by": "person"}
    assert {(d["state"], d["decided_by"]) for d in _proposal(client, proposal["id"])["documents"]} == {
        ("proposed", None)}


def test_finddocs_person_accept_records_the_person(client, db, tmp_path, jobs_run_by_the_test):
    """A person's accept records the run's proposal with `accepted_by` the person, on the page and on the group;
    a person's reject says the person decided; undo restores both."""
    pages, _truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    r = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={"document_indexes": [0, 1]})
    assert r.status_code == 200, r.text
    accepted = r.json()
    letter, cable = accepted["proposal"]["documents"][0], accepted["proposal"]["documents"][1]
    person = letter["decided_by"]["actor"]
    assert letter["decided_by"]["by"] == "person" and person and cable["decided_by"] == letter["decided_by"]
    for document in (letter, cable):
        source = _kind_source(db, document["accepted_as"])
        assert source["by"] == "machine" and source["accepted_by"] == person
        assert source["artifact_id"] == proposal_id
    assert cable["accepted_as"] == ids["d2-p1"] and db.get(Document, ids["d2-p1"]).prototype_key == "cable"
    client.post(f"/api/actions/audit/{accepted['audit_id']}/undo").raise_for_status()
    assert db.get(Document, ids["d2-p1"]).prototype_key is None and _kind_source(db, ids["d2-p1"]) is None
    restored = _proposal(client, proposal_id)["documents"]
    assert (restored[0]["decided_by"], restored[1]["decided_by"]) == (None, None)

    rejected = client.post(f"/api/find-documents/proposals/{proposal_id}/reject", json={"document_indexes": [4]})
    assert rejected.json()["documents"][4]["decided_by"] == {"by": "person", "run_id": None, "actor": person}


def test_finddocs_accept_refuses_pages_grouped_since(client, db, tmp_path, jobs_run_by_the_test):
    """Accepting a document whose pages were grouped since it was proposed is refused in words, naming the
    document and the page, and nothing changes: no page is pulled out of the group already made."""
    pages, _truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    made = client.post("/api/documents/groups", json={"name": "By hand", "child_ids": [ids["d1-p2"], ids["d2-p1"]]})
    assert made.status_code == 200, made.text
    before = sorted((d.id, d.parent_id, d.sort_order) for d in db.query(Document) if not d.deleted_at)
    r = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={})
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "document 1" in detail and f"'{db.get(Document, ids['d1-p2']).name}'" in detail and "By hand" in detail
    assert before == sorted((d.id, d.parent_id, d.sort_order) for d in db.query(Document) if not d.deleted_at)
    assert {d["state"] for d in _proposal(client, proposal_id)["documents"]} == {"proposed"}
    # A document none of whose pages moved is still accepted.
    ok = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={"document_indexes": [2]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["accepted"] == [2]
    # A deleted page is refused too.
    gone = db.get(Document, ids["d4-p1"])
    gone.deleted_at = gone.created_at
    db.save(gone)
    r = client.post(f"/api/find-documents/proposals/{proposal_id}/accept", json={"document_indexes": [3]})
    assert r.status_code == 409 and "deleted" in r.json()["detail"]


def test_finddocs_pages_cut_from_a_photograph_accept_and_refuse(client, db):
    """A page cut from a photograph has the photograph as its parent: a document of such pages is accepted (they
    are the folder's loose pages), and refused once its pages are grouped."""
    from fichero_server.finddocs import store
    from fichero_server.models.found_documents import DocumentsProposal, ProposedDocument

    folder = Document(name="Spreads", doc_type=DocType.folder)
    db.save(folder)
    photo = Document(name="IMG_0001.jpg", doc_type=DocType.file, file_type=FileType.image, parent_id=folder.id)
    db.save(photo)
    cut = []
    for i in range(4):
        page = Document(name=f"IMG_0001 page {i + 1}", doc_type=DocType.chunk, parent_id=photo.id, sort_order=i)
        db.save(page)
        cut.append(page.id)
    proposal = store.store(db, DocumentsProposal(id="", folder_id=folder.id, page_ids=cut, documents=[
        ProposedDocument(index=0, name="Carta 1", page_ids=cut[:2], first_position=0, last_position=1, confidence=0.7),
        ProposedDocument(index=1, name="Carta 2", page_ids=cut[2:], first_position=2, last_position=3, confidence=0.7),
    ]), folder.id)
    r = client.post(f"/api/find-documents/proposals/{proposal.id}/accept", json={"document_indexes": [0]})
    assert r.status_code == 200, r.text
    assert {c.id for c in db.query(Document, parent_id=r.json()["groups_made"][0])} == set(cut[:2])
    client.post("/api/documents/groups", json={"name": "Moved", "child_ids": cut[2:]}).raise_for_status()
    r = client.post(f"/api/find-documents/proposals/{proposal.id}/accept", json={"document_indexes": [1]})
    assert r.status_code == 409 and "IMG_0001 page 3" in r.json()["detail"]


def test_finddocs_a_second_run_supersedes_the_first(client, db, tmp_path, jobs_run_by_the_test):
    """A second run on the same pages supersedes the first proposal: it is kept (its answers teach), left out of
    the folder's listing unless asked for, and accepting it is refused in words."""
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    first = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    assert _proposal(client, first)["state"] == "current"
    second = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    old = _proposal(client, first)
    assert old["state"] == "superseded" and old["superseded_by"] == second
    assert _proposal(client, second)["state"] == "current"
    listed = client.get("/api/find-documents/proposals", params={"folder_id": folder.id}).json()
    assert [p["id"] for p in listed["items"]] == [second]
    everything = client.get("/api/find-documents/proposals",
                            params={"folder_id": folder.id, "include_superseded": True}).json()
    assert [p["id"] for p in everything["items"]] == [second, first]
    r = client.post(f"/api/find-documents/proposals/{first}/accept", json={})
    assert r.status_code == 409 and "replaced by a later run" in r.json()["detail"]
    assert {d["state"] for d in _proposal(client, first)["documents"]} == {"proposed"}
    assert client.post(f"/api/find-documents/proposals/{second}/accept", json={}).status_code == 200


def test_finddocs_redo_of_an_accept_a_later_run_replaced_is_refused_in_words(client, db, tmp_path,
                                                                             jobs_run_by_the_test):
    """Accept, undo, then a later run supersedes the proposal: redoing the accept is refused (409, in words),
    never a 500, and changes nothing."""
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    first = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    accepted = client.post(f"/api/find-documents/proposals/{first}/accept", json={"document_indexes": [0]})
    assert accepted.status_code == 200, accepted.text
    undo = client.post(f"/api/actions/audit/{accepted.json()['audit_id']}/undo")
    assert undo.status_code == 200, undo.text
    _run(client, db, [folder.id], accept_above=None)
    redo = client.post(f"/api/actions/audit/{undo.json()['audit_id']}/undo")
    assert redo.status_code == 409, redo.text
    assert "replaced by a later run" in redo.json()["detail"]
    assert {d["state"] for d in _proposal(client, first)["documents"]} == {"proposed"}
