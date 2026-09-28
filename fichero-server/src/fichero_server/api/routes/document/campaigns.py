"""Campaigns of writing: record them in order, put segments in them, say what a reading takes in
(slice 14, #4935; `source.campaign.*`). Records: `models/campaigns.py`.

Writes are audited, undoable actions: `campaign.create` / `withdraw` / `restore`, `campaign.assign`
(segments into a campaign; undo puts each back where it was), `reading.take_in` (which campaigns a
reading takes in; undo restores the earlier answer).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action
from fichero_server.api.main import get_library_database
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Document, Segment
from fichero_server.models.campaigns import Campaign, CampaignMembership, ReadingCampaigns
from fichero_server.models.hands import Hand
from fichero_server.models.segments import assert_not_provisional

router = APIRouter(prefix="/campaigns")


class CampaignCreateParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    name: str = Field(min_length=1, max_length=200)
    sequence: int = Field(default=1, ge=1)
    hand_id: Optional[str] = None
    date: Optional[str] = Field(default=None, max_length=200)
    notes: Optional[str] = Field(default=None, max_length=500)


def _live_campaign(db: Database, campaign_id: str) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None or campaign.withdrawn_at is not None:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")
    return campaign


@action("campaign.create", CampaignCreateParams, domains=["campaign"], undoable=True,
        invert=lambda before, after, ctx: ("campaign.withdraw", {"campaign_id": after["campaign_id"]}) if after else None)
def _action_create(db: Database, params: CampaignCreateParams, ctx: ActionContext):
    """A campaign of writing on a source, in its order (`source.campaign.ordered`)."""
    if db.get(Document, params.document_id) is None:
        raise HTTPException(status_code=404, detail=f"Document not found: {params.document_id}")
    if params.hand_id:
        hand = db.get(Hand, params.hand_id)
        if hand is None or hand.deleted_at is not None:
            raise HTTPException(status_code=404, detail=f"Hand not found: {params.hand_id}")
    campaign = Campaign(**params.model_dump(), provenance_kind=provenance_kind_from_ctx(ctx),
                        created_by=ctx.actor or None)
    db.save(campaign)
    return {"campaign_id": campaign.id}, ChangeSpec(
        domains=["campaign"], target_ids=[campaign.id], before=None, after={"campaign_id": campaign.id},
        emit_type="campaign.created", document_ids=[campaign.document_id],
    )


class CampaignIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    campaign_id: str


def _set_campaign(db: Database, campaign_id: str, withdrawn: bool):
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")
    campaign.withdrawn_at = utc_now() if withdrawn else None
    db.save(campaign)
    return {"campaign_id": campaign.id, "withdrawn": withdrawn}, ChangeSpec(
        domains=["campaign"], target_ids=[campaign.id], before=None,
        after={"campaign_id": campaign.id, "withdrawn": withdrawn}, emit_type="campaign.changed",
        document_ids=[campaign.document_id],
    )


@action("campaign.withdraw", CampaignIdParams, domains=["campaign"], undoable=True,
        invert=lambda before, after, ctx: ("campaign.restore", {"campaign_id": after["campaign_id"]}) if after else None)
def _action_withdraw(db: Database, params: CampaignIdParams, ctx: ActionContext):
    return _set_campaign(db, params.campaign_id, True)


@action("campaign.restore", CampaignIdParams, domains=["campaign"], undoable=False)
def _action_restore(db: Database, params: CampaignIdParams, ctx: ActionContext):
    return _set_campaign(db, params.campaign_id, False)


class CampaignAssignParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: None takes the segments out of every campaign (the undo of a first assignment).
    campaign_id: Optional[str] = None
    segment_ids: list[str] = Field(min_length=1, max_length=5000)


class CampaignRestoreAssignParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: Each segment back in the campaign it was in (None: in none).
    previous: dict[str, Optional[str]]


def _assign(db: Database, assignments: dict[str, Optional[str]], actor: Optional[str]) -> dict[str, Optional[str]]:
    """Put each segment in its campaign (None: in none); answer where each one was before."""
    previous: dict[str, Optional[str]] = {}
    for segment_id, campaign_id in assignments.items():
        live = [m for m in db.query(CampaignMembership, segment_id=segment_id) if m.superseded_at is None]
        previous[segment_id] = live[-1].campaign_id if live else None
        for row in live:
            row.superseded_at = utc_now()
            db.save(row)
        if campaign_id is not None:
            db.save(CampaignMembership(segment_id=segment_id, campaign_id=campaign_id, created_by=actor))
    return previous


def _assign_spec(db: Database, segment_ids: list[str], after: dict) -> ChangeSpec:
    documents = sorted({seg.document_id for seg in (db.get(Segment, sid) for sid in segment_ids) if seg is not None})
    return ChangeSpec(
        domains=["campaign", "segment"], target_ids=segment_ids, before=None, after=after,
        emit_type="campaign.assigned", document_ids=documents, segment_ids=segment_ids,
    )


@action("campaign.assign", CampaignAssignParams, domains=["campaign", "segment"], undoable=True,
        invert=lambda before, after, ctx: ("campaign.restore_assign", {"previous": after["previous"]}) if after else None)
def _action_assign(db: Database, params: CampaignAssignParams, ctx: ActionContext):
    """Put segments in a campaign: each segment belongs to ONE (`source.campaign.ordered`); a segment
    already in another campaign moves, and ⌘Z puts it back."""
    if params.campaign_id is not None:
        campaign = _live_campaign(db, params.campaign_id)
    for segment_id in params.segment_ids:
        assert_not_provisional(segment_id, what="segment_ids")
        segment = db.get(Segment, segment_id)
        if segment is None or segment.deleted_at is not None:
            raise HTTPException(status_code=404, detail=f"Segment not found: {segment_id}")
        if params.campaign_id is not None and segment.document_id != campaign.document_id:
            ancestor = db.get(Document, segment.document_id)
            if ancestor is None or ancestor.parent_id != campaign.document_id:
                raise HTTPException(
                    status_code=422,
                    detail=f"segment {segment_id} is not on the source the campaign {campaign.name!r} is of",
                )
    previous = _assign(db, {sid: params.campaign_id for sid in params.segment_ids}, ctx.actor or None)
    return {"previous": previous}, _assign_spec(db, params.segment_ids, {"previous": previous})


@action("campaign.restore_assign", CampaignRestoreAssignParams, domains=["campaign", "segment"], undoable=True,
        invert=lambda before, after, ctx: ("campaign.restore_assign", {"previous": after["previous"]}) if after else None)
def _action_restore_assign(db: Database, params: CampaignRestoreAssignParams, ctx: ActionContext):
    """Each segment back where it was -- the undo of an assign, and (by symmetry) its redo."""
    previous = _assign(db, dict(params.previous), ctx.actor or None)
    return {"previous": previous}, _assign_spec(db, list(params.previous), {"previous": previous})


class ReadingTakeInParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    representation_id: str
    campaign_ids: list[str] = Field(default_factory=list, max_length=50)


def _take_in(db: Database, representation_id: str, campaign_ids: list[str], actor: Optional[str]) -> list[str] | None:
    live = [r for r in db.query(ReadingCampaigns, representation_id=representation_id) if r.superseded_at is None]
    before = live[-1].campaign_ids if live else None
    for row in live:
        row.superseded_at = utc_now()
        db.save(row)
    db.save(ReadingCampaigns(representation_id=representation_id, campaign_ids=campaign_ids, created_by=actor))
    return before


@action("reading.take_in", ReadingTakeInParams, domains=["campaign", "representation"], undoable=True,
        invert=lambda before, after, ctx: ("reading.take_in", {
            "representation_id": after["representation_id"], "campaign_ids": after.get("before") or []}) if after else None)
def _action_take_in(db: Database, params: ReadingTakeInParams, ctx: ActionContext):
    """Say which campaigns a reading takes in (`source.campaign.reading-says-which`): the consonants
    and their later vowels, or only one of them."""
    from fichero_server.models import ContentRepresentation

    reading = db.get(ContentRepresentation, params.representation_id)
    if reading is None:
        raise HTTPException(status_code=404, detail=f"Reading not found: {params.representation_id}")
    for campaign_id in params.campaign_ids:
        _live_campaign(db, campaign_id)
    before = _take_in(db, reading.id, list(params.campaign_ids), ctx.actor or None)
    after = {"representation_id": reading.id, "campaign_ids": list(params.campaign_ids), "before": before}
    return after, ChangeSpec(
        domains=["campaign", "representation"], target_ids=[reading.id], before=None, after=after,
        emit_type="reading.campaigns", document_ids=[reading.document_id] if reading.document_id else [],
    )


class CampaignListResponse(BaseModel):
    items: list[Campaign]


class SegmentCampaignResponse(BaseModel):
    segment_id: str
    campaign: Optional[Campaign] = None


class ReadingCampaignsResponse(BaseModel):
    representation_id: str
    campaign_ids: list[str] = []


@router.get("/document/{document_id}", response_model=CampaignListResponse)
async def campaigns_of_document(document_id: str, db: Database = Depends(get_library_database)) -> CampaignListResponse:
    """A source's campaigns in their order: first laid down first."""
    rows = [c for c in db.query(Campaign, document_id=document_id) if c.withdrawn_at is None]
    return CampaignListResponse(items=sorted(rows, key=lambda c: (c.sequence, c.created_at)))


@router.get("/segment/{segment_id}", response_model=SegmentCampaignResponse)
async def campaign_of_segment(segment_id: str, db: Database = Depends(get_library_database)) -> SegmentCampaignResponse:
    live = [m for m in db.query(CampaignMembership, segment_id=segment_id) if m.superseded_at is None]
    campaign = db.get(Campaign, live[-1].campaign_id) if live else None
    return SegmentCampaignResponse(segment_id=segment_id, campaign=campaign if campaign and not campaign.withdrawn_at else None)


@router.get("/reading/{representation_id}", response_model=ReadingCampaignsResponse)
async def campaigns_of_reading(representation_id: str, db: Database = Depends(get_library_database)) -> ReadingCampaignsResponse:
    live = [r for r in db.query(ReadingCampaigns, representation_id=representation_id) if r.superseded_at is None]
    return ReadingCampaignsResponse(representation_id=representation_id,
                                    campaign_ids=live[-1].campaign_ids if live else [])
