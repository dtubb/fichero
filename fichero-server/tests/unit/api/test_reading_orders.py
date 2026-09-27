"""Named reading orders (#4930, slice 10).

`source.order.named-multiple`, `source.order.next-previous`, `source.segment.flow`.

A page's lines have a place on the paper; they do not have one reading order. So
an order is named, authored and plural, and `neighbours` refuses to answer
without being told which order — answering from a default would be the engine
choosing a scholarly reading and not saying so.

Everything goes through the real actions and the real routes.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import Document, DocType, FileType, Segment, Status
from fichero_server.models.anchors import SourceAnchor
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.reading_orders import (
    AS_WRITTEN,
    OrderNeedsRenumbering,
    POSITION_GAP_FLOOR,
    ReadingOrder,
    ReadingOrderEntry,
    midpoint,
    renumbered,
)
from fichero_server.models.segments import SegmentPass
import fichero_server.api.routes.document.reading_orders  # noqa: F401

pytestmark = pytest.mark.source_model

#: Three lines down a page, and a marginal note beside the second one. The note
#: is drawn LAST but sits second on the page, which is the case that separates
#: page order from creation order.
LINES = (("first line", 0.10), ("second line", 0.30), ("third line", 0.50))


def _person() -> ActionContext:
    return ActionContext(actor="historian", is_bootstrap=True)


def _page(db) -> tuple[Document, SegmentPass, list[Segment]]:
    doc = Document(
        name="ledger.jpg", doc_type=DocType.file, file_type=FileType.image,
        path="/path/ledger.jpg", status=Status.completed,
    )
    db.save(doc)
    pass_row = SegmentPass(
        document_id=doc.id, name="hand", provenance_kind=ProvenanceKind.human
    )
    db.save(pass_row)
    rows = []
    for text, y in LINES:
        row = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, y, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=y, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
            metadata={"words": text},
        )
        db.save(row)
        rows.append(row)
    return doc, pass_row, rows


def _create(db, doc, pass_row, **extra):
    return registry.invoke(
        db,
        "reading_order.create",
        {"document_id": doc.id, "pass_id": pass_row.id, **extra},
        _person(),
    ).result


def _place(db, **params):
    return registry.invoke(db, "reading_order.place", params, _person()).result


def _sequence(db, order_id: str) -> list[str]:
    from fichero_server.api.routes.document.reading_orders import entries_in_sequence

    return [row.segment_id for row in entries_in_sequence(db, order_id)]


class TestSeveralOrdersOverOnePage:
    """`source.order.named-multiple`."""

    def test_an_as_written_order_is_seeded_in_page_order(self, db):
        doc, pass_row, rows = _page(db)

        made = _create(db, doc, pass_row, seed_from_pass=True)

        assert made["entries"] == 3
        # Page order: down the page, which is the order the source was written
        # in — NOT the order the rows were created in.
        assert _sequence(db, made["order_id"]) == [row.id for row in rows]

    def test_a_line_drawn_last_but_placed_second_reads_second(self, db):
        """The case that separates PAGE order from creation order, and the reason
        `as-written` imports `_segment_order_key` rather than the row sort the
        app's index mapping uses."""
        doc, pass_row, rows = _page(db)
        marginal = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="marginalia",
            doc_kind=f"{doc.id}:marginalia",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.7, 0.2, 0.2, 0.04]),
            bbox_x=0.7, bbox_y=0.2, bbox_w=0.2, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(marginal)

        made = _create(db, doc, pass_row, seed_from_pass=True)

        sequence = _sequence(db, made["order_id"])
        assert sequence == [rows[0].id, marginal.id, rows[1].id, rows[2].id]
        assert sequence[-1] != marginal.id, "creation order leaked into as-written"

    def test_two_orders_over_the_same_segments_hold_different_sequences(self, db):
        doc, pass_row, rows = _page(db)
        written = _create(db, doc, pass_row, seed_from_pass=True)
        imposed = _create(db, doc, pass_row, name="the editor's order", kind="imposed")

        # An imposed order, built by hand, backwards.
        for row in reversed(rows):
            _place(db, order_id=imposed["order_id"], segment_id=row.id, at_end=True)

        assert _sequence(db, written["order_id"]) == [row.id for row in rows]
        assert _sequence(db, imposed["order_id"]) == [row.id for row in reversed(rows)]

    def test_deleting_one_order_leaves_the_other(self, db):
        doc, pass_row, rows = _page(db)
        first = _create(db, doc, pass_row, seed_from_pass=True)
        second = _create(db, doc, pass_row, name="second", kind="imposed")

        registry.invoke(db, "reading_order.delete", {"order_id": first["order_id"]}, _person())

        assert db.get(ReadingOrder, first["order_id"]).deleted_at is not None
        assert db.get(ReadingOrder, second["order_id"]).deleted_at is None
        # The entries stay, so restoring brings the CLAIM back, not an empty order.
        assert len(db.query(ReadingOrderEntry, order_id=first["order_id"])) == 3

    def test_a_deleted_order_can_be_restored_with_its_entries(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        registry.invoke(db, "reading_order.delete", {"order_id": made["order_id"]}, _person())

        registry.invoke(db, "reading_order.restore", {"order_id": made["order_id"]}, _person())

        assert db.get(ReadingOrder, made["order_id"]).deleted_at is None
        assert _sequence(db, made["order_id"]) == [row.id for row in rows]


class TestPlacingWritesOneRow:
    def test_inserting_between_two_entries_touches_one_row(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {
            row.segment_id: row
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }
        versions_before = {row.id: row.version for row in entries.values()}

        extra = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.9, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=0.9, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(extra)

        _place(
            db,
            order_id=made["order_id"],
            segment_id=extra.id,
            after_entry_id=entries[rows[0].id].id,
        )

        # The three seeded rows are untouched: a midpoint insert renumbers nothing.
        for entry_id, version in versions_before.items():
            assert db.get(ReadingOrderEntry, entry_id).version == version
        assert _sequence(db, made["order_id"])[1] == extra.id

    def test_placing_at_the_start_and_at_the_end(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row)

        _place(db, order_id=made["order_id"], segment_id=rows[1].id)
        _place(db, order_id=made["order_id"], segment_id=rows[0].id)  # start again
        _place(db, order_id=made["order_id"], segment_id=rows[2].id, at_end=True)

        assert _sequence(db, made["order_id"]) == [rows[0].id, rows[1].id, rows[2].id]

    def test_moving_an_entry_moves_it_rather_than_adding_a_second(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {
            row.segment_id: row
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }

        _place(
            db,
            order_id=made["order_id"],
            segment_id=rows[0].id,
            after_entry_id=entries[rows[2].id].id,
        )

        assert len(db.query(ReadingOrderEntry, order_id=made["order_id"])) == 3
        assert _sequence(db, made["order_id"]) == [rows[1].id, rows[2].id, rows[0].id]

    def test_a_stale_move_is_refused(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {
            row.segment_id: row
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }
        _place(db, order_id=made["order_id"], segment_id=rows[0].id, at_end=True)

        with pytest.raises(HTTPException) as raised:
            _place(
                db, order_id=made["order_id"], segment_id=rows[0].id,
                expected_version=entries[rows[0].id].version,
            )
        assert raised.value.status_code == 409

    def test_a_segment_of_another_pass_is_refused_outside_a_flow(self, db):
        doc, pass_row, rows = _page(db)
        other_pass = SegmentPass(
            document_id=doc.id, name="another hand", provenance_kind=ProvenanceKind.human
        )
        db.save(other_pass)
        stranger = Segment(
            document_id=doc.id, pass_id=other_pass.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.7, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=0.7, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(stranger)
        made = _create(db, doc, pass_row)

        with pytest.raises(HTTPException) as raised:
            _place(db, order_id=made["order_id"], segment_id=stranger.id)
        assert raised.value.status_code == 409
        assert "flow" in str(raised.value.detail)

    def test_a_flow_may_cross_passes(self, db):
        """`source.segment.flow` — the one order that crosses pages, which means
        its entries' segments belong to different passes."""
        doc, pass_row, rows = _page(db)
        second_page_pass = SegmentPass(
            document_id=doc.id, name="page 2", provenance_kind=ProvenanceKind.human
        )
        db.save(second_page_pass)
        continued = Segment(
            document_id=doc.id, pass_id=second_page_pass.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.1, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=0.1, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(continued)
        flow = _create(db, doc, pass_row, name="reads straight through", kind="flow")

        _place(db, order_id=flow["order_id"], segment_id=rows[2].id)
        _place(db, order_id=flow["order_id"], segment_id=continued.id, at_end=True)

        assert _sequence(db, flow["order_id"]) == [rows[2].id, continued.id]

    def test_removing_an_entry_leaves_the_segment_alone(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entry = next(
            row for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
            if row.segment_id == rows[1].id
        )

        registry.invoke(db, "reading_order.remove", {"entry_id": entry.id}, _person())

        assert _sequence(db, made["order_id"]) == [rows[0].id, rows[2].id]
        assert db.get(Segment, rows[1].id) is not None


class TestNeighbours:
    """`source.order.next-previous`."""

    def test_neighbours_differ_between_two_orders_for_the_same_segment(self, db, client):
        doc, pass_row, rows = _page(db)
        written = _create(db, doc, pass_row, seed_from_pass=True)
        imposed = _create(db, doc, pass_row, name="backwards", kind="imposed")
        for row in reversed(rows):
            _place(db, order_id=imposed["order_id"], segment_id=row.id, at_end=True)

        middle = rows[1].id
        first = client.get(
            f"/api/reading-orders/{written['order_id']}/neighbours?segment_id={middle}"
        ).json()
        second = client.get(
            f"/api/reading-orders/{imposed['order_id']}/neighbours?segment_id={middle}"
        ).json()

        assert (first["previous_segment_id"], first["next_segment_id"]) == (
            rows[0].id, rows[2].id
        )
        # The SAME segment, the other order: before and after swap.
        assert (second["previous_segment_id"], second["next_segment_id"]) == (
            rows[2].id, rows[0].id
        )

    def test_the_ends_of_an_order_report_null_rather_than_wrapping(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)

        first = client.get(
            f"/api/reading-orders/{made['order_id']}/neighbours?segment_id={rows[0].id}"
        ).json()
        last = client.get(
            f"/api/reading-orders/{made['order_id']}/neighbours?segment_id={rows[2].id}"
        ).json()

        assert first["previous_segment_id"] is None
        assert last["next_segment_id"] is None

    def test_there_is_no_next_segment_call_without_an_order(self, db, client):
        """The behaviour, not a validation detail: a page holds several orders, so
        a route that answered without one would be picking a reading."""
        doc, pass_row, rows = _page(db)
        _create(db, doc, pass_row, seed_from_pass=True)

        response = client.get(f"/api/reading-orders//neighbours?segment_id={rows[0].id}")
        assert response.status_code in (404, 422)

    def test_a_segment_outside_the_order_is_a_404(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row)

        response = client.get(
            f"/api/reading-orders/{made['order_id']}/neighbours?segment_id={rows[0].id}"
        )
        assert response.status_code == 404


class TestPositions:
    def test_a_midpoint_between_neighbours(self):
        assert midpoint("o", 1.0, 2.0) == 1.5
        assert midpoint("o", None, None) == 1.0
        assert midpoint("o", 3.0, None) == 4.0

    def test_neighbours_too_close_are_refused_and_the_fix_is_named(self):
        with pytest.raises(OrderNeedsRenumbering) as raised:
            midpoint("o", 1.0, 1.0 + POSITION_GAP_FLOOR / 10)
        assert "reading_order.renumber" in str(raised.value)

    def test_renumbering_rewrites_the_numbers_and_keeps_the_sequence(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        # Squeeze two entries together the way repeated midpoint inserts would.
        entries = sorted(
            db.query(ReadingOrderEntry, order_id=made["order_id"]),
            key=lambda row: row.position,
        )
        entries[1].position = entries[0].position + 1e-12
        db.save(entries[1])
        before = _sequence(db, made["order_id"])

        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        )

        after = sorted(
            db.query(ReadingOrderEntry, order_id=made["order_id"]),
            key=lambda row: row.position,
        )
        assert [row.position for row in after] == renumbered(3)
        # The SEQUENCE is what must not change: renumbering rewrites spacing.
        assert _sequence(db, made["order_id"]) == before

    def test_after_renumbering_an_insert_is_possible_again(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = sorted(
            db.query(ReadingOrderEntry, order_id=made["order_id"]),
            key=lambda row: row.position,
        )
        entries[1].position = entries[0].position + 1e-12
        db.save(entries[1])

        extra = Segment(
            document_id=doc.id, pass_id=pass_row.id, kind="line",
            doc_kind=f"{doc.id}:line",
            anchor=SourceAnchor(document_id=doc.id, rect=[0.1, 0.95, 0.5, 0.04]),
            bbox_x=0.1, bbox_y=0.95, bbox_w=0.5, bbox_h=0.04, tile="",
            provenance_kind=ProvenanceKind.human,
        )
        db.save(extra)
        with pytest.raises(HTTPException) as raised:
            _place(
                db, order_id=made["order_id"], segment_id=extra.id,
                after_entry_id=entries[0].id,
            )
        assert raised.value.status_code == 422

        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        )
        placed = _place(
            db, order_id=made["order_id"], segment_id=extra.id,
            after_entry_id=entries[0].id,
        )
        assert placed["position"] == 1.5


class TestTheOrderIsNeverSortedByUuid:
    def test_entries_created_in_one_transaction_are_stable_and_not_uuid_order(self, db):
        """The trap this slice was warned about: `position` is a float placed by
        midpoint, so the FALLBACK decides when positions are equal — and the lazy
        fallback is `id`, which #4921 forbids as a meaningful order. Positions are
        distinct by construction, so the sequence is the positions' and a uuid
        never decides it."""
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)

        entries = sorted(
            db.query(ReadingOrderEntry, order_id=made["order_id"]),
            key=lambda row: row.position,
        )
        assert len({row.position for row in entries}) == 3, "two entries share a position"
        assert _sequence(db, made["order_id"]) == [row.segment_id for row in entries]

        # Now force the question: give the entries positions in the REVERSE of
        # their uuid order and read the sequence back. If anything fell through to
        # `id`, this comes out uuid-ascending instead of position-ascending — and
        # unlike comparing against whatever order the uuids happen to have, this
        # cannot pass by luck.
        by_uuid = sorted(entries, key=lambda row: row.id)
        for index, row in enumerate(reversed(by_uuid)):
            row.position = float(index + 1)
            db.save(row)

        assert _sequence(db, made["order_id"]) == [
            row.segment_id for row in reversed(by_uuid)
        ]
        assert _sequence(db, made["order_id"]) != [row.segment_id for row in by_uuid]


class TestTheListRead:
    def test_a_source_lists_its_orders_with_as_written_first(self, db, client):
        doc, pass_row, rows = _page(db)
        _create(db, doc, pass_row, name="an editor's order", kind="imposed")
        _create(db, doc, pass_row, seed_from_pass=True)

        response = client.get(f"/api/reading-orders/document/{doc.id}")
        assert response.status_code == 200, response.text
        orders = response.json()["orders"]

        assert [row["name"] for row in orders][0] == AS_WRITTEN
        # A list must not pull every entry of every order; it reports the count.
        assert orders[0]["entry_count"] == 3
        assert "entries" not in orders[0]

    def test_a_deleted_order_is_left_out_unless_asked_for(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        registry.invoke(db, "reading_order.delete", {"order_id": made["order_id"]}, _person())

        assert client.get(f"/api/reading-orders/document/{doc.id}").json()["orders"] == []
        with_deleted = client.get(
            f"/api/reading-orders/document/{doc.id}?include_deleted=true"
        ).json()["orders"]
        assert len(with_deleted) == 1


class TestAsWrittenArrivesWithThePage:
    """A page is never orderless: the `as-written` order is made with the pass and
    grows as segments do. The alternative — an order created on demand — shows an
    empty order list on a page that visibly has lines, which is a worse first
    impression than no order at all."""

    def test_creating_a_pass_creates_its_as_written_order(self, db):
        from fichero_server.api.routes.document.reading_orders import as_written_order

        doc = Document(
            name="fresh.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/path/fresh.jpg", status=Status.completed,
        )
        db.save(doc)

        result = registry.invoke(
            db,
            "segment.pass_create",
            {"document_id": doc.id, "name": "a hand"},
            _person(),
        ).result

        order = as_written_order(db, result["id"])
        assert order is not None
        assert order.name == AS_WRITTEN
        assert order.provenance_kind == ProvenanceKind.human  # a person made this pass

    def test_a_segment_created_afterwards_lands_at_its_PAGE_place(self, db):
        """Not appended: `as-written` is the order the source was written in, so a
        line drawn last but positioned in the middle belongs in the middle."""
        from fichero_server.api.routes.document.reading_orders import as_written_order

        doc = Document(
            name="grow.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/path/grow.jpg", status=Status.completed,
        )
        db.save(doc)
        pass_result = registry.invoke(
            db, "segment.pass_create", {"document_id": doc.id, "name": "a hand"}, _person()
        ).result
        pass_id = pass_result["id"]

        made = []
        for y in (0.10, 0.50, 0.30):  # deliberately out of page order
            created = registry.invoke(
                db,
                "segment.create",
                {
                    "document_id": doc.id,
                    "pass_id": pass_id,
                    "kind": "line",
                    "anchor": {"document_id": doc.id, "rect": [0.1, y, 0.5, 0.04]},
                },
                _person(),
            ).result
            made.append((y, created["segment_ids"][0]))

        order = as_written_order(db, pass_id)
        by_y = [segment_id for _y, segment_id in sorted(made)]
        assert _sequence(db, order.id) == by_y, "the order is creation order, not page order"

    def test_a_pass_made_before_this_slice_is_not_given_an_order_silently(self, db):
        """A library that predates slice 10 gets its orders by an audited call, not
        by a write path quietly inventing a machine's order inside somebody's
        editing session."""
        from fichero_server.api.routes.document.reading_orders import as_written_order

        doc, pass_row, rows = _page(db)  # built directly, as an old library's rows are

        assert as_written_order(db, pass_row.id) is None

        made = _create(db, doc, pass_row, seed_from_pass=True)
        assert as_written_order(db, pass_row.id).id == made["order_id"]


class TestConversionWritesTheOrderAtomically:
    """Slice 6 converts a page on its first edit. The order is written in THAT
    transaction — a page that converted and then failed to get its order would be
    a half-converted page wearing a converted page's clothes."""

    def _artifact(self, db, doc):
        from fichero_server.media.ocr_geometry import OCRGeometryBox, OCRGeometryResult
        from fichero_server.models import Artifact

        text = "one two three"
        spans = [(0, 3), (4, 7), (8, 13)]
        artifact = Artifact(
            document_id=doc.id, artifact_type="transcription", provider="qwen",
            model="qwen-vl", content=text,
            ocr_geometry=OCRGeometryResult(
                provider="qwen", text=text,
                boxes=[
                    OCRGeometryBox(
                        text=text[start:end], bbox=[0.1, 0.1 + i * 0.2, 0.4, 0.05],
                        level="line", char_start=start, char_end=end, confidence=0.9,
                    )
                    for i, (start, end) in enumerate(spans)
                ],
            ),
        )
        db.save(artifact)
        return artifact

    def test_a_converted_page_has_its_order_with_every_line_in_it(self, db, client):
        from fichero_server.api.routes.document.reading_orders import as_written_order
        from fichero_server.api.routes.document.segment_conversion import (
            converted_pass_id,
            live_rows_in_order,
        )

        doc = Document(
            name="convert.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/path/convert.jpg", status=Status.completed,
        )
        db.save(doc)
        artifact = self._artifact(db, doc)

        response = client.put(
            f"/api/artifacts/{artifact.id}/regions",
            json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.4, 0.05]},
        )
        assert response.status_code == 200, response.text

        pass_id = converted_pass_id(artifact.id)
        order = as_written_order(db, pass_id)
        assert order is not None, "a converted page has no as-written order"
        # Every converted row is in it, in the order conversion gave them --
        # `box_index` order, which is what `_segment_order_key` reads first.
        assert _sequence(db, order.id) == [row.id for row in live_rows_in_order(db, pass_id)]

    def test_the_orders_provenance_is_the_machines_not_a_persons(self, db, client):
        """The order is derived from where the boxes are: an observation, not a
        reading. Recording it as a person's would make a machine's arrangement
        indistinguishable from a curator's decision."""
        from fichero_server.api.routes.document.reading_orders import as_written_order
        from fichero_server.api.routes.document.segment_conversion import converted_pass_id

        doc = Document(
            name="prov.jpg", doc_type=DocType.file, file_type=FileType.image,
            path="/path/prov.jpg", status=Status.completed,
        )
        db.save(doc)
        artifact = self._artifact(db, doc)
        client.put(
            f"/api/artifacts/{artifact.id}/regions",
            json={"op": "move", "indices": [0], "bbox": [0.11, 0.1, 0.4, 0.05]},
        )

        order = as_written_order(db, converted_pass_id(artifact.id))
        assert order.provenance_kind != ProvenanceKind.human
        assert order.created_by is None


class TestRenumberingIsOrderPreserving:
    """Renumbering must preserve the SEQUENCE, and the reason is in another action.

    `restore_place` undoes a move by restoring an exact position. If a renumber
    lands between the move and its undo, that position is expressed in different
    numbers — and the undo is still correct only because renumbering preserves
    the order: an entry restored at 2.5 still falls between whatever is now 2.0
    and 3.0, the same two neighbours as before.

    So this is the test that catches anyone making renumber cleverer later, in an
    action that does not mention undo at all.
    """

    def test_undo_across_a_renumber_lands_between_the_same_neighbours(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {
            row.segment_id: row
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }

        # Move the first line to the end, remembering where it was.
        before_position = entries[rows[0].id].position
        before_parent = entries[rows[0].id].parent_entry_id
        moved = _place(
            db, order_id=made["order_id"], segment_id=rows[0].id, at_end=True
        )
        assert _sequence(db, made["order_id"]) == [rows[1].id, rows[2].id, rows[0].id]

        # A renumber happens in between — positions are now different NUMBERS.
        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        )
        renumbered_positions = {
            row.segment_id: row.position
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }
        assert renumbered_positions[rows[0].id] != moved["position"]

        # Undo the move with the position it had BEFORE the renumber.
        registry.invoke(
            db,
            "reading_order.restore_place",
            {
                "entry_id": entries[rows[0].id].id,
                "position": before_position,
                "parent_entry_id": before_parent,
            },
            _person(),
        )

        # Back between the same two neighbours — which here means first, before
        # the line that followed it originally.
        assert _sequence(db, made["order_id"]) == [rows[0].id, rows[1].id, rows[2].id]

    def test_renumbering_twice_changes_nothing_the_second_time(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)

        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        ).result
        after_first = {
            row.id: (row.position, row.version)
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }
        second = registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        ).result

        # Nothing to do, so nothing written: no version is bumped for a row whose
        # position is already what renumbering would give it.
        assert second["renumbered"] == 0
        assert {
            row.id: (row.position, row.version)
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        } == after_first

    def test_nested_levels_are_renumbered_independently(self, db):
        """Each level is its own sequence: 1.0, 2.0 inside a parent, and 1.0, 2.0
        at the top. Compacting the levels together would renumber a child into its
        parent's sequence and change what the order claims."""
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row)
        _place(db, order_id=made["order_id"], segment_id=rows[0].id)
        parent = db.query(ReadingOrderEntry, order_id=made["order_id"])[0]
        for row in rows[1:]:
            _place(
                db, order_id=made["order_id"], segment_id=row.id,
                parent_entry_id=parent.id, at_end=True,
            )

        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        )

        entries = db.query(ReadingOrderEntry, order_id=made["order_id"])
        top = sorted(row.position for row in entries if row.parent_entry_id is None)
        children = sorted(row.position for row in entries if row.parent_entry_id == parent.id)
        assert top == [1.0]
        assert children == [1.0, 2.0], "the child level was folded into the parent's numbering"


class TestRestoringOntoATakenPosition:
    """The gap in "undo across a renumber is correct because renumber preserves
    the order" — found by the test above failing, not by reasoning.

    The claim holds for a position strictly between two others: 2.5 still lands
    between whatever is now 2.0 and 3.0. It fails when the position is one a
    renumber has since GIVEN TO SOMEBODY ELSE — restoring at 1.0 when another
    entry now sits at 1.0 makes two entries share a position, and the sequence
    falls through to the tie-break: a uuid deciding which line reads first.
    """

    def test_restoring_onto_a_taken_position_lands_before_its_holder(self, db):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {
            row.segment_id: row
            for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        }
        first_entry = entries[rows[0].id]
        original_position = first_entry.position

        # Move it away, then renumber so its old position belongs to another entry.
        _place(db, order_id=made["order_id"], segment_id=rows[0].id, at_end=True)
        registry.invoke(
            db, "reading_order.renumber", {"order_id": made["order_id"]}, _person()
        )
        holder = next(
            row for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
            if row.id != first_entry.id and abs(row.position - original_position) < 1e-9
        )
        assert holder.segment_id != rows[0].id, "the fixture did not create a collision"

        registry.invoke(
            db,
            "reading_order.restore_place",
            {"entry_id": first_entry.id, "position": original_position},
            _person(),
        )

        restored = db.get(ReadingOrderEntry, first_entry.id)
        # NOT the requested number, because that number is taken; the MEANING is
        # preserved instead — it came before the entry now holding it.
        assert restored.position != original_position
        assert restored.position < holder.position
        assert _sequence(db, made["order_id"]) == [rows[0].id, rows[1].id, rows[2].id]

    def test_no_two_entries_of_one_level_ever_share_a_position(self, db):
        """The invariant the fix protects. Two entries at one position means the
        sequence is decided by whatever comes next in the sort — and #4921 is the
        ruling that a uuid is not an order."""
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = list(db.query(ReadingOrderEntry, order_id=made["order_id"]))

        for row in entries:
            registry.invoke(
                db,
                "reading_order.restore_place",
                {"entry_id": row.id, "position": 1.0},
                _person(),
            )

        positions = [
            row.position for row in db.query(ReadingOrderEntry, order_id=made["order_id"])
        ]
        assert len(set(positions)) == len(positions), positions


class TestThePlaceRoute:
    """`POST /api/reading-orders/{order_id}/place` (slice 13, Q5): the ONE reorder call the app's
    three lists make, by drag or by key. The app is generated from the contract, and the generic
    action route is not in it, so without this route the reorder the maintainer ruled on could
    not be sent at all."""

    def test_a_move_through_the_route_is_the_audited_action_and_undoes(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {row.segment_id: row for row in db.query(ReadingOrderEntry, order_id=made["order_id"])}

        response = client.post(f"/api/reading-orders/{made['order_id']}/place", json={
            "segment_id": rows[0].id, "after_entry_id": entries[rows[2].id].id,
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ok"] and body["audit_id"]
        assert _sequence(db, made["order_id"]) == [rows[1].id, rows[2].id, rows[0].id]

        undone = client.post(f"/api/actions/audit/{body['audit_id']}/undo")
        assert undone.status_code == 200, undone.text
        assert _sequence(db, made["order_id"]) == [rows[0].id, rows[1].id, rows[2].id]

    def test_a_stale_move_through_the_route_is_a_409(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        entries = {row.segment_id: row for row in db.query(ReadingOrderEntry, order_id=made["order_id"])}
        _place(db, order_id=made["order_id"], segment_id=rows[0].id, at_end=True)

        response = client.post(f"/api/reading-orders/{made['order_id']}/place", json={
            "segment_id": rows[0].id, "expected_version": entries[rows[0].id].version,
        })
        assert response.status_code == 409

    def test_the_order_id_comes_from_the_path_only(self, db, client):
        doc, pass_row, rows = _page(db)
        made = _create(db, doc, pass_row, seed_from_pass=True)
        response = client.post(f"/api/reading-orders/{made['order_id']}/place", json={
            "segment_id": rows[0].id, "order_id": "another", "at_end": True,
        })
        assert response.status_code == 422
