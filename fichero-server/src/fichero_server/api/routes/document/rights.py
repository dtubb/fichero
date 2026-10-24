"""Rights and consent records: set, withdraw, and what applies to a target (slice 14, #4953).

Spec: `rights-and-access.md` (`source.rights.*`); the record and its arithmetic are
`models/rights.py`. Writes are audited, undoable actions. WHO may set one
(`source.rights.who-acts`: owners and editors) is the existing write check -- `target_id` is a
write target, so a viewer, or anyone denied the target, is refused before the action runs.

This module decides what a record SAYS and what the records above a target add up to. It does
not yet decide who is refused what: that is `source.rights.one-check`, held for its own ruling.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Document, Segment
from fichero_server.models.rights import (
    MODEL_USE_RANK,
    EffectiveRights,
    ModelUse,
    RightsRecord,
    RightsTarget,
    combine,
)

router = APIRouter(prefix="/rights")

LIBRARY_TARGET = "library"


def chain(db: Database, target_kind: str, target_id: str) -> list[tuple[str, str]]:
    """The targets whose records apply to this one, from the library DOWN to it."""
    links: list[tuple[str, str]] = []
    document_id: str | None = None
    if target_kind == RightsTarget.segment.value:
        segment = db.get(Segment, target_id)
        if segment is None:
            raise HTTPException(status_code=404, detail=f"Segment not found: {target_id}")
        links.append((RightsTarget.segment.value, target_id))
        document_id = segment.document_id
    elif target_kind == RightsTarget.document.value:
        document_id = target_id
    elif target_kind != RightsTarget.library.value:
        raise HTTPException(status_code=422, detail=f"a rights record hangs on a library, document or segment, not {target_kind!r}")
    seen: set[str] = set()
    while document_id and document_id not in seen:
        seen.add(document_id)
        document = db.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
        links.append((RightsTarget.document.value, document.id))
        document_id = document.parent_id
    links.append((RightsTarget.library.value, LIBRARY_TARGET))
    return list(reversed(links))


def records_on(db: Database, target_kind: str, target_id: str) -> list[RightsRecord]:
    return sorted(
        (r for r in db.query(RightsRecord, target_kind=target_kind, target_id=target_id) if r.withdrawn_at is None),
        key=lambda r: r.created_at,
    )


def effective_rights(db: Database, target_kind: str, target_id: str) -> EffectiveRights:
    """Every live record from the library down to the target, combined tighten-only."""
    return combine([record for kind, tid in chain(db, target_kind, target_id) for record in records_on(db, kind, tid)])


class RightsSetParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_kind: RightsTarget
    target_id: str = LIBRARY_TARGET
    holders: list[str] = Field(default_factory=list)
    consent: Optional[dict[str, Any]] = None
    #: Capped: it goes into the audit chain, which nothing can purge. A reference to the
    #: agreement, never the rights-holder's own words.
    conditions: Optional[str] = Field(default=None, max_length=500)
    labels: list[str] = Field(default_factory=list)
    restricted: bool = False
    readers: list[str] = Field(default_factory=list)
    model_use: Optional[ModelUse] = None


def _invert_rights_set(before, after, ctx: ActionContext):
    record_id = (after or {}).get("record_id")
    return ("rights.withdraw", {"record_id": record_id}) if record_id else None


def _rights_record_for(db: Database, params: RightsSetParams, target_kind: str, target_id: str, ctx: ActionContext) -> RightsRecord:
    """The record `rights.set` would write on this target, refused in words if it may not be (nothing is saved): shared by the
    one-target and the many-target actions, so a bulk set cannot be a way around any rule."""
    links = chain(db, target_kind, target_id)  # 404s a target that does not exist
    if params.restricted and not params.readers:
        raise HTTPException(
            status_code=422,
            detail="a restricted record names the people who may see it; with nobody named, nobody could",
        )
    if params.restricted:
        from fichero_server.security import authz

        setter = authz.resolve_user(ctx.actor)
        if setter is not None and setter.id not in params.readers:
            # Never silently add the author: they may mean to hand the material over.
            raise HTTPException(
                status_code=422,
                detail=(
                    f"this restriction does not name you ({setter.username}), so it would lock you out of "
                    f"the {target_kind} you are restricting; add your own account to the readers, or ask "
                    "one of the people named to set it"
                ),
            )
    if params.model_use is not None:
        above = combine([r for kind, tid in links[:-1] for r in records_on(db, kind, tid)])
        if above.model_use is not None and MODEL_USE_RANK[params.model_use.value] > MODEL_USE_RANK[above.model_use]:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"a record may only tighten: above this {target_kind} the rights say "
                    f"{above.model_use!r}, and {params.model_use.value!r} would loosen it"
                ),
            )
    return RightsRecord(
        target_kind=target_kind,
        target_id=target_id,
        holders=params.holders,
        consent=params.consent,
        conditions=params.conditions,
        labels=params.labels,
        restricted=params.restricted,
        readers=params.readers,
        model_use=params.model_use.value if params.model_use else None,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
    )


@action("rights.set", RightsSetParams, domains=["rights"], undoable=True, invert=_invert_rights_set)
def _action_rights_set(db: Database, params: RightsSetParams, ctx: ActionContext):
    """Attach a rights and consent record (`source.rights.record`)."""
    target_kind = params.target_kind.value
    target_id = LIBRARY_TARGET if target_kind == RightsTarget.library.value else params.target_id
    record = _rights_record_for(db, params, target_kind, target_id, ctx)
    db.save(record)
    spec = ChangeSpec(
        domains=["rights"], target_ids=[record.id], before=None,
        after={"record_id": record.id, "target_kind": target_kind, "target_id": target_id},
        emit_type="rights.set",
    )
    return {"record_id": record.id}, spec


class RightsTargetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: RightsTarget
    id: str


class RightsSetManyParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    targets: list[RightsTargetRef] = Field(min_length=1, max_length=500, description="the segments, documents or folders the same record is set on")
    holders: list[str] = Field(default_factory=list)
    consent: Optional[dict[str, Any]] = None
    conditions: Optional[str] = Field(default=None, max_length=500)
    labels: list[str] = Field(default_factory=list)
    restricted: bool = False
    readers: list[str] = Field(default_factory=list)
    model_use: Optional[ModelUse] = None


def _invert_rights_set_many(before, after, ctx: ActionContext):
    ids = (after or {}).get("record_ids")
    return ("rights.withdraw_many", {"record_ids": ids}) if ids else None


@action("rights.set_many", RightsSetManyParams, domains=["rights"], undoable=True, invert=_invert_rights_set_many)
def _action_rights_set_many(db: Database, params: RightsSetManyParams, ctx: ActionContext):
    """The same rights record on each of several targets: ONE audit row, ONE undo step, all or nothing (every target is checked,
    by the rules `rights.set` applies, before any record is written). Each target keeps its other records."""
    single = RightsSetParams(target_kind=RightsTarget.segment, **params.model_dump(exclude={"targets"}))
    seen: set[tuple[str, str]] = set()
    records = []
    for target in params.targets:
        key = (target.kind.value, target.id)
        if key in seen:
            raise HTTPException(status_code=422, detail=f"{target.kind.value} {target.id!r} is named twice in one bulk edit")
        seen.add(key)
        target_id = LIBRARY_TARGET if target.kind == RightsTarget.library else target.id
        records.append(_rights_record_for(db, single, target.kind.value, target_id, ctx))
    db.save_many(records)
    ids = [r.id for r in records]
    spec = ChangeSpec(domains=["rights"], target_ids=ids, before=None,
                      after={"record_ids": ids, "targets": [{"kind": k, "id": i} for k, i in sorted(seen)]},
                      emit_type="rights.set")
    return {"record_ids": ids}, spec


class RightsRecordIdsParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_ids: list[str] = Field(min_length=1, max_length=500)


def _records(db: Database, ids: list[str]) -> list[RightsRecord]:
    found = []
    for record_id in dict.fromkeys(ids):
        record = db.get(RightsRecord, record_id)
        if record is None:
            raise HTTPException(status_code=404, detail=f"Rights record not found: {record_id}")
        found.append(record)
    return found


@action("rights.withdraw_many", RightsRecordIdsParams, domains=["rights"], undoable=True,
        invert=lambda before, after, ctx: ("rights.restore_many", {"record_ids": after["record_ids"]}) if (after or {}).get("record_ids") else None)
def _action_rights_withdraw_many(db: Database, params: RightsRecordIdsParams, ctx: ActionContext):
    """The inverse of `rights.set_many`: withdraw several records in one audited step (all found first, then all written)."""
    records = _records(db, params.record_ids)
    now = utc_now()
    for record in records:
        record.withdrawn_at = now
    db.save_many(records)
    ids = [r.id for r in records]
    return {"record_ids": ids, "withdrawn": True}, ChangeSpec(
        domains=["rights"], target_ids=ids, before={"record_ids": ids, "withdrawn": False},
        after={"record_ids": ids, "withdrawn": True}, emit_type="rights.withdrawn")


@action("rights.restore_many", RightsRecordIdsParams, domains=["rights"], undoable=False)
def _action_rights_restore_many(db: Database, params: RightsRecordIdsParams, ctx: ActionContext):
    records = _records(db, params.record_ids)
    for record in records:
        record.withdrawn_at = None
    db.save_many(records)
    ids = [r.id for r in records]
    return {"record_ids": ids, "withdrawn": False}, ChangeSpec(
        domains=["rights"], target_ids=ids, before={"record_ids": ids, "withdrawn": True},
        after={"record_ids": ids, "withdrawn": False}, emit_type="rights.set")


class RightsRecordIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str


def _invert_rights_withdraw(before, after, ctx: ActionContext):
    record_id = (after or {}).get("record_id")
    return ("rights.restore", {"record_id": record_id}) if record_id else None


@action("rights.withdraw", RightsRecordIdParams, domains=["rights"], undoable=True, invert=_invert_rights_withdraw)
def _action_rights_withdraw(db: Database, params: RightsRecordIdParams, ctx: ActionContext):
    record = db.get(RightsRecord, params.record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Rights record not found: {params.record_id}")
    record.withdrawn_at = utc_now()
    db.save(record)
    spec = ChangeSpec(
        domains=["rights"], target_ids=[record.id],
        before={"record_id": record.id, "withdrawn": False},
        after={"record_id": record.id, "withdrawn": True},
        emit_type="rights.withdrawn",
    )
    return {"record_id": record.id, "withdrawn": True}, spec


@action("rights.restore", RightsRecordIdParams, domains=["rights"], undoable=False)
def _action_rights_restore(db: Database, params: RightsRecordIdParams, ctx: ActionContext):
    record = db.get(RightsRecord, params.record_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Rights record not found: {params.record_id}")
    record.withdrawn_at = None
    db.save(record)
    spec = ChangeSpec(
        domains=["rights"], target_ids=[record.id],
        before={"record_id": record.id, "withdrawn": True},
        after={"record_id": record.id, "withdrawn": False},
        emit_type="rights.set",
    )
    return {"record_id": record.id, "withdrawn": False}, spec


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class RightsAnswer(BaseModel):
    ok: bool
    result: dict[str, Any]
    audit_id: Optional[str] = None


@router.post("", response_model=RightsAnswer)
async def set_rights(
    body: RightsSetParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RightsAnswer:
    result = registry.invoke(db, "rights.set", body.model_dump(mode="json"), ctx)
    return RightsAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


@router.post("/many", response_model=RightsAnswer)
async def set_rights_many(
    body: RightsSetManyParams,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RightsAnswer:
    """The same record on several targets (the Inspector's multi-selection): one audit id, one undo, all or nothing."""
    result = registry.invoke(db, "rights.set_many", body.model_dump(mode="json"), ctx)
    return RightsAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


@router.post("/{record_id}/withdraw", response_model=RightsAnswer)
async def withdraw_rights(
    record_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> RightsAnswer:
    result = registry.invoke(db, "rights.withdraw", {"record_id": record_id}, ctx)
    return RightsAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


class EffectiveRightsResponse(BaseModel):
    target_kind: str
    target_id: str
    restricted: bool
    #: None when unrestricted (the permission layer alone decides); otherwise the accounts named.
    readers: Optional[list[str]] = None
    model_use: Optional[str] = None
    labels: list[str]
    #: The live records that contributed, from the library down.
    records: list[RightsRecord]


@router.get("/effective", response_model=EffectiveRightsResponse)
async def get_effective_rights(
    target_kind: RightsTarget = Query(...),
    target_id: str = Query(LIBRARY_TARGET),
    db: Database = Depends(get_library_database),
) -> EffectiveRightsResponse:
    """What applies to a target: every record above it, combined tighten-only."""
    kind = target_kind.value
    if kind != RightsTarget.library.value and target_id == LIBRARY_TARGET:
        # Asked of a document, folder or segment without naming it (`openapi.mcp.refusals-in-words`): it was
        # looked up as the id "library" and refused as "Document not found: library".
        raise HTTPException(status_code=422, detail=f"name the {kind} whose rights you want: target_id is "
                                                    f"required unless target_kind is library")
    tid = LIBRARY_TARGET if kind == RightsTarget.library.value else target_id
    effective = effective_rights(db, kind, tid)
    by_id = {r.id: r for k, t in chain(db, kind, tid) for r in records_on(db, k, t)}
    return EffectiveRightsResponse(
        target_kind=kind, target_id=tid, restricted=effective.restricted,
        readers=sorted(effective.readers) if effective.readers is not None else None,
        model_use=effective.model_use, labels=effective.labels,
        records=[by_id[i] for i in effective.record_ids],
    )
