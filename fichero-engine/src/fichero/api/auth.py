"""
Local-host shared-secret authentication for the embedded backend.

The engine and the Fichero.app are co-tenants on the same Mac. The backend
binds to 127.0.0.1, which keeps it off the network — but does NOT prevent
other apps running as the same user from hitting the API. This module adds
a per-launch shared secret that the Swift app reads from a 0600-permissioned
file in Application Support, and the engine requires it as a Bearer token on
every request. (#742)

Defense in depth: the middleware also rejects requests where the client host
isn't 127.0.0.1.
"""
from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Endpoints that don't require auth. Health is unauthenticated so the Swift
# app can poll readiness before it has a chance to read the token file.
# OpenAPI docs are static metadata with no library data.
_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/health",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
)


def _token_file_path() -> Path:
    """Resolve the per-user token file location.

    macOS convention: ~/Library/Application Support/Fichero/.api-key.
    """
    base = Path.home() / "Library" / "Application Support" / "Fichero"
    return base / ".api-key"


def initialize_token(*, force_rotate: bool = False) -> str:
    """Return the auth token, generating + persisting a fresh one only if needed.

    Default behaviour reuses the existing token at the file path if present —
    this keeps concurrent app instantiations (live uvicorn + pytest's
    TestClient + a second uvicorn for development) on the same token so
    they don't kick each other into 401s (#1110). The file is written with
    mode 0600 so non-owner processes can't read it.

    Pass ``force_rotate=True`` (or set ``FICHERO_FORCE_ROTATE_AUTH=1``) to
    generate a new token regardless of whether one already exists — useful
    for "stale token from a crashed run shouldn't be replayable" hardening
    when the user explicitly opts in.
    """
    path = _token_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    rotate = force_rotate or os.environ.get(
        "FICHERO_FORCE_ROTATE_AUTH", ""
    ).lower() in {"1", "true", "yes"}

    if not rotate and path.exists():
        try:
            existing = path.read_text().strip()
        except OSError:
            existing = ""
        if existing:
            logger.debug("Reusing existing auth token from %s", path)
            return existing

    token = secrets.token_urlsafe(32)
    # Atomic-ish write: open with restrictive mode, write, then chmod again
    # to handle umask quirks. Existing file is overwritten.
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)

    logger.info("Auth token %s at %s (mode 0600)",
                "rotated" if rotate else "initialized", path)
    return token


def attach_auth_middleware(app: FastAPI, token: str) -> None:
    """Add a middleware that requires `Authorization: Bearer <token>` on
    every request not in `_UNAUTHENTICATED_PATHS`, and that the request
    came from 127.0.0.1.
    """
    expected_header = f"Bearer {token}"

    @app.middleware("http")
    async def _enforce_auth(request: Request, call_next):
        # Loopback-only check (defense in depth — uvicorn already binds 127.0.0.1
        # but a misconfiguration shouldn't bypass auth).
        client_host = request.client.host if request.client else None
        if client_host not in {"127.0.0.1", "::1"}:
            logger.warning("Reject non-loopback request from %s", client_host)
            return JSONResponse(
                {"detail": "loopback only"}, status_code=403
            )

        # Allow unauthenticated paths through.
        if request.url.path in _UNAUTHENTICATED_PATHS:
            return await call_next(request)

        provided = request.headers.get("authorization", "")
        # Constant-time comparison to avoid timing oracles on the token value.
        if not secrets.compare_digest(provided, expected_header):
            return JSONResponse(
                {"detail": "missing or invalid Authorization header"},
                status_code=401,
            )

        return await call_next(request)
