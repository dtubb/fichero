"""Source-model slice 10 (#4930) — named reading orders: the writes, and the
reads that answer "what comes next" only when an order is named.

Spec: `build-notes-readings-cascade-orders.md`, "Slice 10 — named reading
orders". Behaviours: `source.order.named-multiple`, `source.order.next-previous`,
`source.segment.flow`.

WHY THE ORDER IS A RECORD AND NOT A SORT. A page's lines have a place on the
paper; they do not have one reading order. So an order is named, authored and
plural -- and `neighbours` refuses to answer without being told WHICH order,
because answering from a default would be the engine choosing a scholarly
reading and not saying so.

`as-written` is PAGE order (ruled 2026-09-26) and its sequence comes from
`segment_readings._segment_order_key`, IMPORTED. This module owns no sort of its
own: a third rule beside that one and `segments._segment_row_sort_key` is the
drift both of their docstrings warn about, and one of the two had a defect found
by enumerating them (`a79b901d8`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.library_header import optional_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segment_readings import _segment_order_key
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.db import Database
from fichero_server.models import Segment
from fichero_server.models.knowledge import ProvenanceKind
from fichero_server.models.reading_orders import (
    AS_WRITTEN,
    POSITION_GAP_FLOOR,
    AlreadyInOrder,
    OrderNotNamed,
    OrderNeedsRenumbering,
    OrderPassMismatch,
    ReadingOrder,
    ReadingOrderEntry,
    ReadingOrderKind,
    midpoint,
    renumbered,
)
from fichero_server.models.segments import assert_not_provisional
from fichero_server.core.timeutil import utc_now

router = APIRouter(prefix="/reading-orders")


def _as_http_error(exc: Exception) -> HTTPException:
    """One place mapping a refusal to a status code, as the segment routes do."""
    if isinstance(exc, (AlreadyInOrder, OrderPassMismatch)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (OrderNeedsRenumbering, OrderNotNamed)):
        return HTTPException(status_code=422, detail=str(exc))
    raise exc


def _live_order(db: Database, order_id: str) -> ReadingOrder:
    row = db.get(ReadingOrder, order_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Reading order not found: {order_id}")
    if row.deleted_at is not None:
        raise HTTPException(status_code=409, detail=f"Reading order is deleted: {order_id}")
    return row


def entries_in_sequence(
    db: Database, order_id: str, *, parent_entry_id: str | None = None
) -> list[ReadingOrderEntry]:
    """One level of one order, in its own order.

    `position` alone decides, and `id` is the last-resort tie-break that makes
    the sort total -- never a meaningful position (#4921). Two entries sharing a
    position is what `OrderNeedsRenumbering` exists to prevent, so a tie here
    means a library that predates that refusal, not a normal state.
    """
    rows = [
        row
        for row in db.query(ReadingOrderEntry, order_id=order_id)
        if row.parent_entry_id == parent_entry_id
    ]
    rows.sort(key=lambda row: (row.position, row.id))
    return rows


# ---------------------------------------------------------------------------
# `as-written`, kept current as segments arrive
# ---------------------------------------------------------------------------


def as_written_order(db: Database, pass_id: str) -> ReadingOrder | None:
    """The pass's own `as-written` order, or None if it has none yet."""
    for row in db.query(ReadingOrder, pass_id=pass_id):
        if row.deleted_at is None and row.name == AS_WRITTEN:
            return row
    return None


def ensure_as_written_order(
    db: Database,
    *,
    document_id: str,
    pass_id: str,
    provenance_kind: ProvenanceKind,
    created_by: str | None = None,
) -> ReadingOrder:
    """The pass's `as-written` order, made if it is missing.

    Idempotent, because it is called from a pass's creation AND from a
    conversion, and a pass that somehow reached both must not end up with two
    orders of the same name -- two `as-written` orders would make "the page's own
    order" ambiguous, which is the one order that must never be.
    """
    existing = as_written_order(db, pass_id)
    if existing is not None:
        return existing
    order = ReadingOrder(
        document_id=document_id,
        pass_id=pass_id,
        name=AS_WRITTEN,
        kind=ReadingOrderKind.as_written.value,
        # The MACHINE's order until a person edits it: it is derived from where
        # the boxes are, which is an observation and not a reading. Taken as an
        # ARGUMENT rather than from a `ctx`, because two of the three callers have
        # no action context: conversion builds its pass from an artifact, and the
        # empty-pass bootstrap runs inside an edit that is already underway.
        provenance_kind=provenance_kind,
        created_by=created_by,
    )
    db.save(order)
    return order


#: The fields of an order entry that a delete records and its undo writes back -- exactly the row,
#: so the segment comes back to its place, a person's reordering included.
ENTRY_FIELDS = ("id", "order_id", "segment_id", "position", "parent_entry_id", "version")


def remove_segment_entries(db: Database, segment_ids: list[str]) -> list[dict]:
    """Take the deleted segments out of EVERY order, and answer the rows as they were.

    A deleted segment's entry left in the table is a ghost to every reader of the order -- export's
    ReadingOrder, flows, neighbours, the next/previous walk, the Reader's line map -- so the delete
    removes it, and `segment.undelete` (its inverse, and the redo of a create's undo) writes the rows
    back unchanged (2026-09-28). An entry nested under a removed one keeps its parent id: it is out
    of the walk while its parent is deleted and back in its place when the parent is restored.
    """
    removed: list[dict] = []
    for segment_id in dict.fromkeys(segment_ids):
        for entry in db.query(ReadingOrderEntry, segment_id=segment_id):
            removed.append({field: getattr(entry, field) for field in ENTRY_FIELDS})
            db.delete(entry)
    return removed


def restore_segment_entries(db: Database, entries: list[dict]) -> None:
    """Write back what `remove_segment_entries` took, where it was. An order since deleted gets nothing
    back (there is nothing to show it in); an entry the order already holds for that segment is not
    doubled; an entry whose parent entry is gone (and is not coming back with it) is placed by page
    order instead of being left nested under nothing."""
    coming_back = {entry["id"] for entry in entries}
    for fields in entries:
        order = db.get(ReadingOrder, fields["order_id"])
        if order is None or order.deleted_at is not None:
            continue
        if db.get(ReadingOrderEntry, fields["id"]) is not None or any(
            row.segment_id == fields["segment_id"] for row in db.query(ReadingOrderEntry, order_id=order.id)
        ):
            continue
        parent = fields.get("parent_entry_id")
        if parent and parent not in coming_back and db.get(ReadingOrderEntry, parent) is None:
            segment = db.get(Segment, fields["segment_id"])
            if segment is not None:
                place_in_page_order(db, order, segment)
            continue
        db.save(ReadingOrderEntry(**{field: fields.get(field) for field in ENTRY_FIELDS}))


def place_in_page_order(db: Database, order: ReadingOrder, segment: Segment) -> ReadingOrderEntry | None:
    """Put one segment into `order` where PAGE order says it belongs.

    ONE row written, by finding the last entry whose segment sorts before this
    one and taking the midpoint after it -- not by appending, which would put a
    line drawn late at the end of an order that claims to be the order the source
    was written in.

    The sort is `_segment_order_key`, IMPORTED. Returns None when the segment is
    already in the order, so a caller can be called twice without checking.
    """
    if any(row.segment_id == segment.id for row in db.query(ReadingOrderEntry, order_id=order.id)):
        return None
    # A segment with a parent (a line drawn inside a region) is placed among that parent's children, where
    # page order puts it -- never at the top level beside the regions, which is where it landed before
    # (2026-09-28). A parent the order does not hold leaves it at the top level, as before.
    parent_entry = next(
        (row for row in db.query(ReadingOrderEntry, order_id=order.id)
         if segment.parent_segment_id and row.segment_id == segment.parent_segment_id),
        None,
    )
    parent_entry_id = parent_entry.id if parent_entry is not None else None
    entries = entries_in_sequence(db, order.id, parent_entry_id=parent_entry_id)

    key = _segment_order_key(segment)
    previous_position: float | None = None
    following_position: float | None = None
    for row in entries:
        sibling = db.get(Segment, row.segment_id)
        if sibling is None:
            continue
        if _segment_order_key(sibling) <= key:
            previous_position = row.position
        else:
            following_position = row.position
            break

    entry = ReadingOrderEntry(
        order_id=order.id,
        segment_id=segment.id,
        position=midpoint(order.id, previous_position, following_position),
        parent_entry_id=parent_entry_id,
    )
    db.save(entry)
    return entry


def order_for_text(db: Database, order_id: str) -> ReadingOrder:
    """One live order, for the derived text to follow.

    Its own function so the text path and the entry reads refuse a deleted or
    missing order the same way: a text assembled from an order nobody can read
    back would be a page whose sequence has no record.
    """
    return _live_order(db, order_id)


# ---------------------------------------------------------------------------
# reading_order.create
# ---------------------------------------------------------------------------


class ReadingOrderCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    pass_id: str
    name: str = AS_WRITTEN
    kind: str = ReadingOrderKind.as_written.value
    certainty: Optional[float] = None
    #: Fill the new order with the pass's segments in PAGE order. What
    #: `as-written` means, and the reason a page always has one order to read it
    #: by rather than an empty one the app must explain.
    seed_from_pass: bool = False


def _invert_order_create(before, after, ctx: ActionContext):
    if not after:
        return None
    order_id = after.get("order_id")
    return ("reading_order.delete", {"order_id": order_id}) if order_id else None


@action(
    "reading_order.create",
    ReadingOrderCreateParams,
    domains=["reading_order"],
    undoable=True,
    invert=_invert_order_create,
)
def _action_order_create(
    db: Database, params: ReadingOrderCreateParams, ctx: ActionContext
):
    """Make one named order over one pass (`source.order.named-multiple`)."""
    assert_not_provisional(params.pass_id, what="pass_id")
    order = ReadingOrder(
        document_id=params.document_id,
        pass_id=params.pass_id,
        name=params.name,
        kind=params.kind,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
        certainty=params.certainty,
    )
    db.save(order)

    seeded = 0
    if params.seed_from_pass:
        rows = [
            row
            for row in db.query(Segment, pass_id=params.pass_id)
            if row.deleted_at is None
        ]
        # PAGE order, imported. See the module docstring for why this module
        # holds no sort of its own.
        rows.sort(key=_segment_order_key)
        for index, row in enumerate(rows):
            db.save(
                ReadingOrderEntry(
                    order_id=order.id, segment_id=row.id, position=float(index + 1)
                )
            )
        seeded = len(rows)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[order.id],
        before=None,
        after={"order_id": order.id, "entries": seeded},
        emit_type="reading_order.created",
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"order_id": order.id, "entries": seeded}, spec


# ---------------------------------------------------------------------------
# reading_order.place / .remove
# ---------------------------------------------------------------------------


class ReadingOrderPlaceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    segment_id: str
    #: The entry this one goes AFTER, or `None` for the start of its level.
    after_entry_id: Optional[str] = None
    #: Append instead. One flag rather than a second action: appending is what a
    #: caller wants nine times in ten, and making it read the last entry's id
    #: first would be a round trip for nothing.
    at_end: bool = False
    parent_entry_id: Optional[str] = None
    expected_version: Optional[int] = None


def _invert_order_place(before, after, ctx: ActionContext):
    """Put the entry back where it was, or take it out if it was not there.

    Reads `before` for the old place -- a POSITION and two ids, which are
    numbers and ids, the only things the build notes allow in an audit row.
    """
    if not after:
        return None
    entry_id = after.get("entry_id")
    if not entry_id:
        return None
    if not before or before.get("position") is None:
        return ("reading_order.remove", {"entry_id": entry_id})
    return (
        "reading_order.restore_place",
        {
            "entry_id": entry_id,
            "position": before["position"],
            "parent_entry_id": before.get("parent_entry_id"),
        },
    )


@action(
    "reading_order.place",
    ReadingOrderPlaceParams,
    domains=["reading_order"],
    undoable=True,
    invert=_invert_order_place,
)
def _action_order_place(db: Database, params: ReadingOrderPlaceParams, ctx: ActionContext):
    """Put one segment at one place in one order, writing ONE row.

    The position is the midpoint between its new neighbours, so inserting in the
    middle of a thousand-entry flow touches one row rather than renumbering
    everything after it.
    """
    assert_not_provisional(params.segment_id, what="segment_id")
    order = _live_order(db, params.order_id)

    segment = db.get(Segment, params.segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    if segment.pass_id != order.pass_id and order.kind != ReadingOrderKind.flow.value:
        raise _as_http_error(
            OrderPassMismatch(order.id, params.segment_id, order.pass_id)
        )

    siblings = entries_in_sequence(db, order.id, parent_entry_id=params.parent_entry_id)
    existing = next(
        (row for row in db.query(ReadingOrderEntry, order_id=order.id)
         if row.segment_id == params.segment_id),
        None,
    )

    before_state = None
    if existing is not None:
        if params.expected_version is not None and existing.version != params.expected_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"entry {existing.id} changed since it was read",
                    "entry_id": existing.id,
                    "expected_version": params.expected_version,
                    "current_version": existing.version,
                },
            )
        before_state = {
            "entry_id": existing.id,
            "position": existing.position,
            "parent_entry_id": existing.parent_entry_id,
        }
        siblings = [row for row in siblings if row.id != existing.id]

    anchor_index = len(siblings) - 1 if params.at_end else -1
    if params.after_entry_id is not None:
        anchor_index = next(
            (i for i, row in enumerate(siblings) if row.id == params.after_entry_id), -1
        )
        if anchor_index == -1:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"after_entry_id {params.after_entry_id} is not an entry of order "
                    f"{order.id} at this level"
                ),
            )
    previous = siblings[anchor_index].position if anchor_index >= 0 else None
    following = (
        siblings[anchor_index + 1].position if anchor_index + 1 < len(siblings) else None
    )

    try:
        position = midpoint(order.id, previous, following)
    except OrderNeedsRenumbering as refusal:
        raise _as_http_error(refusal) from refusal

    if existing is not None:
        existing.position = position
        existing.parent_entry_id = params.parent_entry_id
        existing.version += 1
        db.save(existing)
        entry = existing
    else:
        entry = ReadingOrderEntry(
            order_id=order.id,
            segment_id=params.segment_id,
            position=position,
            parent_entry_id=params.parent_entry_id,
        )
        db.save(entry)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[entry.id],
        before=before_state,
        after={"entry_id": entry.id, "position": entry.position, "order_id": order.id},
        emit_type="reading_order.changed",
        segment_ids=[params.segment_id],
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"entry_id": entry.id, "position": entry.position, "version": entry.version}, spec


class ReadingOrderRemoveParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: str


def _invert_order_remove(before, after, ctx: ActionContext):
    if not before or not before.get("entry_id"):
        return None
    return (
        "reading_order.restore_place",
        {
            "entry_id": before["entry_id"],
            "position": before.get("position"),
            "parent_entry_id": before.get("parent_entry_id"),
            "order_id": before.get("order_id"),
            "segment_id": before.get("segment_id"),
        },
    )


@action(
    "reading_order.remove",
    ReadingOrderRemoveParams,
    domains=["reading_order"],
    undoable=True,
    invert=_invert_order_remove,
)
def _action_order_remove(db: Database, params: ReadingOrderRemoveParams, ctx: ActionContext):
    """Take one segment out of one order. The SEGMENT is untouched."""
    entry = db.get(ReadingOrderEntry, params.entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Entry not found: {params.entry_id}")
    order = _live_order(db, entry.order_id)

    before_state = {
        "entry_id": entry.id,
        "order_id": entry.order_id,
        "segment_id": entry.segment_id,
        "position": entry.position,
        "parent_entry_id": entry.parent_entry_id,
    }
    db.delete(entry)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[entry.id],
        before=before_state,
        after={"entry_id": entry.id, "removed": True},
        emit_type="reading_order.changed",
        segment_ids=[entry.segment_id],
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"entry_id": entry.id, "removed": True}, spec


class ReadingOrderRestorePlaceParams(BaseModel):
    """The inverse of `place` and of `remove`: put an entry back at a position.

    Its own action rather than a flag on `place`, because it takes a POSITION
    rather than a neighbour -- undo restores the exact place, and re-deriving a
    midpoint from neighbours that have since moved would put the entry
    somewhere else and call it undo.
    """

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    position: float
    parent_entry_id: Optional[str] = None
    #: Only needed when the entry was REMOVED and has to be made again.
    order_id: Optional[str] = None
    segment_id: Optional[str] = None


def _restored_position(
    db: Database,
    entry: ReadingOrderEntry,
    requested: float,
    parent_entry_id: str | None,
) -> float:
    """The position to restore to, which is USUALLY the requested one.

    **Found by a test 2026-09-26, and it is the gap in "undo across a renumber is
    correct because renumbering preserves the order".** That is true when the
    restored position falls strictly between two others — 2.5 still lands between
    whatever is now 2.0 and 3.0. It is NOT true when the position is one a
    renumber has since handed to somebody else: restoring at 1.0 after a renumber
    put another entry at 1.0 makes two entries share a position, and the sequence
    falls through to the tie-break — a uuid deciding which line reads first, which
    is exactly what #4921 forbids and what the renumber existed to prevent.

    So a collision is resolved by landing immediately BEFORE the entry now holding
    that position, which preserves what the stored position MEANT (this entry came
    before that one) rather than the number it was written as.
    """
    taken = next(
        (
            row
            for row in db.query(ReadingOrderEntry, order_id=entry.order_id)
            if row.id != entry.id
            and row.parent_entry_id == parent_entry_id
            and abs(row.position - requested) < POSITION_GAP_FLOOR
        ),
        None,
    )
    if taken is None:
        return requested

    siblings = [
        row
        for row in entries_in_sequence(db, entry.order_id, parent_entry_id=parent_entry_id)
        if row.id != entry.id
    ]
    index = next(i for i, row in enumerate(siblings) if row.id == taken.id)
    previous = siblings[index - 1].position if index > 0 else None
    return midpoint(entry.order_id, previous, taken.position)


@action(
    "reading_order.restore_place",
    ReadingOrderRestorePlaceParams,
    domains=["reading_order"],
    undoable=False,
)
def _action_order_restore_place(
    db: Database, params: ReadingOrderRestorePlaceParams, ctx: ActionContext
):
    entry = db.get(ReadingOrderEntry, params.entry_id)
    if entry is None:
        if not params.order_id or not params.segment_id:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Entry not found: {params.entry_id}; restoring a removed entry "
                    "needs order_id and segment_id"
                ),
            )
        entry = ReadingOrderEntry(
            id=params.entry_id,
            order_id=params.order_id,
            segment_id=params.segment_id,
            position=params.position,
            parent_entry_id=params.parent_entry_id,
        )
    else:
        entry.position = _restored_position(
            db, entry, params.position, params.parent_entry_id
        )
        entry.parent_entry_id = params.parent_entry_id
        entry.version += 1
    db.save(entry)
    order = db.get(ReadingOrder, entry.order_id)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[entry.id],
        before=None,
        after={"entry_id": entry.id, "position": entry.position},
        emit_type="reading_order.changed",
        segment_ids=[entry.segment_id],
        pass_ids=[order.pass_id] if order else [],
        document_ids=[order.document_id] if order else [],
    )
    return {"entry_id": entry.id, "position": entry.position}, spec


# ---------------------------------------------------------------------------
# reading_order.renumber / .delete / .restore
# ---------------------------------------------------------------------------


class ReadingOrderRenumberParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str


@action(
    "reading_order.renumber",
    ReadingOrderRenumberParams,
    domains=["reading_order"],
    # NOT undoable, and the reason is that there is nothing to undo: renumbering
    # rewrites the NUMBERS and preserves the SEQUENCE exactly, so no reader of
    # the order can tell it happened. An "undo" would restore spacing nobody can
    # see, at the cost of an inverse that has to carry every position. The audit
    # row records that it ran, which is what matters.
    undoable=False,
)
def _action_order_renumber(
    db: Database, params: ReadingOrderRenumberParams, ctx: ActionContext
):
    """Rewrite one order's positions as 1.0, 2.0, 3.0 — the only action that
    touches many rows of one order, and never more than one order.

    The app never calls this on its own: it is what `OrderNeedsRenumbering` tells
    a caller to run when midpoints have run out of room.

    **IT MUST STAY ORDER-PRESERVING, and that property is load-bearing somewhere
    else entirely.** `reading_order.restore_place` undoes a move by restoring an
    EXACT position. If a renumber happens between a move and its undo, that
    position is now expressed in different numbers — and the undo is still correct
    only because renumbering preserves the sequence: an entry restored at 2.5
    still falls between whatever is now 2.0 and 3.0, which are the same two
    neighbours it fell between before. Anything cleverer than order-preserving
    rescaling here (dropping entries, reordering ties, compacting levels
    together) silently breaks undo in a different action. The test
    `TestRenumberingIsOrderPreserving` is what would catch that.
    """
    order = _live_order(db, params.order_id)
    rows = list(db.query(ReadingOrderEntry, order_id=order.id))
    by_level: dict[str | None, list[ReadingOrderEntry]] = {}
    for row in rows:
        by_level.setdefault(row.parent_entry_id, []).append(row)

    touched = 0
    for level_rows in by_level.values():
        level_rows.sort(key=lambda row: (row.position, row.id))
        for row, position in zip(level_rows, renumbered(len(level_rows))):
            if row.position != position:
                row.position = position
                row.version += 1
                db.save(row)
                touched += 1

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[order.id],
        before=None,
        after={"order_id": order.id, "renumbered": touched},
        emit_type="reading_order.changed",
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"order_id": order.id, "renumbered": touched}, spec


class ReadingOrderDeleteParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str


def _invert_order_delete(before, after, ctx: ActionContext):
    order_id = (after or {}).get("order_id")
    return ("reading_order.restore", {"order_id": order_id}) if order_id else None


@action(
    "reading_order.delete",
    ReadingOrderDeleteParams,
    domains=["reading_order"],
    undoable=True,
    invert=_invert_order_delete,
)
def _action_order_delete(db: Database, params: ReadingOrderDeleteParams, ctx: ActionContext):
    """Soft-delete one order. Its entries stay, so restoring brings the whole
    claim back rather than an empty order."""
    order = _live_order(db, params.order_id)
    order.deleted_at = utc_now()
    db.save(order)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[order.id],
        before={"order_id": order.id, "deleted": False},
        after={"order_id": order.id, "deleted": True},
        emit_type="reading_order.deleted",
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"order_id": order.id, "deleted": True}, spec


@action(
    "reading_order.restore",
    ReadingOrderDeleteParams,
    domains=["reading_order"],
    undoable=False,
)
def _action_order_restore(db: Database, params: ReadingOrderDeleteParams, ctx: ActionContext):
    order = db.get(ReadingOrder, params.order_id)
    if order is None:
        raise HTTPException(
            status_code=404, detail=f"Reading order not found: {params.order_id}"
        )
    order.deleted_at = None
    db.save(order)

    spec = ChangeSpec(
        domains=["reading_order"],
        target_ids=[order.id],
        before={"order_id": order.id, "deleted": True},
        after={"order_id": order.id, "deleted": False},
        emit_type="reading_order.changed",
        pass_ids=[order.pass_id],
        document_ids=[order.document_id],
    )
    return {"order_id": order.id, "deleted": False}, spec


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


class ReadingOrderRead(BaseModel):
    """One order, without its entries: a list of orders must not pull every
    entry of every order (`source.store.bounded-reads`)."""

    id: str
    document_id: str
    pass_id: str
    name: str
    kind: str
    provenance_kind: str
    created_by: str | None = None
    certainty: float | None = None
    entry_count: int


class ReadingOrderListResponse(BaseModel):
    document_id: str
    orders: list[ReadingOrderRead]


class ReadingOrderEntryRead(BaseModel):
    id: str
    order_id: str
    segment_id: str
    position: float
    parent_entry_id: str | None = None
    version: int


class ReadingOrderEntryListResponse(BaseModel):
    order_id: str
    parent_entry_id: str | None = None
    entries: list[ReadingOrderEntryRead]


class NeighboursResponse(BaseModel):
    order_id: str
    segment_id: str
    previous_segment_id: str | None = None
    next_segment_id: str | None = None


def _order_read(db: Database, order: ReadingOrder) -> ReadingOrderRead:
    return ReadingOrderRead(
        id=order.id,
        document_id=order.document_id,
        pass_id=order.pass_id,
        name=order.name,
        kind=order.kind,
        provenance_kind=order.provenance_kind.value,
        created_by=order.created_by,
        certainty=order.certainty,
        entry_count=len(db.query(ReadingOrderEntry, order_id=order.id)),
    )


@router.get("/document/{document_id}", response_model=ReadingOrderListResponse)
async def list_document_orders(
    document_id: str,
    include_deleted: bool = Query(False, description="Include soft-deleted orders"),
    db: Database = Depends(get_library_database),
) -> ReadingOrderListResponse:
    """`GET /api/reading-orders/document/{document_id}` — a source's orders."""
    orders = [
        _order_read(db, row)
        for row in db.query(ReadingOrder, document_id=document_id)
        if include_deleted or row.deleted_at is None
    ]
    orders.sort(key=lambda row: (row.kind != AS_WRITTEN, row.name, row.id))
    return ReadingOrderListResponse(document_id=document_id, orders=orders)


@router.get("/{order_id}/entries", response_model=ReadingOrderEntryListResponse)
async def list_order_entries(
    order_id: str,
    parent_entry_id: Optional[str] = Query(
        None, description="One level at a time; omit for the top level"
    ),
    db: Database = Depends(get_library_database),
) -> ReadingOrderEntryListResponse:
    """`GET /api/reading-orders/{order_id}/entries` — one LEVEL of one order.

    One level at a time on purpose: orders nest (regions in order, lines in order
    inside each), and returning a whole tree would make a bounded read depend on
    how deeply a scholar nested their reading.
    """
    _live_order(db, order_id)
    return ReadingOrderEntryListResponse(
        order_id=order_id,
        parent_entry_id=parent_entry_id,
        entries=[
            ReadingOrderEntryRead(**row.model_dump())
            for row in entries_in_sequence(db, order_id, parent_entry_id=parent_entry_id)
        ],
    )


@router.get("/{order_id}/neighbours", response_model=NeighboursResponse)
async def order_neighbours(
    order_id: str,
    segment_id: str = Query(..., description="The segment to find the neighbours of"),
    db: Database = Depends(get_library_database),
) -> NeighboursResponse:
    """`GET /api/reading-orders/{order_id}/neighbours` — what reads before and
    after one segment IN THIS ORDER (`source.order.next-previous`).

    Always of a NAMED order. There is no "next segment" call without one: a page
    holds several orders, so answering from a default would be the engine picking
    a scholarly reading without saying so. FastAPI refuses a missing `order_id`
    at the path; `OrderNotNamed` covers a caller that reaches the function some
    other way.
    """
    if not order_id:
        raise _as_http_error(OrderNotNamed())
    _live_order(db, order_id)

    entry = next(
        (row for row in db.query(ReadingOrderEntry, order_id=order_id)
         if row.segment_id == segment_id),
        None,
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"segment {segment_id} is not in order {order_id}",
        )

    # TWO indexed lookups, not a read of the order: a flow across a codex holds
    # thousands of entries, and picking neighbours in memory would cost the
    # manuscript's length per call (`source.store.bounded-reads`). The SQL lives
    # in the persistence layer behind this typed method (#1876).
    previous_segment_id, next_segment_id = db.reading_order_neighbours(
        order_id, position=entry.position, parent_entry_id=entry.parent_entry_id
    )
    return NeighboursResponse(
        order_id=order_id,
        segment_id=segment_id,
        previous_segment_id=previous_segment_id,
        next_segment_id=next_segment_id,
    )


class ReadingOrderWrite(BaseModel):
    """`POST /api/reading-orders` — make an order. The other writes are the
    audited actions; the ones the app needs get a typed route here, because the
    generic action route is not in the contract the app is generated from."""

    model_config = ConfigDict(extra="forbid")

    document_id: str
    pass_id: str
    name: str = AS_WRITTEN
    kind: str = ReadingOrderKind.as_written.value
    certainty: Optional[float] = None
    seed_from_pass: bool = False


@router.post("", response_model=dict)
async def create_reading_order(
    body: ReadingOrderWrite,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> dict:
    result = registry.invoke(db, "reading_order.create", body.model_dump(), ctx)
    return {"ok": result.ok, "result": result.result, "audit_id": result.audit_id}


class ReadingOrderPlaceBody(BaseModel):
    """`POST /api/reading-orders/{order_id}/place` -- move or insert one segment (slice 13, Q5).

    The body of `reading_order.place` without the order id, which is in the path."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str
    after_entry_id: Optional[str] = None
    at_end: bool = False
    parent_entry_id: Optional[str] = None
    expected_version: Optional[int] = None


class ReadingOrderActionAnswer(BaseModel):
    ok: bool
    result: dict
    audit_id: Optional[str] = None


@router.post("/{order_id}/place", response_model=ReadingOrderActionAnswer)
async def place_in_reading_order(
    order_id: str,
    body: ReadingOrderPlaceBody,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ReadingOrderActionAnswer:
    """The ONE reorder call the Reader, the Inspector and the Segments pane all make, by drag or
    by key (ruled 2026-09-27, Q5). Thin: the audited `reading_order.place` does the work, so
    it is undoable through the audit trail like every other edit."""
    result = registry.invoke(db, "reading_order.place", {"order_id": order_id, **body.model_dump()}, ctx)
    return ReadingOrderActionAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


# ---------------------------------------------------------------------------
# Flows that could continue onto a page (`source.segment.flow`): so the app can add THIS page's
# segments to a flow that ended on an earlier page -- a letter's text running on from folio 3r to 3v.
# ---------------------------------------------------------------------------


class FlowCandidate(BaseModel):
    order: ReadingOrderRead
    #: Where the flow ends now: its last entry's segment and that segment's page.
    last_segment_id: str | None = None
    last_page_id: str | None = None
    #: "earlier page": ends on a page before this one in the source's page order. "same project":
    #: a flow on a source a project shares with this page -- other sources have no page order with
    #: this one, so it is offered and marked, not ranked.
    relation: str


class FlowCandidatesResponse(BaseModel):
    document_id: str
    flows: list[FlowCandidate]
    #: Flows on pages this caller may not read, left out and counted (#5135, #5180).
    withheld: int = 0


def flows_continuing_onto(db: Database, page_id: str) -> list[tuple[ReadingOrder, Segment | None, str]]:
    """Live flows that could continue onto `page_id`: ending on an earlier page of its source, or on a
    source a project shares with it. A flow that already ends on this page (or later) is not a
    candidate. Nearest first."""
    from fichero_server.models import Document
    from fichero_server.models.knowledge import ProjectInclusion

    page = db.get(Document, page_id)
    if page is None or page.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Document not found: {page_id}")
    siblings = [page]
    if page.parent_id:
        from fichero_server.api.routes.document.documents import _ordered_by_sort_order

        siblings = _ordered_by_sort_order([d for d in db.query(Document, parent_id=page.parent_id) if d.deleted_at is None])
    position = {doc.id: i for i, doc in enumerate(siblings)}
    here = position[page.id]
    members = {page.id, *( [page.parent_id] if page.parent_id else [])}
    projects = {row.project_id for row in db.query_in(ProjectInclusion, "target_id", sorted(members))}
    shared = {row.target_id for row in db.query_in(ProjectInclusion, "project_id", sorted(projects))} - members
    project_pages = set(shared)
    for doc_id in shared:          # a project may include a whole source: its pages count too
        project_pages.update(d.id for d in db.query(Document, parent_id=doc_id) if d.deleted_at is None)

    homes = [doc_id for doc_id in position if position[doc_id] < here] + sorted(project_pages)
    out = []
    for order in db.query_in(ReadingOrder, "document_id", homes):
        if order.deleted_at is not None or order.kind != ReadingOrderKind.flow.value:
            continue
        entries = entries_in_sequence(db, order.id)
        last = db.get(Segment, entries[-1].segment_id) if entries else None
        last_page = last.document_id if last is not None else order.document_id
        if last_page in position:
            if position[last_page] >= here:
                continue            # it already reaches this page, or runs past it
            out.append((order, last, "earlier page", here - position[last_page]))
        elif last_page in project_pages:
            out.append((order, last, "same project", len(position) + 1))
    out.sort(key=lambda row: (row[3], row[0].name, row[0].id))
    return [(order, last, relation) for order, last, relation, _distance in out]


@router.get("/flows/onto/{document_id}", response_model=FlowCandidatesResponse)
async def flows_onto_page(
    document_id: str,
    request: Request,
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> FlowCandidatesResponse:
    """`GET /api/reading-orders/flows/onto/{document_id}` -- the flows this page's segments could be
    added to (`reading_order.place` then continues them here). Nearest earlier page first."""
    from fichero_server.api.main import readable_documents

    found = flows_continuing_onto(db, document_id)
    readable = set(readable_documents(request, x_fichero_library_path,
                                      sorted({order.document_id for order, _l, _r in found})))
    kept = [row for row in found if row[0].document_id in readable]
    return FlowCandidatesResponse(
        document_id=document_id,
        flows=[FlowCandidate(order=_order_read(db, order), last_segment_id=last.id if last else None,
                             last_page_id=last.document_id if last else order.document_id, relation=relation)
               for order, last, relation in kept],
        withheld=len(found) - len(kept),
    )
