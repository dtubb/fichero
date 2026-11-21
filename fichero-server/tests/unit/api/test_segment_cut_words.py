"""Cut Words: a line's reading split at its spaces into word segments, cut on the page where the words meet.

Spec: docs/contributor_manual/specs/ui/segment-editor.md -- `segment-editor.cut-words-from-positions` (the cut midway
between the end of one word and the start of the next, from the recogniser's positions; each word a child of the line
with its stretch of the reading), `segment-editor.cut-fallback-ink-gaps` (no positions: the widest gaps in the ink, low
confidence), `segment-editor.cut-records-source-and-confidence` (`cut_source`, `cut_confidence`, the reading it was
cut from). Through the real action and the real undo route.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.media import line_join
from fichero_server.models import ContentRepresentation, DocType, Document, FileType, Segment, Status

pytestmark = pytest.mark.source_model

W, H = 1000, 400


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


def _page(db, client, words_px=()):
    """A page with black blocks where the words are (x from, x to, in pixels, on y 100..130)."""
    from PIL import Image, ImageDraw

    image = Image.new("L", (W, H), 255)
    draw = ImageDraw.Draw(image)
    for x0, x1 in words_px:
        draw.rectangle([x0, 100, x1, 130], fill=0)
    path = Path(db.path.parent) / "folio.png"
    image.save(path)
    doc = Document(name="folio.png", doc_type=DocType.file, file_type=FileType.image, path=str(path),
                   status=Status.completed)
    db.save(doc)
    response = client.post("/api/segments/passes", json={"document_id": doc.id, "name": "lines"})
    assert response.status_code == 200, response.text
    return doc, response.json()["id"]


def _line(client, doc, pass_id) -> str:
    response = client.post("/api/segments", json={
        "document_id": doc.id, "pass_id": pass_id, "kind": "line",
        "anchor": {"document_id": doc.id, "polygon": [[0.1, 0.24], [0.9, 0.24], [0.9, 0.34], [0.1, 0.34]]},
        "baseline": [[0.1, 0.32], [0.9, 0.32]],
    })
    assert response.status_code == 200, response.text
    return response.json()["id"]


def _read(db, line, text, positions=None, confidences=None):
    made = registry.invoke(db, "representation.create", {
        "document_id": db.get(Segment, line).document_id, "segment_id": line, "kind": "transcription",
        "content": text}, _person()).result["id"]
    reading = db.get(ContentRepresentation, made)
    reading.char_positions, reading.char_confidences = positions, confidences
    db.save(reading)
    return made


def _cut(db, ids):
    return registry.invoke(db, "segment.cut_words", {
        "segment_ids": ids, "expected_versions": {sid: db.get(Segment, sid).version for sid in ids}}, _person())


def _words(db, line):
    rows = [row for row in db.all(Segment) if row.parent_segment_id == line and row.deleted_at is None]
    return sorted(rows, key=lambda row: line_join.bounds(line_join.outline_of(row.anchor))[0])


def _xs(row):
    x0, _y0, x1, _y1 = line_join.bounds(line_join.outline_of(row.anchor))
    return x0, x1


#: "en el nombre": positions along the baseline (0 to 1) for each of its twelve characters.
TEXT = "en el nombre"
POSITIONS = [0.0, 0.08, 0.16, 0.25, 0.33, 0.41, 0.5, 0.58, 0.66, 0.75, 0.83, 0.91]


class TestFromPositions:
    def test_each_word_is_a_child_of_the_line_cut_midway_between_the_words(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        reading = _read(db, line, TEXT, POSITIONS, [0.9] * 5 + [0.6] + [0.95] * 6)

        result = _cut(db, [line])

        words = _words(db, line)
        assert len(words) == 3 == len(result.result["segment_ids"])
        # The cuts sit midway between "en" ending (the space at 0.16) and "el" starting (0.25), and so on, along
        # a baseline from x 0.1 to 0.9.
        first_cut = 0.1 + 0.8 * (0.16 + 0.25) / 2
        second_cut = 0.1 + 0.8 * (0.41 + 0.5) / 2
        assert _xs(words[0]) == pytest.approx((0.1, first_cut), abs=3e-3)
        assert _xs(words[1]) == pytest.approx((first_cut, second_cut), abs=3e-3)
        assert _xs(words[2]) == pytest.approx((second_cut, 0.9), abs=3e-3)
        assert [w.metadata["reading_span"] for w in words] == [[0, 2], [3, 5], [6, 12]]
        assert {w.metadata["cut_source"] for w in words} == {"ctc"}
        assert {w.metadata["cut_from_representation_id"] for w in words} == {reading}
        assert all(w.kind == "word" for w in words)
        # The second word's right-hand cut falls next to the 0.6-sure space; its confidence is the lower side.
        assert words[1].metadata["cut_confidence"] == pytest.approx(0.6)

    def test_one_undo_takes_the_words_away_and_redo_cuts_them_again(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT, POSITIONS)

        result = _cut(db, [line])
        undone = client.post(f"/api/actions/audit/{result.audit_id}/undo")
        assert undone.status_code == 200, undone.text
        assert _words(db, line) == []
        redone = client.post(f"/api/actions/audit/{undone.json()['audit_id']}/undo")
        assert redone.status_code == 200, redone.text
        assert len(_words(db, line)) == 3
        again = client.post(f"/api/actions/audit/{redone.json()['audit_id']}/undo")
        assert again.status_code == 200, again.text
        assert _words(db, line) == []

    def test_cutting_again_replaces_the_machines_words_and_keeps_a_persons(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT, POSITIONS)
        person = client.post("/api/segments", json={
            "document_id": doc.id, "pass_id": pass_id, "kind": "word", "parent_segment_id": line,
            "anchor": {"document_id": doc.id, "rect": [0.1, 0.24, 0.15, 0.1]},
        }).json()["id"]

        first = _cut(db, [line])
        second = _cut(db, [line])

        words = _words(db, line)
        assert person in [w.id for w in words]
        assert len(words) == 3, "the person's word stands for the first; the machine's two are cut once, not twice"
        assert set(second.result["replaced"]) == set(first.result["segment_ids"])

    def test_a_persons_word_stands_only_where_its_outline_is_not_its_bounding_box(self, db, client):
        # An L-shaped word: the first word's place, and a thin strip under the rest of the line. Its bounding box
        # covers the whole line; its outline covers only the first word's centre.
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT, POSITIONS)
        person = client.post("/api/segments", json={
            "document_id": doc.id, "pass_id": pass_id, "kind": "word", "parent_segment_id": line,
            "anchor": {"document_id": doc.id, "polygon": [
                [0.1, 0.24], [0.25, 0.24], [0.25, 0.33], [0.9, 0.33], [0.9, 0.34], [0.1, 0.34]]},
        }).json()["id"]

        _cut(db, [line])

        words = _words(db, line)
        assert person in [w.id for w in words]
        assert len(words) == 3, "the person's word stands for the first; the other two are cut"


class TestThePageReadsTheSame:
    def test_cutting_words_leaves_the_pages_text_as_it_was(self, db, client):
        from fichero_server.api.routes.document.segment_readings import document_text

        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT, POSITIONS)
        before = document_text(db, doc.id)

        _cut(db, [line])

        assert document_text(db, doc.id) == before


class TestFallback:
    def test_with_no_positions_the_widest_ink_gaps_are_taken_and_marked_low(self, db, client):
        # Three words of ink: 100-200, 300-450, 560-900 px along a baseline from 100 to 900.
        doc, pass_id = _page(db, client, words_px=[(100, 200), (300, 450), (560, 899)])
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT)

        _cut(db, [line])

        words = _words(db, line)
        assert len(words) == 3
        assert {w.metadata["cut_source"] for w in words} == {"ink-gap"}
        assert all(w.metadata["cut_confidence"] <= 0.4 for w in words)
        assert _xs(words[0])[1] == pytest.approx(250 / W, abs=0.01)
        assert _xs(words[1])[1] == pytest.approx(505 / W, abs=0.01)

    def test_a_line_with_no_reading_cannot_be_cut_and_says_why(self, db, client):
        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)

        with pytest.raises(HTTPException) as refused:
            _cut(db, [line])
        assert refused.value.status_code == 422
        assert refused.value.detail["left_alone"] == [{"segment_id": line, "reason": "no-reading"}]


class TestAfterARead:
    def test_lines_read_with_positions_are_cut_by_themselves_and_a_line_that_cannot_be_is_left(self, db, client):
        from fichero_server.llm.working_lines import cut_words_after_read

        doc, pass_id = _page(db, client)
        read = _line(client, doc, pass_id)
        _read(db, read, TEXT, POSITIONS)
        unread = _line(client, doc, pass_id)

        made = cut_words_after_read(db, doc.id, [read, unread])

        assert len(made) == 3
        assert len(_words(db, read)) == 3 and _words(db, unread) == []
        assert cut_words_after_read(db, doc.id, [unread]) == [], "a line it cannot cut never fails the read"


class TestExport:
    def test_the_words_go_to_the_export_with_how_they_were_cut(self, db, client):
        """`segment-editor.export-carries-every-edit`: the library's words reach the formats' page with their cut."""
        from fichero_server.page_export import CUT_FACTS, page_from_library

        doc, pass_id = _page(db, client)
        line = _line(client, doc, pass_id)
        _read(db, line, TEXT, POSITIONS, [0.9] * len(TEXT))
        _cut(db, [line])

        page, _choices = page_from_library(db, doc.id, pass_id=pass_id)

        words = [segment for segment in page.segments if segment.kind == "word"]
        assert len(words) == 3
        assert {segment.foreign[CUT_FACTS]["source"] for segment in words} == {"ctc"}
        assert all(segment.foreign[CUT_FACTS]["confidence"] == pytest.approx(0.9) for segment in words)


def test_words_a_second_cut_replaces_leave_forwarding_notes_and_its_undo_brings_them_back(db, client):
    """Review of batch 16 (2026-11-14): the machine words a cut replaces are soft-deleted with a `deleted` note, as
    `segment.delete` leaves, so a reference to one can say what became of it; the undo leaves `restored`."""
    from fichero_server.models.segments import SegmentForwarding

    doc, pass_id = _page(db, client)
    line = _line(client, doc, pass_id)
    _read(db, line, TEXT, POSITIONS)
    _cut(db, [line])
    first = [word.id for word in _words(db, line)]
    again = _cut(db, [line])
    notes = {(note.old_segment_id, note.kind) for note in db.all(SegmentForwarding)}
    assert all((wid, "deleted") in notes for wid in first)

    undone = client.post(f"/api/actions/audit/{again.audit_id}/undo")
    assert undone.status_code == 200, undone.text
    notes = {(note.old_segment_id, note.kind) for note in db.all(SegmentForwarding)}
    assert all((wid, "restored") in notes for wid in first)


def _order_under(db, line):
    """The word ids in the page's reading order under the line, in sequence."""
    from fichero_server.api.routes.document.reading_orders import entries_in_sequence
    from fichero_server.models.reading_orders import ReadingOrder, ReadingOrderEntry

    row = db.get(Segment, line)
    for order in db.query(ReadingOrder, pass_id=row.pass_id):
        (entry,) = [e for e in db.query(ReadingOrderEntry, order_id=order.id) if e.segment_id == line] or [None]
        if entry is not None:
            return [e.segment_id for e in entries_in_sequence(db, order.id, parent_entry_id=entry.id)]
    return []


class TestDirections:
    """`segment-editor.edge.rtl-vertical`: a word cut and the order of its words follow the line's resolved direction;
    the first word of a right-to-left line is its right-hand piece, of a vertical line its top piece."""

    #: Three Hebrew words of 2, 3 and 5 letters: spans [0, 2], [3, 6], [7, 12].
    HEBREW = "אב גדה וזחטי"

    def test_a_right_to_left_line_is_cut_from_the_right_and_its_words_are_ordered_from_the_right(self, db, client):
        # Read from the right: the 2-letter word at 760-899 px, the 3-letter at 450-650, the 5-letter at 100-350.
        doc, pass_id = _page(db, client, words_px=[(760, 899), (450, 650), (100, 350)])
        line = _line(client, doc, pass_id)
        _read(db, line, self.HEBREW)

        _cut(db, [line])

        left_to_right = _words(db, line)
        assert [w.metadata["reading_span"] for w in left_to_right] == [[7, 12], [3, 6], [0, 2]]
        assert _xs(left_to_right[2])[0] == pytest.approx(705 / W, abs=0.01)
        assert _order_under(db, line) == [w.id for w in reversed(left_to_right)], "the first word read comes first"

    def test_a_vertical_line_is_cut_from_the_top_and_its_words_are_ordered_from_the_top(self, db, client):
        from PIL import Image, ImageDraw

        doc, pass_id = _page(db, client)
        image = Image.new("L", (W, H), 255)
        draw = ImageDraw.Draw(image)
        for y0, y1 in [(40, 90), (150, 230), (290, 360)]:  # down the column x 500..530
            draw.rectangle([500, y0, 530, y1], fill=0)
        image.save(doc.path)
        response = client.post("/api/segments", json={
            "document_id": doc.id, "pass_id": pass_id, "kind": "line",
            "anchor": {"document_id": doc.id, "polygon": [[0.49, 0.05], [0.54, 0.05], [0.54, 0.95], [0.49, 0.95]]},
            "baseline": [[0.52, 0.05], [0.52, 0.95]],
        })
        assert response.status_code == 200, response.text
        line = response.json()["id"]
        registry.invoke(db, "segment.update_many", {"updates": [
            {"segment_id": line, "expected_version": db.get(Segment, line).version, "direction": "ttb"}]}, _person())
        _read(db, line, "一二 三四五 六七八九十")

        _cut(db, [line])

        words = [row for row in db.all(Segment) if row.parent_segment_id == line and row.deleted_at is None]
        top_down = sorted(words, key=lambda row: line_join.bounds(line_join.outline_of(row.anchor))[1])
        assert [w.metadata["reading_span"] for w in top_down] == [[0, 2], [3, 6], [7, 12]]
        assert _order_under(db, line) == [w.id for w in top_down]
