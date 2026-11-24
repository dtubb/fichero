"""Join Lines in the Same Row: the lines of one row become one line each, in one step.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.join-lines-in-the-same-row` (the lines that
share a row are grouped; a line with no row-mate is left alone; one undo for the whole page),
`segment-editor.join-rows-keeps-parts-as-words` (each part becomes a word of the joined line, a part's own words stay),
`segment-editor.join-rows-says-what-it-will-do` (the read-only preview names the groups and what is left alone).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media import line_join
from fichero_server.models import ActionAudit, ContentRepresentation, Segment
from tests.unit.api.test_segment_convert_to_box import _read
from tests.unit.api.test_segments_validate import _box, _page, _segment

pytestmark = pytest.mark.source_model


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _line(client, doc, pass_id, x, y, w=0.2, h=0.05, parent=None):
    return _segment(client, doc, pass_id, polygon=_box(x, y, w, h), baseline=[[x, y + h], [x + w, y + h]], parent=parent)


def _join(db, ids):
    return registry.invoke(
        db, "segment.join_rows",
        {"segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}}, _person())


def _preview(client, doc, ids):
    return client.get(f"/api/segments/document/{doc.id}/join-rows-preview", params={"segment_ids": ids})


def _live(db, doc, kind):
    return [r for r in db.all(Segment) if r.document_id == doc.id and r.kind == kind and r.deleted_at is None]


class TestRowGrouping:
    def test_boxes_that_share_a_row_group_in_reading_order_and_the_rest_are_alone(self):
        boxes = [(0.5, 0.2, 0.7, 0.25), (0.1, 0.2, 0.3, 0.25), (0.1, 0.5, 0.4, 0.55), (0.1, 0.3, 0.4, 0.35)]
        assert line_join.rows(boxes, "ltr") == [[1, 0]]

    def test_lines_stacked_in_one_column_are_not_a_row(self):
        assert line_join.rows([(0.1, 0.2, 0.5, 0.25), (0.12, 0.27, 0.5, 0.32)], "ltr") == []

    def test_a_slight_vertical_drift_is_still_one_row(self):
        assert line_join.rows([(0.1, 0.2, 0.3, 0.25), (0.4, 0.21, 0.7, 0.26)], "ltr") == [[0, 1]]

    def test_right_to_left_rows_start_from_the_right(self):
        assert line_join.rows([(0.1, 0.2, 0.3, 0.25), (0.4, 0.2, 0.7, 0.25)], "rtl") == [[1, 0]]


class TestJoinRows:
    def test_each_row_becomes_one_line_and_a_lone_line_is_left_alone(self, db, client):
        doc, pass_id = _page(db, client)
        a1, a2 = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        b1, b2 = _line(client, doc, pass_id, 0.1, 0.4), _line(client, doc, pass_id, 0.4, 0.4)
        alone = _line(client, doc, pass_id, 0.1, 0.6)
        for sid, text in ((a1, "in"), (a2, "nomine"), (alone, "solus")):
            _read(db, doc, sid, text)

        done = _join(db, [a2, b2, alone, a1, b1])

        assert [(j["kept_id"], j["segment_ids"]) for j in done.result["joined"]] == [(a1, [a1, a2]), (b1, [b1, b2])]
        assert done.result["left_alone"] == [{"segment_id": alone, "reason": "no other line in its row"}]
        assert {r.id for r in _live(db, doc, "line")} == {a1, b1, alone}
        x0, _y0, x1, _y1 = line_join.bounds(db.get(Segment, a1).anchor.polygon)
        assert (x0, x1) == pytest.approx((0.1, 0.6), abs=1e-3)
        assert db.get(Segment, alone).version == 1
        joined = [r.content for r in db.all(ContentRepresentation) if r.segment_id == a1]
        assert "in nomine" in joined

    def test_lines_of_different_regions_in_one_row_are_left_alone_with_the_reason(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, kind="region", polygon=_box(0.05, 0.1, 0.3, 0.3))
        right = _segment(client, doc, pass_id, kind="region", polygon=_box(0.4, 0.1, 0.3, 0.3))
        one, two = _line(client, doc, pass_id, 0.1, 0.2, parent=left), _line(client, doc, pass_id, 0.5, 0.2, parent=right)

        preview = _preview(client, doc, [one, two]).json()
        with pytest.raises(HTTPException) as refused:
            _join(db, [one, two])

        assert preview["groups"] == [] and preview["left_alone"] == [
            {"segment_id": one, "reason": "its row-mates are in another region"},
            {"segment_id": two, "reason": "its row-mates are in another region"},
        ]
        assert refused.value.status_code == 422 and "Nothing to join" in refused.value.detail
        assert {r.id for r in _live(db, doc, "line")} == {one, two}

    def test_one_undo_puts_every_row_back_and_redo_joins_them_again(self, client, db):
        doc, pass_id = _page(db, client)
        a1, a2 = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        b1, b2 = _line(client, doc, pass_id, 0.1, 0.4), _line(client, doc, pass_id, 0.4, 0.4)
        shapes = {sid: db.get(Segment, sid).anchor.polygon for sid in (a1, a2, b1, b2)}

        done = _join(db, [a1, a2, b1, b2])
        assert {r.id for r in _live(db, doc, "line")} == {a1, b1}

        assert client.post(f"/api/actions/audit/{done.audit_id}/undo").status_code == 200
        assert {r.id for r in _live(db, doc, "line")} == {a1, a2, b1, b2}
        assert {sid: db.get(Segment, sid).anchor.polygon for sid in shapes} == shapes
        assert _live(db, doc, "word") == []

        redo = [row for row in db.all(ActionAudit) if row.inverse_of == done.audit_id]
        assert len(redo) == 1
        assert client.post(f"/api/actions/audit/{redo[0].id}/undo").status_code == 200
        assert {r.id for r in _live(db, doc, "line")} == {a1, b1}

    def test_a_stale_version_refuses_the_whole_join(self, db, client):
        doc, pass_id = _page(db, client)
        one, two = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        with pytest.raises(HTTPException) as refused:
            registry.invoke(db, "segment.join_rows",
                            {"segment_ids": [one, two], "expected_versions": {one: 99, two: 1}}, _person())
        assert refused.value.status_code == 409
        assert {r.id for r in _live(db, doc, "line")} == {one, two}


class TestPartsAsWords:
    def test_each_part_without_words_becomes_a_word_of_the_joined_line_with_its_outline_and_text(self, db, client):
        doc, pass_id = _page(db, client)
        one, two = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        _read(db, doc, one, "in")
        _read(db, doc, two, "nomine")
        shapes = [db.get(Segment, one).anchor.polygon, db.get(Segment, two).anchor.polygon]

        done = _join(db, [one, two])

        words = sorted(_live(db, doc, "word"), key=lambda r: r.anchor.polygon[0][0])
        assert [w.parent_segment_id for w in words] == [one, one]
        assert [w.anchor.polygon for w in words] == shapes
        texts = [[r.content for r in db.all(ContentRepresentation) if r.segment_id == w.id] for w in words]
        assert texts == [["in"], ["nomine"]]
        assert done.result["joined"][0]["word_ids"] == [w.id for w in words]

    def test_a_part_that_already_has_words_keeps_them_and_gets_no_extra_word(self, db, client):
        doc, pass_id = _page(db, client)
        one, two = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        word = _segment(client, doc, pass_id, kind="word", polygon=_box(0.4, 0.2, 0.1, 0.05), parent=two)

        _join(db, [one, two])

        assert db.get(Segment, word).parent_segment_id == one
        assert sorted(r.id for r in _live(db, doc, "word") if r.parent_segment_id == one) == sorted(
            [word] + [r.id for r in _live(db, doc, "word") if r.id != word])
        assert len(_live(db, doc, "word")) == 2


class TestThePreview:
    def test_the_preview_names_the_groups_and_what_is_left_and_writes_nothing(self, db, client):
        doc, pass_id = _page(db, client)
        a1, a2 = _line(client, doc, pass_id, 0.1, 0.2), _line(client, doc, pass_id, 0.4, 0.2)
        alone = _line(client, doc, pass_id, 0.1, 0.6)
        before = {sid: db.get(Segment, sid).version for sid in (a1, a2, alone)}

        response = _preview(client, doc, [a1, a2, alone])

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["groups"] == [{"kept_id": a1, "segment_ids": [a1, a2]}]
        assert body["left_alone"] == [{"segment_id": alone, "reason": "no other line in its row"}]
        assert body["summary"] == "Joins 2 lines into 1 line; leaves 1 line alone."
        assert {sid: db.get(Segment, sid).version for sid in before} == before
        assert len(_live(db, doc, "line")) == 3 and _live(db, doc, "word") == []
