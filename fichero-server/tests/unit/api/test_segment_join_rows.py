"""Join Lines in the Same Row: the lines that sit in one row become one line each, in one undo step.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.join-lines-in-the-same-row`,
`segment-editor.join-rows-keeps-parts-as-words`, `segment-editor.join-rows-says-what-it-will-do`.

Row grouping on synthetic boxes, the read-only preview route, the action and its one undo.
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


def _segment(client, doc, pass_id, *, kind="line", polygon, baseline=None, parent=None) -> str:
    body = {"document_id": doc.id, "pass_id": pass_id, "kind": kind, "anchor": {"document_id": doc.id, "polygon": polygon}}
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


def _row_page(db, client):
    """Two rows of two lines each (a, b above; c, d below) and one line, e, alone at the bottom."""
    doc, pass_id = _page(db, client)
    ids = {
        "a": _segment(client, doc, pass_id, polygon=_box(0.05, 0.10, 0.20, 0.05), baseline=[[0.05, 0.14], [0.25, 0.14]]),
        "b": _segment(client, doc, pass_id, polygon=_box(0.30, 0.11, 0.20, 0.05), baseline=[[0.30, 0.15], [0.50, 0.15]]),
        "c": _segment(client, doc, pass_id, polygon=_box(0.05, 0.30, 0.20, 0.05), baseline=[[0.05, 0.34], [0.25, 0.34]]),
        "d": _segment(client, doc, pass_id, polygon=_box(0.30, 0.30, 0.20, 0.05), baseline=[[0.30, 0.34], [0.50, 0.34]]),
        "e": _segment(client, doc, pass_id, polygon=_box(0.05, 0.60, 0.20, 0.05), baseline=[[0.05, 0.64], [0.25, 0.64]]),
    }
    return doc, pass_id, ids


def _rows(groups):
    return [{"segment_ids": group, "keep_id": group[0]} for group in groups]


def _join_rows(db, groups):
    ids = [sid for group in groups for sid in group]
    return registry.invoke(
        db, "segment.join_rows",
        {"groups": _rows(groups), "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}},
        _person(),
    )


def _live(db, segment_id) -> bool:
    return db.get(Segment, segment_id).deleted_at is None


class TestRowGrouping:
    def _boxes(self, *specs):
        return [_box(*spec) for spec in specs]

    def test_lines_that_overlap_vertically_are_one_row_and_a_line_alone_is_left_out(self):
        outlines = self._boxes((0.05, 0.10, 0.2, 0.05), (0.30, 0.11, 0.2, 0.05), (0.05, 0.60, 0.2, 0.05))
        assert line_join.row_groups(outlines, None) == [[0, 1]]

    def test_a_group_is_in_reading_order_whatever_the_input_order(self):
        outlines = self._boxes((0.30, 0.11, 0.2, 0.05), (0.05, 0.10, 0.2, 0.05))
        assert line_join.row_groups(outlines, None) == [[1, 0]]
        assert line_join.row_groups(outlines, "rtl") == [[0, 1]]

    def test_a_touch_that_is_less_than_half_the_shorter_line_is_not_a_row(self):
        outlines = self._boxes((0.05, 0.10, 0.2, 0.05), (0.30, 0.14, 0.2, 0.05))
        assert line_join.row_groups(outlines, None) == []

    def test_rows_chain_through_a_middle_line(self):
        outlines = self._boxes((0.05, 0.10, 0.2, 0.05), (0.30, 0.12, 0.2, 0.05), (0.55, 0.14, 0.2, 0.05))
        assert line_join.row_groups(outlines, None) == [[0, 1, 2]]

    def test_vertical_text_groups_by_column(self):
        outlines = self._boxes((0.10, 0.05, 0.05, 0.2), (0.11, 0.30, 0.05, 0.2), (0.60, 0.05, 0.05, 0.2))
        assert line_join.row_groups(outlines, "ttb") == [[0, 1]]


class TestPreview:
    def _preview(self, client, doc, **params):
        response = client.get(f"/api/segments/document/{doc.id}/join-rows-preview", params=params)
        assert response.status_code == 200, response.text
        return response.json()

    def test_it_names_the_groups_and_the_lines_left_alone_and_writes_nothing(self, db, client):
        doc, _pass_id, ids = _row_page(db, client)
        versions = {sid: db.get(Segment, sid).version for sid in ids.values()}

        answer = self._preview(client, doc)

        assert [group["segment_ids"] for group in answer["groups"]] == [[ids["a"], ids["b"]], [ids["c"], ids["d"]]]
        assert [group["keep_id"] for group in answer["groups"]] == [ids["a"], ids["c"]]
        assert answer["left_alone"] == [ids["e"]]
        assert {sid: db.get(Segment, sid).version for sid in ids.values()} == versions
        assert all(_live(db, sid) for sid in ids.values())

    def test_given_a_selection_only_the_selected_lines_are_grouped(self, db, client):
        doc, _pass_id, ids = _row_page(db, client)
        answer = self._preview(client, doc, segment_ids=[ids["a"], ids["b"], ids["e"]])
        assert [group["segment_ids"] for group in answer["groups"]] == [[ids["a"], ids["b"]]]
        assert answer["left_alone"] == [ids["e"]]

    def test_lines_of_different_regions_are_not_one_row(self, db, client):
        doc, pass_id = _page(db, client)
        left = _segment(client, doc, pass_id, kind="region", polygon=_box(0.0, 0.0, 0.45, 0.5))
        right = _segment(client, doc, pass_id, kind="region", polygon=_box(0.5, 0.0, 0.45, 0.5))
        a = _segment(client, doc, pass_id, polygon=_box(0.05, 0.1, 0.3, 0.05), parent=left)
        b = _segment(client, doc, pass_id, polygon=_box(0.55, 0.1, 0.3, 0.05), parent=right)
        answer = self._preview(client, doc)
        assert answer["groups"] == []
        assert set(answer["left_alone"]) == {a, b}

    def test_a_segment_of_another_page_is_refused(self, db, client):
        doc, _pass_id, ids = _row_page(db, client)
        other, _other_pass = _page(db, client)
        response = client.get(f"/api/segments/document/{other.id}/join-rows-preview", params={"segment_ids": [ids["a"]]})
        assert response.status_code == 404


class TestJoinRows:
    def test_each_group_becomes_one_line_and_the_lone_line_is_left_alone(self, db, client):
        _doc, _pass_id, ids = _row_page(db, client)
        lone = db.get(Segment, ids["e"])
        lone_version = lone.version
        _read(db, ids["a"], "en el")
        _read(db, ids["b"], "nombre")

        result = _join_rows(db, [[ids["a"], ids["b"]], [ids["c"], ids["d"]]])

        assert result.result["kept_ids"] == [ids["a"], ids["c"]]
        assert _live(db, ids["a"]) and _live(db, ids["c"])
        assert not _live(db, ids["b"]) and not _live(db, ids["d"])
        x0, _y0, x1, _y1 = line_join.bounds(db.get(Segment, ids["a"]).anchor.polygon)
        assert (x0, x1) == pytest.approx((0.05, 0.50), abs=2e-3)
        assert db.get(Segment, ids["e"]).version == lone_version and _live(db, ids["e"])
        joined = db.get(ContentRepresentation, result.result["representation_ids"][0])
        assert joined.content == "en el nombre"

    def test_one_undo_puts_every_line_back_and_redo_joins_them_again(self, db, client):
        _doc, _pass_id, ids = _row_page(db, client)
        before = {sid: db.get(Segment, sid).anchor.polygon for sid in ids.values()}
        joined = _join_rows(db, [[ids["a"], ids["b"]], [ids["c"], ids["d"]]])

        undone = client.post(f"/api/actions/audit/{joined.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        assert all(_live(db, sid) for sid in ids.values())
        assert {sid: db.get(Segment, sid).anchor.polygon for sid in ids.values()} == before

        redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
        assert redone.status_code == 200, redone.text
        assert not _live(db, ids["b"]) and not _live(db, ids["d"])
        assert _live(db, ids["a"]) and _live(db, ids["c"])

        again = client.post(f"/api/actions/audit/{redone.json()['audit_id']}/undo")
        assert again.status_code == 200, again.text
        assert all(_live(db, sid) for sid in ids.values())

    def test_a_changed_line_refuses_the_whole_join(self, db, client):
        from fastapi import HTTPException

        _doc, _pass_id, ids = _row_page(db, client)
        versions = {sid: db.get(Segment, sid).version for sid in (ids["a"], ids["b"], ids["c"], ids["d"])}
        registry.invoke(
            db, "segment.update",
            {"segment_id": ids["d"], "expected_version": versions[ids["d"]], "direction": "ltr"}, _person(),
        )
        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.join_rows",
                {"groups": _rows([[ids["a"], ids["b"]], [ids["c"], ids["d"]]]), "expected_versions": versions}, _person(),
            )
        assert refused.value.status_code == 409
        assert all(_live(db, sid) for sid in ids.values()), "nothing was joined, not even the first group"

    def test_a_group_of_one_is_refused(self, db, client):
        from fastapi import HTTPException

        _doc, _pass_id, ids = _row_page(db, client)
        with pytest.raises(HTTPException) as refused:
            _join_rows(db, [[ids["a"]]])
        assert refused.value.status_code == 422

    def test_the_route_joins_and_answers_the_audit_id(self, db, client):
        _doc, _pass_id, ids = _row_page(db, client)
        response = client.post("/api/segments/join-rows", json={
            "groups": _rows([[ids["a"], ids["b"]]]),
            "expected_versions": {ids["a"]: db.get(Segment, ids["a"]).version, ids["b"]: db.get(Segment, ids["b"]).version},
        })
        assert response.status_code == 200, response.text
        assert response.json()["kept_ids"] == [ids["a"]]
        assert response.json()["audit_id"]
        assert not _live(db, ids["b"])


class TestPartsAsWords:
    """`segment-editor.join-rows-keeps-parts-as-words`: the words of the lines joined are the words of the one line."""

    def _words(self, db, line_id):
        words = [row for row in db.query(Segment, pass_id=db.get(Segment, line_id).pass_id)
                 if row.kind == "word" and row.deleted_at is None and row.parent_segment_id == line_id]
        return [row.id for row in sorted(words, key=lambda row: line_join.bounds(line_join.outline_of(row.anchor))[0])]

    def test_the_words_of_every_joined_line_are_the_joined_lines_words_in_page_order(self, db, client):
        doc, pass_id, ids = _row_page(db, client)
        a1 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.05, 0.10, 0.10, 0.05), parent=ids["a"])
        a2 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.15, 0.10, 0.10, 0.05), parent=ids["a"])
        b1 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.30, 0.11, 0.10, 0.05), parent=ids["b"])
        b2 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.40, 0.11, 0.10, 0.05), parent=ids["b"])

        _join_rows(db, [[ids["b"], ids["a"]]])

        assert self._words(db, ids["b"]) == [a1, a2, b1, b2], "the first of the group keeps its id and takes every word"
        assert all(db.get(Segment, word).parent_segment_id == ids["b"] for word in (a1, a2, b1, b2))

    def test_one_undo_gives_each_line_its_words_back(self, db, client):
        doc, pass_id, ids = _row_page(db, client)
        a1 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.05, 0.10, 0.10, 0.05), parent=ids["a"])
        b1 = _segment(client, doc, pass_id, kind="word", polygon=_box(0.30, 0.11, 0.10, 0.05), parent=ids["b"])

        joined = _join_rows(db, [[ids["a"], ids["b"]]])
        undone = client.post(f"/api/actions/audit/{joined.audit_id}/undo")
        assert undone.status_code == 200, undone.text

        assert db.get(Segment, a1).parent_segment_id == ids["a"]
        assert db.get(Segment, b1).parent_segment_id == ids["b"]
        assert _live(db, ids["b"])
