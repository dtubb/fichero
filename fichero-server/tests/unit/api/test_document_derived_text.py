"""Source-model slice 8, part 4 (#4934) -- a page's text is WORKED OUT, and a
stretch of a reading survives the reading changing under it.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 8", sections "A page's
text is worked out" and "A stretch of a reading".

Behaviours pinned:
* `source.point.text-is-derived` -- the derived text of a page equals the join
  of its segments' counting readings in order, with spans that point back;
  leaving furniture out drops a running head.
* `source.pass.working` -- the text comes from the working pass, and says which
  and why.
* `source.reading.stretch-names-its-reading` -- a stretch is carried over only
  when the same characters occur exactly once; otherwise it is reported
  unplaced, never re-measured by position.

Asserted on the real derived text through the real route, over a page
converted by the real first-edit path.
"""

from __future__ import annotations

import pytest

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.document.segment_conversion import (
    converted_pass_id,
    live_rows_in_order,
)
from fichero_server.api.routes.document.segment_readings import document_text
from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
from fichero_server.models import Artifact, DocType, Document, FileType, Segment, Status
from fichero_server.models.readings import PassBasis, replace_stretch

pytestmark = pytest.mark.source_model

LINES = ["Libro de cuentas", "en el nombre", "de dios amen"]
PAGE_TEXT = " ".join(LINES)


def _make_doc(db, name: str = "folio.jpg") -> Document:
    doc = Document(
        name=name, doc_type=DocType.file, file_type=FileType.image,
        path=f"/path/{name}", status=Status.completed,
    )
    db.save(doc)
    return doc


def _artifact(db, doc, *, artifact_type: str = "transcription") -> Artifact:
    boxes = []
    cursor = 0
    for index, line in enumerate(LINES):
        start = PAGE_TEXT.index(line, cursor)
        boxes.append(
            OCRGeometryBox(
                text=line, bbox=[0.1, 0.1 + index * 0.2, 0.6, 0.08], level="line",
                char_start=start, char_end=start + len(line),
            )
        )
        cursor = start + len(line)
    artifact = Artifact(
        document_id=doc.id, artifact_type=artifact_type, provider="qwen", model="qwen-vl",
        content=PAGE_TEXT,
        ocr_geometry=OCRGeometryResult(provider="qwen", text=PAGE_TEXT, boxes=boxes),
    )
    db.save(artifact)
    return artifact


def _convert(client, artifact_id: str) -> None:
    response = client.put(
        f"/api/artifacts/{artifact_id}/regions",
        json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.6, 0.08]},
    )
    assert response.status_code == 200, response.text


def _person() -> ActionContext:
    return ActionContext(actor="historian", library_path=None, is_bootstrap=True)


class TestTheDerivedText:
    """`source.point.text-is-derived`."""

    def test_the_page_text_is_the_join_of_its_lines_readings_in_order(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        derived = document_text(db, doc.id)

        assert derived.text == PAGE_TEXT
        assert derived.pass_id == converted_pass_id(artifact.id)
        assert derived.kind == "transcription"
        # Box order, and the answer says so rather than implying a named order
        # exists (those are slice 10).
        assert derived.order is None

    def test_every_span_points_back_at_the_line_and_the_reading(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))

        derived = document_text(db, doc.id)

        assert [span.segment_id for span in derived.spans] == [row.id for row in rows]
        for span, line in zip(derived.spans, LINES):
            assert derived.text[span.start : span.end] == line
            assert span.representation_id is not None

    def test_the_route_answers_the_same_thing(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        payload = client.get(f"/api/segments/document/{doc.id}/text").json()

        assert payload["text"] == PAGE_TEXT
        assert len(payload["spans"]) == len(LINES)
        # The page's first edit recorded which pass the person was working on
        # (slice 6), so the basis is that choice -- not a ranking. A choice
        # beating the ranking is the whole point of recording one.
        assert payload["pass_basis"] == PassBasis.chosen.value

    def test_a_persons_reading_replaces_the_machines_in_the_derived_text(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))

        registry.invoke(
            db, "representation.create",
            {
                "document_id": doc.id, "segment_id": rows[1].id,
                "kind": "transcription", "content": "en el nõbre", "level": "as_written",
            },
            _person(),
        )

        derived = document_text(db, doc.id)
        assert "en el nõbre" in derived.text
        assert "en el nombre" not in derived.text

    def test_furniture_is_left_out_and_can_be_asked_for(self, db, client):
        """A running head is on the page and is properly a segment, but it is
        not the text of the document."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        # The first line IS the running head on this folio. Marked directly:
        # `segment.update`'s furniture flag is not this slice's business.
        db.save(rows[0].model_copy(update={"is_furniture": True}))

        without = document_text(db, doc.id)
        assert without.text == " ".join(LINES[1:])
        assert LINES[0] not in without.text

        with_it = document_text(db, doc.id, include_furniture=True)
        assert with_it.text == PAGE_TEXT

    def test_a_line_whose_readings_disagree_leaves_a_recorded_gap(self, db, client):
        """A strict project where two people read a line differently. Leaving a
        hole silently would be a lie about the page; picking one would be the
        engine deciding. The span records the gap, with no reading named."""
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))
        for content in ("en el nõbre", "en el nomine"):
            registry.invoke(
                db, "representation.create",
                {
                    "document_id": doc.id, "segment_id": rows[1].id,
                    "kind": "transcription", "content": content,
                },
                _person(),
            )

        derived = document_text(db, doc.id)

        gap = [span for span in derived.spans if span.segment_id == rows[1].id]
        assert len(gap) == 1
        assert gap[0].representation_id is None
        assert gap[0].start == gap[0].end
        assert "nõbre" not in derived.text and "nomine" not in derived.text

    def test_a_named_pass_can_be_read_instead_of_the_working_one(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        derived = document_text(db, doc.id, pass_id=converted_pass_id(artifact.id))
        assert derived.pass_basis == PassBasis.chosen.value

        with pytest.raises(LookupError):
            document_text(db, doc.id, pass_id="no-such-pass")

    def test_an_unconverted_page_has_no_pass_and_says_so(self, db, client):
        """Honest emptiness: the words are still in the artifact, and this call
        is about the segment store. Nothing is invented, and `pass_basis` tells
        the caller exactly why the text is empty."""
        doc = _make_doc(db)
        _artifact(db, doc)

        derived = document_text(db, doc.id)

        assert derived.text == ""
        assert derived.spans == []
        assert derived.pass_id is None
        assert derived.pass_basis == PassBasis.none.value

    def test_a_named_reading_order_is_refused_until_slice_10(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        with pytest.raises(ValueError) as excinfo:
            document_text(db, doc.id, order="as-written")
        assert "slice 10" in str(excinfo.value)

    def test_a_deleted_line_drops_out_of_the_text(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        rows = live_rows_in_order(db, converted_pass_id(artifact.id))

        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [rows[2].id], "expected_versions": {rows[2].id: rows[2].version}},
            _person(),
        )

        derived = document_text(db, doc.id)
        assert LINES[2] not in derived.text
        assert rows[2].id not in [span.segment_id for span in derived.spans]


class TestAStretchSurvivesTheReadingChanging:
    """`source.reading.stretch-names-its-reading`."""

    def test_a_stretch_is_carried_over_when_its_words_occur_once(self):
        old = "en el nõbre de dios"
        placed = replace_stretch(
            old_text=old,
            char_start=old.index("de dios"),
            char_end=len(old),
            new_text="en el nombre de dios",
            new_representation_id="rep-new",
        )
        assert placed.placed is True
        assert placed.representation_id == "rep-new"
        assert placed.reason is None
        # It found the CHARACTERS, not the offsets.
        assert "en el nombre de dios"[placed.char_start : placed.char_end] == "de dios"

    def test_the_offsets_move_rather_than_being_kept(self):
        """A mark on characters 12..18 of one transcription lands on different
        words in a transcription that expanded an abbreviation earlier in the
        line. Keeping the offsets would move somebody's annotation onto text
        they never read."""
        old = "en el nõbre de dios"
        new = "en el nombre de dios"
        placed = replace_stretch(
            old_text=old, char_start=old.index("dios"), char_end=old.index("dios") + 4,
            new_text=new, new_representation_id="rep-new",
        )
        assert placed.placed is True
        assert new[placed.char_start : placed.char_end] == "dios"
        assert placed.char_start != old.index("dios"), "the offset moved with the text"

    def test_a_stretch_whose_words_occur_twice_is_reported_unplaced(self):
        placed = replace_stretch(
            old_text="de dios amen",
            char_start=0,
            char_end=2,
            new_text="de dios de amen",
            new_representation_id="rep-new",
        )
        assert placed.placed is False
        assert placed.representation_id is None
        assert "ambiguous" in placed.reason

    def test_a_stretch_whose_words_are_gone_is_reported_unplaced(self):
        placed = replace_stretch(
            old_text="en el nõbre",
            char_start=6,
            char_end=11,
            new_text="en el nombre",
            new_representation_id="rep-new",
        )
        assert placed.placed is False
        assert "does not appear" in placed.reason

    def test_a_stretch_outside_the_old_reading_is_refused_not_clamped(self):
        placed = replace_stretch(
            old_text="en el",
            char_start=3,
            char_end=99,
            new_text="en el nombre",
            new_representation_id="rep-new",
        )
        assert placed.placed is False
        assert "not inside" in placed.reason
