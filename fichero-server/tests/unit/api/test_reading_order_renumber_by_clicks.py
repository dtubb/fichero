"""Order by clicking: the segments clicked in turn read 1, 2, 3 ..., the rest after them in their own order.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.order-by-clicking` (the clicks sent once,
as `reading_order.sequence`, when the Order tool is left; one undo for the whole sequence, never per click; ⇧-click
continues after a segment; the segments not clicked keep their relative order after the clicked ones).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.reading_orders import entries_in_sequence
from fichero_server.models.reading_orders import ReadingOrderEntry
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_segment_reparent import _page, _segment


def _lines_page(db):
    """One region holding five lines a..e, top to bottom, and a named order seeded from the page."""
    doc, pass_row, region, _other_region, line_a, line_b = _page(db)
    rest = [_segment(db, doc, pass_row, "line", parent=region.id, y=y) for y in (0.3, 0.35, 0.4)]
    lines = [line_a, line_b, *rest]
    order_id = registry.invoke(
        db, "reading_order.create",
        {"document_id": doc.id, "pass_id": pass_row.id, "name": "by hand", "seed_from_pass": True}, _person(),
    ).result["order_id"]
    return order_id, region, [row.id for row in lines]


def _level(db, order_id, region_id):
    [parent] = db.query(ReadingOrderEntry, order_id=order_id, segment_id=region_id)
    return [row.segment_id for row in entries_in_sequence(db, order_id, parent_entry_id=parent.id)]


def _sequence(db, order_id, clicked, **extra):
    return registry.invoke(
        db, "reading_order.sequence", {"order_id": order_id, "segment_ids": clicked, **extra}, _person(),
    )


def test_the_clicked_lines_read_first_in_click_order_and_the_rest_keep_their_order_after(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)

    _sequence(db, order_id, [d, b])

    assert _level(db, order_id, region.id) == [d, b, a, c, e]


def test_a_shift_click_continues_after_the_selected_segment(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)

    _sequence(db, order_id, [e, a], after_segment_id=b)

    assert _level(db, order_id, region.id) == [b, e, a, c, d]


def test_one_undo_puts_back_the_whole_sequence_and_a_redo_sets_it_again(db, client):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    before = _level(db, order_id, region.id)

    done = _sequence(db, order_id, [e, d, c])
    undone = client.post(f"/api/actions/audit/{done.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    assert _level(db, order_id, region.id) == before

    redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
    assert redone.status_code == 200, redone.text
    assert _level(db, order_id, region.id) == [e, d, c, a, b]


def test_segments_from_two_levels_are_refused_and_nothing_moves(db):
    order_id, region, (a, b, c, d, e) = _lines_page(db)
    before = _level(db, order_id, region.id)
    with pytest.raises(HTTPException) as refused:
        _sequence(db, order_id, [region.id, a])
    assert refused.value.status_code == 422
    assert _level(db, order_id, region.id) == before


def test_a_segment_the_order_does_not_hold_is_refused(db):
    order_id, region, (a, *_rest) = _lines_page(db)
    with pytest.raises(HTTPException) as refused:
        _sequence(db, order_id, [a, "f" * 32])
    assert refused.value.status_code == 404


def test_a_sequence_and_its_undo_refresh_the_pages_cached_text(db):
    """The page's text follows its `as-written` order, so reordering it changes the text (`page_text_cache`)."""
    from types import SimpleNamespace

    from fichero_server.actions.page_text_cache import _document_ids

    spec = SimpleNamespace(domains=["reading_order"], emit_type="reading_order.changed", document_ids=["d"], after={})
    assert _document_ids(spec, "reading_order.sequence", None) == ["d"]
    assert _document_ids(spec, "reading_order.restore_positions", None) == ["d"]
