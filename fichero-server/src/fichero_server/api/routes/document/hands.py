"""Hands and who wrote what: the project's hands, and attributions of segments to them (slice 14, #4935).

Spec: `readings-and-apparatus.md`, "Hands" (`source.hand.*`). Records: `models/hands.py`.

Writes are audited, undoable actions (`hand.create`, `hand.withdraw`, `hand.attribute`,
`hand.unattribute`), so the command line and MCP can do what the app does. Reads: the project's
hands, what a segment's hands are (rivals side by side), and everything in one hand
(`source.hand.record`: "everything in hand B" can be asked).
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.library_header import optional_library_path
from fichero_server.api.main import get_library_database, get_library_database_for_write, readable_documents
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Segment
from fichero_server.models.hands import Hand, HandAttribution
from fichero_server.models.segments import assert_not_provisional

router = APIRouter(prefix="/hands")

#: Words that go into the audit chain, which nothing can purge: capped, and a description, never
#: a researcher's essay.
_NOTE_CAP = 500


class HandCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=200)
    scribe: Optional[str] = Field(default=None, max_length=200)
    date: Optional[str] = Field(default=None, max_length=200)
    place: Optional[str] = Field(default=None, max_length=200)
    style: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=_NOTE_CAP)


def _live_hand(db: Database, hand_id: str) -> Hand:
    hand = db.get(Hand, hand_id)
    if hand is None or hand.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Hand not found: {hand_id}")
    return hand


def _invert_hand_create(before, after, ctx: ActionContext):
    hand_id = (after or {}).get("hand_id")
    return ("hand.withdraw", {"hand_id": hand_id}) if hand_id else None


@action("hand.create", HandCreateParams, domains=["hand"], undoable=True, invert=_invert_hand_create)
def _action_hand_create(db: Database, params: HandCreateParams, ctx: ActionContext):
    """A hand in the project's list (`source.hand.record`)."""
    hand = Hand(
        **params.model_dump(),
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
    )
    db.save(hand)
    spec = ChangeSpec(
        domains=["hand"], target_ids=[hand.id], before=None,
        after={"hand_id": hand.id}, emit_type="hand.created",
    )
    return {"hand_id": hand.id}, spec


class HandIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hand_id: str


def _invert_hand_withdraw(before, after, ctx: ActionContext):
    hand_id = (after or {}).get("hand_id")
    return ("hand.restore", {"hand_id": hand_id}) if hand_id else None


@action("hand.withdraw", HandIdParams, domains=["hand"], undoable=True, invert=_invert_hand_withdraw)
def _action_hand_withdraw(db: Database, params: HandIdParams, ctx: ActionContext):
    """Withdraw a hand. Soft: its attributions stay, and still name it, so a scholar's judgement
    is not lost because somebody tidied the list."""
    hand = _live_hand(db, params.hand_id)
    hand.deleted_at = utc_now()
    db.save(hand)
    spec = ChangeSpec(
        domains=["hand"], target_ids=[hand.id],
        before={"hand_id": hand.id, "withdrawn": False},
        after={"hand_id": hand.id, "withdrawn": True}, emit_type="hand.withdrawn",
    )
    return {"hand_id": hand.id, "withdrawn": True}, spec


@action("hand.restore", HandIdParams, domains=["hand"], undoable=False)
def _action_hand_restore(db: Database, params: HandIdParams, ctx: ActionContext):
    hand = db.get(Hand, params.hand_id)
    if hand is None:
        raise HTTPException(status_code=404, detail=f"Hand not found: {params.hand_id}")
    hand.deleted_at = None
    db.save(hand)
    spec = ChangeSpec(
        domains=["hand"], target_ids=[hand.id],
        before={"hand_id": hand.id, "withdrawn": True},
        after={"hand_id": hand.id, "withdrawn": False}, emit_type="hand.created",
    )
    return {"hand_id": hand.id, "withdrawn": False}, spec


class HandAttributeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hand_id: str
    segment_id: str
    certainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)


def _invert_hand_attribute(before, after, ctx: ActionContext):
    attribution_id = (after or {}).get("attribution_id")
    return ("hand.unattribute", {"attribution_id": attribution_id}) if attribution_id else None


@action("hand.attribute", HandAttributeParams, domains=["hand", "segment"], undoable=True,
        invert=_invert_hand_attribute)
def _action_hand_attribute(db: Database, params: HandAttributeParams, ctx: ActionContext):
    """Say that a segment is in a hand (`source.hand.attributed`). Another judgement on the same
    segment does NOT replace this one: rivals stand side by side, each with its author."""
    assert_not_provisional(params.segment_id, what="segment_id")
    _live_hand(db, params.hand_id)
    segment = db.get(Segment, params.segment_id)
    if segment is None or segment.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.segment_id}")
    attribution = HandAttribution(
        hand_id=params.hand_id, segment_id=params.segment_id, certainty=params.certainty,
        provenance_kind=provenance_kind_from_ctx(ctx), created_by=ctx.actor or None,
    )
    db.save(attribution)
    spec = ChangeSpec(
        domains=["hand", "segment"], target_ids=[attribution.id, params.segment_id], before=None,
        after={"attribution_id": attribution.id, "hand_id": params.hand_id, "segment_id": params.segment_id},
        emit_type="hand.attributed", document_ids=[segment.document_id],
    )
    return {"attribution_id": attribution.id}, spec


class AttributionIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attribution_id: str


def _invert_hand_unattribute(before, after, ctx: ActionContext):
    attribution_id = (after or {}).get("attribution_id")
    return ("hand.reattribute", {"attribution_id": attribution_id}) if attribution_id else None


def _attribution(db: Database, attribution_id: str) -> HandAttribution:
    attribution = db.get(HandAttribution, attribution_id)
    if attribution is None:
        raise HTTPException(status_code=404, detail=f"Attribution not found: {attribution_id}")
    return attribution


@action("hand.unattribute", AttributionIdParams, domains=["hand", "segment"], undoable=True,
        invert=_invert_hand_unattribute)
def _action_hand_unattribute(db: Database, params: AttributionIdParams, ctx: ActionContext):
    """Withdraw one judgement. The others on the segment stand."""
    attribution = _attribution(db, params.attribution_id)
    attribution.withdrawn_at = utc_now()
    db.save(attribution)
    spec = ChangeSpec(
        domains=["hand", "segment"], target_ids=[attribution.id, attribution.segment_id],
        before={"attribution_id": attribution.id, "withdrawn": False},
        after={"attribution_id": attribution.id, "withdrawn": True}, emit_type="hand.unattributed",
    )
    return {"attribution_id": attribution.id, "withdrawn": True}, spec


@action("hand.reattribute", AttributionIdParams, domains=["hand", "segment"], undoable=False)
def _action_hand_reattribute(db: Database, params: AttributionIdParams, ctx: ActionContext):
    attribution = _attribution(db, params.attribution_id)
    attribution.withdrawn_at = None
    db.save(attribution)
    spec = ChangeSpec(
        domains=["hand", "segment"], target_ids=[attribution.id, attribution.segment_id],
        before={"attribution_id": attribution.id, "withdrawn": True},
        after={"attribution_id": attribution.id, "withdrawn": False}, emit_type="hand.attributed",
    )
    return {"attribution_id": attribution.id, "withdrawn": False}, spec


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class HandActionAnswer(BaseModel):
    ok: bool
    result: dict[str, Any]
    audit_id: Optional[str] = None


def _answer(db: Database, name: str, params: dict, ctx: ActionContext) -> HandActionAnswer:
    result = registry.invoke(db, name, params, ctx)
    return HandActionAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


@router.post("", response_model=HandActionAnswer)
async def create_hand(
    body: HandCreateParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> HandActionAnswer:
    return _answer(db, "hand.create", body.model_dump(), ctx)


@router.post("/{hand_id}/withdraw", response_model=HandActionAnswer)
async def withdraw_hand(
    hand_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> HandActionAnswer:
    return _answer(db, "hand.withdraw", {"hand_id": hand_id}, ctx)


@router.post("/attributions", response_model=HandActionAnswer)
async def attribute_segment(
    body: HandAttributeParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> HandActionAnswer:
    return _answer(db, "hand.attribute", body.model_dump(), ctx)


@router.post("/attributions/{attribution_id}/withdraw", response_model=HandActionAnswer)
async def withdraw_attribution(
    attribution_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> HandActionAnswer:
    return _answer(db, "hand.unattribute", {"attribution_id": attribution_id}, ctx)


class HandListResponse(BaseModel):
    items: list[Hand]


@router.get("", response_model=HandListResponse)
async def list_hands(db: Database = Depends(get_library_database)) -> HandListResponse:
    """The project's hands, by label."""
    return HandListResponse(
        items=sorted((h for h in db.all(Hand) if h.deleted_at is None), key=lambda h: h.label)
    )


class AttributionListResponse(BaseModel):
    items: list[HandAttribution]
    #: Attributions left out because this caller may not read their page (#5180): counted, never silent.
    withheld: int = 0


@router.get("/segment/{segment_id}", response_model=AttributionListResponse)
async def hands_of_segment(
    segment_id: str, db: Database = Depends(get_library_database)
) -> AttributionListResponse:
    """Every live judgement of who wrote this segment -- rivals side by side, oldest first."""
    return AttributionListResponse(items=sorted(
        (a for a in db.query(HandAttribution, segment_id=segment_id) if a.withdrawn_at is None),
        key=lambda a: a.created_at,
    ))


@router.get("/{hand_id}/attributions", response_model=AttributionListResponse)
async def everything_in_a_hand(
    hand_id: str,
    request: Request,
    x_fichero_library_path: str | None = Depends(optional_library_path),
    db: Database = Depends(get_library_database),
) -> AttributionListResponse:
    """Everything in one hand, across every source ("everything in hand B") -- that this caller may
    read: a hand is library-level, its attributions are on pages, and one on a page this caller may
    not read is left out and counted (#5180)."""
    if db.get(Hand, hand_id) is None:
        raise HTTPException(status_code=404, detail=f"Hand not found: {hand_id}")
    every = [a for a in db.query(HandAttribution, hand_id=hand_id) if a.withdrawn_at is None]
    page_of = {a.id: getattr(db.get(Segment, a.segment_id), "document_id", None) for a in every}
    readable = set(readable_documents(request, x_fichero_library_path,
                                      sorted({d for d in page_of.values() if d})))
    items = [a for a in every if page_of[a.id] in readable]
    return AttributionListResponse(items=sorted(items, key=lambda a: a.created_at), withheld=len(every) - len(items))


def hands_from_file(
    db: Database, hands_by_segment: dict[str, list[str]], *, edition: str, source: str, ctx: ActionContext,
) -> int:
    """The hands an imported file names, as project hands and attributions (approved 2026-09-27).

    A file's "m1" is ITS first hand, not every file's: the hand is labelled with its edition --
    "m2 (P.Cair.Zen. 4 59742)" -- so two papyri's "m1" stay two hands. The same label from another
    page of the same edition is the same hand and is reused. Merging hands across sources is a
    person's judgement, never the import's. Each attribution says the FILE said so (`source`).
    Returns how many attributions were written.
    """
    if not hands_by_segment:
        return 0
    live = {h.label: h for h in db.all(Hand) if h.deleted_at is None}
    written = 0
    for segment_id, labels in hands_by_segment.items():
        for label in labels:
            full = f"{label} ({edition})"
            hand = live.get(full)
            if hand is None:
                hand = Hand(label=full, provenance_kind=provenance_kind_from_ctx(ctx), created_by=ctx.actor or None)
                db.save(hand)
                live[full] = hand
            db.save(HandAttribution(
                hand_id=hand.id, segment_id=segment_id, source=source,
                provenance_kind=provenance_kind_from_ctx(ctx), created_by=ctx.actor or None,
            ))
            written += 1
    return written
