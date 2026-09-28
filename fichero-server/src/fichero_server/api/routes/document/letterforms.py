"""Letterforms: allographs, descriptions of marks, and gathering marks to compare (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Letterforms" (`source.letterform.*`). Records:
`models/letterforms.py`. Writes are audited, undoable actions (`allograph.create`,
`allograph.withdraw`, `letterform.describe`, `letterform.withdraw`); reads: the project's allographs,
one segment's description, the open lists of components and features the project uses, and every
mark gathered by character / allograph / hand across sources (`source.letterform.compare`).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Segment
from fichero_server.models.hands import Hand
from fichero_server.models.letterforms import Allograph, LetterFeature, LetterformDescription
from fichero_server.models.segments import assert_not_provisional

router = APIRouter(prefix="/letterforms")

_WORDS = 200


class AllographCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=_WORDS)
    notes: Optional[str] = Field(default=None, max_length=500)


def _invert_allograph_create(before, after, ctx: ActionContext):
    allograph_id = (after or {}).get("allograph_id")
    return ("allograph.withdraw", {"allograph_id": allograph_id}) if allograph_id else None


@action("allograph.create", AllographCreateParams, domains=["letterform"], undoable=True,
        invert=_invert_allograph_create)
def _action_allograph_create(db: Database, params: AllographCreateParams, ctx: ActionContext):
    """A recognised form of a character, in the project's list."""
    allograph = Allograph(**params.model_dump(), provenance_kind=provenance_kind_from_ctx(ctx),
                          created_by=ctx.actor or None)
    db.save(allograph)
    return {"allograph_id": allograph.id}, ChangeSpec(
        domains=["letterform"], target_ids=[allograph.id], before=None,
        after={"allograph_id": allograph.id}, emit_type="allograph.created",
    )


class AllographIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allograph_id: str


def _set_allograph_withdrawn(db: Database, allograph_id: str, withdrawn: bool):
    allograph = db.get(Allograph, allograph_id)
    if allograph is None:
        raise HTTPException(status_code=404, detail=f"Allograph not found: {allograph_id}")
    allograph.withdrawn_at = utc_now() if withdrawn else None
    db.save(allograph)
    return {"allograph_id": allograph.id, "withdrawn": withdrawn}, ChangeSpec(
        domains=["letterform"], target_ids=[allograph.id], before={"withdrawn": not withdrawn},
        after={"allograph_id": allograph.id, "withdrawn": withdrawn}, emit_type="allograph.changed",
    )


@action("allograph.withdraw", AllographIdParams, domains=["letterform"], undoable=True,
        invert=lambda before, after, ctx: ("allograph.restore", {"allograph_id": after["allograph_id"]}) if after else None)
def _action_allograph_withdraw(db: Database, params: AllographIdParams, ctx: ActionContext):
    return _set_allograph_withdrawn(db, params.allograph_id, True)


@action("allograph.restore", AllographIdParams, domains=["letterform"], undoable=False)
def _action_allograph_restore(db: Database, params: AllographIdParams, ctx: ActionContext):
    return _set_allograph_withdrawn(db, params.allograph_id, False)


class LetterformDescribeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    character: str = Field(min_length=1, max_length=80)
    allograph_id: Optional[str] = None
    hand_id: Optional[str] = None
    features: list[LetterFeature] = Field(default_factory=list, max_length=50)


def _invert_describe(before, after, ctx: ActionContext):
    """Undo a description: withdraw it, and bring back the one it superseded, if any."""
    description_id = (after or {}).get("description_id")
    if not description_id:
        return None
    return ("letterform.withdraw", {"description_id": description_id,
                                    "restore_id": (after or {}).get("superseded_id")})


@action("letterform.describe", LetterformDescribeParams, domains=["letterform", "segment"], undoable=True,
        invert=_invert_describe)
def _action_describe(db: Database, params: LetterformDescribeParams, ctx: ActionContext):
    """Describe one mark (`source.letterform.chain`, `.features`). A mark has ONE live description:
    describing it again supersedes (withdraws) the earlier one, which ⌘Z brings back."""
    assert_not_provisional(params.segment_id, what="segment_id")
    segment = db.get(Segment, params.segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    if params.allograph_id:
        allograph = db.get(Allograph, params.allograph_id)
        if allograph is None or allograph.withdrawn_at is not None:
            raise HTTPException(status_code=404, detail=f"Allograph not found: {params.allograph_id}")
        if allograph.character != params.character:
            raise HTTPException(
                status_code=422,
                detail=f"allograph {allograph.name!r} is a form of {allograph.character!r}, not {params.character!r}",
            )
    if params.hand_id:
        hand = db.get(Hand, params.hand_id)
        if hand is None or hand.deleted_at is not None:
            raise HTTPException(status_code=404, detail=f"Hand not found: {params.hand_id}")
    live = [d for d in db.query(LetterformDescription, segment_id=segment.id) if d.withdrawn_at is None]
    for earlier in live:
        earlier.withdrawn_at = utc_now()
        db.save(earlier)
    description = LetterformDescription(
        **params.model_dump(exclude={"features"}), features=params.features,
        provenance_kind=provenance_kind_from_ctx(ctx), created_by=ctx.actor or None,
    )
    db.save(description)
    after = {"description_id": description.id, "superseded_id": live[-1].id if live else None}
    return after, ChangeSpec(
        domains=["letterform", "segment"], target_ids=[description.id, segment.id], before=None, after=after,
        emit_type="letterform.described", document_ids=[segment.document_id], segment_ids=[segment.id],
    )


class LetterformWithdrawParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description_id: str
    #: Bring this earlier description back in the same step (the undo of a re-description).
    restore_id: Optional[str] = None


def _invert_withdraw(before, after, ctx: ActionContext):
    """Symmetric, so ⇧⌘Z works: withdrawing A while bringing back B inverts to withdrawing B while
    bringing back A; a plain withdraw inverts to restoring A."""
    if not after:
        return None
    if after.get("restored_id"):
        return ("letterform.withdraw", {"description_id": after["restored_id"], "restore_id": after["description_id"]})
    return ("letterform.restore", {"description_id": after["description_id"]})


def _set_description(db: Database, description_id: str, withdrawn: bool) -> LetterformDescription:
    description = db.get(LetterformDescription, description_id)
    if description is None:
        raise HTTPException(status_code=404, detail=f"Description not found: {description_id}")
    description.withdrawn_at = utc_now() if withdrawn else None
    db.save(description)
    return description


def _description_spec(description: LetterformDescription, db: Database, after: dict, emit: str) -> ChangeSpec:
    segment = db.get(Segment, description.segment_id)
    return ChangeSpec(
        domains=["letterform", "segment"], target_ids=[description.id], before=None, after=after,
        emit_type=emit, document_ids=[segment.document_id] if segment else [], segment_ids=[description.segment_id],
    )


@action("letterform.withdraw", LetterformWithdrawParams, domains=["letterform", "segment"], undoable=True,
        invert=_invert_withdraw)
def _action_withdraw(db: Database, params: LetterformWithdrawParams, ctx: ActionContext):
    """Withdraw a description (kept, never deleted), optionally bringing an earlier one of the same
    mark back in the same step -- the undo of a re-description."""
    description = _set_description(db, params.description_id, True)
    restored_id = None
    if params.restore_id:
        earlier = db.get(LetterformDescription, params.restore_id)
        if earlier is not None and earlier.segment_id == description.segment_id:
            earlier.withdrawn_at = None
            db.save(earlier)
            restored_id = earlier.id
    after = {"description_id": description.id, "restored_id": restored_id}
    return after, _description_spec(description, db, after, "letterform.withdrawn")


class LetterformRestoreParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description_id: str


@action("letterform.restore", LetterformRestoreParams, domains=["letterform", "segment"], undoable=True,
        invert=lambda before, after, ctx: ("letterform.withdraw", {"description_id": after["description_id"]}) if after else None)
def _action_restore(db: Database, params: LetterformRestoreParams, ctx: ActionContext):
    description = _set_description(db, params.description_id, False)
    after = {"description_id": description.id}
    return after, _description_spec(description, db, after, "letterform.described")


class AllographListResponse(BaseModel):
    items: list[Allograph]


class DescriptionListResponse(BaseModel):
    items: list[LetterformDescription]


class FeatureListResponse(BaseModel):
    #: The open lists as the project has used them: every (component, feature) pair, with how often.
    items: list[dict]


@router.get("/allographs", response_model=AllographListResponse)
async def list_allographs(
    character: Optional[str] = Query(None),
    db: Database = Depends(get_library_database),
) -> AllographListResponse:
    rows = [a for a in db.all(Allograph) if a.withdrawn_at is None and (character is None or a.character == character)]
    return AllographListResponse(items=sorted(rows, key=lambda a: (a.character, a.name)))


@router.get("/segment/{segment_id}", response_model=DescriptionListResponse)
async def description_of_segment(segment_id: str, db: Database = Depends(get_library_database)) -> DescriptionListResponse:
    return DescriptionListResponse(
        items=[d for d in db.query(LetterformDescription, segment_id=segment_id) if d.withdrawn_at is None]
    )


@router.get("/features", response_model=FeatureListResponse)
async def features_in_use(db: Database = Depends(get_library_database)) -> FeatureListResponse:
    counts: dict[tuple[str, str], int] = {}
    for description in db.all(LetterformDescription):
        if description.withdrawn_at is None:
            for f in description.features:
                counts[(f.component, f.feature)] = counts.get((f.component, f.feature), 0) + 1
    return FeatureListResponse(items=[
        {"component": c, "feature": f, "count": n} for (c, f), n in sorted(counts.items())
    ])


@router.get("", response_model=DescriptionListResponse)
async def gather(
    character: Optional[str] = Query(None),
    allograph_id: Optional[str] = Query(None),
    hand_id: Optional[str] = Query(None),
    db: Database = Depends(get_library_database),
) -> DescriptionListResponse:
    """Every live mark of a character, an allograph or a hand, across sources (`.compare`). At least
    one of the three is named: gathering every mark in a library is not a comparison."""
    if not (character or allograph_id or hand_id):
        raise HTTPException(status_code=422, detail="name a character, an allograph or a hand to gather by")
    rows = [
        d for d in db.all(LetterformDescription)
        if d.withdrawn_at is None
        and (character is None or d.character == character)
        and (allograph_id is None or d.allograph_id == allograph_id)
        and (hand_id is None or d.hand_id == hand_id)
    ]
    return DescriptionListResponse(items=rows)
