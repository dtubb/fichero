"""Library ACL snapshot + membership routes for the Settings / inspector UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from fichero.security import authz
from fichero.actions import ActionContext, registry
from fichero.db.app import get_app_db
from fichero.api.auth import action_context, auth_kind_from_request, library_access_denial_payload
from fichero.api.routes.library.registry import get_global_database
from fichero.api.library_header import require_library_path
from fichero.api.main import LibraryAccessDeniedError, get_library_database_for_write
from fichero.db import Database
from fichero.models import (
    AccessibleLibrary,
    KnownLibrary,
    LibraryAuthzSnapshot,
    LibraryMember,
    LibraryMembersResponse,
    SetLibraryRoleRequest,
    ShareRequest,
    ShareResponse,
)

_SHARE_OBJECT_TYPES = {"library", "entity", "document"}

router = APIRouter(prefix="/authz", tags=["authz"])


class AccessibleLibraryListResponse(BaseModel):
    items: list[AccessibleLibrary]
    count: int


@router.get("/libraries", response_model=AccessibleLibraryListResponse)
def list_accessible_libraries(
    request: Request,
    registry_db: Database = Depends(get_global_database),
) -> AccessibleLibraryListResponse:
    """Return the known libraries visible to the current credential."""
    app_db = get_app_db()
    known_libraries = sorted(
        registry_db.all(KnownLibrary),
        key=lambda lib: lib.last_accessed,
        reverse=True,
    )
    if getattr(getattr(request, "state", None), "bootstrap_auth", False):
        items = [
            AccessibleLibrary(
                library_path=authz.normalize_library_path(library.path) or library.path,
                library_name=library.name or library.path.rstrip("/").split("/")[-1],
                role=authz.ROLE_OWNER,
            )
            for library in known_libraries
        ]
        return AccessibleLibraryListResponse(items=items, count=len(items))

    resolved_user = authz.resolve_user(getattr(getattr(request, "state", None), "user", None))
    if resolved_user is None:
        raise HTTPException(status_code=401, detail="session required")

    known_by_path = {
        authz.normalize_library_path(library.path) or library.path: library
        for library in known_libraries
    }
    items: list[AccessibleLibrary] = []
    for role in app_db.list_library_roles_for_user(resolved_user.id):
        library = known_by_path.get(role.library_path)
        library_name = (
            library.name
            if library is not None and library.name
            else role.library_path.rstrip("/").split("/")[-1]
        )
        items.append(
            AccessibleLibrary(
                library_path=role.library_path,
                library_name=library_name,
                role=role.role,
            )
        )
    return AccessibleLibraryListResponse(items=items, count=len(items))


@router.get("/library", response_model=LibraryAuthzSnapshot)
def get_library_authz_snapshot(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
    target_id: str | None = None,
) -> LibraryAuthzSnapshot:
    """Return the current library's ACL state for the logged-in user."""
    app_db = get_app_db()
    # Roles are stored under the NORMALIZED library path, and can_read/can_write
    # normalize internally — so the role lookups here must normalize too, or an
    # owner sending an un-normalized path (trailing slash, symlink) is wrongly
    # shown can_manage_roles=False / roles=[] while target_can_write stays True.
    library_path = authz.normalize_library_path(x_fichero_library_path) or x_fichero_library_path
    auth_kind = auth_kind_from_request(request) or "unknown"
    if getattr(getattr(request, "state", None), "bootstrap_auth", False):
        return LibraryAuthzSnapshot(
            library_path=library_path,
            multiuser_enabled=authz.multiuser_enabled(),
            auth_kind=auth_kind,
            can_manage_roles=True,
            current_user_id=None,
            current_user_role=authz.ROLE_OWNER,
            target_id=target_id,
            target_can_read=True,
            target_can_write=True,
            roles=app_db.list_library_roles(library_path),
        )

    resolved_user = authz.resolve_user(getattr(getattr(request, "state", None), "user", None))
    current_user_role = None
    if resolved_user is not None:
        role = app_db.get_library_role(resolved_user.id, library_path)
        current_user_role = role.role if role else None

    can_manage_roles = authz.multiuser_enabled() and current_user_role == authz.ROLE_OWNER

    roles = app_db.list_library_roles(library_path) if can_manage_roles else []
    target_can_read = authz.can_read(
        getattr(getattr(request, "state", None), "user", None),
        library_path,
        target_id,
    )
    target_can_write = authz.can_write(
        getattr(getattr(request, "state", None), "user", None),
        library_path,
        target_id,
    )

    return LibraryAuthzSnapshot(
        library_path=library_path,
        multiuser_enabled=authz.multiuser_enabled(),
        auth_kind=auth_kind,
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

    if authz.multiuser_enabled() and not getattr(getattr(request, "state", None), "bootstrap_auth", False):
        try:
            authz.require_owner(session_user, library_path)
        except authz.AuthorizationError as exc:
            raise LibraryAccessDeniedError(
                library_access_denial_payload(
                    request,
                    library_path,
                    required="write",
                    detail=str(exc),
                )
            ) from exc

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
        raise LibraryAccessDeniedError(
            library_access_denial_payload(
                request,
                x_fichero_library_path,
                required="write",
                detail=str(exc),
            )
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return list_library_members(request, x_fichero_library_path)


@router.delete("/members", response_model=LibraryMembersResponse)
def revoke_library_member_role(
    request: Request,
    user: str,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
    x_fichero_library_path: str = Depends(require_library_path),
) -> LibraryMembersResponse:
    """Revoke a member's whole-library role — typed surface over ``acl.set``
    remove. Same owner-gated, audited, change-stream path as the generic
    ``POST /api/actions/invoke``; an owner cannot revoke their own role.
    Returns the refreshed member list.
    """
    try:
        registry.invoke(db, "acl.set", {"user": user, "remove": True}, ctx)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except authz.AuthorizationError as exc:
        raise LibraryAccessDeniedError(
            library_access_denial_payload(
                request,
                x_fichero_library_path,
                required="write",
                detail=str(exc),
            )
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return list_library_members(request, x_fichero_library_path)


def _build_share_url(request: Request, object_type: str, object_id: str | None) -> str:
    """Engine-served link to the shared object. The recipient's app connects to
    this engine (it may be remote) and resolves the object — never a local path.
    """
    base = str(getattr(request, "base_url", "")).rstrip("/")
    if object_type == "document" and object_id:
        return f"{base}/api/documents/{object_id}"
    if object_type == "entity" and object_id:
        return f"{base}/api/entities/{object_id}"
    # library: the engine root the recipient connects to, then opens the library.
    return base


@router.post("/share", response_model=ShareResponse)
def share_library_object(
    body: ShareRequest,
    request: Request,
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
    x_fichero_library_path: str = Depends(require_library_path),
) -> ShareResponse:
    """Share a library / entity / document (#1867) — the authz-gated model.

    Grants the recipient a per-library role through the audited ``acl.set``
    action (owner-gated, emits authz.changed) and returns an engine link to the
    object. Entity/document shares grant library access so the recipient can
    reach the object (the ACL is per-library); those types require an object_id.
    """
    object_type = body.object_type.strip().lower()
    if object_type not in _SHARE_OBJECT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid object_type: {body.object_type!r} "
            f"(expected one of: {', '.join(sorted(_SHARE_OBJECT_TYPES))})",
        )
    if object_type in {"entity", "document"} and not body.object_id:
        raise HTTPException(
            status_code=422,
            detail=f"object_id is required to share a {object_type}",
        )

    try:
        registry.invoke(db, "acl.set", {"user": body.user, "role": body.role}, ctx)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except authz.AuthorizationError as exc:
        raise LibraryAccessDeniedError(
            library_access_denial_payload(
                request,
                x_fichero_library_path,
                required="write",
                detail=str(exc),
            )
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    library_path = authz.normalize_library_path(x_fichero_library_path) or x_fichero_library_path
    return ShareResponse(
        user=body.user,
        role=body.role,
        object_type=object_type,
        object_id=body.object_id,
        library_path=library_path,
        share_url=_build_share_url(request, object_type, body.object_id),
    )
