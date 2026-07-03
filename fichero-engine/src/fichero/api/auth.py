"""
Local-host shared-secret authentication for the embedded backend.

The engine and the Fichero.app are co-tenants on the same Mac. The backend
binds to 127.0.0.1, which keeps it off the network — but does NOT prevent
other apps running as the same user from hitting the API. This module adds
a per-launch shared secret that the Swift app reads from a 0600-permissioned
file in Application Support, and the engine requires it as a Bearer token on
every request. (#742)

When ``FICHERO_MULTIUSER`` is ON, that shared secret remains a standing
bootstrap superuser: any process that can read the 0600 ``.api-key`` file can
list users, reset passwords, disable accounts, and mint owner accounts. That
is the embedded-local bootstrap trust model, scoped to the same Unix user.
The multi-user account/session layer is attribution and convenience, not a
security boundary against same-user local processes.

Defense in depth: the middleware also rejects requests where the client host
isn't 127.0.0.1.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
import os
import secrets
import stat
from pathlib import Path

from fastapi import Depends, FastAPI, Header, Request
from fastapi.responses import JSONResponse

from fichero import accounts
from fichero.api.library_header import require_library_path
from fichero.actions import ActionContext
from fichero.app_db import get_app_db
from fichero.multiuser import multiuser_enabled

logger = logging.getLogger(__name__)

_LAST_SEEN_THROTTLE_SECONDS = 60
_SESSION_SLIDING_EXTENSION_TTL = timedelta(days=30)

# Endpoints that don't require auth. Health is unauthenticated so the Swift
# app can poll readiness before it has a chance to read the token file.
# OpenAPI docs are static metadata with no library data.
_UNAUTHENTICATED_PATHS = frozenset(
    {
        "/api/health",
        "/api/auth/login",
        "/api/pair",
        "/openapi.json",
        "/docs",
        "/redoc",
    }
)
_UNAUTHENTICATED_PREFIXES = ("/docs/", "/redoc/")
_LOOPBACK_HOSTS = {"127.0.0.1", "::1"}
_TESTCLIENT_HOSTS = {"localhost", "testserver", "testclient"}
_FORWARDED_HEADERS = ("forwarded", "x-forwarded-for", "x-forwarded-host", "x-real-ip")


def _token_file_path() -> Path:
    """Resolve the per-user token file location.

    macOS convention: ~/Library/Application Support/Fichero/.api-key.
    """
    base = Path.home() / "Library" / "Application Support" / "Fichero"
    return base / ".api-key"


def _is_account_or_device_token(token: str) -> bool:
    """Return true when a token already belongs to a session/device row.

    The bootstrap loopback secret must stay distinct from remote-client
    credentials. If an older client overwrote ``.api-key`` with a paired-device
    token, reusing that file would silently downgrade owner bootstrap auth into
    a non-owner device session. Detect and rotate on the next backend restart.
    """
    if not token:
        return False
    token_hash = accounts.hash_token(token)
    app_db = get_app_db()
    return (
        app_db.get_session_by_token_hash(token_hash) is not None
        or app_db.get_device_by_token_hash(token_hash) is not None
    )


def _write_token_file(path: Path, token: str) -> None:
    """Write ``token`` to ``path`` with 0600 perms, overwriting any existing."""
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, token.encode("utf-8"))
    finally:
        os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def initialize_token(*, force_rotate: bool = False) -> str:
    """Return the auth token, generating + persisting a fresh one only if needed.

    Default behaviour reuses the existing token at the file path if present —
    this keeps concurrent app instantiations (live uvicorn + pytest's
    TestClient + a second uvicorn for development) on the same token so
    they don't kick each other into 401s (#1110). The file is written with
    mode 0600 so non-owner processes can't read it.

    **App-supplied token (#2862):** if ``FICHERO_BOOTSTRAP_TOKEN`` is set, the
    host app minted the bootstrap token and passed it to this spawn. Persist it
    (0600) and return it. This is authoritative for the spawn — it removes the
    old race where the engine minted the token and the app had to poll for the
    ``.api-key`` file, and it lets the app issue an *authenticated* readiness
    probe the instant we bind (no chicken-and-egg 401 window). The app never
    passes a device/session credential here, so no downgrade check is needed.

    Pass ``force_rotate=True`` (or set ``FICHERO_FORCE_ROTATE_AUTH=1``) to
    generate a new token regardless of whether one already exists — useful
    for "stale token from a crashed run shouldn't be replayable" hardening
    when the user explicitly opts in.
    """
    path = _token_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    env_token = os.environ.get("FICHERO_BOOTSTRAP_TOKEN", "").strip()
    if env_token:
        _write_token_file(path, env_token)
        logger.info("Auth token adopted from FICHERO_BOOTSTRAP_TOKEN at %s (mode 0600)", path)
        return env_token

    rotate = force_rotate or os.environ.get(
        "FICHERO_FORCE_ROTATE_AUTH", ""
    ).lower() in {"1", "true", "yes"}

    if not rotate and path.exists():
        try:
            existing = path.read_text().strip()
        except OSError:
            existing = ""
        if existing:
            if _is_account_or_device_token(existing):
                logger.warning(
                    "Rotating bootstrap auth token because %s currently holds a session/device credential",
                    path,
                )
            else:
                logger.debug("Reusing existing auth token from %s", path)
                return existing

    token = secrets.token_urlsafe(32)
    # Atomic-ish write: open with restrictive mode, write, then chmod again
    # to handle umask quirks. Existing file is overwritten.
    _write_token_file(path, token)

    logger.info(
        "Auth token %s at %s (mode 0600)", "rotated" if rotate else "initialized", path
    )
    return token


def _use_multiuser_auth() -> bool:
    """Feature flag for multi-user session auth."""
    return multiuser_enabled()


def _should_touch_last_seen(last_seen_at: datetime, now: datetime) -> bool:
    return (now - last_seen_at).total_seconds() >= _LAST_SEEN_THROTTLE_SECONDS


def _session_refresh_window() -> timedelta | None:
    raw = os.getenv("FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS", "").strip()
    if not raw:
        return None
    try:
        seconds = int(raw)
    except ValueError:
        logger.warning(
            "Ignoring invalid FICHERO_SESSION_SLIDING_REFRESH_WINDOW_SECONDS=%r", raw
        )
        return None
    if seconds <= 0:
        return None
    return timedelta(seconds=seconds)


def _session_expiry_should_refresh(expires_at: datetime, now: datetime) -> bool:
    refresh_window = _session_refresh_window()
    if refresh_window is None:
        return False
    return expires_at - now <= refresh_window


def _authenticate_session_token(token: str):
    """Resolve a bearer session token to a live user/session pair."""
    token_hash = accounts.hash_token(token)
    app_db = get_app_db()
    session = app_db.get_session_by_token_hash(token_hash)
    if session is None:
        return None, None
    if session.revoked or session.expires_at <= datetime.now():
        return None, session
    user = app_db.get_user(session.user_id)
    if user is None or not user.active:
        return None, session
    now = datetime.now()
    if _should_touch_last_seen(session.last_seen_at, now):
        expires_at = None
        if _session_expiry_should_refresh(session.expires_at, now):
            expires_at = now + _SESSION_SLIDING_EXTENSION_TTL
        app_db.touch_session(token_hash, when=now, expires_at=expires_at)
        session.last_seen_at = now
        if expires_at is not None:
            session.expires_at = expires_at
    return user, session


def _authenticate_device_token(token: str):
    """Resolve a bearer device token to a live user/device pair."""
    token_hash = accounts.hash_token(token)
    app_db = get_app_db()
    device = app_db.get_device_by_token_hash(token_hash)
    if device is None or device.revoked or device.expires_at <= datetime.now():
        return None, device
    user = app_db.get_user(device.user_id)
    if user is None or not user.active:
        return None, device
    now = datetime.now()
    if _should_touch_last_seen(device.last_seen, now):
        app_db.touch_device(token_hash, when=now)
    return user, device


def _is_loopback_request(request: Request) -> bool:
    """Return true only for direct loopback clients.

    Forwarding headers make a request proxy-originated for bootstrap-secret
    purposes; do not trust their values. TestClient uses synthetic host names,
    accepted only under pytest so auth middleware tests can exercise the path.
    """
    client_host = request.client.host if request.client else None
    if client_host in _LOOPBACK_HOSTS:
        return not any(name in request.headers for name in _FORWARDED_HEADERS)
    if client_host in _TESTCLIENT_HOSTS and os.environ.get("PYTEST_CURRENT_TEST"):
        return not any(name in request.headers for name in _FORWARDED_HEADERS)
    return False


def actor_from_request(request: Request) -> str:
    """Return the trusted audit actor for this request.

    The actor is derived only from middleware-populated ``request.state`` so a
    caller cannot forge another user through headers or request bodies.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        return "system"
    username = getattr(user, "username", None)
    if username:
        return str(username)
    user_id = getattr(user, "id", None)
    if user_id:
        return str(user_id)
    return "system"


def request_actor(request: Request) -> str:
    """FastAPI dependency wrapper for ``actor_from_request``."""
    return actor_from_request(request)


def action_context(
    request: Request,
    x_fichero_library_path: str = Depends(require_library_path),
    x_fichero_origin_window: str | None = Header(
        default=None, alias="X-Fichero-Origin-Window"
    ),
) -> ActionContext:
    """Build the canonical action context for user-initiated API requests."""
    return ActionContext(
        actor=actor_from_request(request),
        origin_window=x_fichero_origin_window,
        library_path=x_fichero_library_path,
    )


def attach_auth_middleware(
    app: FastAPI,
    token: str | None = None,
    *,
    token_provider: Callable[[], str] | None = None,
) -> None:
    """Add a middleware that requires `Authorization: Bearer <token>` on
    every request not in `_UNAUTHENTICATED_PATHS`, and that the request
    came from 127.0.0.1.

    Pass a literal ``token`` (tests, embedded launch) to pin the expected
    secret eagerly. Pass ``token_provider`` instead to resolve the secret
    lazily on the FIRST authenticated request — this keeps merely importing
    the app (e.g. the CLI pulling route response models out of
    ``fichero.api``) from running ``initialize_token()`` and grabbing the
    ``app.duckdb`` lock at import time (#2388).
    """
    if token is None and token_provider is None:
        raise ValueError("attach_auth_middleware needs token or token_provider")

    # ponytail: single-slot cache; initialize_token() is idempotent so a
    # concurrent first-request race just resolves the same file twice.
    resolved: dict[str, str] = {}
    if token is not None:
        resolved["header"] = f"Bearer {token}"

    def _expected_header() -> str:
        header = resolved.get("header")
        if header is None:
            header = f"Bearer {token_provider()}"  # type: ignore[misc]
            resolved["header"] = header
        return header

    @app.middleware("http")
    async def _enforce_auth(request: Request, call_next):
        # Allow unauthenticated paths through.
        if request.url.path in _UNAUTHENTICATED_PATHS or any(
            request.url.path.startswith(prefix) for prefix in _UNAUTHENTICATED_PREFIXES
        ):
            return await call_next(request)

        expected_header = _expected_header()
        is_loopback = _is_loopback_request(request)
        if not _use_multiuser_auth():
            provided = request.headers.get("authorization", "")
            if not is_loopback:
                client_host = request.client.host if request.client else None
                logger.warning("Reject non-loopback request from %s", client_host)
                return JSONResponse({"detail": "loopback only"}, status_code=403)
            if not secrets.compare_digest(provided, expected_header):
                return JSONResponse(
                    {"detail": "missing or invalid Authorization header"},
                    status_code=401,
                )
            return await call_next(request)

        provided = request.headers.get("authorization", "")
        if secrets.compare_digest(provided, expected_header):
            if not is_loopback:
                return JSONResponse(
                    {"detail": "bootstrap auth is loopback only"},
                    status_code=401,
                )
            # Bootstrap superuser path: the shared secret remains owner-capable
            # only for direct same-Mac loopback clients.
            request.state.bootstrap_auth = True
            request.state.user = None
            return await call_next(request)

        if not provided.startswith("Bearer "):
            return JSONResponse(
                {"detail": "missing or invalid Authorization header"},
                status_code=401,
            )

        raw_token = provided.removeprefix("Bearer ").strip()
        if not raw_token:
            return JSONResponse(
                {"detail": "missing or invalid Authorization header"},
                status_code=401,
            )

        user, session = _authenticate_session_token(raw_token)
        if user is not None and session is not None:
            request.state.user = user
            request.state.session = session
            request.state.bootstrap_auth = False
            return await call_next(request)

        user, device = _authenticate_device_token(raw_token)
        if user is None or device is None:
            return JSONResponse(
                {"detail": "missing or invalid Authorization header"},
                status_code=401,
            )

        request.state.user = user
        request.state.device = device
        request.state.bootstrap_auth = False

        return await call_next(request)
