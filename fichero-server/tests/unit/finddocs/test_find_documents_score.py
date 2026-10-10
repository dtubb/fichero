"""Scoring a Find the Documents proposal against a person's breakdown, tested to the spec (`finddocs.scored`).

Spec: docs/contributor_manual/specs/source/finding-documents.md. A person's breakdown is the documents a person
accepted or adjusted; `POST /api/find-documents/score` scores the folder's proposal against it and keeps the score
on the folder; `GET /api/find-documents/score` lists the scores with `suggested_accept_above`, the lowest level the
run was at least 99% right at over at least 50 joins. The folder is `boxes.correspondence_box` (documents 0
[d1-p1, d1-p1v, d1-p2, d1-p2v], 1 [d2-p1], 2 [d3-p1], 3 [d4-p1, d4-p1v, d4-p2, d4-p2v], 4 [d5-p1], ...), which the
run gets right.
"""
from __future__ import annotations

import pytest

from fichero_server import finddocs
from fichero_server.finddocs import score as finddocs_score
from fichero_server.models import Artifact, Document
from fichero_server.models.found_documents import (
    DocumentsProposal,
    FindDocumentsScore,
    FoundDocumentsDecision,
    LevelAgreement,
    ProposedDocument,
    ProposedJoin,
)
from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _project, _proposal, _run


@pytest.fixture
def box(client, db, tmp_path, jobs_run_by_the_test):
    pages, truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    return {"folder": folder, "ids": ids, "id": proposal_id, "proposal": _proposal(client, proposal_id)}


def _score(client, folder_id, **extra):
    return client.post("/api/find-documents/score", json={"folder_id": folder_id, **extra})


def test_finddocs_score_against_what_a_person_accepted_and_adjusted(client, db, box):
    """A person accepts documents 0 and 1 and splits document 3 at its second page (the run had one document
    there). Judged joins are those touching the person's documents: six, of which the run called four boundaries,
    all right, and missed the split: precision 1.0, recall 0.8; documents 0 and 1 are exact, the split halves
    are not; the two accepted kinds are confirmed and right. The score is stored and GET returns it."""
    ids, folder = box["ids"], box["folder"]
    r = client.post(f"/api/find-documents/proposals/{box['id']}/accept", json={"document_indexes": [0, 1]})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/find-documents/proposals/{box['id']}/split",
                    json={"document_index": 3, "page_id": ids["d4-p2"]})
    assert r.status_code == 200, r.text

    r = _score(client, folder.id)
    assert r.status_code == 200, r.text
    body = r.json()
    score = body["score"]
    assert (score["folder_id"], score["proposal_id"], score["job_id"]) == (
        folder.id, box["id"], box["proposal"]["job_id"])
    assert score["scored_at"] and body["audit_id"]
    assert (score["documents"], score["joins"], score["boundaries_proposed"], score["boundaries_actual"]) == (4, 6, 4, 5)
    assert (score["precision"], score["recall"], score["exact_documents"]) == (1.0, 0.8, 2)
    kinds = [d["prototype_key"] for d in box["proposal"]["documents"][:2] if d["prototype_key"]]
    assert (score["kinds_confirmed"], score["kinds_right"]) == (len(kinds), len(kinds)) and kinds
    assert score["kind_accuracy"] == 1.0
    at_half = next(lv for lv in score["levels"] if lv["level"] == 0.5)
    assert (at_half["joins"], at_half["agreed"]) == (6, 5)
    assert [lv["level"] for lv in score["levels"]] == list(finddocs_score.LEVELS)
    assert body["suggested_accept_above"] is None and body["min_joins"] == 50

    # Kept on the folder, one artifact, and listed by GET (also for the folder alone).
    (artifact,) = db.query(Artifact, artifact_type="finddocs_score")
    assert artifact.document_id == folder.id and artifact.id == score["id"]
    for query in ("", f"?folder_id={folder.id}"):
        listed = client.get(f"/api/find-documents/score{query}")
        assert listed.status_code == 200, listed.text
        assert listed.json()["items"] == [score] and listed.json()["count"] == 1
        assert listed.json()["suggested_accept_above"] is None
    # The suggestion never switches the auto-accept on.
    assert finddocs.AUTO_ACCEPT_ABOVE is None


def test_finddocs_score_a_changed_kind_is_a_correction(client, db, box):
    """A kind a person accepted and then changed on the node counts as a wrong kind."""
    r = client.post(f"/api/find-documents/proposals/{box['id']}/accept", json={"document_indexes": [0, 1]})
    assert r.status_code == 200, r.text
    node = db.get(Document, r.json()["proposal"]["documents"][0]["accepted_as"])
    node.prototype_key = "something_else"
    db.save(node)
    score = _score(client, box["folder"].id).json()["score"]
    assert (score["kinds_confirmed"], score["kinds_right"], score["kind_accuracy"]) == (2, 1, 0.5)


def test_finddocs_score_refuses_a_folder_no_person_decided(client, db, tmp_path, jobs_run_by_the_test):
    """A folder whose documents only the run accepted (its own auto-accept) has no person's breakdown: 422, in
    words, and nothing stored. A folder never run is refused too; an unknown folder is 404."""
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    r = _score(client, folder.id)
    assert r.status_code == 422 and "has not been run" in r.json()["detail"]
    _run(client, db, [folder.id], accept_above=0.0)
    r = _score(client, folder.id)
    assert r.status_code == 422, r.text
    assert "accepted or adjusted by a person" in r.json()["detail"]
    assert not db.query(Artifact, artifact_type="finddocs_score")
    assert _score(client, "no-such-folder").status_code == 404


def _doc(index, pages):
    return ProposedDocument(index=index, name=f"D{index}", page_ids=pages, first_position=0, last_position=0,
                            confidence=1.0, adjusted_by=FoundDocumentsDecision(by="person", actor="p"))


def test_finddocs_score_agreement_at_each_level():
    """Constructed: pages a..f, the run's probability that a document starts at each; the person's documents are
    [a, b], [c, d], [e] (f untouched, so the join e|f is still judged, being at e's end, and is a boundary).
    Calls: b 0.2 (runs on, 0.8 sure, right), c 0.97 (boundary, right), d 0.6 (boundary, 0.6 sure, wrong),
    e 0.995 (boundary, right), f 0.3 (runs on, 0.7 sure, wrong)."""
    probabilities = {"b": 0.2, "c": 0.97, "d": 0.6, "e": 0.995, "f": 0.3}
    pages = list("abcdef")
    proposal = DocumentsProposal(
        id="p", folder_id="f", page_ids=pages,
        joins=[ProposedJoin(page_id=p, previous_page_id=pages[i], probability=probabilities[p])
               for i, p in enumerate(pages[1:])],
        documents=[_doc(0, ["a", "b"]), _doc(1, ["c", "d"]), _doc(2, ["e"]), ProposedDocument(
            index=3, name="D3", page_ids=["f"], first_position=5, last_position=5, confidence=0.3)])
    numbers = finddocs_score.measure(None, proposal)
    levels = {lv.level: (lv.joins, lv.agreed) for lv in numbers["levels"]}
    assert levels == {0.5: (5, 3), 0.6: (5, 3), 0.7: (4, 3), 0.8: (3, 3), 0.9: (2, 2), 0.95: (2, 2), 0.99: (1, 1)}
    assert (numbers["boundaries_proposed"], numbers["boundaries_actual"]) == (3, 3)
    assert (round(numbers["precision"], 4), round(numbers["recall"], 4)) == (0.6667, 0.6667)
    # [a, b] exact (no start join, b runs on, c a boundary); [c, d] not (d called a boundary); [e] not (the
    # run did not end it before f).
    assert numbers["exact_documents"] == 1


def _stored(db, folder_id, scored_at, levels):
    score = FindDocumentsScore(
        id=f"s-{folder_id}-{scored_at}", folder_id=folder_id, proposal_id="p", scored_at=scored_at, documents=1,
        joins=0, boundaries_proposed=0, boundaries_actual=0, exact_documents=0,
        levels=[LevelAgreement(level=lv, joins=j, agreed=a, share=a / j if j else None) for lv, (j, a) in levels.items()])
    db.save(Artifact(id=score.id, document_id=folder_id, artifact_type="finddocs_score", provider="fichero",
                     model=finddocs_score.MODEL, data=score.model_dump(mode="json")))


def test_finddocs_suggested_accept_above_needs_fifty_joins_at_99_percent(client, db):
    """Below 50 joins no level is suggested, however right; pooled over the newest score of each folder (an older
    score of a folder not counted again), the lowest level at least 99% right over 50 joins is."""
    def at(low, high):
        return {0.5: low, 0.6: low, 0.7: low, 0.8: low, 0.9: high, 0.95: high, 0.99: high}

    _stored(db, "A", "2026-10-10T10:00:00", at((30, 28), (30, 30)))
    assert client.get("/api/find-documents/score").json()["suggested_accept_above"] is None
    _stored(db, "A", "2026-10-09T10:00:00", at((40, 40), (40, 40)))  # older: not pooled
    assert client.get("/api/find-documents/score").json()["suggested_accept_above"] is None
    _stored(db, "B", "2026-10-10T11:00:00", at((25, 24), (25, 25)))
    body = client.get("/api/find-documents/score").json()
    assert body["suggested_accept_above"] == 0.9
    assert next(lv for lv in body["levels"] if lv["level"] == 0.9)["joins"] == 55
    assert [s["folder_id"] for s in client.get("/api/find-documents/score?folder_id=A").json()["items"]] == ["A", "A"]
    assert finddocs.AUTO_ACCEPT_ABOVE is None
