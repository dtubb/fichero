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
