"""A merged line names the lines it came from.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.provenance-on-every-segment` ("a merged
line names the lines it came from"). `GET /api/segments/{segment_id}` answers `merged_from`: every id merged into the
line, directly or through a line merged into it, and not put back by an undo since.

All through the real action, the real undo route and the real read route.
"""

from __future__ import annotations

import pytest

from fichero_server.models import Segment
from tests.unit.api.test_segment_merge_lines import _merge, _page, _segment

pytestmark = pytest.mark.source_model


def _lines(client, doc, pass_id, count):
    return [_segment(client, doc, pass_id, rect=[0.1, 0.1 + 0.1 * k, 0.6, 0.05],
                     baseline=[[0.1, 0.14 + 0.1 * k], [0.7, 0.14 + 0.1 * k]]) for k in range(count)]


def _merged_from(client, segment_id):
    response = client.get(f"/api/segments/{segment_id}")
    assert response.status_code == 200, response.text
    return response.json()["merged_from"]


def test_a_line_never_merged_names_nothing(db, client):
    doc, pass_id = _page(db, client)
    [line] = _lines(client, doc, pass_id, 1)
    assert _merged_from(client, line) == []


def test_a_merged_line_names_the_lines_it_came_from(db, client):
    doc, pass_id = _page(db, client)
    first, second, third = _lines(client, doc, pass_id, 3)
    _merge(db, [first, second, third], first)
    assert sorted(_merged_from(client, first)) == sorted([second, third])


def test_a_line_merged_twice_names_the_lines_of_both_merges(db, client):
    doc, pass_id = _page(db, client)
    first, second, third = _lines(client, doc, pass_id, 3)
    _merge(db, [second, third], second)
    _merge(db, [first, second], first)
    assert sorted(_merged_from(client, first)) == sorted([second, third])


def test_an_undone_merge_names_nothing(db, client):
    doc, pass_id = _page(db, client)
    first, second = _lines(client, doc, pass_id, 2)
    merged = _merge(db, [first, second], first)
    undone = client.post(f"/api/actions/audit/{merged.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    assert db.get(Segment, second).deleted_at is None
    assert _merged_from(client, first) == []


def test_the_read_asks_for_the_forwarding_notes_once_however_many_merges_the_document_has(db, client, monkeypatch):
    from fichero_server.models.segments import SegmentForwarding

    doc, pass_id = _page(db, client)
    lines = _lines(client, doc, pass_id, 6)
    _merge(db, lines[0:2], lines[0])
    _merge(db, lines[2:4], lines[2])
    _merge(db, lines[4:6], lines[4])
    asked = []
    original = type(db).query

    def counting(self, model, *args, **kwargs):
        if model is SegmentForwarding:
            asked.append(kwargs)
        return original(self, model, *args, **kwargs)

    monkeypatch.setattr(type(db), "query", counting)
    assert _merged_from(client, lines[0]) == [lines[1]]
    assert len(asked) == 1
