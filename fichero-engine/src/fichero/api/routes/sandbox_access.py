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

The DMG build never calls it: that engine is not sandboxed and can already open the
library. The app gates the call on FICHERO_APP_STORE.

Authorization is the API-wide shared-secret middleware (#742). Nothing extra is
warranted, and a bookmark is not a bearer token for arbitrary files: it only
resolves inside the sandbox that minted it, so an attacker holding one but not the
app's sandbox gains nothing — while an attacker who already has the loopback token
has the app's own privileges anyway.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from fichero.security.security_scoped_access import BookmarkGrantError, grant_access, granted_paths

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
def create_security_scoped_access(payload: SecurityScopedAccessRequest) -> SecurityScopedAccessResponse:
    """Resolve one security-scoped bookmark on the LIVE engine process.

    Must be called BEFORE the app asks the engine to open the library — otherwise
    DuckDB hits the path with no grant and fails with a permission error.

    Idempotent: re-posting a path already held reports success without resolving
    again. A bookmark that cannot be turned into access is a 400 with the reason,
    never a silent success — the app is about to open this library, and "granted"
    must mean granted.
    """
    already = payload.path in granted_paths()
    try:
        grant_access(payload.path, payload.bookmark)
    except BookmarkGrantError as exc:
        logger.error("Security-scoped access DENIED for %s: %s", payload.path, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SecurityScopedAccessResponse(path=payload.path, granted=True, already_held=already)
