"""Hand the running sandboxed engine access to a library the user just picked (#3773).

NOT to be confused with ``routes/bookmarks.py`` — those are *reading* bookmarks
(Document aliases in the node model). These are macOS **security-scoped** bookmarks:
the capability that lets a sandboxed process open a file outside its container.

Why an endpoint exists at all
-----------------------------
Under the Mac App Store build the engine runs inside the app's sandbox via
``com.apple.security.inherit``. Inheritance passes only the STATIC rights in the
parent's entitlements — not the dynamic Powerbox grant the user creates by picking
a folder in an open panel. The app therefore mints a security-scoped bookmark and
hands it over.

At spawn that handoff is an environment variable. But the user picks libraries
while the engine is ALREADY RUNNING, and the engine is never restarted — so a
library chosen mid-session (including the first library a new user ever picks)
would stay unreadable until the app relaunched. An environment cannot be changed
after the fact; a request can. Hence this route.

The app sends it sandboxed or not (#5219). On an UNSANDBOXED engine a bookmark cannot
widen anything (audit A1), so there the route answers by caller (#5484): the engine's
OWNER (loopback + bootstrap token) picked this folder in the app's own panel, and that
pick is the permission -- the folder and everything under it are allowed and remembered
across restarts. Anyone else (a paired device, a remote session) gets the A1 refusal.

Authorization is the API-wide shared-secret middleware (#742). Nothing extra is
warranted, and a bookmark is not a bearer token for arbitrary files: it only
resolves inside the sandbox that minted it, so an attacker holding one but not the
app's sandbox gains nothing — while an attacker who already has the loopback token
has the app's own privileges anyway.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from fichero_server.security.path_security import (
    OwnerFolderGrantRefused,
    is_allowed_ingest_path,
    is_owner_granted_folder,
    note_owner_granted_folder,
)
from fichero_server.security.security_scoped_access import (
    BookmarkGrantError,
    _engine_is_sandboxed,
    grant_access,
    granted_paths,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class SecurityScopedAccessRequest(BaseModel):
    """One library the app is handing to the engine."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="Absolute path of the library folder the bookmark resolves to.")
    bookmark: str = Field(
        ...,
        description=(
            "Base64-encoded app-scoped security-scoped bookmark data, minted by the app with "
            "NSURL.bookmarkData(options: .withSecurityScope). Same encoding as the "
            "FICHERO_LIBRARY_BOOKMARKS spawn payload."
        ),
    )


class SecurityScopedAccessResponse(BaseModel):
    """Whether the engine can now read the library."""

    model_config = ConfigDict(extra="forbid")

    path: str = Field(..., description="The library path the grant applies to.")
    granted: bool = Field(..., description="True when this engine process can now read the path.")
    already_held: bool = Field(
        default=False,
        description="True when the engine already had this grant, so the bookmark was not resolved again.",
    )


@router.post(
    "/sandbox/security-scoped-access",
    response_model=SecurityScopedAccessResponse,
    summary="Grant the running engine access to a security-scoped library folder",
    responses={
        400: {
            "description": (
                "The bookmark could not be turned into access — malformed, or "
                "startAccessingSecurityScopedResource() refused. The engine cannot read this "
                "library, and the app must say so rather than open it."
            )
        }
    },
)
def create_security_scoped_access(
    payload: SecurityScopedAccessRequest, request: Request
) -> SecurityScopedAccessResponse:
    """Resolve one security-scoped bookmark on the LIVE engine process.

    Must be called BEFORE the app asks the engine to open the library — otherwise
    DuckDB hits the path with no grant and fails with a permission error.

    Idempotent: re-posting a path already held reports success without resolving
    again. A bookmark that cannot be turned into access is a 400 with the reason,
    never a silent success — the app is about to open this library, and "granted"
    must mean granted.
    """
    if not _engine_is_sandboxed():
        from fichero_server.api.routes.library.registry import _caller_is_engine_owner

        if _caller_is_engine_owner(request):
            return _grant_owner_picked_folder(payload.path)
    already = payload.path in granted_paths()
    try:
        grant_access(payload.path, payload.bookmark)
    except BookmarkGrantError as exc:
        logger.error("Security-scoped access DENIED for %s: %s", payload.path, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SecurityScopedAccessResponse(path=payload.path, granted=True, already_held=already)


def _grant_owner_picked_folder(path: str) -> SecurityScopedAccessResponse:
    """The OWNER picked this folder in the app's own panel on an unsandboxed engine (#5484).

    Picking it there IS the permission: the engine allows that exact folder (resolved) and
    everything under it, and remembers it across restarts. The bookmark is not used -- an
    unsandboxed engine cannot widen anything from a bookmark (audit A1), and the owner needs none.
    Only the owner reaches here (loopback + bootstrap token); a paired device or remote session
    still goes through ``grant_access`` and its A1 refusal. A system folder, a path with ``..``,
    or one that does not exist is a 400 that says why.
    """
    if is_owner_granted_folder(path) or is_allowed_ingest_path(path):
        # Picked before, or inside the fixed roots (or under a folder picked before): nothing new.
        return SecurityScopedAccessResponse(path=path, granted=True, already_held=True)
    try:
        key = note_owner_granted_folder(path)
    except OwnerFolderGrantRefused as exc:
        logger.warning("Owner folder grant refused for %s: %s", path, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from fichero_server.api.routes.library.registry import get_global_database, persist_owner_granted_folder

    persist_owner_granted_folder(get_global_database(), key)
    logger.info("Owner picked a folder; the engine now reads it and everything under it: %s", key)
    return SecurityScopedAccessResponse(path=path, granted=True, already_held=False)
