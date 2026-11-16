"""Overlapping regions: a line drawn inside two belongs to the one holding more of it, then the smaller.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.edge.overlapping-regions` (two regions that
overlap are allowed, a stamp over text is two regions; a line inside both belongs to the one that holds more of it,
then the smaller: `SegmentShapes.containingRegion`'s rule, in the engine for the create).
"""
from __future__ import annotations

import pytest

from fichero_server.actions.registry import registry
from fichero_server.models.segments import Segment
from tests.unit.api.test_document_derived_text import _person
from tests.unit.api.test_segments_validate import _box, _page

pytestmark = pytest.mark.source_model


def _region(db, doc, pass_id, box):
    return registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "region", "anchor": {"document_id": doc.id, "polygon": box},
    }, _person()).result["segment_ids"][0]


def _line(db, doc, pass_id, box):
    made = registry.invoke(db, "segment.create", {
        "document_id": doc.id, "pass_id": pass_id, "kind": "line", "place_in_region": True,
        "anchor": {"document_id": doc.id, "polygon": box},
    }, _person())
    return db.get(Segment, made.result["segment_ids"][0])


def test_two_overlapping_regions_are_allowed(db, client):
    doc, pass_id = _page(db, client)
    text = _region(db, doc, pass_id, _box(0.05, 0.05, 0.9, 0.9))
    stamp = _region(db, doc, pass_id, _box(0.6, 0.1, 0.2, 0.2))
    assert db.get(Segment, text) and db.get(Segment, stamp)


def test_a_line_inside_both_belongs_to_the_smaller(db, client):
    doc, pass_id = _page(db, client)
    _region(db, doc, pass_id, _box(0.05, 0.05, 0.9, 0.9))
    stamp = _region(db, doc, pass_id, _box(0.6, 0.1, 0.2, 0.2))
    assert _line(db, doc, pass_id, _box(0.62, 0.15, 0.15, 0.03)).parent_segment_id == stamp


def test_a_line_mostly_outside_the_stamp_belongs_to_the_region_holding_more(db, client):
    doc, pass_id = _page(db, client)
    text = _region(db, doc, pass_id, _box(0.05, 0.05, 0.9, 0.9))
    _region(db, doc, pass_id, _box(0.6, 0.1, 0.2, 0.2))
    assert _line(db, doc, pass_id, _box(0.3, 0.15, 0.35, 0.03)).parent_segment_id == text


def test_a_line_no_region_holds_most_of_stays_on_the_page(db, client):
    doc, pass_id = _page(db, client)
    _region(db, doc, pass_id, _box(0.6, 0.1, 0.2, 0.2))
    assert _line(db, doc, pass_id, _box(0.1, 0.15, 0.55, 0.03)).parent_segment_id is None
