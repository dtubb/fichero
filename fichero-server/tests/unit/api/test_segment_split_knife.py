"""The Knife: one stroke splits every line whose baseline it crosses.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.split-knife` (`segment.split` with
`cut_path`: each crossed line cut at the crossings, its outline along the stroke, each part its own baseline;
two crossings make three parts; a grazed line is left alone and said so; the reading cut at the nearest
character position when known, else in proportion with `cut: estimated`; one stroke is one action, one
undo), `segment-editor.edge.no-baseline` and `segment-editor.edge.rtl-vertical`.

All through the real action and the real undo route.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

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


def _box(x, y, w, h):
    return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]


def _line(client, doc, pass_id, *, polygon, baseline=None) -> str:
    body = {"document_id": doc.id, "pass_id": pass_id, "kind": "line",
            "anchor": {"document_id": doc.id, "polygon": polygon}}
    if baseline:
        body["baseline"] = baseline
    response = client.post("/api/segments", json=body)
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _read(db, segment_id, text, positions=None):
    result = registry.invoke(
        db, "representation.create",
        {"document_id": db.get(Segment, segment_id).document_id, "segment_id": segment_id,
         "kind": "transcription", "content": text},
        _person(),
    )
    if positions is not None:
        reading = db.get(ContentRepresentation, result.result["id"])
        reading.char_positions = positions
        db.save(reading)


def _texts(db, result, segment_id) -> list[str]:
    """The readings the split cut for each part of `segment_id`, first to last."""
    split = next(split for split in result.result["splits"] if split["kept_id"] == segment_id)
    by_part = {}
    for representation_id in split["representation_ids"]:
        reading = db.get(ContentRepresentation, representation_id)
        by_part[reading.segment_id] = reading.content
    return [by_part.get(part) for part in _parts(result, segment_id)]


def _knife(db, ids, stroke):
    return registry.invoke(
        db, "segment.split",
        {"cut_path": stroke, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}},
        _person(),
    )


def _parts(result, segment_id) -> list[str]:
    split = next(split for split in result.result["splits"] if split["kept_id"] == segment_id)
    return [split["kept_id"], *split["new_segment_ids"]]


def _xs(db, segment_id) -> tuple[float, float]:
    x0, _y0, x1, _y1 = line_join.bounds(db.get(Segment, segment_id).anchor.polygon)
    return x0, x1


class TestOneStroke:
    def test_a_stroke_across_a_line_cuts_its_outline_and_baseline_there(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])

        result = _knife(db, [line], [[0.5, 0.15], [0.5, 0.3]])

        first, second = _parts(result, line)
        assert _xs(db, first) == pytest.approx((0.1, 0.5), abs=2e-3)
        assert _xs(db, second) == pytest.approx((0.5, 0.9), abs=2e-3)
        assert db.get(Segment, first).baseline == [[0.1, 0.24], [0.5, 0.24]]
        assert db.get(Segment, second).baseline == [[0.5, 0.24], [0.9, 0.24]]

    def test_two_crossings_make_three_parts(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])

        # Down through the line, along under it, and back up: a U that crosses the baseline twice.
        result = _knife(db, [line], [[0.3, 0.15], [0.3, 0.3], [0.7, 0.3], [0.7, 0.15]])

        parts = _parts(result, line)
        assert len(parts) == 3
        spans = [x for part in parts for x in _xs(db, part)]
        assert spans == pytest.approx([0.1, 0.3, 0.3, 0.7, 0.7, 0.9], abs=2e-3)

    def test_a_grazed_line_is_left_alone_and_said(self, db, client):
        doc, pass_id = _page(db, client)
        crossed = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])
        grazed = _line(client, doc, pass_id, polygon=_box(0.1, 0.3, 0.8, 0.05), baseline=[[0.1, 0.34], [0.9, 0.34]])
        before = db.get(Segment, grazed).model_copy()

        # Through the first line, and into the top of the second's outline without reaching its baseline.
        result = _knife(db, [crossed, grazed], [[0.5, 0.15], [0.5, 0.32]])

        assert [split["kept_id"] for split in result.result["splits"]] == [crossed]
        assert result.result["left_alone"] == [{"segment_id": grazed, "reason": "grazed"}]
        after = db.get(Segment, grazed)
        assert (after.version, after.anchor.polygon) == (before.version, before.anchor.polygon)

    def test_a_stroke_that_crosses_nothing_is_refused_and_names_the_lines(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])

        with pytest.raises(HTTPException) as refused:
            _knife(db, [line], [[0.2, 0.21], [0.8, 0.21]])
        assert refused.value.status_code == 422
        assert refused.value.detail["left_alone"] == [{"segment_id": line, "reason": "grazed"}]

    def test_a_line_with_no_baseline_is_left_alone_and_said(self, db, client):
        doc, pass_id = _page(db, client)
        crossed = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])
        boxed = _line(client, doc, pass_id, polygon=_box(0.1, 0.3, 0.8, 0.05))

        result = _knife(db, [crossed, boxed], [[0.5, 0.15], [0.5, 0.4]])

        assert result.result["left_alone"] == [{"segment_id": boxed, "reason": "no-baseline"}]


class TestManyLinesOneUndo:
    def _two(self, db, client):
        doc, pass_id = _page(db, client)
        top = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])
        bottom = _line(client, doc, pass_id, polygon=_box(0.1, 0.3, 0.8, 0.05), baseline=[[0.1, 0.34], [0.9, 0.34]])
        return top, bottom

    def test_one_stroke_over_two_lines_is_one_action_and_one_undo(self, db, client):
        top, bottom = self._two(db, client)
        shapes = {sid: db.get(Segment, sid).anchor.polygon for sid in (top, bottom)}
        _read(db, top, "en el nombre")

        result = _knife(db, [top, bottom], [[0.5, 0.15], [0.5, 0.4]])
        new_ids = [part for sid in (top, bottom) for part in _parts(result, sid)[1:]]
        assert len(new_ids) == 2

        response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
        assert response.status_code == 200, response.text

        for sid in (top, bottom):
            assert db.get(Segment, sid).anchor.polygon == shapes[sid]
        assert all(db.get(Segment, new_id).deleted_at is not None for new_id in new_ids)
        assert db.get(Segment, top).version > 1

    def test_redo_cuts_both_lines_again_and_undoes_again(self, db, client):
        top, bottom = self._two(db, client)
        result = _knife(db, [top, bottom], [[0.5, 0.15], [0.5, 0.4]])
        cut = {sid: db.get(Segment, sid).anchor.polygon for sid in (top, bottom)}

        undone = client.post(f"/api/actions/audit/{result.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
        assert redone.status_code == 200, redone.text
        for sid in (top, bottom):
            assert db.get(Segment, sid).anchor.polygon == cut[sid]

        again = client.post(f"/api/actions/audit/{redone.json()['audit_id']}/undo")
        assert again.status_code == 200, again.text
        live = [row for row in db.query(Segment, document_id=db.get(Segment, top).document_id) if row.deleted_at is None]
        assert len([row for row in live if row.kind == "line"]) == 2


class TestTheReading:
    def test_the_reading_is_cut_in_proportion_and_marked_estimated(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.0, 0.2, 1.0, 0.05), baseline=[[0.0, 0.24], [1.0, 0.24]])
        _read(db, line, "abcdefghij")

        result = _knife(db, [line], [[0.3, 0.15], [0.3, 0.3]])

        first, second = _parts(result, line)
        assert _texts(db, result, line) == ["abc", "defghij"]
        assert db.get(Segment, first).metadata.get("cut") == "estimated"
        assert db.get(Segment, second).metadata.get("cut") == "estimated"

    def test_undoing_the_cut_takes_the_cut_mark_off_the_line_again(self, db, client):
        """A version snapshot carries no metadata, so the undo puts the line's metadata back itself: the line is
        not still marked `cut: estimated` once it is whole again (found 2026-11-14)."""
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.0, 0.2, 1.0, 0.05), baseline=[[0.0, 0.24], [1.0, 0.24]])
        _read(db, line, "abcdefghij")
        result = _knife(db, [line], [[0.3, 0.15], [0.3, 0.3]])
        undone = client.post(f"/api/actions/audit/{result.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        assert "cut" not in (db.get(Segment, line).metadata or {})

    def test_known_character_positions_cut_at_the_nearest_character_and_are_not_estimates(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.0, 0.2, 1.0, 0.05), baseline=[[0.0, 0.24], [1.0, 0.24]])
        # "en el": the second word starts well past where a proportional cut would fall.
        _read(db, line, "en el", positions=[0.0, 0.1, 0.2, 0.6, 0.7])

        result = _knife(db, [line], [[0.58, 0.15], [0.58, 0.3]])

        first, _second = _parts(result, line)
        assert _texts(db, result, line) == ["en ", "el"]
        assert db.get(Segment, first).metadata.get("cut") is None

    def test_a_right_to_left_line_keeps_its_first_words_on_the_right_hand_part(self, db, client):
        doc, pass_id = _page(db, client)
        # A Hebrew line, its baseline drawn left to right as Kraken does.
        line = _line(client, doc, pass_id, polygon=_box(0.0, 0.2, 1.0, 0.05), baseline=[[0.0, 0.24], [1.0, 0.24]])
        _read(db, line, "אבגדהוזחטי")

        result = _knife(db, [line], [[0.7, 0.15], [0.7, 0.3]])

        kept, _rest = _parts(result, line)
        assert _xs(db, kept) == pytest.approx((0.7, 1.0), abs=2e-3), "the reading starts at the right"
        assert _texts(db, result, line) == ["אבג", "דהוזחטי"]

    def test_a_vertical_line_is_cut_across_from_the_top(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.5, 0.0, 0.05, 1.0), baseline=[[0.52, 0.0], [0.52, 1.0]])
        registry.invoke(
            db, "segment.update_many",
            {"updates": [{"segment_id": line, "expected_version": db.get(Segment, line).version, "direction": "ttb"}]},
            _person(),
        )
        _read(db, line, "一二三四五六七八九十")

        result = _knife(db, [line], [[0.4, 0.4], [0.6, 0.4]])

        kept, _rest = _parts(result, line)
        _x0, y0, _x1, y1 = line_join.bounds(db.get(Segment, kept).anchor.polygon)
        assert (y0, y1) == pytest.approx((0.0, 0.4), abs=2e-3)
        assert _texts(db, result, line) == ["一二三四", "五六七八九十"]


class TestWords:
    def test_each_word_goes_with_the_part_its_centre_falls_in_and_undo_puts_it_back(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])
        words = []
        for x in (0.15, 0.35, 0.55, 0.75):
            response = client.post("/api/segments", json={
                "document_id": doc.id, "pass_id": pass_id, "kind": "word", "parent_segment_id": line,
                "anchor": {"document_id": doc.id, "rect": [x, 0.205, 0.08, 0.04]},
            })
            assert response.status_code == 200, response.text
            words.append(response.json()["id"])

        result = _knife(db, [line], [[0.5, 0.15], [0.5, 0.3]])

        kept, rest = _parts(result, line)
        assert [db.get(Segment, word).parent_segment_id for word in words] == [kept, kept, rest, rest]
        response = client.post(f"/api/actions/audit/{result.audit_id}/undo")
        assert response.status_code == 200, response.text
        assert [db.get(Segment, word).parent_segment_id for word in words] == [line] * 4


class TestRefusals:
    def test_a_changed_line_refuses_the_whole_stroke(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])
        stale = db.get(Segment, line).version - 1

        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.split", {"cut_path": [[0.5, 0.1], [0.5, 0.3]], "expected_versions": {line: stale}},
                _person(),
            )
        assert refused.value.status_code == 409

    def test_a_cut_path_is_given_alone(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id, polygon=_box(0.1, 0.2, 0.8, 0.05), baseline=[[0.1, 0.24], [0.9, 0.24]])

        with pytest.raises(HTTPException) as refused:
            registry.invoke(
                db, "segment.split",
                {"segment_id": line, "cut_path": [[0.5, 0.1], [0.5, 0.3]],
                 "expected_versions": {line: db.get(Segment, line).version}},
                _person(),
            )
        assert refused.value.status_code == 422
