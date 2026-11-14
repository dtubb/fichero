"""segment-editor.reassign-by-drag (docs/contributor_manual/specs/ui/segment-editor.md, #4941, #6582).

`segment.reparent` moves each line's entry, in every order holding it, among the new region's lines by page
position; the entry keeps its id. One undo puts the parents AND the entries back; a redo moves them again.
"""
from __future__ import annotations

from fichero_server.actions.registry import registry
from fichero_server.api.routes.document.reading_orders import entries_in_sequence
from fichero_server.models import ActionAudit
from fichero_server.models.reading_orders import ReadingOrderEntry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_segment_reparent import _page, _reparent, _segment


def _ordered_page(db):
    doc, pass_row, region_one, region_two, line, other = _page(db)
    early = _segment(db, doc, pass_row, "line", parent=region_two.id, y=0.52)
    late = _segment(db, doc, pass_row, "line", parent=region_two.id, y=0.6)
    # A line the first region holds though it sits among the second's: what a drag reassigns.
    stray = _segment(db, doc, pass_row, "line", parent=region_one.id, y=0.55)
    order_id = registry.invoke(
        db, "reading_order.create",
        {"document_id": doc.id, "pass_id": pass_row.id, "name": "by hand", "seed_from_pass": True},
        _person(),
    ).result["order_id"]
    return order_id, region_one, region_two, line, other, late, early, stray


def _entry(db, order_id, segment_id):
    [row] = db.query(ReadingOrderEntry, order_id=order_id, segment_id=segment_id)
    return row


def _children(db, order_id, region_id):
    parent = _entry(db, order_id, region_id)
    return [row.segment_id for row in entries_in_sequence(db, order_id, parent_entry_id=parent.id)]


def _undo(client, audit_id):
    response = client.post(f"/api/actions/audit/{audit_id}/undo")
    assert response.status_code == 200, response.text
    return response.json()["audit_id"]


def test_a_moved_line_reads_among_the_new_regions_lines_by_page_position(db):
    order_id, region_one, region_two, line, other, late, early, stray = _ordered_page(db)
    before = _entry(db, order_id, stray.id)

    _reparent(db, [stray], region_two.id)

    assert _children(db, order_id, region_two.id) == [early.id, stray.id, late.id]
    assert _children(db, order_id, region_one.id) == [line.id, other.id]
    assert _entry(db, order_id, stray.id).id == before.id, "the entry keeps its id"


def test_one_undo_puts_the_parents_and_the_entries_back_and_a_redo_moves_them_again(db, client):
    order_id, region_one, region_two, line, other, late, early, stray = _ordered_page(db)
    was = {row.segment_id: (row.parent_entry_id, row.position)
           for row in (_entry(db, order_id, stray.id), _entry(db, order_id, other.id))}

    _reparent(db, [stray, other], region_two.id)
    audit = [a for a in db.all(ActionAudit) if a.action_name == "segment.reparent"][-1]
    undo_id = _undo(client, audit.id)

    assert db.get(Segment, stray.id).parent_segment_id == region_one.id
    assert {sid: (_entry(db, order_id, sid).parent_entry_id, _entry(db, order_id, sid).position)
            for sid in was} == was, "the entries are back where they were"

    _undo(client, undo_id)
    assert db.get(Segment, stray.id).parent_segment_id == region_two.id
    assert _children(db, order_id, region_two.id) == [other.id, early.id, stray.id, late.id]


def test_lifting_a_line_out_puts_its_entry_at_the_top_level_by_page_position(db):
    order_id, region_one, region_two, line, other, late, early, stray = _ordered_page(db)

    _reparent(db, [late], None)

    top = [row.segment_id for row in entries_in_sequence(db, order_id)]
    assert top == [region_one.id, region_two.id, late.id]


def test_a_region_moved_into_another_keeps_its_lines_nested_under_it(db):
    order_id, region_one, region_two, line, other, late, early, stray = _ordered_page(db)

    _reparent(db, [region_two], region_one.id)

    assert _children(db, order_id, region_one.id) == [line.id, other.id, region_two.id, stray.id]
    assert _children(db, order_id, region_two.id) == [early.id, late.id]
