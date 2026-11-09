"""#6425: the reading order seeded when a result becomes a pass nests a line under its region, each once.

`_convert_one` (a result's boxes become a pass) and the reading-orders create action both seed the as-written order
through `seeded_entries`; the create action's test is `test_reading_orders.py::TestSeededOrdersNest`. This is the other
caller: before, the Order tab listed a line twice, under its region and again at the top.
"""
from __future__ import annotations

import fichero_server.api.main  # noqa: F401  (registers every action)
from fichero_server.api.routes.document.reading_orders import entries_in_sequence
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Segment, SegmentPass
from fichero_server.models.reading_orders import ReadingOrder
from fichero_server.models.segments import converted_segment_id
from tests.unit.workflows.test_a_new_result_is_a_pass_at_once import _page, _save


def _result():
    return OCRGeometryResult(provider="apple_vision", text="Ledger first second Total", boxes=[
        OCRGeometryBox(text="Ledger", bbox=[0.05, 0.05, 0.8, 0.30], level="region"),
        OCRGeometryBox(text="first", bbox=[0.1, 0.10, 0.5, 0.04], level="line", metadata={"parent_box_index": 0}),
        OCRGeometryBox(text="second", bbox=[0.1, 0.20, 0.5, 0.04], level="line", metadata={"parent_box_index": 0}),
        OCRGeometryBox(text="Total", bbox=[0.1, 0.60, 0.5, 0.04], level="line"),
    ])


def test_a_converted_result_seeds_its_order_with_each_line_once_under_its_region(db):
    doc = _page(db)
    artifact_id = _save(db, doc, _result())

    pass_row = db.query(SegmentPass, document_id=doc.id)[0]
    box = {i: db.get(Segment, converted_segment_id(artifact_id, i)) for i in range(4)}  # 0 region, 1 and 2 its lines, 3 the loose line
    order = next(o for o in db.query(ReadingOrder, pass_id=pass_row.id))

    top = [e.segment_id for e in entries_in_sequence(db, order.id)]
    assert top == [box[0].id, box[3].id], "the region, then the loose line: nothing listed twice"
    region_entry = next(e for e in entries_in_sequence(db, order.id) if e.segment_id == box[0].id)
    under = [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)]
    assert under == [box[1].id, box[2].id], "the region's lines sit under it, in page order"
