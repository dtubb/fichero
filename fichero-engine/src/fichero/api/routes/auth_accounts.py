"""Multi-user account and session routes.

These endpoints are feature-flagged behind ``FICHERO_MULTIUSER``. When the flag
is off they stay inert so the engine continues to behave like the current
shared-secret-only single-user app.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from functools import cache
import sys
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fichero import accounts
from fichero.api.auth import _use_multiuser_auth, auth_kind_from_request
from fichero.app_db import AppDatabase, get_app_db
from fichero.models import AccountInvite, AccountUser, AuthIdentityResponse, AuthIdentityUser

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(days=30)
LOGIN_RATE_LIMIT = 5
LOGIN_RATE_WINDOW = timedelta(minutes=1)
INVITE_TTL = timedelta(minutes=15)
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


class InviteRequest(BaseModel):
    username: str = Field(min_length=1)
    display_name: str | None = Field(default=None, min_length=1)


class InviteRedeemRequest(BaseModel):
    invite_token: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class InviteResponse(BaseModel):
    id: str
    username: str
    display_name: str
    created_at: datetime
    expires_at: datetime


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
    window_start = now - LOGIN_RATE_WINDOW
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
    window_start = now - window
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
    return request.client.host if request.client else "unknown"


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
    attempts.append(now)
    attempts_by_scope[host] = attempts


def _record_login_failure(request: Request, username: str, now: datetime) -> None:
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

    now = datetime.now()
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
def identity(request: Request) -> AuthIdentityResponse:
    auth_kind = auth_kind_from_request(request)
    if auth_kind is None:
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")

    user = _current_session_user(request)
    return AuthIdentityResponse(
        multiuser_enabled=_use_multiuser_auth(),
        auth_kind=auth_kind,
        user=_identity_user(user),
        is_owner_access=auth_kind == "bootstrap" or bool(getattr(user, "is_owner", False)),
    )


@auth_router.get("/invites", response_model=list[InviteResponse])
def list_invites(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> list[InviteResponse]:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)
    return [_invite_response(invite) for invite in app_db.list_pending_invites()]


@auth_router.post("/invites", response_model=InviteMintResponse)
def create_invite(
    body: InviteRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> InviteMintResponse:
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    now = datetime.now()
    _check_invite_rate_limit(_INVITE_MINT_ATTEMPTS_BY_IP, request, now)

    username = body.username.strip()
    display_name = (body.display_name or username).strip()
    if not username or not display_name:
        raise HTTPException(status_code=422, detail="username and display_name are required")

    existing = app_db.get_user_by_username(username)
    if existing is not None and existing.active:
        raise HTTPException(status_code=409, detail="username already exists")
    if app_db.get_pending_invite_for_username(username) is not None:
        raise HTTPException(status_code=409, detail="pending invite already exists")

    raw_token = accounts.new_session_token()
    invite = app_db.create_invite(
        username=username,
        display_name=display_name,
        token_hash=accounts.hash_token(raw_token),
        ttl=INVITE_TTL,
    )
    return InviteMintResponse(
        invite=_invite_response(invite),
        invite_token=raw_token,
        redemption_url=_invite_redemption_url(raw_token),
    )


@auth_router.post("/invites/redeem", response_model=LoginResponse)
def redeem_invite(
    body: InviteRedeemRequest,
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> LoginResponse | JSONResponse:
    _multiuser_disabled()

    now = datetime.now()
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

    password_hash = accounts.hash_password(body.new_password)
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

    raw_session_token = accounts.new_session_token()
    app_db.create_session(
        user_id=user.id,
        token_hash=accounts.hash_token(raw_session_token),
        device_label="Invite redemption",
        ttl=SESSION_TTL,
    )
    app_db.consume_invite(invite.id, when=now)
    return LoginResponse(session_token=raw_session_token, user=_to_public_user(user))


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
    app_db.revoke_invite(invite_id)
    return StatusResponse(status="ok")


@auth_router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> list[SessionResponse]:
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

    return [
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

    if app_db.get_user_by_username(username) is not None:
        raise HTTPException(status_code=409, detail="username already exists")

    user = app_db.create_user(
        username=username,
        display_name=display_name,
        password_hash=accounts.hash_password(body.password),
        is_owner=is_owner,
        active=True,
    )
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
    _multiuser_disabled()
    _require_owner_or_bootstrap(request)

    user = app_db.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")

    if body.password is not None:
        app_db.set_password(user_id, accounts.hash_password(body.password))
        app_db.revoke_all_for_user(user_id)

    if body.active is not None:
        app_db.set_active(user_id, body.active)
        if not body.active:
            app_db.revoke_all_for_user(user_id)

    updated = app_db.get_user(user_id)
    if updated is None:
        raise HTTPException(status_code=404, detail="user not found")
    return _to_public_user(updated)
