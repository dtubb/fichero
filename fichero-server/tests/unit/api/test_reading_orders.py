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
