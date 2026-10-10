"""Adjusting a Find the Documents proposal, tested to the spec (`finddocs.adjust`, `finddocs.corrections-teach`).

Spec: docs/contributor_manual/specs/source/finding-documents.md. A folder of letters, cables and a receipt
(`boxes.correspondence_box`: documents 0 [d1-p1, d1-p1v, d1-p2, d1-p2v], 1 [d2-p1], 2 [d3-p1],
3 [d4-p1, d4-p1v, d4-p2, d4-p2v], 4 [d5-p1], 5 [d6-p1, d6-p1-again, d6-p2], 6 [d7-p1]; "v" a blank verso,
"-again" a second shot) is proposed by a run; a person then splits, joins and moves pages through
`POST /api/find-documents/proposals/{id}/split|join|move-page`, undoes through `/api/actions/audit/{id}/undo`,
and accepts the adjusted documents.
"""
from __future__ import annotations

import pytest

from fichero_server.models import DocType, Document
from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _children, _project, _proposal, _run


@pytest.fixture
def box(client, db, tmp_path, jobs_run_by_the_test):
    pages, truth, _groups = correspondence_box()
    folder, ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id], accept_above=None)["proposal_ids"][0]
    proposal = _proposal(client, proposal_id)
    assert [d["page_ids"] for d in proposal["documents"]] == [[ids[p] for p in doc] for doc in truth]
    return {"folder": folder, "ids": ids, "id": proposal_id, "proposal": proposal}


def _post(client, box, verb, **body):
    return client.post(f"/api/find-documents/proposals/{box['id']}/{verb}", json=body)


def _pages(proposal):
    return [d["page_ids"] for d in proposal["documents"]]


def _undo(client, audit_id):
    r = client.post(f"/api/actions/audit/{audit_id}/undo")
    assert r.status_code == 200, r.text
    return r.json()


def _example(e):
    return (e["left_page_id"], e["right_page_id"], e["boundary"], e["adjustment"])


def _run_join(proposal, right_page_id):
    return next(j for j in proposal["joins"] if j["page_id"] == right_page_id)


def test_finddocs_split_makes_two_documents_and_a_boundary_example(client, db, box):
    """Splitting document 0 at its second page makes two documents, renumbers the rest, keeps the group that
    held it holding both halves, records "boundary: true" between the two pages with the run's reasons, and
    changes nothing in the library; one undo restores the proposal exactly and redo splits again."""
    ids, before = box["ids"], box["proposal"]
    children = [(d.id, d.parent_id, d.sort_order) for d in _children(db, box["folder"].id)]
    r = _post(client, box, "split", document_index=0, page_id=ids["d1-p2"])
    assert r.status_code == 200, r.text
    after = r.json()["proposal"]
    assert _pages(after) == [[ids["d1-p1"], ids["d1-p1v"]], [ids["d1-p2"], ids["d1-p2v"]], *_pages(before)[1:]]
    assert [d["index"] for d in after["documents"]] == list(range(8))
    first, second = after["documents"][0], after["documents"][1]
    person = first["adjusted_by"]
    assert person["by"] == "person" and person["actor"] and second["adjusted_by"] == person
    assert first["confidence"] == second["confidence"] == 1.0
    assert (first["first_position"], first["last_position"], second["first_position"]) == (0, 1, 2)
    assert after["documents"][2]["adjusted_by"] is None and after["documents"][2] == {
        **before["documents"][1], "index": 2}
    # The letter-and-reply group held documents 0 and 2: it now holds both halves and the reply (now 3).
    held = next(g for g in before["groups"] if 0 in g["document_indexes"])["document_indexes"]
    now = next(g for g in after["groups"] if 0 in g["document_indexes"])["document_indexes"]
    assert now == [n for i in held for n in ([0, 1] if i == 0 else [i + 1])]
    (example,) = after["examples"]
    assert r.json()["examples"] == [example]
    assert _example(example) == (ids["d1-p1v"], ids["d1-p2"], True, "split")
    assert example["decided_by"] == person and example["proposal_id"] == box["id"] and example["at"]
    join = _run_join(before, ids["d1-p2"])
    assert example["run_probability"] == join["probability"] < 0.5
    assert len(example["run_reasons"]) == len(join["signals"])
    assert [(d.id, d.parent_id, d.sort_order) for d in _children(db, box["folder"].id)] == children

    undo = _undo(client, r.json()["audit_id"])
    assert _proposal(client, box["id"]) == before
    _undo(client, undo["audit_id"])
    assert _pages(_proposal(client, box["id"])) == _pages(after)


def test_finddocs_join_removes_a_boundary_with_a_no_boundary_example(client, box):
    """Joining the cable (1) to the reply (2) makes one document of both pages, set by the person, the rest
    renumbered; the example says "boundary: false" across the join; one undo restores the proposal exactly."""
    ids, before = box["ids"], box["proposal"]
    r = _post(client, box, "join", document_index=1)
    assert r.status_code == 200, r.text
    after = r.json()["proposal"]
    assert _pages(after) == [_pages(before)[0], [ids["d2-p1"], ids["d3-p1"]], *_pages(before)[3:]]
    joined = after["documents"][1]
    assert joined["confidence"] == 1.0 and joined["adjusted_by"]["by"] == "person"
    assert (joined["first_position"], joined["last_position"]) == (4, 5)
    assert joined["kind"] == before["documents"][1]["kind"]
    for group in after["groups"]:
        assert all(0 <= i < len(after["documents"]) for i in group["document_indexes"])
    (example,) = after["examples"]
    assert _example(example) == (ids["d2-p1"], ids["d3-p1"], False, "join")
    assert example["run_probability"] == _run_join(before, ids["d3-p1"])["probability"] > 0.5
    assert example["run_reasons"]

    _undo(client, r.json()["audit_id"])
    assert _proposal(client, box["id"]) == before


def test_finddocs_move_page_moves_it_and_records_both_examples(client, box):
    """Moving the reply's (5) last page to the receipt after it, then its first page to the cable before it:
    the page changes document, both documents are set by the person, and each move records two examples (one
    document across the page's new join, a new document across the join it left); undo restores exactly."""
    ids, before = box["ids"], box["proposal"]
    r = _post(client, box, "move-page", document_index=5, to="next")
    assert r.status_code == 200, r.text
    after = r.json()["proposal"]
    assert _pages(after)[5:7] == [[ids["d6-p1"], ids["d6-p1-again"]], [ids["d6-p2"], ids["d7-p1"]]]
    assert len(after["documents"]) == 7
    assert {after["documents"][5]["adjusted_by"]["by"], after["documents"][6]["adjusted_by"]["by"]} == {"person"}
    assert after["documents"][6]["confidence"] == 1.0
    assert sorted(_example(e) for e in after["examples"]) == sorted([
        (ids["d6-p2"], ids["d7-p1"], False, "move-page"), (ids["d6-p1-again"], ids["d6-p2"], True, "move-page")])
    assert r.json()["examples"] == after["examples"]

    moved = _post(client, box, "move-page", document_index=5, to="previous")
    assert moved.status_code == 200, moved.text
    again = moved.json()["proposal"]
    assert _pages(again)[4:6] == [[ids["d5-p1"], ids["d6-p1"]], [ids["d6-p1-again"]]]
    assert sorted(_example(e) for e in moved.json()["examples"]) == sorted([
        (ids["d5-p1"], ids["d6-p1"], False, "move-page"), (ids["d6-p1"], ids["d6-p1-again"], True, "move-page")])
    assert len(again["examples"]) == 4

    _undo(client, moved.json()["audit_id"])
    assert _proposal(client, box["id"]) == after
    _undo(client, r.json()["audit_id"])
    assert _proposal(client, box["id"]) == before


def test_finddocs_adjust_out_of_range_is_refused_in_words(client, box):
    """An index or page the proposal does not have, a split at a first page, a join past the last document, a
    move with no neighbour or that would empty a document: 422 in words, and the proposal is unchanged."""
    ids, before = box["ids"], box["proposal"]
    refused = [
        ("split", {"document_index": 99, "page_id": ids["d1-p2"]}, "no document 100"),
        ("split", {"document_index": 0, "page_id": ids["d2-p1"]}, "not one of document 1's pages"),
        ("split", {"document_index": 0, "page_id": ids["d1-p1"]}, "first page"),
        ("join", {"document_index": 6}, "no document after it"),
        ("join", {"document_index": -1}, "no document 0"),
        ("move-page", {"document_index": 0, "to": "previous"}, "no document previous"),
        ("move-page", {"document_index": 1, "to": "next"}, "join it instead"),
        ("move-page", {"document_index": 7, "to": "previous"}, "no document 8"),
    ]
    for verb, body, words in refused:
        r = _post(client, box, verb, **body)
        assert r.status_code == 422, (verb, body, r.text)
        assert words in r.json()["detail"], (verb, r.json()["detail"])
    assert _post(client, box, "move-page", document_index=3, to="sideways").status_code == 422
    assert client.post("/api/find-documents/proposals/nope/join", json={"document_index": 0}).status_code == 404
    assert _proposal(client, box["id"]) == before


def test_finddocs_adjust_refuses_a_superseded_proposal_or_a_decided_document(client, db, box):
    """A document already accepted or rejected cannot be adjusted (409, in words), nor can any document of a
    proposal a later run replaced; nothing changes either time."""
    accepted = client.post(f"/api/find-documents/proposals/{box['id']}/accept",
                           json={"document_indexes": [0], "arrange": False})
    assert accepted.status_code == 200, accepted.text
    rejected = client.post(f"/api/find-documents/proposals/{box['id']}/reject", json={"document_indexes": [4]})
    assert rejected.status_code == 200, rejected.text
    now = _proposal(client, box["id"])
    for verb, body, words in [("split", {"document_index": 0, "page_id": box["ids"]["d1-p2"]}, "already accepted"),
                              ("join", {"document_index": 3}, "already rejected"),
                              ("move-page", {"document_index": 5, "to": "previous"}, "already rejected")]:
        r = _post(client, box, verb, **body)
        assert r.status_code == 409 and words in r.json()["detail"], (verb, r.text)
    assert _proposal(client, box["id"]) == now

    _run(client, db, [box["folder"].id], accept_above=None)
    old = _proposal(client, box["id"])
    assert old["state"] == "superseded"
    for verb, body in [("split", {"document_index": 5, "page_id": box["ids"]["d6-p2"]}),
                       ("join", {"document_index": 1}),
                       ("move-page", {"document_index": 3, "to": "next"})]:
        r = _post(client, box, verb, **body)
        assert r.status_code == 409 and "replaced by a later run" in r.json()["detail"], (verb, r.text)
    assert _proposal(client, box["id"]) == old


def test_finddocs_redo_of_an_adjustment_a_later_run_replaced_is_refused(client, db, box):
    """Join, undo, a later run supersedes the proposal: redoing the join is refused (409), never a 500."""
    r = _post(client, box, "join", document_index=1)
    assert r.status_code == 200, r.text
    undo = _undo(client, r.json()["audit_id"])
    _run(client, db, [box["folder"].id], accept_above=None)
    redo = client.post(f"/api/actions/audit/{undo['audit_id']}/undo")
    assert redo.status_code == 409 and "replaced by a later run" in redo.json()["detail"], redo.text
    assert _pages(_proposal(client, box["id"])) == _pages(box["proposal"])


def test_finddocs_accept_after_adjusting_groups_the_adjusted_documents(client, db, box):
    """After joining the English letter (3) and the cable (4), and splitting the reply (5, now 4) at its second
    page, accepting makes a group node of each adjusted document's pages, and the last half stays its page."""
    ids, folder = box["ids"], box["folder"]
    assert _post(client, box, "join", document_index=3).status_code == 200
    split = _post(client, box, "split", document_index=4, page_id=ids["d6-p2"])
    assert split.status_code == 200, split.text
    letter = [ids["d4-p1"], ids["d4-p1v"], ids["d4-p2"], ids["d4-p2v"], ids["d5-p1"]]
    assert _pages(split.json()["proposal"])[3:6] == [letter, [ids["d6-p1"], ids["d6-p1-again"]], [ids["d6-p2"]]]
    r = client.post(f"/api/find-documents/proposals/{box['id']}/accept",
                    json={"document_indexes": [3, 4, 5], "groups": False})
    assert r.status_code == 200, r.text
    accepted = r.json()
    joined, half = accepted["groups_made"]
    for group_id, pages in ((joined, letter), (half, [ids["d6-p1"], ids["d6-p1-again"]])):
        group = db.get(Document, group_id)
        assert group.doc_type == DocType.group and group.parent_id == folder.id
        assert [m["id"] for m in group.metadata["group_members"]] == pages
    documents = accepted["proposal"]["documents"]
    assert [d["accepted_as"] for d in documents[3:6]] == [joined, half, ids["d6-p2"]]
    assert {d["decided_by"]["by"] for d in documents[3:6]} == {"person"}
    assert len(accepted["proposal"]["examples"]) == 2
    _undo(client, accepted["audit_id"])
    assert not [d for d in db.query(Document, doc_type=DocType.group) if not d.deleted_at]
