"""Library ACL snapshot route for the Settings / inspector UI."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from fichero import authz
from fichero.app_db import get_app_db
from fichero.api.library_header import require_library_path
from fichero.models import LibraryAuthzSnapshot

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
