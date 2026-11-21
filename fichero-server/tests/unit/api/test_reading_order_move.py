"""Drag in the segment list reorders: `reading_order.move` puts the dragged segments at a place and under a parent.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.list-drag-reorder` (a drop between rows
reorders; a drop on a region nests; a multi-row drag keeps relative order; undo restores). Engine half only.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.reading_orders import entries_in_sequence
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_reading_order_renumber_by_clicks import _lines_page, _level


def _top(db, order_id):
    return [row.segment_id for row in entries_in_sequence(db, order_id, parent_entry_id=None)]


def _move(db, order_id, ids, **extra):
    return registry.invoke(db, "reading_order.move", {"order_id": order_id, "segment_ids": ids, **extra}, _person())


def test_a_drop_between_rows_reorders_the_level(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    _move(db, order_id, [e], parent_segment_id=region.id, after_segment_id=a)
    assert _level(db, order_id, region.id) == [a, e, b, c, d]


def test_a_drop_with_no_row_above_puts_them_first(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    _move(db, order_id, [d], parent_segment_id=region.id)
    assert _level(db, order_id, region.id) == [d, a, b, c, e]


def test_a_drop_on_another_region_nests_the_lines_there(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    other = next(s for s in _top(db, order_id) if s != region.id)
    _move(db, order_id, [b], parent_segment_id=other)
    assert _level(db, order_id, other) == [b]
    assert _level(db, order_id, region.id) == [a, c, d, e]


def test_many_rows_keep_their_relative_order(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    _move(db, order_id, [b, d], parent_segment_id=region.id, after_segment_id=e)
    assert _level(db, order_id, region.id) == [a, c, e, b, d]


def test_one_undo_restores_level_and_parent_and_a_redo_moves_again(db, client):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    other = next(s for s in _top(db, order_id) if s != region.id)
    done = _move(db, order_id, [b, c], parent_segment_id=other)
    undone = client.post(f"/api/actions/audit/{done.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    assert _level(db, order_id, region.id) == [a, b, c, d, e]
    assert _level(db, order_id, other) == []
    assert client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo").status_code == 200
    assert _level(db, order_id, other) == [b, c]


def test_a_drop_into_itself_or_what_it_holds_is_refused_and_nothing_moves(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    before = _top(db, order_id)
    with pytest.raises(HTTPException) as refused:
        _move(db, order_id, [region.id], parent_segment_id=a)
    assert refused.value.status_code == 422
    assert _top(db, order_id) == before
    assert _level(db, order_id, region.id) == [a, b, c, d, e]


def test_an_after_row_at_another_level_or_a_segment_not_in_the_order_is_refused(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    other = next(s for s in _top(db, order_id) if s != region.id)
    with pytest.raises(HTTPException) as wrong_level:
        _move(db, order_id, [b], parent_segment_id=other, after_segment_id=a)
    assert wrong_level.value.status_code == 422
    with pytest.raises(HTTPException) as missing:
        _move(db, order_id, ["f" * 32], parent_segment_id=region.id)
    assert missing.value.status_code == 404
