"""Per-library ACL authorizer.

Authorization is enforced at shared choke-points:

* ``fichero_server.actions.registry.ActionRegistry.invoke`` for writes.
* ``fichero_server.api.main.get_library_database`` for reads.
* ``fichero_server.api.main.get_library_database_for_write`` for route writes.

All checks are gated behind ``FICHERO_MULTIUSER``. With the flag off, this
module returns allow so existing single-user behavior is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from fichero_server.db.app import get_app_db
from fichero_server.db.library_paths import nfc_path
from fichero_server.models import (
    AccountUser,
    Artifact,
    Document,
    Segment,
    SegmentCarry,
    SegmentForwarding,
    SegmentMatch,
    SegmentPass,
    SegmentVersion,
)
from fichero_server.security.multiuser import multiuser_enabled as _multiuser_enabled

logger = logging.getLogger(__name__)

ROLE_OWNER = "owner"
ROLE_EDITOR = "editor"
ROLE_VIEWER = "viewer"
VALID_ROLES = frozenset({ROLE_OWNER, ROLE_EDITOR, ROLE_VIEWER})

EFFECT_GRANT = "grant"
EFFECT_DENY = "deny"
VALID_EFFECTS = frozenset({EFFECT_GRANT, EFFECT_DENY})


class AuthorizationError(PermissionError):
    """Raised when multi-user ACLs deny an operation.

    `required` (F4, 2026-09-20 review) names WHAT was denied -- "read",
    "write", or "owner" -- so the handler that turns this into a 403 can
    tell the app the truth instead of hard-coding "write" for every raise
    site (this same class is also raised for "read access denied",
    "owner access required" and "cannot revoke your own library role").
    Read from this attribute, never parsed out of the message string.
    """

    def __init__(self, message: str, *, required: str = "write") -> None:
        super().__init__(message)
        self.required = required


class AuthzResolutionError(RuntimeError):
    """A target id's document/ancestor chain could not be resolved (#4917).

    Raised by `_target_ancestor_ids` on any lookup failure -- a broken
    library, a bad path, a dropped connection. `_matching_override_effect`
    treats this as a DENY, never as "no ancestors, no restriction": a
    resolution failure must never be indistinguishable from "nothing to
    restrict".
    """

    def __init__(self, target_id: str) -> None:
        self.target_id = target_id
        super().__init__(f"could not resolve ancestors for target {target_id!r}")


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
        raise AuthorizationError("read access denied", required="read")


def assert_can_write(user: Any, library: str | Path | None, target_id: str | None = None) -> None:
    if not can_write(user, library, target_id):
        raise AuthorizationError("write access denied", required="write")


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
        raise AuthorizationError("owner access required", required="owner")
    role = get_app_db().get_library_role(resolved.id, library_path)
    if role is None or role.role != ROLE_OWNER:
        raise AuthorizationError("owner access required", required="owner")
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
        raise AuthorizationError("cannot revoke your own library role", required="owner")
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

    # Ruling 1 (cost, #4917): the cheap question first. No override at all
    # for this user/library means none can possibly match, so resolving
    # ancestors -- up to 7 indexed `db.get` calls for a non-document id --
    # would be pure waste on EVERY audited write's EVERY target id,
    # including claim/entity/note ids that will never resolve to anything.
    # Only load overrides here (never inside the resolver, which stays
    # pure ancestor-lookup); resolve ONLY once we know an override exists
    # to check against.
    overrides = get_app_db().list_library_acl_overrides(user_id, library_path)
    if not overrides:
        return None
    by_target = {override.target_id: override.effect for override in overrides}

    try:
        target_and_ancestors = _target_ancestor_ids(library_path, target_id)
    except AuthzResolutionError:
        # Fail CLOSED (#4917): a lookup error is a real problem, not "no
        # restriction applies" -- deny outright rather than let a broken
        # resolution silently behave like an unrestricted target.
        logger.warning("authz: treating unresolvable target %r as denied", target_id)
        return EFFECT_DENY
    if not target_and_ancestors:
        target_and_ancestors = [target_id]

    for candidate in target_and_ancestors:
        effect = by_target.get(candidate)
        if effect in VALID_EFFECTS:
            return effect
    return None


#: (model, how to reach the document id it belongs to) -- an ORDERED
#: table, not a chain of ifs, so a later slice can extend it (#4917).
#: Each resolver takes `(db, row)` so a kind that names something else
#: (a `SegmentCarry` names a match, not a document, directly) can do one
#: more indexed get. Checked only when `target_id` is not itself a
#: `Document` -- one indexed `db.get` per kind, in order, until one hits;
#: never a scan.
_DOCUMENT_ID_RESOLVERS: tuple[tuple[type, Callable[[Any, Any], "str | None"]], ...] = (
    (Artifact, lambda db, row: row.document_id),
    (Segment, lambda db, row: row.document_id),
    (SegmentPass, lambda db, row: row.document_id),
    (SegmentMatch, lambda db, row: row.document_id),
    (SegmentVersion, lambda db, row: row.document_id),
    (SegmentForwarding, lambda db, row: row.document_id),
    (SegmentCarry, lambda db, row: _document_id_of_segment_match(db, row.match_id)),
)


def _document_id_of_segment_match(db: Any, match_id: str) -> str | None:
    match = db.get(SegmentMatch, match_id)
    return match.document_id if match else None


def _resolve_owning_document_id(db: Any, target_id: str) -> str | None:
    """The document id `target_id` belongs to, per `_DOCUMENT_ID_RESOLVERS`,
    or `None` when it matches NONE of the known kinds (kept as "itself
    only" by the caller -- today's honest behaviour for anything outside
    the segment domain, e.g. a claim or entity id).

    Raises `AuthzResolutionError` (F1, 2026-09-20 review) when a kind DOES
    match but its owning document cannot be established -- an
    empty/missing `document_id` on the row (a `SegmentCarry` whose match
    was deleted; any row with a blank `document_id`), or a `document_id`
    that names no `Document` row. This distinction matters: "no kind
    matched" is honestly nothing to resolve, but "a kind matched, document
    unknown" is the EXACT silent-unrestricted shape this fix exists to
    remove (a row found, "itself only" returned, no override on the
    document -- or folder -- ever able to match) -- it must deny, never
    fall through the same way.
    """
    for model, get_document_id in _DOCUMENT_ID_RESOLVERS:
        row = db.get(model, target_id)
        if row is None:
            continue
        document_id = get_document_id(db, row)
        if not document_id or db.get(Document, document_id) is None:
            raise AuthzResolutionError(target_id)
        return document_id
    return None


def _target_ancestor_ids(library_path: str, target_id: str) -> list[str]:
    """Target id, then every document ancestor up to the root (#4917).

    Resolves an id that BELONGS TO a document -- an artifact, a segment, a
    segment pass, a match, a version, a forwarding note, a carry -- to its
    owning document FIRST (`_resolve_owning_document_id`), then walks
    `Document.parent_id` exactly as before. A grant/deny placed on the
    document (or a folder above it) therefore reaches every one of these
    child kinds, not just a literal document id -- `ActionRegistry.invoke`
    checks each segment/pass id named by an action's params AS ITS OWN
    target, so this is the ONE place that connection has to exist.

    An id that matches nothing known is "itself only" -- unchanged
    behaviour for ids outside the segment domain.

    FAILS CLOSED: any lookup error raises `AuthzResolutionError`, which
    `_matching_override_effect` treats as a deny -- never silently
    "no ancestors, no restriction" (the exact shape of the bug this
    replaces).
    """
    from fichero_server.db.manager import db_manager

    try:
        db = db_manager.get_database(library_path)
        doc = db.get(Document, target_id)
        ids: list[str] = []
        if doc is None:
            document_id = _resolve_owning_document_id(db, target_id)
            if document_id is None:
                return [target_id]
            ids.append(target_id)
            doc = db.get(Document, document_id)
        seen: set[str] = set(ids)
        while doc is not None and doc.id not in seen:
            ids.append(doc.id)
            seen.add(doc.id)
            parent_id = doc.parent_id
            doc = db.get(Document, parent_id) if parent_id else None
        return ids
    except AuthzResolutionError:
        # Already the right shape (raised by `_resolve_owning_document_id`
        # itself, F1) -- re-raise as-is rather than wrapping it a second
        # time under the generic handler below.
        raise
    except Exception as exc:
        logger.warning(
            "authz: ancestor resolution failed for target %r in %r: %s",
            target_id, library_path, exc,
        )
        raise AuthzResolutionError(target_id) from exc
