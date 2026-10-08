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


def test_finddocs_accepts_at_95_percent_by_default(client, db, tmp_path, jobs_run_by_the_test):
    """`finddocs.recipe-step` (ruled 2026-10-08, #5550): left out, a run accepts by itself every document at least
    95% sure and proposes the rest for a person -- the route (so the MCP and CLI generated from it) and the recipe
    step share the one setting, `finddocs.AUTO_ACCEPT_ABOVE`."""
    from fichero_server import finddocs
    from fichero_server.models.found_documents import FindDocumentsRequest

    assert finddocs.AUTO_ACCEPT_ABOVE == 0.95
    assert FindDocumentsRequest(scope_ids=["x"]).accept_above == finddocs.AUTO_ACCEPT_ABOVE
    assert FindDocumentsRequest(scope_ids=["x"], accept_above=None).accept_above is None
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    run = _run(client, db, [folder.id])  # no accept_above: the default
    proposal = _proposal(client, run["proposal_ids"][0])
    sure = [d["index"] for d in proposal["documents"] if d["confidence"] >= 0.95]
    assert sure and len(sure) < len(proposal["documents"]), "the box has documents on both sides of 95%"
    assert [d["index"] for d in proposal["documents"] if d["state"] == "accepted"] == sure
    assert {d["state"] for d in proposal["documents"] if d["index"] not in sure} == {"proposed"}
    assert f"{len(sure)} accepted (at least 95% sure)" in run["reason"]
    # null leaves every document for a person.
    again = tmp_path / "again"
    again.mkdir()
    folder2, _ = _project(db, again, pages)
    waiting = _run(client, db, [folder2.id], accept_above=None)
    assert {d["state"] for d in _proposal(client, waiting["proposal_ids"][0])["documents"]} == {"proposed"}
    assert "waiting for you" in waiting["reason"]


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
