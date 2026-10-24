"""Editorial facts: record, withdraw, and read them drawn as the editor's signs (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Three different kinds of 'sure'" (`source.sure.*`). Records:
`models/editorial.py`; the signs: `editorial/leiden.py`.

Writes are audited, undoable actions (`editorial.record`, `editorial.withdraw`), so the command line,
MCP and the app do the same thing. The read answers a segment's live facts AND its counting reading
drawn with them (`source.sure.brackets-are-drawn`): the brackets are made at read time, never stored.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.editorial.leiden import draw
from fichero_server.models import Segment
from fichero_server.models.editorial import EditorialFact, EditorialFactKind
from fichero_server.models.segments import assert_not_provisional
from fichero_server.core.off_loop import off_loop

router = APIRouter(prefix="/editorial")

#: Words that go into the audit chain, which nothing can purge: capped descriptions, never essays.
_WORDS_CAP = 200


class EditorialRecordParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    kind: EditorialFactKind
    representation_id: Optional[str] = None
    char_start: Optional[int] = Field(default=None, ge=0)
    char_end: Optional[int] = Field(default=None, ge=0)
    extent: Optional[str] = Field(default=None, max_length=_WORDS_CAP)
    extent_quantity: Optional[float] = Field(default=None, ge=0)
    extent_unit: Optional[str] = Field(default=None, max_length=40)
    reason: Optional[str] = Field(default=None, max_length=_WORDS_CAP)
    place: Optional[str] = Field(default=None, max_length=40)
    certainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _live_segment(db: Database, segment_id: str) -> Segment:
    assert_not_provisional(segment_id, what="segment_id")
    segment = db.get(Segment, segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    return segment


def _check_span(db: Database, params: EditorialRecordParams) -> None:
    """A span names the reading it is measured on, and fits inside it -- a span into no text, or past
    its end, would be drawn somewhere nobody meant."""
    has_span = params.char_start is not None or params.char_end is not None
    if not has_span:
        return
    # A LOST stretch has no text to span, but it has a place: a TEI <gap/> mid-line is lost letters
    # BETWEEN two others. So a lost fact may give char_start alone -- a position, where the gap is
    # drawn (`leiden.draw`) -- and every other kind needs a span.
    position_only = (params.kind == EditorialFactKind.lost
                     and params.char_start is not None and params.char_end is None)
    if not position_only and (
        params.char_start is None or params.char_end is None or params.char_start >= params.char_end
    ):
        raise HTTPException(status_code=422, detail="a span needs char_start < char_end (a lost stretch may give char_start alone)")
    if params.representation_id is None:
        raise HTTPException(status_code=422, detail="a span names the reading it is measured on (representation_id)")
    from fichero_server.api.routes.document.segment_readings import readings_of_segment

    reading = next((r for r in readings_of_segment(db, params.segment_id) if r.id == params.representation_id), None)
    if reading is None:
        raise HTTPException(status_code=422, detail=f"reading {params.representation_id} is not one of this segment's")
    end = params.char_end if params.char_end is not None else params.char_start
    if end > len(reading.content):
        raise HTTPException(
            status_code=422,
            detail=f"the span ends at {end}, past the reading's {len(reading.content)} characters",
        )


def _spec(fact: EditorialFact, segment: Segment, *, before: Any, after: Any, emit: str) -> ChangeSpec:
    return ChangeSpec(
        domains=["editorial", "segment"], target_ids=[fact.id, segment.id], before=before, after=after,
        emit_type=emit, document_ids=[segment.document_id], segment_ids=[segment.id],
    )


def _invert_record(before, after, ctx: ActionContext):
    fact_id = (after or {}).get("fact_id")
    return ("editorial.withdraw", {"fact_id": fact_id}) if fact_id else None


@action("editorial.record", EditorialRecordParams, domains=["editorial", "segment"], undoable=True,
        invert=_invert_record)
def _action_record(db: Database, params: EditorialRecordParams, ctx: ActionContext):
    """Record one editorial fact about a stretch of a segment's text (`source.sure.editorial-facts`)."""
    segment = _live_segment(db, params.segment_id)
    _check_span(db, params)
    fact = EditorialFact(
        **params.model_dump(), provenance_kind=provenance_kind_from_ctx(ctx), created_by=ctx.actor or None,
    )
    db.save(fact)
    return {"fact_id": fact.id}, _spec(fact, segment, before=None, after={"fact_id": fact.id},
                                       emit="editorial.recorded")


class FactIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_id: str


def _live_fact(db: Database, fact_id: str) -> tuple[EditorialFact, Segment]:
    fact = db.get(EditorialFact, fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail=f"Editorial fact not found: {fact_id}")
    segment = db.get(Segment, fact.segment_id)
    if segment is None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {fact.segment_id}")
    return fact, segment


def _invert_withdraw(before, after, ctx: ActionContext):
    fact_id = (after or {}).get("fact_id")
    return ("editorial.restore", {"fact_id": fact_id}) if fact_id else None


@action("editorial.withdraw", FactIdParams, domains=["editorial", "segment"], undoable=True,
        invert=_invert_withdraw)
def _action_withdraw(db: Database, params: FactIdParams, ctx: ActionContext):
    """Withdraw a fact: kept in the record, no longer drawn."""
    fact, segment = _live_fact(db, params.fact_id)
    fact.withdrawn_at = utc_now()
    db.save(fact)
    return {"fact_id": fact.id, "withdrawn": True}, _spec(
        fact, segment, before={"fact_id": fact.id, "withdrawn": False},
        after={"fact_id": fact.id, "withdrawn": True}, emit="editorial.withdrawn",
    )


@action("editorial.restore", FactIdParams, domains=["editorial", "segment"], undoable=False)
def _action_restore(db: Database, params: FactIdParams, ctx: ActionContext):
    fact, segment = _live_fact(db, params.fact_id)
    fact.withdrawn_at = None
    db.save(fact)
    return {"fact_id": fact.id, "withdrawn": False}, _spec(
        fact, segment, before={"fact_id": fact.id, "withdrawn": True},
        after={"fact_id": fact.id, "withdrawn": False}, emit="editorial.recorded",
    )


class EditorialRecordManyParams(BaseModel):
    """One whole-segment fact (no span: a stretch is measured on one reading, and a selection has no one reading) on each of
    several segments, e.g. the Inspector's Certainty set on a multi-selection."""
    model_config = ConfigDict(extra="forbid")

    segment_ids: list[str] = Field(min_length=1, max_length=500)
    kind: EditorialFactKind
    extent: Optional[str] = Field(default=None, max_length=_WORDS_CAP)
    reason: Optional[str] = Field(default=None, max_length=_WORDS_CAP)
    place: Optional[str] = Field(default=None, max_length=40)
    certainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _invert_record_many(before, after, ctx: ActionContext):
    ids = (after or {}).get("fact_ids")
    return ("editorial.withdraw_many", {"fact_ids": ids}) if ids else None


@action("editorial.record_many", EditorialRecordManyParams, domains=["editorial", "segment"], undoable=True,
        invert=_invert_record_many)
def _action_record_many(db: Database, params: EditorialRecordManyParams, ctx: ActionContext):
    """One fact on several segments: ONE audit row, ONE undo, all or nothing (every segment is checked first)."""
    segments = [_live_segment(db, sid) for sid in dict.fromkeys(params.segment_ids)]
    fields = params.model_dump(exclude={"segment_ids"})
    facts = [EditorialFact(segment_id=seg.id, **fields, provenance_kind=provenance_kind_from_ctx(ctx),
                           created_by=ctx.actor or None) for seg in segments]
    db.save_many(facts)
    ids = [f.id for f in facts]
    return {"fact_ids": ids}, ChangeSpec(
        domains=["editorial", "segment"], target_ids=ids + [seg.id for seg in segments], before=None,
        after={"fact_ids": ids}, emit_type="editorial.recorded",
        document_ids=sorted({seg.document_id for seg in segments}), segment_ids=[seg.id for seg in segments])


class FactIdsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fact_ids: list[str] = Field(min_length=1, max_length=500)


def _set_facts_withdrawn(db: Database, ids: list[str], withdrawn: bool):
    pairs = [_live_fact(db, i) for i in dict.fromkeys(ids)]
    now = utc_now()
    for fact, _segment in pairs:
        fact.withdrawn_at = now if withdrawn else None
    db.save_many([fact for fact, _ in pairs])
    found = [fact.id for fact, _ in pairs]
    segs = sorted({seg.id for _, seg in pairs})
    return {"fact_ids": found, "withdrawn": withdrawn}, ChangeSpec(
        domains=["editorial", "segment"], target_ids=found + segs, before={"fact_ids": found, "withdrawn": not withdrawn},
        after={"fact_ids": found, "withdrawn": withdrawn},
        emit_type="editorial.withdrawn" if withdrawn else "editorial.recorded",
        document_ids=sorted({seg.document_id for _, seg in pairs}), segment_ids=segs)


@action("editorial.withdraw_many", FactIdsParams, domains=["editorial", "segment"], undoable=True,
        invert=lambda before, after, ctx: ("editorial.restore_many", {"fact_ids": after["fact_ids"]})
        if (after or {}).get("fact_ids") else None)
def _action_withdraw_many(db: Database, params: FactIdsParams, ctx: ActionContext):
    return _set_facts_withdrawn(db, params.fact_ids, True)


@action("editorial.restore_many", FactIdsParams, domains=["editorial", "segment"], undoable=False)
def _action_restore_many(db: Database, params: FactIdsParams, ctx: ActionContext):
    return _set_facts_withdrawn(db, params.fact_ids, False)


class EditorialListResponse(BaseModel):
    items: list[EditorialFact]
    #: The counting transcription, as the editor prints it: its text with the live facts about it
    #: drawn in (Leiden). None when no reading counts.
    drawn: Optional[str] = None
    #: The reading `drawn` was made from.
    drawn_from: Optional[str] = None


@router.get("/segment/{segment_id}", response_model=EditorialListResponse)
@off_loop
def facts_of_segment(
    segment_id: str,
    db: Database = Depends(get_library_database),
) -> EditorialListResponse:
    """A segment's live editorial facts, and its counting reading drawn with them."""
    from fichero_server.api.routes.document.segment_readings import counting_by_kind, readings_of_segment

    segment = db.get(Segment, segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
    from fichero_server.models.segments import SegmentPass

    owner = db.get(SegmentPass, segment.pass_id)
    if owner is None or owner.deleted_at is not None:
        # A deleted pass takes its segments with it (an import's undo deletes its pass, #5179): its
        # facts are not a live segment's facts, whatever the segment row still says.
        raise HTTPException(status_code=404, detail=f"Segment {segment_id} is in a deleted pass")
    facts = sorted(
        (f for f in db.query(EditorialFact, segment_id=segment_id) if f.withdrawn_at is None),
        key=lambda f: (f.char_start if f.char_start is not None else -1, f.created_at),
    )
    readings = readings_of_segment(db, segment_id)
    counting = counting_by_kind(db, segment_id, readings).get("transcription")
    reading = next((r for r in readings if counting and r.id == counting.representation_id), None)
    if reading is None:
        return EditorialListResponse(items=facts)
    about = [f for f in facts if f.representation_id in (None, reading.id)]
    return EditorialListResponse(items=facts, drawn=draw(reading.content, about), drawn_from=reading.id)
