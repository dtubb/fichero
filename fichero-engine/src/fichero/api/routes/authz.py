"""Library ACL snapshot + membership routes for the Settings / inspector UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError

from fichero import authz
from fichero.actions import ActionContext, registry
from fichero.app_db import get_app_db
from fichero.api.auth import action_context
from fichero.api.library_header import require_library_path
from fichero.api.main import get_library_database_for_write
from fichero.db import Database
from fichero.models import (
    LibraryAuthzSnapshot,
    LibraryMember,
    LibraryMembersResponse,
    SetLibraryRoleRequest,
)

router = APIRouter(prefix="/authz", tags=["authz"])


@router.get("/library", response_model=LibraryAuthzSnapshot)
def get_library_authz_snapshot(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
    target_id: str | None = None,
) -> LibraryAuthzSnapshot:
    """Return the current library's ACL state for the logged-in user."""
    app_db = get_app_db()
    resolved_user = authz.resolve_user(getattr(getattr(request, "state", None), "user", None))
    current_user_role = None
    if resolved_user is not None:
        role = app_db.get_library_role(resolved_user.id, x_fichero_library_path)
        current_user_role = role.role if role else None

    can_manage_roles = authz.multiuser_enabled() and current_user_role == authz.ROLE_OWNER

    roles = app_db.list_library_roles(x_fichero_library_path) if can_manage_roles else []
    target_can_read = authz.can_read(
        getattr(getattr(request, "state", None), "user", None),
        x_fichero_library_path,
        target_id,
    )
    target_can_write = authz.can_write(
        getattr(getattr(request, "state", None), "user", None),
        x_fichero_library_path,
        target_id,
    )

    return LibraryAuthzSnapshot(
        library_path=x_fichero_library_path,
        multiuser_enabled=authz.multiuser_enabled(),
        can_manage_roles=can_manage_roles,
        current_user_id=resolved_user.id if resolved_user is not None else None,
        current_user_role=current_user_role,
        target_id=target_id,
        target_can_read=target_can_read,
        target_can_write=target_can_write,
        roles=roles,
    )


@router.get("/members", response_model=LibraryMembersResponse)
def list_library_members(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
) -> LibraryMembersResponse:
    """Who can access this library, roles joined with account profiles.

    Owner-gated when multi-user is on (mirrors the snapshot's ``can_manage_roles``).
    The ``roles`` table keys on the *normalized* library path, so normalize the
    transport header before the lookup or the join silently returns empty.
    """
    app_db = get_app_db()
    session_user = getattr(getattr(request, "state", None), "user", None)
    library_path = authz.normalize_library_path(x_fichero_library_path) or x_fichero_library_path

    if authz.multiuser_enabled():
        try:
            authz.require_owner(session_user, library_path)
        except authz.AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc

    users_by_id = {user.id: user for user in app_db.list_users()}
    members: list[LibraryMember] = []
    for role in app_db.list_library_roles(library_path):
        user = users_by_id.get(role.user_id)
        members.append(
            LibraryMember(
                user_id=role.user_id,
                username=user.username if user else role.user_id,
                display_name=user.display_name if user else role.user_id,
                is_owner_account=bool(user.is_owner) if user else False,
                role=role.role,
            )
        )

    return LibraryMembersResponse(
        library_path=library_path,
        members=members,
        count=len(members),
    )


@router.put("/members", response_model=LibraryMembersResponse)
def set_library_member_role(
    body: SetLibraryRoleRequest,
    request: Request,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
    x_fichero_library_path: str = Depends(require_library_path),
) -> LibraryMembersResponse:
    """Assign/change a library role — typed surface over the ``acl.set`` action.

    Routes through ``registry.invoke`` so the mutation is owner-gated, audited,
    and emitted on the change stream exactly like ``POST /api/actions/invoke``.
    Returns the refreshed member list so the UI updates in one round-trip.
    """
    try:
        registry.invoke(db, "acl.set", body.model_dump(), ctx)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except authz.AuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return list_library_members(request, x_fichero_library_path)
