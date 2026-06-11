"""Multi-user account and session routes.

These endpoints are feature-flagged behind ``FICHERO_MULTIUSER``. When the flag
is off they stay inert so the engine continues to behave like the current
shared-secret-only single-user app.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fichero import accounts
from fichero.api.auth import _use_multiuser_auth
from fichero.api.routes.providers import get_app_database
from fichero.app_db import AppDatabase
from fichero.models import AccountUser

logger = logging.getLogger(__name__)

SESSION_TTL = timedelta(days=30)
# Constant-time fallback for "username not found" so login latency does not
# reveal whether a username exists.
_DUMMY_PASSWORD_HASH = accounts.hash_password("fichero-login-dummy-password")

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


def _current_session_user(request: Request) -> AccountUser | None:
    user = getattr(request.state, "user", None)
    return user if isinstance(user, AccountUser) else None


def _require_owner_or_bootstrap(request: Request) -> None:
    if getattr(request.state, "bootstrap_auth", False):
        return
    user = _current_session_user(request)
    if user is not None and user.is_owner:
        return
    raise HTTPException(status_code=403, detail="owner access required")


@auth_router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> LoginResponse:
    _multiuser_disabled()

    user = app_db.get_user_by_username(body.username.strip())
    if user is None:
        accounts.verify_password(body.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail="invalid username or password")
    if not user.active:
        raise HTTPException(status_code=403, detail="user is disabled")
    if not accounts.verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid username or password")

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
