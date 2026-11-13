"""Merge joins lines' geometry and readings, and moves lines across regions.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.merge-lines` (two or more
lines become one: the first picked keeps its id, the outlines are unioned and hulled across a gap, the
baselines join end to end in the page's reading order, the readings join; across regions the others
are moved into the first line's region in the same action, one undo; owner 2026-11-13).

All through the real action and the real undo route.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media import line_join
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, client):
    doc = Document(
        name="folio.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/folio.jpg", status=Status.completed,
    )
    db.save(doc)
    response = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"})
    assert response.status_code == 200, response.text
    return doc, response.json()["id"]


def _segment(client, doc, pass_id, *, kind="line", rect=None, polygon=None, baseline=None, parent=None) -> str:
    anchor = {"document_id": doc.id}
    if rect:
        anchor["rect"] = rect
    if polygon:
        anchor["polygon"] = polygon
    body = {"document_id": doc.id, "pass_id": pass_id, "kind": kind, "anchor": anchor}
    if baseline:
        body["baseline"] = baseline
    if parent:
        body["parent_segment_id"] = parent
    response = client.post("/api/segments", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _read(db, segment_id, text):
    registry.invoke(
        db, "representation.create",
        {"document_id": db.get(Segment, segment_id).document_id, "segment_id": segment_id,
         "kind": "transcription", "content": text},
        _person(),
    )


def _merge(db, ids, keep, **flags):
    return registry.invoke(
        db, "segment.merge",
        {"segment_ids": ids, "keep_id": keep,
         "expected_versions": {sid: db.get(Segment, sid).version for sid in ids},
         "join_geometry": True, "move_into_region": True, **flags},
        _person(),
    )


def _inside(point, polygon) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


class TestTheJoinedLine:
    def test_touching_outlines_become_their_union(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05), baseline=[[0.1, 0.24], [0.4, 0.24]])
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05), baseline=[[0.4, 0.24], [0.7, 0.24]])

        _merge(db, [left, right], left)

        kept = db.get(Segment, left)
        x0, y0, x1, y1 = line_join.bounds(kept.anchor.polygon)
        assert (x0, x1) == pytest.approx((0.1, 0.7), abs=1e-3)
        assert (y0, y1) == pytest.approx((0.2, 0.25), abs=1e-3)
        assert kept.anchor.rect == pytest.approx([x0, y0, x1 - x0, y1 - y0])
        assert db.get(Segment, right).deleted_at is not None

    def test_a_gap_between_the_lines_is_bridged_into_one_outline(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.2, 0.05))
        right = _segment(client, doc, pass_id, polygon=_box(0.5, 0.2, 0.2, 0.05))

        _merge(db, [left, right], left)

        outline = db.get(Segment, left).anchor.polygon
        assert _inside((0.4, 0.225), outline), "the gap between the two lines is inside the joined outline"
        assert _inside((0.15, 0.225), outline) and _inside((0.65, 0.225), outline)

    def test_baselines_join_end_to_end_in_reading_order_whatever_was_picked_first(self, db, client):
        """The first picked keeps its id; the page's order, not the click order, joins the shapes."""
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05), baseline=[[0.1, 0.24], [0.4, 0.24]])
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05), baseline=[[0.7, 0.24], [0.4, 0.24]])
        _read(db, left, "en el")
        _read(db, right, "nombre")

        result = _merge(db, [right, left], right)

        kept = db.get(Segment, right)
        assert result.result["order"] == [left, right]
        # The right line's baseline was drawn backwards; it is turned to run the way the line reads.
        assert kept.baseline == [[0.1, 0.24], [0.4, 0.24], [0.4, 0.24], [0.7, 0.24]]
        joined = db.get(ContentRepresentation, result.result["representation_ids"][0])
        assert joined.content == "en el nombre"

    def test_right_to_left_lines_join_from_the_right(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05), baseline=[[0.4, 0.24], [0.1, 0.24]])
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05), baseline=[[0.7, 0.24], [0.4, 0.24]])
        for sid in (left, right):
            registry.invoke(
                db, "segment.update",
                {"segment_id": sid, "expected_version": db.get(Segment, sid).version, "direction": "rtl"},
                _person(),
            )

        result = _merge(db, [left, right], left)

        assert result.result["order"] == [right, left]
        assert db.get(Segment, left).baseline[0] == [0.7, 0.24]

    def test_a_line_with_no_baseline_adds_none(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05), baseline=[[0.1, 0.24], [0.4, 0.24]])
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05))

        _merge(db, [left, right], left)

        assert db.get(Segment, left).baseline == [[0.1, 0.24], [0.4, 0.24]]

    def test_without_join_geometry_the_kept_line_keeps_its_own_shape(self, db, client):
        """The region-edit combine and the Reader's join send no flag and see what they always saw."""
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05))
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05))
        before = db.get(Segment, left)

        _merge(db, [left, right], left, join_geometry=False, move_into_region=False)

        after = db.get(Segment, left)
        assert after.anchor.polygon == before.anchor.polygon
        assert after.version == before.version


class TestAcrossRegions:
    def _two_regions(self, db, client):
        doc, pass_id = _page(db, client)
        top = _segment(client, doc, pass_id, kind="region", rect=[0.0, 0.0, 1.0, 0.3])
        bottom = _segment(client, doc, pass_id, kind="region", rect=[0.0, 0.3, 1.0, 0.3])
        first = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05), parent=top)
        second = _segment(client, doc, pass_id, polygon=_box(0.1, 0.32, 0.3, 0.05), parent=bottom)
        return top, bottom, first, second

    def test_the_other_line_moves_into_the_first_lines_region_in_one_action(self, db, client):
        top, _bottom, first, second = self._two_regions(db, client)

        result = _merge(db, [first, second], first)

        assert db.get(Segment, first).parent_segment_id == top
        assert db.get(Segment, second).parent_segment_id == top
        assert db.get(Segment, second).deleted_at is not None
        assert result.audit_id

    def test_still_refused_when_the_move_is_not_asked_for(self, db, client):
        from fastapi import HTTPException

        _top, _bottom, first, second = self._two_regions(db, client)
        with pytest.raises(HTTPException) as refused:
            _merge(db, [first, second], first, move_into_region=False)
        assert refused.value.status_code == 409

    def test_one_undo_puts_both_lines_back_in_their_regions_and_shapes(self, db, client):
        top, bottom, first, second = self._two_regions(db, client)
        before = db.get(Segment, first).anchor.polygon
        _read(db, first, "en el nombre")
        _read(db, second, "de dios amen")

        merge = _merge(db, [first, second], first)
        joined_id = merge.result["representation_ids"][0]
        response = client.post(f"/api/actions/audit/{merge.audit_id}/undo")
        assert response.status_code == 200, response.text

        kept, other = db.get(Segment, first), db.get(Segment, second)
        assert kept.anchor.polygon == before
        assert kept.baseline is None
        assert (kept.parent_segment_id, other.parent_segment_id) == (top, bottom)
        assert other.deleted_at is None
        assert db.get(ContentRepresentation, joined_id).retracted_at is not None

    def test_redo_joins_them_again(self, db, client):
        _top, _bottom, first, second = self._two_regions(db, client)
        merge = _merge(db, [first, second], first)
        joined = db.get(Segment, first).anchor.polygon

        undone = client.post(f"/api/actions/audit/{merge.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
        assert redone.status_code == 200, redone.text

        assert db.get(Segment, first).anchor.polygon == joined
        assert db.get(Segment, second).deleted_at is not None


class TestRefusals:
    def test_shapes_on_different_images_are_not_joined(self, db, client):
        from fastapi import HTTPException

        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.3, 0.05))
        right = _segment(client, doc, pass_id, polygon=_box(0.4, 0.2, 0.3, 0.05))
        row = db.get(Segment, right)
        row.anchor = row.anchor.model_copy(update={"rendition_id": "enhanced"})
        db.save(row)

        with pytest.raises(HTTPException) as refused:
            _merge(db, [left, right], left)
        assert refused.value.status_code == 422
        assert db.get(Segment, right).deleted_at is None


class TestMergeRegions:
    """`segment-editor.merge-regions`: two regions joined become one region whose outline is the union; the other's
    lines become the kept region's, placed in its order by page position; one undo puts every line back."""

    def _page_with_two_regions(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.1, 0.4, 0.5))
        right = _segment(client, doc, pass_id, kind="region", polygon=_box(0.55, 0.1, 0.4, 0.5))
        lines = {
            "l1": _segment(client, doc, pass_id, polygon=_box(0.06, 0.15, 0.38, 0.04), parent=left),
            "l2": _segment(client, doc, pass_id, polygon=_box(0.06, 0.35, 0.38, 0.04), parent=left),
            "r1": _segment(client, doc, pass_id, polygon=_box(0.56, 0.15, 0.38, 0.04), parent=right),
            "r2": _segment(client, doc, pass_id, polygon=_box(0.56, 0.35, 0.38, 0.04), parent=right),
        }
        return doc, pass_id, left, right, lines

    def _order(self, db, pass_id, region_id):
        from fichero_server.api.routes.document.reading_orders import as_written_order, entries_in_sequence
        from fichero_server.models.reading_orders import ReadingOrderEntry

        order = as_written_order(db, pass_id)
        region_entry = next(e for e in db.query(ReadingOrderEntry, order_id=order.id) if e.segment_id == region_id)
        return [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=region_entry.id)]

    def test_the_regions_become_one_and_the_lines_follow_in_page_order(self, db, client):
        _doc, pass_id, left, right, lines = self._page_with_two_regions(db, client)
        assert self._order(db, pass_id, left) == [lines["l1"], lines["l2"]]

        _merge(db, [left, right], left)

        kept = db.get(Segment, left)
        x0, _y0, x1, _y1 = line_join.bounds(kept.anchor.polygon)
        assert (x0, x1) == pytest.approx((0.05, 0.95), abs=2e-3)
        assert all(db.get(Segment, line).parent_segment_id == left for line in lines.values())
        assert db.get(Segment, right).deleted_at is not None
        order = self._order(db, pass_id, left)
        assert set(order) == set(lines.values())
        assert order.index(lines["l1"]) < order.index(lines["l2"])
        assert order.index(lines["r1"]) < order.index(lines["r2"])

    def test_one_undo_puts_every_line_back_in_its_region_and_order(self, db, client):
        _doc, pass_id, left, right, lines = self._page_with_two_regions(db, client)
        before_right = self._order(db, pass_id, right)

        merge = _merge(db, [left, right], left)
        response = client.post(f"/api/actions/audit/{merge.audit_id}/undo")
        assert response.status_code == 200, response.text

        assert [db.get(Segment, lines[k]).parent_segment_id for k in ("l1", "l2", "r1", "r2")] == [left, left, right, right]
        assert db.get(Segment, right).deleted_at is None
        assert self._order(db, pass_id, right) == before_right
        assert self._order(db, pass_id, left) == [lines["l1"], lines["l2"]]

    def test_redo_merges_them_again(self, db, client):
        _doc, _pass_id, left, right, lines = self._page_with_two_regions(db, client)
        merge = _merge(db, [left, right], left)
        undone = client.post(f"/api/actions/audit/{merge.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
        assert redone.status_code == 200, redone.text
        assert all(db.get(Segment, line).parent_segment_id == left for line in lines.values())
        again = client.post(f"/api/actions/audit/{redone.json()['audit_id']}/undo")
        assert again.status_code == 200, again.text
        assert db.get(Segment, lines["r1"]).parent_segment_id == right
