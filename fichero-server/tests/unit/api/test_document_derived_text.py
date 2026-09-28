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
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.core.timeutil import utc_now
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

    def test_a_named_order_gives_a_different_text_from_box_order(self, db, client):
        """Slice 10 (#4930) replaced the refusal this test used to assert. The
        behaviour that replaced it is the one worth pinning: two orders over the
        same page give two texts, which is the whole point of naming them."""
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.api.routes.document.reading_orders import as_written_order

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        pass_id = converted_pass_id(artifact.id)
        rows = live_rows_in_order(db, pass_id)
        person = ActionContext(actor="historian", is_bootstrap=True)

        box_order_text = document_text(db, doc.id).text
        written = as_written_order(db, pass_id)
        assert document_text(db, doc.id, order=written.id).text == box_order_text

        # An imposed order, the lines backwards.
        imposed = registry.invoke(
            db,
            "reading_order.create",
            {
                "document_id": doc.id, "pass_id": pass_id,
                "name": "backwards", "kind": "imposed",
            },
            person,
        ).result
        for row in reversed(rows):
            registry.invoke(
                db,
                "reading_order.place",
                {"order_id": imposed["order_id"], "segment_id": row.id, "at_end": True},
                person,
            )

        backwards = document_text(db, doc.id, order=imposed["order_id"])
        assert backwards.text != box_order_text
        # The LINES are reversed, not the words: asserted through the spans, which
        # are the only thing that says which line a stretch of text came from.
        # (Reversing the words would be a different, wrong claim -- a line holds
        # several of them.)
        box_order = document_text(db, doc.id)
        assert [span.segment_id for span in backwards.spans] == list(
            reversed([span.segment_id for span in box_order.spans])
        )
        # And the answer says WHICH order made it, so a reader can check.
        assert backwards.order == imposed["order_id"]
        assert document_text(db, doc.id).order is None

    def test_an_order_that_does_not_exist_is_refused(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        with pytest.raises(HTTPException) as raised:
            document_text(db, doc.id, order="no-such-order")
        assert raised.value.status_code == 404

    def test_a_segment_the_order_does_not_mention_is_left_out_not_appended(self, db, client):
        """An order is a claim about what reads and in what sequence. Appending
        the lines it does not name would silently add text the order does not
        claim — and a commentary order that deliberately omits the running heads
        would grow them back."""
        from fichero_server.actions.registry import ActionContext, registry

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        pass_id = converted_pass_id(artifact.id)
        rows = live_rows_in_order(db, pass_id)
        person = ActionContext(actor="historian", is_bootstrap=True)

        partial = registry.invoke(
            db,
            "reading_order.create",
            {"document_id": doc.id, "pass_id": pass_id, "name": "first line only",
             "kind": "commentary"},
            person,
        ).result
        registry.invoke(
            db,
            "reading_order.place",
            {"order_id": partial["order_id"], "segment_id": rows[0].id},
            person,
        )

        derived = document_text(db, doc.id, order=partial["order_id"])
        assert len(derived.spans) == 1
        assert derived.spans[0].segment_id == rows[0].id

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


class TestWordsOnOneLineReadLeftToRight:
    """The words of a line must not come out in uuid order (found 2026-09-26).

    `_segment_order_key` sorted by `bbox_y` and then fell through to `row.id`.
    Two segments on the SAME line have identical `bbox_y` and, when nothing
    recorded a `box_index`, nothing else to separate them — so a random uuid
    decided which word came first. `media/ocr_geometry.py::reading_order` sorts
    boxes top-then-LEFT precisely to avoid this; the row key now matches it.
    """

    def test_three_words_of_one_line_are_joined_left_to_right(self, db, client):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.segments import SegmentPass
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.api.routes.document.segment_readings import document_text

        doc = Document(
            name="one-line.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/path/one-line.jpg", status=Status.completed,
        )
        db.save(doc)
        pass_row = SegmentPass(
            document_id=doc.id, name="hand", provenance_kind=ProvenanceKind.human,
        )
        db.save(pass_row)

        # Written in a deliberately WRONG order, so passing cannot be an accident
        # of insertion order: the middle word is saved first.
        placed = [("nombre", 0.30), ("en", 0.10), ("dios", 0.60)]
        for words, x in placed:
            row = Segment(
                document_id=doc.id, pass_id=pass_row.id, kind="word",
                doc_kind=f"{doc.id}:word",
                anchor=SourceAnchor(document_id=doc.id, rect=[x, 0.4, 0.08, 0.03]),
                bbox_x=x, bbox_y=0.4, bbox_w=0.08, bbox_h=0.03, tile="",
                provenance_kind=ProvenanceKind.human,
            )
            db.save(row)
            registry.invoke(
                db,
                "representation.create",
                {
                    "document_id": doc.id, "segment_id": row.id,
                    "kind": "transcription", "content": words,
                },
                ActionContext(actor="historian", is_bootstrap=True),
            )

        derived = document_text(db, doc.id, pass_id=pass_row.id)

        assert derived.text == "en nombre dios", (
            "words of one line were not joined left to right: " + derived.text
        )


class TestWhatAnOrderNamesAndTheTextDoesNotHold:
    """#5090's first step: stop dropping silently.

    `document_text` draws its rows from ONE pass and then keeps only the ordered
    ids it holds. For a deleted line, or furniture the caller excluded, dropping
    is right. For a **cross-pass flow** — a `source.segment.flow` whose entries
    name segments on the next folio's pass, which slice 10 deliberately allows —
    dropping is the transcription coming back short with nothing to show it.

    Nothing distinguished the two. Now every omission is named with a reason, so
    `deleted` (the text is complete) and `other_pass` (a continuation is missing)
    are different answers. Reading the other pass needs a decision about what
    `pass_id` and the `page_content` cache mean and is NOT done here.
    """

    def _person(self):
        from fichero_server.actions.registry import ActionContext

        return ActionContext(actor="historian", is_bootstrap=True)

    def _flow_onto_a_second_pass(self, db, client):
        from fichero_server.actions.registry import registry
        from fichero_server.models.anchors import SourceAnchor
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import SegmentPass

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        pass_id = converted_pass_id(artifact.id)
        rows = live_rows_in_order(db, pass_id)
        person = self._person()

        second_folio = SegmentPass(
            document_id=doc.id, name="folio 2v", provenance_kind=ProvenanceKind.human
        )
        db.save(second_folio)
        continuation = Segment(
            document_id=doc.id, pass_id=second_folio.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.1, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=0.1, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(continuation)

        flow = registry.invoke(
            db, "reading_order.create",
            {"document_id": doc.id, "pass_id": pass_id,
             "name": "reads straight through", "kind": "flow"},
            person,
        ).result
        registry.invoke(
            db, "reading_order.place",
            {"order_id": flow["order_id"], "segment_id": rows[0].id}, person,
        )
        registry.invoke(
            db, "reading_order.place",
            {"order_id": flow["order_id"], "segment_id": continuation.id, "at_end": True},
            person,
        )
        return doc, pass_id, rows, flow, continuation, second_folio

    def test_a_cross_pass_continuation_is_reported_not_silently_dropped(self, db, client):
        doc, _, rows, flow, continuation, second_folio = self._flow_onto_a_second_pass(
            db, client
        )

        derived = document_text(db, doc.id, order=flow["order_id"])

        # Still left out of the text — that part needs the decision the issue names.
        assert continuation.id not in [span.segment_id for span in derived.spans]
        # But no longer invisible.
        assert [(o.segment_id, o.reason) for o in derived.omitted] == [
            (continuation.id, "other_pass")
        ]
        # And it says WHERE, so a caller can go and read it.
        assert derived.omitted[0].pass_id == second_folio.id

    def test_a_deleted_line_and_a_missing_continuation_no_longer_look_the_same(
        self, db, client
    ):
        """The point of the whole change: two omissions, two reasons.

        Since 2026-09-28 (1052fda4a, 9347daedb) `segment.delete`, `segment.merge` and
        `segment.unsplit` take a retired segment's entries OUT of every order, so an action
        no longer leaves an order naming a deleted line. A library written BEFORE that still
        holds such entries -- nothing migrates them -- so `deleted` is still a reason a real
        order can give, and this builds exactly that library: the line is retired the old way,
        its entry left behind."""
        from fichero_server.actions.registry import registry

        doc, _, rows, flow, continuation, _ = self._flow_onto_a_second_pass(db, client)
        registry.invoke(
            db, "reading_order.place",
            {"order_id": flow["order_id"], "segment_id": rows[1].id, "at_end": True},
            self._person(),
        )
        # An older library: the segment soft-deleted, its order entry still there.
        retired = db.get(Segment, rows[1].id)
        retired.deleted_at = utc_now()
        db.save(retired)

        derived = document_text(db, doc.id, order=flow["order_id"])

        reasons = {o.segment_id: o.reason for o in derived.omitted}
        assert reasons == {continuation.id: "other_pass", rows[1].id: "deleted"}

    def test_a_line_deleted_now_leaves_the_order_and_is_simply_absent(self, db, client):
        """The same line deleted through `segment.delete` today: its entry leaves the order with
        it, so the text neither holds it nor names it as an omission -- nothing is missing. The
        continuation on the other pass is still reported."""
        from fichero_server.actions.registry import registry

        doc, _, rows, flow, continuation, _ = self._flow_onto_a_second_pass(db, client)
        registry.invoke(
            db, "reading_order.place",
            {"order_id": flow["order_id"], "segment_id": rows[1].id, "at_end": True},
            self._person(),
        )
        registry.invoke(
            db, "segment.delete",
            {"segment_ids": [rows[1].id], "expected_versions": {rows[1].id: rows[1].version}},
            self._person(),
        )

        derived = document_text(db, doc.id, order=flow["order_id"])

        assert rows[1].id not in [span.segment_id for span in derived.spans]
        assert {o.segment_id: o.reason for o in derived.omitted} == {continuation.id: "other_pass"}

    def test_box_order_omits_nothing_because_it_names_nothing(self, db, client):
        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)

        assert document_text(db, doc.id).omitted == []

    def test_furniture_the_caller_excluded_says_so(self, db, client):
        from fichero_server.actions.registry import registry

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        pass_id = converted_pass_id(artifact.id)
        rows = live_rows_in_order(db, pass_id)
        person = self._person()

        head = db.get(Segment, rows[0].id)
        head.is_furniture = True
        db.save(head)

        made = registry.invoke(
            db, "reading_order.create",
            {"document_id": doc.id, "pass_id": pass_id, "name": "as written",
             "kind": "as-written", "seed_from_pass": True},
            person,
        ).result

        derived = document_text(db, doc.id, order=made["order_id"])
        assert [(o.segment_id, o.reason) for o in derived.omitted] == [
            (rows[0].id, "furniture")
        ]
        # With the furniture asked for, nothing is omitted at all.
        assert document_text(
            db, doc.id, order=made["order_id"], include_furniture=True
        ).omitted == []


class TestAnOrderOfAnotherPassIsRefused:
    """The invariant `document_text`'s own comment claimed and nothing enforced.

    The comment said a named order "must belong to the pass being read — a text
    assembled from one pass's readings in another pass's order would be a
    sentence nobody wrote". Nothing checked it, so such a request produced an
    EMPTY text: every ordered id belonged to a pass whose rows were not loaded.
    Found writing the refusals down for the api reference, 2026-09-27.

    A flow is no exception. A flow belongs to the pass it was made on and
    continues onto others, which is why the omission of a continuation is
    reported (#5090) while the pairing of order and pass is refused.
    """

    def test_reading_one_passs_text_in_another_passs_order_is_refused_by_name(
        self, db, client
    ):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.reading_orders import OrderIsOfAnotherPass
        from fichero_server.models.segments import SegmentPass

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        converted = converted_pass_id(artifact.id)
        person = ActionContext(actor="historian", is_bootstrap=True)

        other = SegmentPass(
            document_id=doc.id, name="a second reading", provenance_kind=ProvenanceKind.human
        )
        db.save(other)
        order_of_the_other = registry.invoke(
            db, "reading_order.create",
            {"document_id": doc.id, "pass_id": other.id, "name": "the other pass's order",
             "kind": "commentary"},
            person,
        ).result

        with pytest.raises(OrderIsOfAnotherPass) as refusal:
            document_text(db, doc.id, pass_id=converted, order=order_of_the_other["order_id"])

        # The sentence names both passes and says which one to ask for, because
        # "empty text" told the caller nothing at all.
        assert other.id in str(refusal.value)
        assert converted in str(refusal.value)
        assert f"pass_id={other.id}" in str(refusal.value)

    def test_the_route_turns_it_into_a_422(self, db, client):
        from fichero_server.actions.registry import ActionContext, registry
        from fichero_server.models.knowledge import ProvenanceKind
        from fichero_server.models.segments import SegmentPass

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        converted = converted_pass_id(artifact.id)
        person = ActionContext(actor="historian", is_bootstrap=True)
        other = SegmentPass(
            document_id=doc.id, name="a second reading", provenance_kind=ProvenanceKind.human
        )
        db.save(other)
        made = registry.invoke(
            db, "reading_order.create",
            {"document_id": doc.id, "pass_id": other.id, "name": "elsewhere",
             "kind": "commentary"},
            person,
        ).result

        response = client.get(
            f"/api/segments/document/{doc.id}/text",
            params={"pass_id": converted, "order": made["order_id"]},
        )
        assert response.status_code == 422, response.text
        assert "not of pass" in response.json()["detail"]

    def test_an_orders_own_pass_still_reads(self, db, client):
        """The guard must not refuse the ordinary case."""
        from fichero_server.actions.registry import ActionContext, registry

        doc = _make_doc(db)
        artifact = _artifact(db, doc)
        _convert(client, artifact.id)
        pass_id = converted_pass_id(artifact.id)
        made = registry.invoke(
            db, "reading_order.create",
            {"document_id": doc.id, "pass_id": pass_id, "name": "as written",
             "kind": "as-written", "seed_from_pass": True},
            ActionContext(actor="historian", is_bootstrap=True),
        ).result

        assert document_text(db, doc.id, pass_id=pass_id, order=made["order_id"]).text
