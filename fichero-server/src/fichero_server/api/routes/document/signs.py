"""Declared signs: the project's sign list, and every instance of a sign (slice 14, #4939).

Spec: `languages-scripts-signs.md` (`source.sign.*`). The record is `models/signs.py`.

Writes are audited, undoable actions (`sign.declare`, `sign.withdraw`), so the command line and
MCP can do what the app does. Reads: the sign list (`source.sign.project-list`, exportable as
it is) and one sign's instances (`source.sign.gather-instances`): every reading whose text uses
the sign's code point, found by ONE query, not by reading the project page by page.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.actions.registry import ActionContext, ChangeSpec, action, registry
from fichero_server.api.auth import action_context
from fichero_server.api.main import get_library_database, get_library_database_for_write
from fichero_server.api.routes.document.segments import provenance_kind_from_ctx
from fichero_server.core.timeutil import utc_now
from fichero_server.db import Database
from fichero_server.models import Segment
from fichero_server.models.segments import assert_not_provisional
from fichero_server.models.signs import DeclaredSign, SignListReference, code_point_char

router = APIRouter(prefix="/signs")


class SignDeclareParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    picture_segment_id: str
    code_point: Optional[str] = None
    list_references: list[SignListReference] = Field(default_factory=list)
    variant_of: Optional[str] = None
    variant: Optional[str] = None
    #: Capped: it goes into the audit chain, which nothing can purge.
    notes: Optional[str] = Field(default=None, max_length=500)


def _live_sign_with(db: Database, code_point: str) -> DeclaredSign | None:
    return next(
        (s for s in db.query(DeclaredSign, code_point=code_point) if s.deleted_at is None), None
    )


def _invert_sign_declare(before, after, ctx: ActionContext):
    sign_id = (after or {}).get("sign_id")
    return ("sign.withdraw", {"sign_id": sign_id}) if sign_id else None


@action(
    "sign.declare",
    SignDeclareParams,
    domains=["sign"],
    undoable=True,
    invert=_invert_sign_declare,
)
def _action_sign_declare(db: Database, params: SignDeclareParams, ctx: ActionContext):
    """Declare a sign from the page it was met on (`source.sign.declared`)."""
    assert_not_provisional(params.picture_segment_id, what="picture_segment_id")
    if db.get(Segment, params.picture_segment_id) is None:
        raise HTTPException(status_code=404, detail=f"Segment not found: {params.picture_segment_id}")
    probe = DeclaredSign(name=params.name, picture_segment_id=params.picture_segment_id,
                         code_point=params.code_point)
    if probe.code_point is not None:
        existing = _live_sign_with(db, probe.code_point)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{probe.code_point} is already the declared sign {existing.name!r} "
                    f"({existing.id}); a code point names one sign in a project"
                ),
            )
    if (params.variant is None) != (params.variant_of is None):
        raise HTTPException(
            status_code=422,
            detail="a variant names both the character it is a variant of and which variant",
        )
    sign = DeclaredSign(
        name=params.name,
        picture_segment_id=params.picture_segment_id,
        code_point=probe.code_point,
        list_references=[ref.model_dump() for ref in params.list_references],
        variant_of=params.variant_of,
        variant=params.variant,
        notes=params.notes,
        provenance_kind=provenance_kind_from_ctx(ctx),
        created_by=ctx.actor or None,
    )
    db.save(sign)
    spec = ChangeSpec(
        domains=["sign"],
        target_ids=[sign.id],
        before=None,
        after={"sign_id": sign.id, "code_point": sign.code_point},
        emit_type="sign.declared",
    )
    return {"sign_id": sign.id, "code_point": sign.code_point}, spec


class SignIdParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sign_id: str


def _invert_sign_withdraw(before, after, ctx: ActionContext):
    sign_id = (after or {}).get("sign_id")
    return ("sign.restore", {"sign_id": sign_id}) if sign_id else None


@action(
    "sign.withdraw",
    SignIdParams,
    domains=["sign"],
    undoable=True,
    invert=_invert_sign_withdraw,
)
def _action_sign_withdraw(db: Database, params: SignIdParams, ctx: ActionContext):
    """Withdraw a sign. Soft: readings that use its code point are untouched, and the record
    stays resolvable in the audit trail."""
    sign = db.get(DeclaredSign, params.sign_id)
    if sign is None:
        raise HTTPException(status_code=404, detail=f"Sign not found: {params.sign_id}")
    sign.deleted_at = utc_now()
    db.save(sign)
    spec = ChangeSpec(
        domains=["sign"], target_ids=[sign.id],
        before={"sign_id": sign.id, "withdrawn": False},
        after={"sign_id": sign.id, "withdrawn": True},
        emit_type="sign.withdrawn",
    )
    return {"sign_id": sign.id, "withdrawn": True}, spec


@action("sign.restore", SignIdParams, domains=["sign"], undoable=False)
def _action_sign_restore(db: Database, params: SignIdParams, ctx: ActionContext):
    sign = db.get(DeclaredSign, params.sign_id)
    if sign is None:
        raise HTTPException(status_code=404, detail=f"Sign not found: {params.sign_id}")
    if sign.code_point is not None:
        other = _live_sign_with(db, sign.code_point)
        if other is not None and other.id != sign.id:
            raise HTTPException(
                status_code=409,
                detail=f"{sign.code_point} was declared again as {other.name!r} ({other.id}) meanwhile",
            )
    sign.deleted_at = None
    db.save(sign)
    spec = ChangeSpec(
        domains=["sign"], target_ids=[sign.id],
        before={"sign_id": sign.id, "withdrawn": True},
        after={"sign_id": sign.id, "withdrawn": False},
        emit_type="sign.declared",
    )
    return {"sign_id": sign.id, "withdrawn": False}, spec


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class SignWrite(SignDeclareParams):
    pass


class ActionAnswer(BaseModel):
    ok: bool
    result: dict[str, Any]
    audit_id: Optional[str] = None


@router.post("", response_model=ActionAnswer)
async def declare_sign(
    body: SignWrite,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ActionAnswer:
    result = registry.invoke(db, "sign.declare", body.model_dump(), ctx)
    return ActionAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


@router.post("/{sign_id}/withdraw", response_model=ActionAnswer)
async def withdraw_sign(
    sign_id: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ActionAnswer:
    result = registry.invoke(db, "sign.withdraw", {"sign_id": sign_id}, ctx)
    return ActionAnswer(ok=result.ok, result=result.result, audit_id=result.audit_id)


class SignListResponse(BaseModel):
    """The project's sign list, as it can be exported and shared (`source.sign.project-list`)."""

    items: list[DeclaredSign]


@router.get("", response_model=SignListResponse)
async def list_signs(db: Database = Depends(get_library_database)) -> SignListResponse:
    items = sorted(
        (s for s in db.all(DeclaredSign) if s.deleted_at is None),
        key=lambda s: (s.code_point or "", s.name),
    )
    return SignListResponse(items=items)


class SignInstance(BaseModel):
    representation_id: str
    segment_id: Optional[str] = None
    document_id: str
    #: How many times the sign occurs in this reading.
    count: int


class SignInstanceListResponse(BaseModel):
    sign_id: str
    code_point: Optional[str] = None
    items: list[SignInstance]
    #: Occurrences across every item, so a caller need not add them up.
    total: int


def sign_instances(db: Database, sign: DeclaredSign) -> list[SignInstance]:
    """Every live reading whose text uses the sign (`source.sign.gather-instances`), by ONE
    query. A sign known only by a sign-list number has no character to find in text, so it
    has no instances here -- those are found by the segments that name it (a later slice)."""
    if sign.code_point is None:
        return []
    ch = code_point_char(sign.code_point)
    rows = db.live_readings_containing(ch)
    return [
        SignInstance(representation_id=r[0], segment_id=r[1], document_id=r[2], count=r[3].count(ch))
        for r in rows
    ]


@router.get("/{sign_id}/instances", response_model=SignInstanceListResponse)
async def list_sign_instances(
    sign_id: str, db: Database = Depends(get_library_database)
) -> SignInstanceListResponse:
    sign = db.get(DeclaredSign, sign_id)
    if sign is None:
        raise HTTPException(status_code=404, detail=f"Sign not found: {sign_id}")
    items = sign_instances(db, sign)
    return SignInstanceListResponse(
        sign_id=sign.id, code_point=sign.code_point, items=items, total=sum(i.count for i in items)
    )
