"""Per-library ACL authorizer.

Authorization is enforced at shared choke-points:

* ``fichero.actions.registry.ActionRegistry.invoke`` for writes.
* ``fichero.api.main.get_library_database`` for reads.
* ``fichero.api.main.get_library_database_for_write`` for route writes.

All checks are gated behind ``FICHERO_MULTIUSER``. With the flag off, this
module returns allow so existing single-user behavior is unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fichero.db.app import get_app_db
from fichero.db.library_paths import nfc_path
from fichero.models import AccountUser, Document
from fichero.multiuser import multiuser_enabled as _multiuser_enabled

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
VALID_ROLES = frozenset({ROLE_OWNER, ROLE_EDITOR, ROLE_VIEWER})

EFFECT_GRANT = "grant"
EFFECT_DENY = "deny"
VALID_EFFECTS = frozenset({EFFECT_GRANT, EFFECT_DENY})


class AuthorizationError(PermissionError):
    """Raised when multi-user ACLs deny an operation."""


@dataclass(frozen=True)
class ResolvedUser:
    id: str
    username: str


def multiuser_enabled() -> bool:
    """Return True when per-user authentication/authorization is enabled."""
    return _multiuser_enabled()


def normalize_library_path(library: str | Path | None) -> str | None:
    """Normalize a library path for ACL key comparisons."""
    if library is None:
        return None
    return str(Path(nfc_path(library)).expanduser().resolve())


def resolve_user(user: Any) -> ResolvedUser | None:
    """Resolve an AccountUser, user id, or username to a stable user id."""
    if user is None:
        return None
    if isinstance(user, AccountUser):
        if not user.active:
            return None
        return ResolvedUser(id=user.id, username=user.username)

    raw = str(user).strip()
    if not raw or raw == "system":
        return None

    app_db = get_app_db()
    row = app_db.get_user(raw)
    if row is None:
        row = app_db.get_user_by_username(raw)
    if row is None or not row.active:
        return None
    return ResolvedUser(id=row.id, username=row.username)


def assert_can_read(user: Any, library: str | Path | None, target_id: str | None = None) -> None:
    if not can_read(user, library, target_id):
        raise AuthorizationError("read access denied")


def assert_can_write(user: Any, library: str | Path | None, target_id: str | None = None) -> None:
    if not can_write(user, library, target_id):
        raise AuthorizationError("write access denied")


def can_read(user: Any, library: str | Path | None, target_id: str | None = None) -> bool:
    """Return whether ``user`` may read a library or target subtree."""
    return _allowed(user, library, target_id, write=False)


def can_write(user: Any, library: str | Path | None, target_id: str | None = None) -> bool:
    """Return whether ``user`` may mutate a library or target subtree."""
    return _allowed(user, library, target_id, write=True)


def require_owner(user: Any, library: str | Path | None) -> ResolvedUser:
    """Resolve and require owner role for ACL management actions."""
    resolved = resolve_user(user)
    library_path = normalize_library_path(library)
    if resolved is None or library_path is None:
        raise AuthorizationError("owner access required")
    role = get_app_db().get_library_role(resolved.id, library_path)
    if role is None or role.role != ROLE_OWNER:
        raise AuthorizationError("owner access required")
    return resolved


def set_role(*, actor: Any, library: str | Path | None, user: str, role: str):
    """Owner-only role grant/update helper used by the registry action."""
    role = role.strip().lower()
    if role not in VALID_ROLES:
        raise ValueError(f"invalid library role: {role}")

    require_owner(actor, library)
    library_path = normalize_library_path(library)
    target_user = resolve_user(user)
    if target_user is None or library_path is None:
        raise ValueError("unknown user or library")
    return get_app_db().set_library_role(
        user_id=target_user.id,
        library_path=library_path,
        role=role,
    )


def remove_role(*, actor: Any, library: str | Path | None, user: str) -> None:
    """Owner-only revoke: delete a user's whole-library role (fail-closed).

    An owner cannot revoke their OWN role — that would let the sole owner lock
    themselves (and everyone) out of a library only they administer. A second
    owner can still remove the first, so a library always keeps at least one.
    """
    resolved_actor = require_owner(actor, library)
    library_path = normalize_library_path(library)
    target_user = resolve_user(user)
    if target_user is None or library_path is None:
        raise ValueError("unknown user or library")
    if target_user.id == resolved_actor.id:
        raise AuthorizationError("cannot revoke your own library role")
    get_app_db().delete_library_role(target_user.id, library_path)


def set_override(
    *,
    actor: Any,
    library: str | Path | None,
    user: str,
    target_id: str,
    effect: str,
):
    """Owner-only grant/deny override helper used by the registry action."""
    effect = effect.strip().lower()
    if effect not in VALID_EFFECTS:
        raise ValueError(f"invalid ACL override effect: {effect}")

    require_owner(actor, library)
    library_path = normalize_library_path(library)
    target_user = resolve_user(user)
    if target_user is None or library_path is None or not target_id:
        raise ValueError("unknown user, library, or target")
    return get_app_db().set_library_acl_override(
        user_id=target_user.id,
        library_path=library_path,
        target_id=target_id,
        effect=effect,
    )


def ensure_owner_role(user: Any, library: str | Path | None) -> bool:
    """Bootstrap a library's first owner.

    The creator/adopter becomes owner only when multi-user mode is enabled,
    there is a resolved authenticated user, and the library has no role rows.
    Returns True when a new owner row was written.
    """
    if not multiuser_enabled():
        return False
    resolved = resolve_user(user)
    library_path = normalize_library_path(library)
    if resolved is None or library_path is None:
        return False

    app_db = get_app_db()
    if app_db.list_library_roles(library_path):
        return False
    app_db.set_library_role(
        user_id=resolved.id,
        library_path=library_path,
        role=ROLE_OWNER,
    )
    return True


def target_ids_from_params(params: Any) -> list[str]:
    """Best-effort target id extraction for registry-level write checks."""
    if params is None:
        return []
    data = params.model_dump(mode="python") if hasattr(params, "model_dump") else params
    if not isinstance(data, dict):
        return []
    target_ids: list[str] = []
    for key, value in data.items():
        if key == "id" or key.endswith("_id"):
            _append_target_id(target_ids, value)
        elif key.endswith("_ids"):
            _append_target_ids(target_ids, value)
    return target_ids


def target_id_from_request(request: Any) -> str | None:
    """Best-effort target id extraction for read dependency checks."""
    for source in (getattr(request, "path_params", {}) or {}, getattr(request, "query_params", {}) or {}):
        for key, value in source.items():
            if key == "id" or key.endswith("_id"):
                target_ids: list[str] = []
                _append_target_id(target_ids, value)
                if target_ids:
                    return target_ids[0]
    return None


def _append_target_id(target_ids: list[str], value: Any) -> None:
    if isinstance(value, str) and value and value not in target_ids:
        target_ids.append(value)


def _append_target_ids(target_ids: list[str], value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _append_target_id(target_ids, item)


def _allowed(
    user: Any,
    library: str | Path | None,
    target_id: str | None,
    *,
    write: bool,
) -> bool:
    if not multiuser_enabled():
        return True

    resolved = resolve_user(user)
    library_path = normalize_library_path(library)
    if resolved is None or library_path is None:
        return False

    app_db = get_app_db()
    role = app_db.get_library_role(resolved.id, library_path)
    if role is None:
        return False

    if role.role == ROLE_OWNER:
        base_allowed = True
    elif role.role == ROLE_EDITOR:
        base_allowed = True
    elif role.role == ROLE_VIEWER:
        base_allowed = not write
    else:
        return False

    effect = _matching_override_effect(resolved.id, library_path, target_id)
    if effect == EFFECT_DENY:
        return False
    if effect == EFFECT_GRANT:
        return base_allowed if write else True
    return base_allowed


def _matching_override_effect(
    user_id: str, library_path: str, target_id: str | None
) -> str | None:
    if not target_id:
        return None

    target_and_ancestors = _target_ancestor_ids(library_path, target_id)
    if not target_and_ancestors:
        target_and_ancestors = [target_id]

    overrides = get_app_db().list_library_acl_overrides(user_id, library_path)
    by_target = {override.target_id: override.effect for override in overrides}
    for candidate in target_and_ancestors:
        effect = by_target.get(candidate)
        if effect in VALID_EFFECTS:
            return effect
    return None


def _target_ancestor_ids(library_path: str, target_id: str) -> list[str]:
    """Return target id followed by document ancestors, if the target is a document."""
    try:
        from fichero.db.manager import db_manager

        db = db_manager.get_database(library_path)
        doc = db.get(Document, target_id)
        ids: list[str] = []
        seen: set[str] = set()
        while doc is not None and doc.id not in seen:
            ids.append(doc.id)
            seen.add(doc.id)
            parent_id = doc.parent_id
            doc = db.get(Document, parent_id) if parent_id else None
        return ids
    except Exception:
        return [target_id]
