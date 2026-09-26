"""Source-model slice 10 — named reading orders (spec:
``build-notes-readings-cascade-orders.md``, "Slice 10"; #4930).

WHAT THIS IS FOR. A page's lines have a place on the paper; they do not have a
single reading order. A marginal commentary is read after the entry it comments
on or instead of it; a bilingual ledger reads down one column or across both; a
misbound codex reads in an order nobody can see on the page. So an order is a
NAMED, AUTHORED object — several per pass, each one a scholarly claim with its
own provenance — and not a property of the segments.

THE ORDERING RULE IS IMPORTED, NEVER RE-DERIVED. `as-written` is PAGE order
(ruled 2026-09-26): down the page and across the line, which is
``segment_readings._segment_order_key``. Creation order, which
``segments._segment_row_sort_key`` uses for the app's index mapping, answers a
different question and would report the order of the editing session rather than
the order of the source. This module holds no sort of its own, and that is
deliberate: a third rule beside those two is the drift both of their docstrings
already warn about, and one of them had a defect (`a79b901d8`) found by
enumerating them rather than by using one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from fichero_server.core.timeutil import utc_now
from fichero_server.models.knowledge import ProvenanceKind


def _new_id() -> str:
    return uuid.uuid4().hex


#: The name every pass's machine-made order carries. A person may add others;
#: this one is made with the pass so a page always has at least one order to
#: read it by.
AS_WRITTEN = "as-written"


class ReadingOrderKind(str, Enum):
    """What KIND of claim an order makes. Open in spirit like reading kinds --
    the field is a ``str`` so a project can add its own term -- with these as
    the ones that ship."""

    as_written = "as-written"
    imposed = "imposed"
    commentary = "commentary"
    flow = "flow"


BUILTIN_ORDER_KINDS: tuple[str, ...] = tuple(kind.value for kind in ReadingOrderKind)


class ReadingOrder(BaseModel):
    """One named order over one pass's segments. Table ``readingorders``."""

    id: str = Field(default_factory=_new_id)
    document_id: str
    #: An order belongs to ONE pass: a pass is a reading of the page, and an
    #: order over segments of two passes would be an order over two different
    #: accounts of the same paper. A `flow` is the one exception and crosses
    #: PAGES, not passes (see `document_id` below).
    pass_id: str
    #: `as-written` for the machine's order; anything for a person's.
    name: str = AS_WRITTEN
    #: One of `BUILTIN_ORDER_KINDS` or a project's own term.
    kind: str = ReadingOrderKind.as_written.value
    #: Engine-set from `ctx` (#4868/#4869), never client-supplied: an order is a
    #: claim, and a machine's claim recorded as a person's is indistinguishable
    #: from a curator's judgement forever.
    provenance_kind: ProvenanceKind
    created_by: str | None = None
    #: How sure its author is. `None` means nobody said -- NOT certainty 0.
    certainty: float | None = None
    created_at: datetime = Field(default_factory=utc_now)
    #: Soft delete: an order is never removed, so a reading that cited it can
    #: still say what it read.
    deleted_at: datetime | None = None


class ReadingOrderEntry(BaseModel):
    """One segment's place in one order. Table ``readingorderentrys``."""

    id: str = Field(default_factory=_new_id)
    order_id: str
    segment_id: str
    #: A FRACTION, so putting an entry between two others writes ONE row (the
    #: midpoint) instead of renumbering everything after it. See
    #: :func:`midpoint`.
    position: float
    #: Orders nest: regions in order, and the lines in order inside each. A
    #: top-level entry has `None`.
    parent_entry_id: str | None = None
    #: Bumped on every move, so a client can refuse a stale edit the same way a
    #: segment does.
    version: int = 1
    created_at: datetime = Field(default_factory=utc_now)


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

#: Closer than this and two neighbours are one position as far as a float is
#: concerned, so the midpoint would equal one of them and the order would stop
#: being an order. The action refuses and a separate, rare, audited renumber
#: fixes it -- the app never renumbers.
POSITION_GAP_FLOOR = 1e-9

#: The first entry's position, and the step between appended ones. Whole numbers
#: so a freshly made order reads 1.0, 2.0, 3.0 -- legible in a database browser,
#: which matters when somebody is working out what an order claims.
POSITION_STEP = 1.0


class OrderNeedsRenumbering(ValueError):
    """Raised when two neighbours are too close to fit anything between them.

    Names the order and the action that fixes it: a caller told only "too close"
    cannot tell whether it did something wrong or hit a limit of the
    representation.
    """

    def __init__(self, order_id: str, before: float, after: float) -> None:
        self.order_id = order_id
        self.before = before
        self.after = after
        super().__init__(
            f"cannot place between {before!r} and {after!r} in order {order_id}: "
            f"the gap is below {POSITION_GAP_FLOOR}. Run `reading_order.renumber` "
            "on this order first (it rewrites its positions as 1.0, 2.0, 3.0 and "
            "is audited like any other change)."
        )


def midpoint(order_id: str, before: float | None, after: float | None) -> float:
    """The position between two neighbours, or at one end of the order.

    ``before=None`` means "at the start", ``after=None`` means "at the end".
    Both ``None`` is the first entry of an empty order.

    Refuses rather than returning a position equal to one of its neighbours,
    which is what a float division does once the gap is small enough: an entry
    sharing a position with its neighbour has no defined place, and the sort
    would fall through to whatever tie-break comes next -- exactly the silent
    uuid ordering #4921 forbids.
    """
    if before is None and after is None:
        return POSITION_STEP
    if before is None:
        return after - POSITION_STEP  # type: ignore[operator]
    if after is None:
        return before + POSITION_STEP
    if after - before < POSITION_GAP_FLOOR:
        raise OrderNeedsRenumbering(order_id, before, after)
    return before + (after - before) / 2.0


def renumbered(positions: int) -> list[float]:
    """``1.0, 2.0, 3.0 …`` for one order's entries, in their current sequence.

    A pure function so the audited action is a read, a call and a write, with
    nothing to get wrong in between.
    """
    return [float(index + 1) * POSITION_STEP for index in range(positions)]


# ---------------------------------------------------------------------------
# Typed refusals the routes owe their callers
# ---------------------------------------------------------------------------


class OrderPassMismatch(ValueError):
    """A segment of another pass placed in this order.

    Allowed in a `flow`, which is the one kind that crosses pages -- and even
    then the segments belong to passes of the same document GROUP.
    """

    def __init__(self, order_id: str, segment_id: str, expected_pass: str) -> None:
        self.order_id = order_id
        self.segment_id = segment_id
        self.expected_pass = expected_pass
        super().__init__(
            f"segment {segment_id} is not in pass {expected_pass}, which order "
            f"{order_id} is over; only a `flow` order may cross passes"
        )


class AlreadyInOrder(ValueError):
    """The same segment placed twice in one order.

    A segment appearing twice would make `neighbours` ambiguous -- "what comes
    after this line" would have two answers -- and a derived text would repeat
    the line. A REPEATED passage is a different claim and belongs in its own
    order, not twice in one.
    """

    def __init__(self, order_id: str, segment_id: str, entry_id: str) -> None:
        self.order_id = order_id
        self.segment_id = segment_id
        self.entry_id = entry_id
        super().__init__(
            f"segment {segment_id} is already in order {order_id} as entry "
            f"{entry_id}; move that entry rather than adding a second one"
        )


class OrderNotNamed(ValueError):
    """`neighbours` asked without naming an order.

    There is no "next segment" without one: the whole point of the slice is that
    a page has several orders, so answering from a default would be the engine
    picking a scholarly reading and not saying so.
    """

    def __init__(self) -> None:
        super().__init__(
            "neighbours needs an order_id: a page can hold several orders and "
            "there is no default next segment"
        )
