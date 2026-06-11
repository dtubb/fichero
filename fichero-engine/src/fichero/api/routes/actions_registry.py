"""Generic action-registry endpoints (EPIC #1848 keystone #2013).

Exposes the whole :data:`fichero.actions.registry` over HTTP so chat tools
(#1847), App Intents (#1837), and UI-action tests all drive the SAME audited
choke point:

  * ``POST /api/actions/invoke``  — run any registered action by name.
  * ``GET  /api/actions/registry`` — list registered actions + their param schemas.
  * ``GET  /api/actions/audit``   — recent audit log (newest first) for the undo stack.
  * ``POST /api/actions/audit/{audit_id}/undo`` — reverse an undoable action (or
    redo, when the target audit is itself an inverse).

Path note: ``/api/actions`` (no suffix) and ``/api/actions/{action_id}`` are
already owned by the Action *Library* router (``routes/actions.py``). To avoid
clobbering it (constitution: iterate-not-replace), the registry listing lives at
``/api/actions/registry`` rather than ``GET /api/actions``, and this router is
registered BEFORE ``actions.router`` so its static paths win over the library's
``/{action_id}`` dynamic segment.

Actor: derived from the request body (``actor``) for now, defaulting to ``"ui"``;
a real user/device id arrives with multi-user (#1844).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from fichero.actions import ActionContext, ActionNotFoundError, registry
from fichero.api.main import get_library_database
from fichero.db import Database
from fichero.models import ActionAudit

router = APIRouter(prefix="/actions", tags=["actions"])


# =============================================================================
# Request / response models
# =============================================================================


class InvokeActionRequest(BaseModel):
    name: str = Field(description="Registered action name, '<domain>.<verb>'")
    params: dict = Field(default_factory=dict, description="Raw action params")
    origin_window: str | None = Field(
        default=None, description="Self-echo de-dup seam for the change stream"
    )
    actor: str | None = Field(default=None, description="Override actor; defaults to 'ui'")
    run_id: str | None = Field(default=None, description="AI run id, if any (#1832)")


class ActionResultResponse(BaseModel):
    ok: bool
    result: Any
    audit_id: str
    changed_domains: list[str]


class RegisteredActionInfo(BaseModel):
    name: str
    undoable: bool
    domains: list[str]
    params_schema: dict


class RegisteredActionsResponse(BaseModel):
    items: list[RegisteredActionInfo]
    count: int


class AuditLogEntry(BaseModel):
    """One row of the audit log, shaped for the UI/undo stack."""

    id: str
    action_name: str
    actor: str
    target_ids: list[str]
    created_at: str
    undone: bool
    inverse_of: str | None = None
    undoable: bool = Field(
        description="Whether this row can be reversed (or, if itself an inverse, redone)."
    )


class AuditLogResponse(BaseModel):
    items: list[AuditLogEntry]
    count: int


def _ctx(
    request: InvokeActionRequest,
    library_path: str,
    header_origin_window: str | None,
) -> ActionContext:
    return ActionContext(
        actor=request.actor or "ui",
        origin_window=request.origin_window or header_origin_window,
        run_id=request.run_id,
        library_path=library_path,
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/invoke", response_model=ActionResultResponse)
async def invoke_action(
    request: InvokeActionRequest,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> ActionResultResponse:
    """Validate + run a registered action through the audited choke point."""
    ctx = _ctx(request, x_fichero_library_path, x_fichero_origin_window)
    try:
        result = registry.invoke(db, request.name, request.params, ctx)
    except ActionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown action: {request.name}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    return ActionResultResponse(
        ok=result.ok,
        result=result.result,
        audit_id=result.audit_id,
        changed_domains=result.changed_domains,
    )


@router.get("/registry", response_model=RegisteredActionsResponse)
async def list_registered_actions() -> RegisteredActionsResponse:
    """List every registered action + its param JSON schema.

    This is what chat tools (#1847) and App Intents (#1837) read to build their
    tool/intent definitions from the single registry.
    """
    items = [
        RegisteredActionInfo(
            name=reg.name,
            undoable=reg.undoable,
            domains=list(reg.domains),
            params_schema=reg.params_model.model_json_schema(),
        )
        for reg in registry.all()
    ]
    return RegisteredActionsResponse(items=items, count=len(items))


def _audit_is_reversible(audit: ActionAudit) -> bool:
    """Can this audit row be reversed (forward → undo) or redone (inverse → replay)?

    An inverse row (``inverse_of`` set) is always reversible while not yet undone —
    undoing it replays the original forward action. A forward row is reversible iff
    its action is still registered, ``undoable``, and has an ``invert``.
    """
    if audit.undone:
        return False
    if audit.inverse_of is not None:
        return True
    try:
        reg = registry.get(audit.action_name)
    except ActionNotFoundError:
        return False
    return bool(reg.undoable and reg.invert is not None)


@router.get("/audit", response_model=AuditLogResponse)
async def list_audit_log(
    limit: int = 50,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
) -> AuditLogResponse:
    """Recent action-audit rows, newest first — the UI's undo-stack history.

    ``before``/``after`` payloads are deliberately omitted (they can be large and
    are only needed server-side for inversion); this returns the lightweight
    actor/action/target/timestamp/undone shape the undo stack reads.
    """
    limit = max(1, min(limit, 500))
    rows = sorted(db.all(ActionAudit), key=lambda a: a.created_at, reverse=True)[:limit]
    items = [
        AuditLogEntry(
            id=a.id,
            action_name=a.action_name,
            actor=a.actor,
            target_ids=list(a.target_ids),
            created_at=a.created_at.isoformat(),
            undone=a.undone,
            inverse_of=a.inverse_of,
            undoable=_audit_is_reversible(a),
        )
        for a in rows
    ]
    return AuditLogResponse(items=items, count=len(items))


@router.post("/audit/{audit_id}/undo", response_model=ActionResultResponse)
async def undo_action(
    audit_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> ActionResultResponse:
    """Reverse an action — or redo, when the target audit is itself an inverse.

    Two paths, both registry-driven and both producing a fresh audit row so the
    chain stays reversible indefinitely:

    * **Undo a forward action** (``inverse_of is None``): look the action up in the
      registry, call its ``invert(before, after, ctx) -> (name, params)``, and
      ``invoke`` that inverse, tagged ``inverse_of=this audit`` so it can be redone.
    * **Undo an inverse / redo** (``inverse_of`` set): replay the ORIGINAL forward
      action with its recorded ``action_name`` + ``params``. This is correct for
      *any* action regardless of how its inverse was implemented — no per-action
      redo logic and no need for inverse actions (restore/unmerge) to be
      independently ``undoable``.
    """
    audit = db.get(ActionAudit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"Audit record not found: {audit_id}")
    if audit.undone:
        raise HTTPException(status_code=409, detail="This action was already undone")

    ctx = ActionContext(
        actor="ui",
        origin_window=x_fichero_origin_window,
        library_path=x_fichero_library_path,
    )

    if audit.inverse_of is not None:
        # Redo: this row is an inverse → replay the original forward action.
        original = db.get(ActionAudit, audit.inverse_of)
        if original is None:
            raise HTTPException(
                status_code=409,
                detail=f"Original audit gone, cannot redo: {audit.inverse_of}",
            )
        replay_name, replay_params = original.action_name, original.params
    else:
        # Undo: derive the inverse action from the forward action's invert().
        try:
            reg = registry.get(audit.action_name)
        except ActionNotFoundError:
            raise HTTPException(
                status_code=409,
                detail=f"Action no longer registered: {audit.action_name}",
            )
        if not reg.undoable or reg.invert is None:
            raise HTTPException(
                status_code=409, detail=f"Action is not undoable: {audit.action_name}"
            )
        inverse = reg.invert(audit.before, audit.after, ctx)
        if inverse is None:
            raise HTTPException(
                status_code=409, detail="Action did not yield an inverse to apply"
            )
        replay_name, replay_params = inverse

    try:
        result = registry.invoke(db, replay_name, replay_params, ctx, inverse_of=audit.id)
    except ActionNotFoundError:
        raise HTTPException(
            status_code=409, detail=f"Inverse/replay action unknown: {replay_name}"
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    audit.undone = True
    db.save(audit)

    return ActionResultResponse(
        ok=result.ok,
        result=result.result,
        audit_id=result.audit_id,
        changed_domains=result.changed_domains,
    )
