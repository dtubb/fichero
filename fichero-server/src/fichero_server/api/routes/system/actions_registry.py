"""Generic action-registry endpoints (EPIC #1848 keystone #2013).

Exposes the whole :data:`fichero_server.actions.registry` over HTTP so chat tools
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

Actor: derived from the authenticated request state by ``action_context`` so it
cannot be forged through request bodies or headers.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, model_validator

from fichero_server.api.library_header import optional_library_path, require_library_path
from fichero_server.security import authz
from fichero_server.actions import ActionContext, ActionNotFoundError, ChangeSpec, action, registry
from fichero_server.api.auth import action_context, library_access_denial_payload
from fichero_server.db.app import get_app_db
from fichero_server.api.main import (
    LibraryAccessDeniedError,
    get_library_database,
    get_library_database_for_write,
)
from fichero_server.db import Database
from fichero_server.models import ActionAudit

router = APIRouter(prefix="/actions", tags=["actions"])


# =============================================================================
# Request / response models
# =============================================================================


class InvokeActionRequest(BaseModel):
    name: str = Field(description="Registered action name, '<domain>.<verb>'")
    params: dict = Field(default_factory=dict, description="Raw action params")
    run_id: str | None = Field(default=None, description="AI run id, if any (#1832)")

    # SECURITY: actor and origin_window are NOT accepted from the request body.
    # The actor is derived from the authenticated session (action_context dependency)
    # and cannot be forged. Reject any request that tries to set them (#3285).
    actor: str | None = Field(
        default=None,
        description="DEPRECATED — rejected if set. Actor comes from the authenticated session.",
        exclude=True,
    )
    origin_window: str | None = Field(
        default=None,
        description="DEPRECATED — rejected if set. Use X-Fichero-Origin-Window header.",
        exclude=True,
    )

    @model_validator(mode="after")
    def reject_deprecated_fields(self) -> "InvokeActionRequest":
        """Reject actor/origin_window in the body — they must come from auth headers."""
        if self.actor is not None:
            raise ValueError(
                "actor must not be set in the request body; "
                "it is derived from the authenticated session"
            )
        if self.origin_window is not None:
            raise ValueError(
                "origin_window must not be set in the request body; "
                "use the X-Fichero-Origin-Window header instead"
            )
        return self


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
    client: str | None = Field(
        default=None,
        description="Client surface that invoked the action (X-Fichero-Client), e.g. fichero-mcp (#4469).",
    )
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


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/invoke", response_model=ActionResultResponse)
async def invoke_action(
    body: InvokeActionRequest,
    http_request: Request,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> ActionResultResponse:
    """Validate + run a registered action through the audited choke point."""
    ctx.run_id = body.run_id
    try:
        result = registry.invoke(db, body.name, body.params, ctx)
    except ActionNotFoundError:
        raise HTTPException(status_code=404, detail=f"Unknown action: {body.name}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except authz.AuthorizationError as exc:
        raise LibraryAccessDeniedError(
            library_access_denial_payload(
                request=http_request,
                library_path=ctx.library_path or "",
                required="write",
                detail=str(exc),
            )
        ) from exc
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


def _refresh_replay_expected_versions(params: dict, after: dict | None) -> dict:
    """Freshen any optimistic-concurrency token(s) in a redo's replayed
    params using the CURRENT state the undo's OWN execution just recorded
    (#4957: "redo is the inverse of the inverse, worked out from the undo's
    own `after`, never a replay of recorded params").

    Redo replays the ORIGINAL forward action by name, but that action's
    recorded ``expected_version``/``expected_versions`` are however-old they
    were when it first ran. "Versions only go up" (the constitution segments
    hold to): the undo itself bumped the version at least once since then,
    so a byte-for-byte replay of the recorded params is refused as stale
    even with no other writer in between. ``after`` is the ``ChangeSpec``
    the undo action's OWN ``execute`` returned -- always the freshest known
    state, because versions only go up -- so it, not the ancient recorded
    params, is the source of truth for what to compare against. A
    genuinely stale redo (another writer touched the row after the undo)
    still compares the invoked action's live row against this refreshed
    value and is still correctly refused.

    Convention-keyed, not per-action: only ``expected_version``/
    ``expected_versions`` params paired with an ``after`` carrying
    ``version``/``versions`` are touched, so actions with no such field
    (create/delete/merge/etc., identified purely by id) pass through
    unchanged.
    """
    if not after or not isinstance(params, dict):
        return params
    refreshed = dict(params)
    current_version = after.get("version")
    if "expected_version" in refreshed and isinstance(current_version, int):
        refreshed["expected_version"] = current_version
    current_versions = after.get("versions")
    if "expected_versions" in refreshed and isinstance(current_versions, dict):
        merged = dict(refreshed["expected_versions"])
        for target_id, version in current_versions.items():
            if target_id in merged:
                merged[target_id] = version
        refreshed["expected_versions"] = merged
    return refreshed


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
    x_fichero_library_path: str = Depends(require_library_path),
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
            client=a.client,
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
    request: Request,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
    x_fichero_library_path: str | None = Depends(optional_library_path),
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
    * **Undo an inverse / redo** (``inverse_of`` set): by default, replay the
      ORIGINAL forward action's ``action_name``, with its recorded ``params``
      freshened by :func:`_refresh_replay_expected_versions` (#4957) so a
      versioned action's ``expected_version``/``expected_versions`` compare
      against the state the undo just left, not the value recorded back when
      the action first ran. No per-action redo logic and no need for inverse
      actions (restore/unmerge/unsplit/uncarry) to be independently
      ``undoable``. When THIS row's own action opts in via
      ``redo_via_own_invert`` (segment actions that mint a new id/row on a
      plain replay), undo it through its OWN ``invert(before, after, ctx)``
      instead — see :attr:`fichero_server.actions.registry.ActionRegistration.redo_via_own_invert`.
    """
    audit = db.get(ActionAudit, audit_id)
    if audit is None:
        raise HTTPException(
            status_code=404, detail=f"Audit record not found: {audit_id}"
        )
    if audit.undone:
        raise HTTPException(status_code=409, detail="This action was already undone")
    if not isinstance(ctx, ActionContext):
        # Direct unit calls bypass FastAPI dependency injection.
        ctx = ActionContext(
            actor="system",
            origin_window=x_fichero_origin_window,
            library_path=x_fichero_library_path,
        )

    if audit.inverse_of is not None:
        # Redo: this row is an inverse. Two strategies, per THIS row's OWN
        # action registration (#4957):
        acting_reg = None
        try:
            acting_reg = registry.get(audit.action_name)
        except ActionNotFoundError:
            pass
        if acting_reg is not None and acting_reg.redo_via_own_invert and acting_reg.invert is not None:
            # Opt-in (segment actions that MINT a new id/row on a plain
            # replay -- create, merge, split, carry, pass_create's inverse
            # pass_delete, match_propose): undo THIS row through its OWN
            # invert, computed from ITS OWN recorded `after`, never from an
            # earlier row's now-stale params. This is what makes redoing a
            # create come back as an undelete of the SAME id, and what stops
            # a second undo of a redone merge/split/carry from acting on
            # ids/versions an intervening redo already replaced.
            derived = acting_reg.invert(audit.before, audit.after, ctx)
            if derived is None:
                raise HTTPException(
                    status_code=409, detail="Action did not yield a redo to apply"
                )
            replay_name, replay_params = derived
        else:
            # Default: replay the ORIGINAL forward action's action_name, with
            # its recorded params freshened by
            # `_refresh_replay_expected_versions` (#4957) so a versioned
            # action's `expected_version`/`expected_versions` compare
            # against the state the undo just left, not the value recorded
            # back when the action first ran. Correct for update/delete/
            # undelete/restore_version (traced across arbitrarily many
            # undo/redo laps) and for every non-segment action, with no
            # need for inverse actions (restore/unmerge/unsplit/uncarry) to
            # be independently `undoable`.
            original = db.get(ActionAudit, audit.inverse_of)
            if original is None:
                raise HTTPException(
                    status_code=409,
                    detail=f"Original audit gone, cannot redo: {audit.inverse_of}",
                )
            replay_name = original.action_name
            replay_params = _refresh_replay_expected_versions(original.params, audit.after)
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
        result = registry.invoke(
            db, replay_name, replay_params, ctx, inverse_of=audit.id
        )
    except ActionNotFoundError:
        raise HTTPException(
            status_code=409, detail=f"Inverse/replay action unknown: {replay_name}"
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except authz.AuthorizationError as exc:
        raise LibraryAccessDeniedError(
            library_access_denial_payload(
                request=request,
                library_path=ctx.library_path or "",
                required="write",
                detail=str(exc),
            )
        ) from exc

    audit.undone = True
    db.save(audit)

    return ActionResultResponse(
        ok=result.ok,
        result=result.result,
        audit_id=result.audit_id,
        changed_domains=result.changed_domains,
    )


# =============================================================================
# ACL management action (#2024)
# =============================================================================


class AclSetParams(BaseModel):
    user: str = Field(description="Target user id or username")
    role: str | None = Field(default=None, description="owner/editor/viewer")
    target_id: str | None = Field(default=None, description="Folder/file id override")
    effect: str | None = Field(default=None, description="grant/deny override")
    remove: bool = Field(
        default=False,
        description="Revoke: remove the user's whole-library role (fail-closed)",
    )


def _invert_acl_set(
    before: dict | None, after: dict | None, ctx: ActionContext
) -> tuple[str, dict] | None:
    if not before or (after and "override" in after):
        return None
    role_before = before.get("role")
    user_id = before.get("user_id")
    if not user_id:
        return None
    if role_before is None:
        return ("acl.set", {"user": user_id, "remove": True})
    return ("acl.set", {"user": user_id, "role": role_before})


@action("acl.set", AclSetParams, domains=["authz"], undoable=True, invert=_invert_acl_set)
def _acl_set(_db: Database, params: AclSetParams, ctx: ActionContext):
    """Owner-only ACL mutation through the shared registry write path."""
    resolved = authz.resolve_user(params.user)
    if resolved is None:
        raise ValueError("unknown user or library")
    library_path = authz.normalize_library_path(ctx.library_path)
    if library_path is None:
        raise ValueError("unknown user or library")
    existing_role = get_app_db().get_library_role(resolved.id, library_path)
    before = {
        "user_id": resolved.id,
        "role": existing_role.role if existing_role is not None else None,
    }
    changes: dict[str, Any] = {"user": params.user}
    target_ids: list[str] = []

    if params.remove:
        # Revoke = drop the whole-library role. Overrides are subtree-scoped and
        # out of scope here; a role-less user is denied by the fail-closed
        # choke point. Owner-gated inside authz.remove_role.
        authz.remove_role(
            actor=ctx.actor,
            library=ctx.library_path,
            user=params.user,
        )
        changes["removed_role"] = True
        return (
            changes,
            ChangeSpec(
                domains=["authz"],
                target_ids=target_ids,
                before=before,
                after=changes,
                emit_type="authz.changed",
            ),
        )

    if params.role is not None:
        role = authz.set_role(
            actor=ctx.actor,
            library=ctx.library_path,
            user=params.user,
            role=params.role,
        )
        changes["role"] = role.model_dump(mode="json")

    if params.target_id is not None or params.effect is not None:
        if not params.target_id or not params.effect:
            raise ValueError("target_id and effect must be provided together")
        override = authz.set_override(
            actor=ctx.actor,
            library=ctx.library_path,
            user=params.user,
            target_id=params.target_id,
            effect=params.effect,
        )
        changes["override"] = override.model_dump(mode="json")
        target_ids.append(params.target_id)

    if params.role is None and params.effect is None:
        raise ValueError("role or override effect is required")

    return (
        changes,
        ChangeSpec(
            domains=["authz"],
            target_ids=target_ids,
            before=before,
            after=changes,
            emit_type="authz.changed",
        ),
    )
