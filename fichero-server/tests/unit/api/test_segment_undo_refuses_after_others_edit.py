"""Undo and redo of a split and a merge are refused when someone else has changed a member since (#4957).

source.editor.redo-works: the spec listed merge and split as taking no version, so an undo would delete
parts someone had worked on. These pin that the engine refuses instead, and leaves the rows as they were.
"""

from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.models import Segment
from tests.unit.api.test_segments_write_actions import _create_pass, _create_segment, _make_doc

OLD = [0.1, 0.1, 0.2, 0.1]


def _invoke(client, name, params):
    return client.post("/api/actions/invoke", json={"name": name, "params": params})


def _two_segments(client, db):
    doc = _make_doc(db)
    pass_id = _create_pass(client, doc.id)["id"]
    made = [_create_segment(client, document_id=doc.id, pass_id=pass_id, anchor={"document_id": doc.id, "rect": OLD}).json()
            for _ in range(2)]
    return doc, made


def test_undoing_a_split_is_refused_when_a_part_was_edited_after(client, db):
    doc, (line, _) = _two_segments(client, db)
    split = _invoke(client, "segment.split", {
        "segment_id": line["id"], "expected_version": 1,
        "parts": [{"anchor": {"document_id": doc.id, "rect": [0.1, 0.1, 0.1, 0.1]}},
                  {"anchor": {"document_id": doc.id, "rect": [0.2, 0.1, 0.1, 0.1]}}],
    })
    assert split.status_code == 200, split.text
    part_id = split.json()["result"]["new_segment_ids"][0]
    part = db.get(Segment, part_id)
    edit = _invoke(client, "segment.update", {"segment_id": part_id, "expected_version": part.version, "kind": "heading"})
    assert edit.status_code == 200, edit.text

    undone = client.post(f"/api/actions/audit/{split.json()['audit_id']}/undo")

    assert undone.status_code == 409, undone.text
    assert db.get(Segment, part_id).deleted_at is None, "the edited part is not deleted"


def test_undoing_a_merge_is_refused_when_the_kept_segment_changed_after(client, db):
    _, (absorbed, keeper) = _two_segments(client, db)
    merge = _invoke(client, "segment.merge", {
        "segment_ids": [absorbed["id"], keeper["id"]], "keep_id": keeper["id"],
        "expected_versions": {absorbed["id"]: 1, keeper["id"]: 1},
    })
    assert merge.status_code == 200, merge.text
    kept = db.get(Segment, keeper["id"])
    assert _invoke(client, "segment.update", {"segment_id": keeper["id"], "expected_version": kept.version,
                                              "kind": "heading"}).status_code == 200

    undone = client.post(f"/api/actions/audit/{merge.json()['audit_id']}/undo")

    assert undone.status_code == 409, undone.text
    assert db.get(Segment, absorbed["id"]).deleted_at is not None, "the absorbed segment stays merged"


def test_a_merge_with_a_stale_member_version_is_refused(client, db):
    _, (absorbed, keeper) = _two_segments(client, db)
    assert _invoke(client, "segment.update", {"segment_id": absorbed["id"], "expected_version": 1,
                                              "kind": "heading"}).status_code == 200
    merge = _invoke(client, "segment.merge", {
        "segment_ids": [absorbed["id"], keeper["id"]], "keep_id": keeper["id"],
        "expected_versions": {absorbed["id"]: 1, keeper["id"]: 1},
    })
    assert merge.status_code == 409, merge.text
    assert db.get(Segment, absorbed["id"]).deleted_at is None
