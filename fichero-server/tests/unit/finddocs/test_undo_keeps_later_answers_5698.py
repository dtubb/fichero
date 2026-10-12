"""`finddocs.undo-keeps-later-work` (#5698): undoing one answer on a proposal keeps every later answer.

Spec: docs/contributor_manual/specs/source/finding-documents.md. WHY (2026-10-11, the MCP walk): accept document 2,
reject document 0, undo the accept, and document 0 was back to proposed: every answer saved a snapshot of the
whole proposal, and its undo put the whole snapshot back. Through the routes and the one undo route, on the
drawn correspondence box.
"""
from __future__ import annotations

from tests.unit.finddocs.boxes import correspondence_box
from tests.unit.finddocs.test_find_documents_to_spec import _project, _proposal, _run


def _states(client, proposal_id):
    return {d["index"]: d["state"] for d in _proposal(client, proposal_id)["documents"]}


def _post(client, proposal_id, verb, body):
    r = client.post(f"/api/find-documents/proposals/{proposal_id}/{verb}", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _undo(client, audit_id):
    return client.post(f"/api/actions/audit/{audit_id}/undo")


def _open(client, db, tmp_path):
    pages, _truth, _groups = correspondence_box()
    folder, _ids = _project(db, tmp_path, pages)
    proposal_id = _run(client, db, [folder.id])["proposal_ids"][0]
    assert len(_states(client, proposal_id)) >= 3
    return proposal_id


def test_undoing_an_accept_keeps_a_later_reject(client, db, tmp_path, jobs_run_by_the_test):
    proposal_id = _open(client, db, tmp_path)
    accepted = _post(client, proposal_id, "accept", {"document_indexes": [2], "groups": False})
    rejected = _post(client, proposal_id, "reject", {"document_indexes": [0]})
    assert rejected["audit_id"], "reject answers with its audit row"

    r = _undo(client, accepted["audit_id"])
    assert r.status_code == 200, r.text
    states = _states(client, proposal_id)
    assert states[2] == "proposed" and states[0] == "rejected", states


def test_undoing_a_reject_keeps_a_later_accept(client, db, tmp_path, jobs_run_by_the_test):
    proposal_id = _open(client, db, tmp_path)
    rejected = _post(client, proposal_id, "reject", {"document_indexes": [0]})
    _post(client, proposal_id, "accept", {"document_indexes": [2], "groups": False})

    r = _undo(client, rejected["audit_id"])
    assert r.status_code == 200, r.text
    states = _states(client, proposal_id)
    assert states[0] == "proposed" and states[2] == "accepted", states


def test_undoing_an_adjustment_after_a_later_answer_is_refused_in_words(client, db, tmp_path, jobs_run_by_the_test):
    proposal_id = _open(client, db, tmp_path)
    proposal = _proposal(client, proposal_id)
    long = next(d for d in proposal["documents"] if len(d["page_ids"]) >= 2)
    split = _post(client, proposal_id, "split", {"document_index": long["index"], "page_id": long["page_ids"][1]})
    later = next(i for i, s in _states(client, proposal_id).items() if s == "proposed" and i != long["index"])
    _post(client, proposal_id, "reject", {"document_indexes": [later]})
    before = _proposal(client, proposal_id)

    r = _undo(client, split["audit_id"])
    assert r.status_code == 409, r.text
    assert r.json()["reason"] == "changed" and "later" in r.json()["detail"]
    assert _proposal(client, proposal_id) == before, "nothing changed"


def test_undoing_an_adjustment_after_a_later_accept_is_refused_too(client, db, tmp_path, jobs_run_by_the_test):
    """An accept names pages, not the proposal, so the general rule (a later step on the same things) does not
    see it: the adjustment's own undo checks the proposal is still as it left it."""
    proposal_id = _open(client, db, tmp_path)
    proposal = _proposal(client, proposal_id)
    long = next(d for d in proposal["documents"] if len(d["page_ids"]) >= 2)
    split = _post(client, proposal_id, "split", {"document_index": long["index"], "page_id": long["page_ids"][1]})
    later = next(i for i, s in _states(client, proposal_id).items() if s == "proposed" and i != long["index"])
    _post(client, proposal_id, "accept", {"document_indexes": [later], "groups": False})
    before = _proposal(client, proposal_id)

    r = _undo(client, split["audit_id"])
    assert r.status_code == 409, r.text
    assert r.json()["reason"] == "changed"
    assert _proposal(client, proposal_id) == before, "the accept stands"
