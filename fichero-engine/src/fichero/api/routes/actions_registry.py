"""Generic action-registry endpoints (EPIC #1848 keystone #2013).

Exposes the whole :data:`fichero.actions.registry` over HTTP so chat tools
(#1847), App Intents (#1837), and UI-action tests all drive the SAME audited
choke point:

  * ``POST /api/actions/invoke``  — run any registered action by name.
  * ``GET  /api/actions/registry`` — list registered actions + their param schemas.
  * ``POST /api/actions/audit/{audit_id}/undo`` — reverse an undoable action.

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


@router.post("/audit/{audit_id}/undo", response_model=ActionResultResponse)
async def undo_action(
    audit_id: str,
    db: Database = Depends(get_library_database),
    x_fichero_library_path: str = Header(..., alias="X-Fichero-Library-Path"),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> ActionResultResponse:
    """Reverse an undoable action by replaying its inverse (itself audited → redo)."""
    audit = db.get(ActionAudit, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail=f"Audit record not found: {audit_id}")
    if audit.undone:
        raise HTTPException(status_code=409, detail="This action was already undone")

    try:
        reg = registry.get(audit.action_name)
    except ActionNotFoundError:
        raise HTTPException(
            status_code=409, detail=f"Action no longer registered: {audit.action_name}"
        )
    if not reg.undoable or reg.invert is None:
        raise HTTPException(
            status_code=409, detail=f"Action is not undoable: {audit.action_name}"
        )

    ctx = ActionContext(
        actor="ui",
        origin_window=x_fichero_origin_window,
        library_path=x_fichero_library_path,
    )
    inverse = reg.invert(audit.before, audit.after, ctx)
    if inverse is None:
        raise HTTPException(
            status_code=409, detail="Action did not yield an inverse to apply"
        )
    inv_name, inv_params = inverse

    try:
        result = registry.invoke(db, inv_name, inv_params, ctx)
    except ActionNotFoundError:
        raise HTTPException(status_code=409, detail=f"Inverse action unknown: {inv_name}")
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
