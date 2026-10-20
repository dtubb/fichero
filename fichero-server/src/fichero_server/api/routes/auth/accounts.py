"""Multi-user account and session routes.

These endpoints are feature-flagged behind ``FICHERO_MULTIUSER``. When the flag
is off they stay inert so the engine continues to behave like the current
shared-secret-only single-user app.
"""

from __future__ import annotations

import base64
import hmac
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta
from fichero_server.core.timeutil import ensure_utc, utc_now
from functools import cache
import sys
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from fichero_server.security import accounts, launch_secret
from fichero_server.api.auth import _rate_limit_scope_from_request, _use_multiuser_auth, auth_kind_from_request
from fichero_server.db.app import AppDatabase, get_app_db
from fichero_server.models import _new_id as new_id
from fichero_server.models import (
    AccountInvite,
    AccountUser,
    ActionAudit,
    AuthIdentityClient,
    AuthIdentityResponse,
    AuthIdentityUser,
)

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(days=30)
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = timedelta(minutes=1)
INVITE_TTL = timedelta(minutes=15)
EMAIL_INVITE_TTL = timedelta(days=1)
INVITE_RATE_LIMIT = 5
INVITE_RATE_WINDOW = timedelta(minutes=1)

# Login failure trackers are intentionally process-local.
# The engine manager clamps uvicorn to one worker, so one in-memory table is
# authoritative. If the API is launched outside that path with multiple workers,
# lockouts recorded in one process will not be visible to another.
_LOGIN_ATTEMPTS_BY_IP: dict[str, list[datetime]] = {}
_LOGIN_ATTEMPTS_BY_ACCOUNT: dict[str, list[datetime]] = {}
_LOGIN_WORKER_WARNING_EMITTED = False
_INVITE_MINT_ATTEMPTS_BY_IP: dict[str, list[datetime]] = {}
_INVITE_REDEEM_ATTEMPTS_BY_IP: dict[str, list[datetime]] = {}


# Constant-time fallback for "username not found" so login latency does not
# reveal whether a username exists.
@cache
def _dummy_password_hash() -> str:
    return accounts.hash_password("fichero-login-dummy-password")

auth_router = APIRouter(prefix="/auth", tags=["auth"])
users_router = APIRouter(prefix="/users", tags=["users"])


class StatusResponse(BaseModel):
    status: str


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    is_owner: bool
    active: bool
    created_at: datetime


class UserListResponse(BaseModel):
    items: list[UserResponse]
    count: int


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    device_label: str | None = Field(default=None, min_length=1)


class LoginResponse(BaseModel):
    session_token: str
    user: UserResponse


class SessionUserResponse(BaseModel):
    id: str
    username: str
    display_name: str


class SessionResponse(BaseModel):
    id: str
    user: SessionUserResponse
    device_label: str
    created: datetime
    last_seen: datetime


class SessionListResponse(BaseModel):
    items: list[SessionResponse]
    count: int


class InviteRequest(BaseModel):
    username: str = Field(min_length=1)
    display_name: str | None = Field(default=None, min_length=1)
    channel: Literal["qr", "messages", "email"] = "qr"


class InviteRedeemClient(BaseModel):
    kind: Literal["app", "device"] = "app"
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(default="", max_length=120)


class InviteRedeemRequest(BaseModel):
    """Accept an invite with a password, or with the person's public key (multiuser.invite-registers-public-key).

    With a key and no password the person has no password at all: they sign in by challenge."""

    invite_token: str = Field(min_length=1)
    new_password: str | None = Field(default=None, min_length=1)
    public_key_pem: str | None = Field(default=None, min_length=1, max_length=2000)
    client: InviteRedeemClient | None = None


class RedeemedClient(BaseModel):
    id: str
    kind: str
    name: str


class InviteRedeemResponse(LoginResponse):
    client: RedeemedClient | None = None


class InviteResponse(BaseModel):
    id: str
    username: str
    display_name: str
    created_at: datetime
    expires_at: datetime
    channel: Literal["qr", "messages", "email"]


class InviteListResponse(BaseModel):
    items: list[InviteResponse]
    count: int


class InviteMintResponse(BaseModel):
    invite: InviteResponse
    invite_token: str
    redemption_url: str


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    password: str = Field(min_length=1)
    is_owner: bool = False


class UpdateUserRequest(BaseModel):
    password: str | None = Field(default=None, min_length=1)
    active: bool | None = None
    display_name: str | None = Field(default=None, min_length=1)
    is_owner: bool | None = None


def _multiuser_disabled() -> None:
    if not _use_multiuser_auth():
        raise HTTPException(status_code=404, detail="multi-user auth is disabled")


def _to_public_user(user: AccountUser) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_owner=user.is_owner,
        active=user.active,
        created_at=user.created_at,
    )


def get_app_database() -> AppDatabase:
    return get_app_db()


def _current_session_user(request: Request) -> AccountUser | None:
    user = getattr(request.state, "user", None)
    return user if isinstance(user, AccountUser) else None


def _prune_login_attempts(now: datetime) -> None:
    window_start = ensure_utc(now) - LOGIN_RATE_WINDOW
    for attempts_by_scope in (_LOGIN_ATTEMPTS_BY_IP, _LOGIN_ATTEMPTS_BY_ACCOUNT):
        stale_scopes: list[str] = []
        for scope, attempts in attempts_by_scope.items():
            current = [attempt for attempt in attempts if attempt >= window_start]
            if current:
                attempts_by_scope[scope] = current
            else:
                stale_scopes.append(scope)
        for scope in stale_scopes:
            attempts_by_scope.pop(scope, None)


def _prune_attempt_table(
    attempts_by_scope: dict[str, list[datetime]],
    *,
    now: datetime,
    window: timedelta,
) -> None:
    window_start = ensure_utc(now) - window
    stale_scopes: list[str] = []
    for scope, attempts in attempts_by_scope.items():
        current = [attempt for attempt in attempts if attempt >= window_start]
        if current:
            attempts_by_scope[scope] = current
        else:
            stale_scopes.append(scope)
    for scope in stale_scopes:
        attempts_by_scope.pop(scope, None)


def _detect_configured_worker_count() -> int | None:
    for name in ("FICHERO_UVICORN_WORKERS", "UVICORN_WORKERS", "WEB_CONCURRENCY"):
        value = os.environ.get(name)
        if value:
            try:
                return int(value)
            except ValueError:
                return None

    argv = sys.argv[1:]
    for index, arg in enumerate(argv):
        if arg == "--workers" and index + 1 < len(argv):
            try:
                return int(argv[index + 1])
            except ValueError:
                return None
        if arg.startswith("--workers="):
            try:
                return int(arg.split("=", 1)[1])
            except ValueError:
                return None
    return None


def warn_login_single_process_invariant() -> None:
    global _LOGIN_WORKER_WARNING_EMITTED
    if _LOGIN_WORKER_WARNING_EMITTED:
        return
    _LOGIN_WORKER_WARNING_EMITTED = True
    workers = _detect_configured_worker_count()
    if workers is not None and workers != 1:
        logger.warning(
            "Login rate-limit state is process-local, but worker count appears to be %s. "
            "Run Fichero with one uvicorn worker or lockouts may diverge across workers.",
            workers,
        )


def _login_host(request: Request) -> str:
    return _rate_limit_scope_from_request(request)


def _login_account_scope(username: str) -> str:
    return username.strip().lower()


def _retry_after_seconds(attempts: list[datetime], now: datetime) -> int:
    oldest_attempt = min(attempts)
    retry_after = LOGIN_RATE_WINDOW - (now - oldest_attempt)
    return max(1, int(retry_after.total_seconds()) + (1 if retry_after.microseconds else 0))


def _raise_login_rate_limit(now: datetime, attempts: list[datetime]) -> None:
    retry_after = _retry_after_seconds(attempts, now)
    raise HTTPException(
        status_code=429,
        detail="too many login attempts; try again later",
        headers={"Retry-After": str(retry_after)},
    )


def _raise_invite_rate_limit(now: datetime, attempts: list[datetime]) -> None:
    retry_after = _retry_after_seconds(attempts, now)
    raise HTTPException(
        status_code=429,
        detail="too many invite attempts; try again later",
        headers={"Retry-After": str(retry_after)},
    )


def _check_login_rate_limit(request: Request, username: str, now: datetime) -> None:
    warn_login_single_process_invariant()
    _prune_login_attempts(now)
    host = _login_host(request)
    account_scope = _login_account_scope(username)
    ip_attempts = _LOGIN_ATTEMPTS_BY_IP.get(host, [])
    if len(ip_attempts) >= LOGIN_RATE_LIMIT:
        _LOGIN_ATTEMPTS_BY_IP[host] = ip_attempts
        _raise_login_rate_limit(now, ip_attempts)
    account_attempts = _LOGIN_ATTEMPTS_BY_ACCOUNT.get(account_scope, [])
    if len(account_attempts) >= LOGIN_RATE_LIMIT:
        _LOGIN_ATTEMPTS_BY_ACCOUNT[account_scope] = account_attempts
        _raise_login_rate_limit(now, account_attempts)


def _check_invite_rate_limit(
    attempts_by_scope: dict[str, list[datetime]],
    request: Request,
    now: datetime,
) -> None:
    warn_login_single_process_invariant()
    _prune_attempt_table(
        attempts_by_scope,
        now=now,
        window=INVITE_RATE_WINDOW,
    )
    host = _login_host(request)
    attempts = attempts_by_scope.get(host, [])
    if len(attempts) >= INVITE_RATE_LIMIT:
        attempts_by_scope[host] = attempts
        _raise_invite_rate_limit(now, attempts)
    attempts.append(ensure_utc(now))
    attempts_by_scope[host] = attempts


def _record_login_failure(request: Request, username: str, now: datetime) -> None:
    now = ensure_utc(now)
    host = _login_host(request)
    ip_attempts = _LOGIN_ATTEMPTS_BY_IP.get(host, [])
    ip_attempts.append(now)
    _LOGIN_ATTEMPTS_BY_IP[host] = ip_attempts

    account_scope = _login_account_scope(username)
    account_attempts = _LOGIN_ATTEMPTS_BY_ACCOUNT.get(account_scope, [])
    account_attempts.append(now)
    _LOGIN_ATTEMPTS_BY_ACCOUNT[account_scope] = account_attempts


def _reset_login_attempts(request: Request, username: str) -> None:
    _LOGIN_ATTEMPTS_BY_IP.pop(_login_host(request), None)
    _LOGIN_ATTEMPTS_BY_ACCOUNT.pop(_login_account_scope(username), None)


def _require_owner_or_bootstrap(request: Request) -> None:
    if not _use_multiuser_auth():
        return
    if getattr(request.state, "bootstrap_auth", False):
        return
    user = _current_session_user(request)
    if user is not None and user.is_owner:
        return
    raise HTTPException(status_code=403, detail="owner access required")


def _audit(
    request: Request,
    app_db: AppDatabase,
    name: str,
    target_id: str,
    **params: object,
) -> None:
    """Record who is changing an account, invite or session (#5765), chained, BEFORE the change.

    Written first so a failed audit write stops the change: nothing goes unaudited (review 76). A change
    that then fails leaves a row for the attempt. Never takes a password or token.
    """
    if getattr(request.state, "bootstrap_auth", False):
        actor = "bootstrap"
    else:
        user = _current_session_user(request)
        actor = f"user:{user.id}" if user is not None else "system"
    device = getattr(request.state, "device", None)
    app_db.save_chained_account_audit(
        ActionAudit(
            action_name=name,
            actor=actor,
            client=request.headers.get("x-fichero-client"),
            device={"id": device.id, "name": getattr(device, "name", None)} if device is not None else None,
            target_ids=[target_id],
            params=params,
        )
    )


def _require_authenticated_or_bootstrap(request: Request) -> None:
    if not _use_multiuser_auth():
        return
    if getattr(request.state, "bootstrap_auth", False):
        return
    if _current_session_user(request) is not None:
        return
    raise HTTPException(status_code=401, detail="session required")


def _identity_user(user: AccountUser | None) -> AuthIdentityUser | None:
    if user is None:
        return None
    return AuthIdentityUser(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_owner=user.is_owner,
    )


def _session_user(user: AccountUser) -> SessionUserResponse:
    return SessionUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
    )


def _invite_response(invite: AccountInvite) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        username=invite.username,
        display_name=invite.display_name,
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        channel=invite.channel,
    )


def _invite_redemption_url(raw_token: str) -> str:
    return f"fichero://invite?token={quote(raw_token, safe='')}"


def _invite_invalid_response(*, code: str) -> JSONResponse:
    return JSONResponse(
        {
            "detail": "invalid or expired invite",
            "code": code,
        },
        status_code=401,
    )


@auth_router.post("/login", response_model=LoginResponse)
def login(
    request: Request,
    body: LoginRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> LoginResponse:
    _multiuser_disabled()

    now = utc_now()
    username = body.username.strip()
    _check_login_rate_limit(request, username, now)

    user = app_db.get_user_by_username(username)
    if user is None:
        accounts.verify_password(body.password, _dummy_password_hash())
        _record_login_failure(request, username, now)
        raise HTTPException(status_code=401, detail="invalid username or password")
    if not user.active:
        raise HTTPException(status_code=403, detail="user is disabled")
    if not accounts.verify_password(body.password, user.password_hash):
        _record_login_failure(request, username, now)
        raise HTTPException(status_code=401, detail="invalid username or password")
    _reset_login_attempts(request, username)

    raw_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
        device_label=body.device_label,
        ttl=SESSION_TTL,
    )
    logger.info("Created session for user %s", user.username)
    return LoginResponse(session_token=raw_token, user=_to_public_user(user))


@auth_router.post("/logout", response_model=StatusResponse)
def logout(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    _multiuser_disabled()

    session = getattr(request.state, "session", None)
    if session is not None:
        app_db.revoke_session(session.token_hash)
    return StatusResponse(status="ok")


@auth_router.get("/me", response_model=UserResponse)
def me(request: Request) -> UserResponse:
    _multiuser_disabled()

    if getattr(request.state, "bootstrap_auth", False):
        raise HTTPException(status_code=401, detail="session required")
    user = _current_session_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="session required")
    return _to_public_user(user)


@auth_router.get("/identity", response_model=AuthIdentityResponse)
def identity(request: Request, app_db: AppDatabase = Depends(get_app_database)) -> AuthIdentityResponse:
    auth_kind = auth_kind_from_request(request)
    if auth_kind is None:
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")

    user = _current_session_user(request)
    return AuthIdentityResponse(
        multiuser_enabled=_use_multiuser_auth(),
        auth_kind=auth_kind,
        user=_identity_user(user),
        client=_identity_client(request, app_db),
        is_owner_access=auth_kind == "bootstrap" or bool(getattr(user, "is_owner", False)),
    )


@auth_router.get("/invites", response_model=InviteListResponse)
def list_invites(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> InviteListResponse:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)
    items = [_invite_response(invite) for invite in app_db.list_pending_invites()]
    return InviteListResponse(items=items, count=len(items))


@auth_router.post("/invites", response_model=InviteMintResponse)
def create_invite(
    body: InviteRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> InviteMintResponse:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    now = utc_now()
    _check_invite_rate_limit(_INVITE_MINT_ATTEMPTS_BY_IP, request, now)

    username = body.username.strip()
    display_name = (body.display_name or username).strip()
    if not username or not display_name:
        raise HTTPException(status_code=422, detail="username and display_name are required")

    existing = app_db.get_user_by_username(username)
    if existing is not None and existing.active:
        raise HTTPException(status_code=409, detail="username already exists")
    if existing is None and app_db.username_taken(username):  # the same name in another case is taken too
        raise HTTPException(status_code=409, detail="username already exists")
    if app_db.get_pending_invite_for_username(username) is not None:
        raise HTTPException(status_code=409, detail="pending invite already exists")

    raw_token = accounts.new_session_token()
    invite_id = new_id()
    _audit(request, app_db, "invite.create", invite_id, username=username, channel=body.channel)
    invite = app_db.create_invite(
        id=invite_id,
        username=username,
        display_name=display_name,
        token_hash=accounts.hash_token(raw_token),
        channel=body.channel,
        ttl=EMAIL_INVITE_TTL if body.channel == "email" else INVITE_TTL,
    )
    return InviteMintResponse(
        invite=_invite_response(invite),
        invite_token=raw_token,
        redemption_url=_invite_redemption_url(raw_token),
    )


@auth_router.post("/invites/redeem", response_model=InviteRedeemResponse)
def redeem_invite(
    body: InviteRedeemRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> InviteRedeemResponse | JSONResponse:
    _multiuser_disabled()
    if body.public_key_pem is None and body.new_password is None:
        raise HTTPException(status_code=422, detail="a password or a public key is required")
    if body.public_key_pem is not None and (body.client is None or not _is_p256_public_key(body.public_key_pem)):
        raise HTTPException(status_code=422, detail="a P-256 public_key_pem needs a client")

    now = utc_now()
    _check_invite_rate_limit(_INVITE_REDEEM_ATTEMPTS_BY_IP, request, now)

    invite = app_db.get_invite_by_token_hash(accounts.hash_token(body.invite_token.strip()))
    if invite is None:
        return _invite_invalid_response(code="invalid_invite")
    if invite.revoked:
        return _invite_invalid_response(code="invite_revoked")
    if invite.consumed_at is not None:
        return _invite_invalid_response(code="invite_consumed")
    if invite.expires_at <= now:
        return _invite_invalid_response(code="invite_expired")

    user = app_db.get_user_by_username(invite.username)
    if user is not None and user.active:
        raise HTTPException(status_code=409, detail="username already exists")

    # A key and no password: the person gets an unusable password and signs in by challenge.
    password_hash = accounts.hash_password(body.new_password or secrets.token_urlsafe(32))
    if user is None:
        user = app_db.create_user(
            username=invite.username,
            display_name=invite.display_name,
            password_hash=password_hash,
            is_owner=False,
            active=True,
        )
    else:
        app_db.set_password(user.id, password_hash)
        user = app_db.set_active(user.id, True) or user

    client = None
    if body.public_key_pem is not None and body.client is not None:
        client = app_db.create_client(
            user_id=user.id, kind=body.client.kind, name=body.client.name, host=body.client.host,
            public_key_pem=body.public_key_pem,
        )
    raw_session_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_session_token),
        device_label="Invite redemption",
        ttl=SESSION_TTL,
        client_id=client.id if client else None,
    )
    app_db.consume_invite(invite.id, when=now)
    app_db.save_action_audit(
        ActionAudit(
            action_name="invite.redeemed",
            actor=f"invite:{invite.id}",
            target_ids=[invite.id],
            params={"username": invite.username, "channel": invite.channel},
            created_at=now,
        )
    )
    logger.warning("Invite redeemed for %s via %s", invite.username, invite.channel)
    return InviteRedeemResponse(
        session_token=raw_session_token,
        user=_to_public_user(user),
        client=RedeemedClient(id=client.id, kind=client.kind, name=client.name) if client else None,
    )


@auth_router.post("/invites/{invite_id}/revoke", response_model=StatusResponse)
def revoke_invite(
    invite_id: str,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    invite = app_db.get_invite(invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="invite not found")
    _audit(request, app_db, "invite.revoke", invite_id, username=invite.username)
    app_db.revoke_invite(invite_id)
    return StatusResponse(status="ok")


@auth_router.get("/sessions", response_model=SessionListResponse)
def list_sessions(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> SessionListResponse:
    _multiuser_disabled()

    session_user = _current_session_user(request)
    if getattr(request.state, "bootstrap_auth", False) or bool(
        getattr(session_user, "is_owner", False)
    ):
        users_by_id = {user.id: user for user in app_db.list_users()}
        sessions = app_db.list_sessions()
    elif session_user is not None:
        users_by_id = {session_user.id: session_user}
        sessions = app_db.list_sessions(user_id=session_user.id)
    else:
        raise HTTPException(status_code=401, detail="session required")

    items = [
        SessionResponse(
            id=session.id,
            user=_session_user(users_by_id[session.user_id]),
            device_label=session.device_label,
            created=session.created_at,
            last_seen=session.last_seen_at,
        )
        for session in sessions
        if session.user_id in users_by_id
    ]
    return SessionListResponse(items=items, count=len(items))


@auth_router.post("/sessions/{session_id}/revoke", response_model=StatusResponse)
def revoke_session(
    session_id: str,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    _multiuser_disabled()

    target = app_db.get_session(session_id)
    if target is None:
        raise HTTPException(status_code=404, detail="session not found")

    session_user = _current_session_user(request)
    is_bootstrap = bool(getattr(request.state, "bootstrap_auth", False))
    is_owner = bool(getattr(session_user, "is_owner", False))
    if not is_bootstrap and not is_owner and (
        session_user is None or session_user.id != target.user_id
    ):
        raise HTTPException(status_code=403, detail="owner or matching session required")

    _audit(request, app_db, "session.revoke", session_id, user_id=target.user_id)
    app_db.revoke_session_by_id(session_id)
    return StatusResponse(status="ok")


@users_router.post("", response_model=UserResponse)
def create_user(
    request: Request,
    body: CreateUserRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> UserResponse:
    _multiuser_disabled()

    existing_users = app_db.list_users()
    if existing_users:
        _require_owner_or_bootstrap(request)
        is_owner = body.is_owner
    else:
        # First-run bootstrap: the first account is always an owner so the
        # app can bootstrap itself from the shared-secret path without a
        # separate invite flow.
        if not getattr(request.state, "bootstrap_auth", False):
            raise HTTPException(status_code=403, detail="bootstrap auth required")
        is_owner = True

    username = body.username.strip()
    display_name = body.display_name.strip()
    if not username or not display_name:
        raise HTTPException(status_code=422, detail="username and display_name are required")

    if app_db.username_taken(username):  # case-folded: 'CAROL' beside 'carol' is the same name taken
        raise HTTPException(status_code=409, detail="username already exists")

    user_id = new_id()
    _audit(request, app_db, "user.create", user_id, username=username, is_owner=is_owner)
    user = app_db.create_user(
        id=user_id,
        username=username,
        display_name=display_name,
        password_hash=accounts.hash_password(body.password),
        is_owner=is_owner,
        active=True,
    )
    if is_owner:
        from fichero_server.security.multiuser import note_owner_password_set

        note_owner_password_set(app_db)  # a person chose this password
    return _to_public_user(user)


@users_router.get("", response_model=UserListResponse)
def list_users(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> UserListResponse:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    users = app_db.list_users()
    items = [_to_public_user(user) for user in users]
    return UserListResponse(items=items, count=len(items))


@users_router.patch("/{user_id}", response_model=UserResponse)
def update_user(
    request: Request,
    user_id: str,
    body: UpdateUserRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> UserResponse:
    user = app_db.get_user(user_id)
    if not _use_multiuser_auth():
        # While Multi-user is off the only change allowed is the owner's password, so
        # it can be set BEFORE the switch is turned on (`multiuser.turning-on-needs-an-owner-password`, #5908).
        # By the owner's own signed-in session, never the start-up credential (`multiuser.owner-session-sets-the-switch`).
        if getattr(request.state, "session", None) is None or not getattr(request.state.user, "is_owner", False):
            raise HTTPException(status_code=404, detail="multi-user auth is disabled")
        if user is None or not user.is_owner or set(body.model_fields_set) - {"password"} or body.password is None:
            raise HTTPException(status_code=404, detail="multi-user auth is disabled")
    _require_owner_or_bootstrap(request)

    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    display_name = None
    if body.display_name is not None:
        display_name = body.display_name.strip()
        if not display_name:
            raise HTTPException(status_code=422, detail="display_name is required")
    if body.is_owner is False and user.is_owner and len([c for c in app_db.list_users() if c.is_owner]) == 1:
        raise HTTPException(status_code=409, detail="cannot demote the last owner")

    changed = sorted(k for k in body.model_fields_set if getattr(body, k) is not None)
    _audit(request, app_db, "user.update", user_id, changed=changed,
           **{k: getattr(body, k) for k in ("active", "is_owner", "display_name") if k in changed})

    if body.password is not None:
        app_db.set_password(user_id, accounts.hash_password(body.password))
        # every other session ends; the one that made the change stays, so the owner who chose a password can turn Multi-user on
        # with the same key session (`multiuser.owner-session-sets-the-switch`, #5908)
        own = getattr(request.state, "session", None)
        app_db.revoke_all_for_user(user_id, keep_token_hash=own.token_hash if own is not None and own.user_id == user_id else None)
        if user.is_owner:
            from fichero_server.security.multiuser import note_owner_password_set

            note_owner_password_set(app_db)
    if body.active is not None:
        if not body.active:
            app_db.revoke_all_for_user(user_id)
            app_db.revoke_all_devices_for_user(user_id)
        app_db.set_active(user_id, body.active)
    if display_name is not None:
        app_db.set_display_name(user_id, display_name)
    if body.is_owner is not None and body.is_owner != user.is_owner:
        app_db.set_is_owner(user_id, body.is_owner)

    updated = app_db.get_user(user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="user not found")
    return _to_public_user(updated)


@users_router.delete("/{user_id}", response_model=StatusResponse)
def delete_user(
    request: Request,
    user_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    """Remove a user and their active credentials and library grants."""
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    user = app_db.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    session_user = _current_session_user(request)
    if session_user is not None and session_user.id == user_id:
        raise HTTPException(status_code=409, detail="cannot delete your own account")
    if user.is_owner and len([candidate for candidate in app_db.list_users() if candidate.is_owner]) == 1:
        raise HTTPException(status_code=409, detail="cannot delete the last owner")
    _audit(request, app_db, "user.delete", user_id, username=user.username)
    app_db.delete_user(user_id)
    return StatusResponse(status="ok")


# --- Sign-in by challenge (multiuser-always-on, slice 1) -------------------------------------------------------------
# A client proves it holds the private half of the public key registered for it. Single-process in-memory state, the
# same invariant as the login rate limit above.

CHALLENGE_TTL_SECONDS = 60
SIGN_IN_FAILURES_PER_MINUTE = 10
_REFUSED = HTTPException(status_code=401, detail="sign-in refused")
MAX_OUTSTANDING_CHALLENGES = 5  # per client: a flood of challenges cannot grow memory
_engine_id_lock = threading.Lock()
_challenges: dict[str, tuple[str, int]] = {}  # nonce -> (client_id, expires_at, whole seconds)
_sign_in_failures: dict[str, list[float]] = {}  # client_id -> failure times


class ChallengeRequest(BaseModel):
    client_id: str


class ChallengeResponse(BaseModel):
    nonce: str
    expires_in: int
    expires_at: int
    engine_id: str


class SignInRequest(BaseModel):
    client_id: str
    nonce: str
    signature: str  # base64 of the DER ECDSA-P256-SHA256 signature (CryptoKit derRepresentation) over _sign_in_message(...)


class SignInClient(BaseModel):
    id: str
    kind: str
    name: str


class SignInResponse(BaseModel):
    session_token: str
    user: UserResponse
    client: SignInClient


def _identity_client(request: Request, app_db: AppDatabase) -> AuthIdentityClient | None:
    session = getattr(request.state, "session", None)
    client = app_db.session_client(session.token_hash) if session is not None else None
    if client is None:
        return None
    return AuthIdentityClient(id=client.id, kind=client.kind, name=client.name)


def _live_client(app_db: AppDatabase, client_id: str):
    client = app_db.get_client(client_id)
    # A keyless client (a migrated device token) can never sign in.
    return client if client is not None and client.revoked_at is None and client.public_key_pem else None


def _engine_id(app_db: AppDatabase) -> str:
    """This engine's own id, made once and kept: what a sign-in signature is bound to (review 98)."""
    with _engine_id_lock:  # get-then-set must not race: two ids would make half the signatures fail
        engine_id = app_db.get_setting("engine_id")
        if not engine_id:
            engine_id = secrets.token_urlsafe(16)
            app_db.set_setting("engine_id", engine_id)
    return engine_id


def _sign_in_message(engine_id: str, client_id: str, nonce: str, expires_at: int) -> bytes:
    """Domain-separated, so a signature for another engine, client, purpose or expiry never verifies."""
    return "\x00".join(["fichero-sign-in-v1", engine_id, client_id, nonce, str(expires_at)]).encode()


def _signature_is_valid(public_key_pem: str, message: bytes, signature: str) -> bool:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        key.verify(base64.b64decode(signature, validate=True), message, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError):
        return False
    return True


@auth_router.post("/challenge", response_model=ChallengeResponse)
def challenge(body: ChallengeRequest, app_db: AppDatabase = Depends(get_app_database)) -> ChallengeResponse:
    # An unknown and a revoked client look the same, so ids cannot be probed.
    if _live_client(app_db, body.client_id) is None:
        raise _REFUSED
    now = time.time()
    for stale in [n for n, (_, exp) in _challenges.items() if exp <= now]:
        del _challenges[stale]
    mine = [n for n, (cid, _) in _challenges.items() if cid == body.client_id]  # insertion order = oldest first
    for old in mine[: max(0, len(mine) - MAX_OUTSTANDING_CHALLENGES + 1)]:
        del _challenges[old]
    nonce = secrets.token_urlsafe(32)
    expires_at = int(now) + CHALLENGE_TTL_SECONDS
    _challenges[nonce] = (body.client_id, expires_at)
    return ChallengeResponse(
        nonce=nonce, expires_in=CHALLENGE_TTL_SECONDS, expires_at=expires_at, engine_id=_engine_id(app_db)
    )


class FirstRunClient(BaseModel):
    kind: Literal["app"] = "app"
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(default="", max_length=120)


class MigrateOwnerRequest(BaseModel):
    """The owner row already has a name; only the key and the client are new."""

    public_key_pem: str = Field(min_length=1, max_length=2000)
    client: FirstRunClient


class FirstRunRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    public_key_pem: str = Field(min_length=1, max_length=2000)
    client: FirstRunClient


class FirstRunResponse(BaseModel):
    user: UserResponse
    client: SignInClient


_first_run_lock = threading.Lock()


def _is_p256_public_key(pem: str) -> bool:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    try:
        key = serialization.load_pem_public_key(pem.encode())
    except (ValueError, TypeError):
        return False
    return isinstance(key, ec.EllipticCurvePublicKey) and key.curve.name == "secp256r1"


def _require_local_launch(request: Request, secret: str | None, public_key_pem: str) -> None:
    """Guards shared by first-run and migrate-owner: Unix socket only, launch secret, a P-256 key."""
    if request.scope.get("fichero.transport") != "uds":
        raise HTTPException(status_code=403, detail="this route is local only")
    if not launch_secret.matches(secret):
        raise HTTPException(status_code=401, detail="refused")
    if not _is_p256_public_key(public_key_pem):
        raise HTTPException(status_code=422, detail="public_key_pem must be a P-256 public key")


@auth_router.post("/first-run", response_model=FirstRunResponse)
def first_run(
    body: FirstRunRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
    x_fichero_launch_secret: str | None = Header(default=None, alias="X-Fichero-Launch-Secret"),
) -> FirstRunResponse:
    """Create the owner and register their key, once (multiuser.first-launch-creates-owner-and-key).

    Only over the Unix socket, only with the launch secret, only while no owner exists. The old bootstrap token is
    not the launch secret. The owner gets an unusable password: they sign in by their key."""
    _require_local_launch(request, x_fichero_launch_secret, body.public_key_pem)
    with _first_run_lock:
        if any(user.is_owner for user in app_db.list_users()):
            raise HTTPException(status_code=409, detail="this library already has an owner")
        if app_db.get_user_by_username("owner") is not None:
            raise HTTPException(status_code=409, detail="the username 'owner' is already taken")
        user = app_db.create_user(
            username="owner",
            display_name=body.display_name,
            password_hash=accounts.hash_password(secrets.token_urlsafe(32)),
            is_owner=True,
        )
        client = app_db.create_client(
            user_id=user.id, kind=body.client.kind, name=body.client.name, host=body.client.host,
            public_key_pem=body.public_key_pem,
        )
    return FirstRunResponse(user=_to_public_user(user), client=SignInClient(id=client.id, kind=client.kind, name=client.name))


@auth_router.post("/migrate-owner", response_model=FirstRunResponse)
def migrate_owner(
    body: MigrateOwnerRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
    x_fichero_launch_secret: str | None = Header(default=None, alias="X-Fichero-Launch-Secret"),
) -> FirstRunResponse:
    """Give an existing owner row its first key, once (multiuser.migrate-owner).

    Same guards as first-run. The key goes to the owner row only, never to another person."""
    _require_local_launch(request, x_fichero_launch_secret, body.public_key_pem)
    with _first_run_lock:
        owners = [user for user in app_db.list_users() if user.is_owner]
        if not owners:
            raise HTTPException(status_code=404, detail="this library has no owner yet; use first-run")
        if len(owners) > 1:
            raise HTTPException(status_code=409, detail="this library has several owners; none is chosen for you")
        owner = owners[0]
        if app_db.user_has_key(owner.id):
            raise HTTPException(status_code=409, detail="the owner already has a key")
        client = app_db.create_client(
            user_id=owner.id, kind=body.client.kind, name=body.client.name, host=body.client.host,
            public_key_pem=body.public_key_pem,
        )
    return FirstRunResponse(user=_to_public_user(owner), client=SignInClient(id=client.id, kind=client.kind, name=client.name))


# --- Local CLI/MCP clients (multiuser.first-connection-asks-the-person, slice 6a) --------------------------------
# A local client asks over the Unix socket; the owner, signed in in the app, allows it; the client then registers
# its OWN public key. Nothing here is on until the owner turns a switch on (default off). The transport stamps
# `fichero.peer` ({uid, pid, exe, signer}) from the socket's peer credentials; with no peer the request is refused.

REQUEST_TTL_SECONDS = 300
MAX_PENDING_REQUESTS = 20
MAX_PENDING_PER_PROGRAM = 3  # one program cannot fill the owner's list
_client_requests: dict[str, dict] = {}
_client_requests_lock = threading.Lock()
_SWITCH_KEYS = {"mcp": "local_clients_allow_mcp", "cli": "local_clients_allow_cli"}


class LocalClientSwitches(BaseModel):
    mcp: bool
    cli: bool


class LocalClientRequestBody(BaseModel):
    kind: Literal["cli", "mcp"]
    name: str = Field(min_length=1, max_length=120)
    host: str = Field(default="", max_length=120)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: object) -> object:
        # Before min_length, so a whitespace-only name is refused instead of stored as "".
        return value.strip() if isinstance(value, str) else value


class LocalClientPeer(BaseModel):
    pid: int
    exe: str
    signer: str | None = None


class LocalClientRequestResponse(BaseModel):
    id: str
    kind: Literal["cli", "mcp"]
    name: str
    host: str
    peer: LocalClientPeer
    state: Literal["pending", "allowed", "denied"]


class LocalClientRequestList(BaseModel):
    items: list[LocalClientRequestResponse]


class LocalClientDecision(BaseModel):
    allow: bool


class LocalClientRegisterBody(BaseModel):
    request_id: str = Field(min_length=1, max_length=64)
    public_key_pem: str = Field(min_length=1, max_length=2000)


def _signed_in_owner(request: Request):
    """The owner signed in by a session. The bootstrap token and loopback are not the owner here."""
    user = _current_session_user(request)
    if user is None or not user.is_owner:
        raise HTTPException(status_code=403, detail="owner access required")
    return user


def _verified_peer(request: Request) -> dict:
    if request.scope.get("fichero.transport") != "uds":
        raise HTTPException(status_code=403, detail="this route is local only")
    peer = request.scope.get("fichero.peer")
    if not peer or peer.get("uid") != os.getuid():
        raise HTTPException(status_code=403, detail="the connecting program could not be verified")
    return peer


def _switch_on(app_db: AppDatabase, kind: str) -> bool:
    return app_db.get_setting(_SWITCH_KEYS[kind]) == "1"


def _request_view(request_id: str, entry: dict) -> LocalClientRequestResponse:
    peer = entry["peer"]
    return LocalClientRequestResponse(
        id=request_id,
        kind=entry["kind"],
        name=entry["name"],
        host=entry["host"],
        peer=LocalClientPeer(pid=peer["pid"], exe=peer["exe"], signer=peer.get("signer")),
        state=entry["state"],
    )


def _live_requests() -> dict[str, dict]:
    now = time.time()
    for stale in [rid for rid, entry in _client_requests.items() if entry["expires_at"] <= now]:
        del _client_requests[stale]
    return _client_requests


@auth_router.get("/local-clients/switches", response_model=LocalClientSwitches)
def get_local_client_switches(
    request: Request, app_db: AppDatabase = Depends(get_app_database)
) -> LocalClientSwitches:
    _signed_in_owner(request)
    return LocalClientSwitches(mcp=_switch_on(app_db, "mcp"), cli=_switch_on(app_db, "cli"))


@auth_router.put("/local-clients/switches", response_model=LocalClientSwitches)
def put_local_client_switches(
    body: LocalClientSwitches, request: Request, app_db: AppDatabase = Depends(get_app_database)
) -> LocalClientSwitches:
    _signed_in_owner(request)
    _audit(request, app_db, "local_clients.switches", "local_clients", mcp=body.mcp, cli=body.cli)
    for kind, value in (("mcp", body.mcp), ("cli", body.cli)):
        app_db.set_setting(_SWITCH_KEYS[kind], "1" if value else "0")
    return body


@auth_router.post("/local-clients/request", response_model=LocalClientRequestResponse)
def request_local_client(
    body: LocalClientRequestBody, request: Request, app_db: AppDatabase = Depends(get_app_database)
) -> LocalClientRequestResponse:
    peer = _verified_peer(request)
    if not _switch_on(app_db, body.kind):
        raise HTTPException(status_code=403, detail="not allowed on this Mac")
    from fichero_server.api import uds_peer  # lazy: ctypes stays out of app import (#5798)

    shown = uds_peer.identify(peer)
    if not shown["exe"]:
        # The audit token could not be turned into a program: the owner would be asked to allow something nameless.
        raise HTTPException(status_code=403, detail="the connecting program could not be verified")
    with _client_requests_lock:
        live = _live_requests()
        if len(live) >= MAX_PENDING_REQUESTS or sum(
            1 for entry in live.values() if entry["peer"]["exe"] == shown["exe"]
        ) >= MAX_PENDING_PER_PROGRAM:
            raise HTTPException(status_code=429, detail="too many pending requests")
        request_id = secrets.token_urlsafe(16)
        live[request_id] = {
            "kind": body.kind, "name": body.name.strip(), "host": body.host.strip(), "peer": shown, "token": peer["token"],
            "state": "pending", "user_id": None, "expires_at": time.time() + REQUEST_TTL_SECONDS,
        }
        return _request_view(request_id, live[request_id])


@auth_router.get("/local-clients/requests", response_model=LocalClientRequestList)
def list_local_client_requests(request: Request) -> LocalClientRequestList:
    _signed_in_owner(request)
    with _client_requests_lock:
        return LocalClientRequestList(items=[_request_view(rid, e) for rid, e in _live_requests().items()])


@auth_router.post("/local-clients/requests/{request_id}/decision", response_model=LocalClientRequestResponse)
def decide_local_client_request(
    request_id: str, body: LocalClientDecision, request: Request, app_db: AppDatabase = Depends(get_app_database)
) -> LocalClientRequestResponse:
    owner = _signed_in_owner(request)
    with _client_requests_lock:
        entry = _live_requests().get(request_id)
        if entry is None or entry["state"] != "pending":
            raise HTTPException(status_code=404, detail="no such pending request")
        _audit(request, app_db, "local_clients.decide", request_id, allow=body.allow, kind=entry["kind"])
        entry["state"] = "allowed" if body.allow else "denied"
        entry["user_id"] = owner.id
        return _request_view(request_id, entry)


@auth_router.post("/local-clients/register", response_model=SignInClient)
def register_local_client(
    body: LocalClientRegisterBody,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> SignInClient:
    """The allowed client registers its own public key, once, from the same program that asked. No secret crosses."""
    peer = _verified_peer(request)
    if not _is_p256_public_key(body.public_key_pem):
        raise HTTPException(status_code=422, detail="public_key_pem must be a P-256 public key")
    with _client_requests_lock:
        request_id = body.request_id
        entry = _live_requests().get(request_id)
        # The audit token carries the pid version: the same program that asked, not a process that reused its pid.
        if entry is None or not hmac.compare_digest(entry["token"], peer["token"]):
            raise HTTPException(status_code=404, detail="no such request")
        if entry["state"] == "pending":
            raise HTTPException(status_code=409, detail="not allowed yet")
        if entry["state"] == "denied" or not _switch_on(app_db, entry["kind"]):
            raise HTTPException(status_code=403, detail="not allowed on this Mac")
        client = app_db.create_client(
            user_id=entry["user_id"], kind=entry["kind"], name=entry["name"], host=entry["host"],
            public_key_pem=body.public_key_pem,
        )
        del _client_requests[request_id]
    return SignInClient(id=client.id, kind=client.kind, name=client.name)


@auth_router.post("/sign-in", response_model=SignInResponse)
def sign_in(body: SignInRequest, app_db: AppDatabase = Depends(get_app_database)) -> SignInResponse:
    now = time.time()
    recent = [t for t in _sign_in_failures.get(body.client_id, []) if now - t < 60]
    if len(recent) >= SIGN_IN_FAILURES_PER_MINUTE:
        raise HTTPException(status_code=429, detail="too many failed sign-ins", headers={"Retry-After": "60"})
    # Single use: the nonce is spent whether or not the signature is good.
    issued = _challenges.pop(body.nonce, None)
    client = _live_client(app_db, body.client_id)
    ok = (
        issued is not None
        and issued[0] == body.client_id
        and issued[1] > now
        and client is not None
        and _signature_is_valid(
            client.public_key_pem,
            _sign_in_message(_engine_id(app_db), body.client_id, body.nonce, issued[1]),
            body.signature,
        )
    )
    if not ok:
        # Only a live client is counted: sign-in is reachable over TCP and unknown ids must not grow this dict.
        if client is not None:
            _sign_in_failures[body.client_id] = [*recent, now]
        raise _REFUSED
    user = app_db.get_user(client.user_id)
    if user is None or not user.active:
        raise _REFUSED
    raw_token = accounts.new_session_token()
    token_hash = accounts.hash_token(raw_token)
    app_db.create_session(
        user_id=user.id, token_hash=token_hash, device_label=client.name, ttl=SESSION_TTL, client_id=client.id
    )
    return SignInResponse(
        session_token=raw_token,
        user=_to_public_user(user),
        client=SignInClient(id=client.id, kind=client.kind, name=client.name),
    )
