"""Per-device pairing routes for multi-user auth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from fichero import accounts
from fichero.actions import ActionContext, ChangeSpec, action
from fichero.api.auth import _use_multiuser_auth
from fichero.api.routes.auth_accounts import _current_session_user
from fichero.app_db import AppDatabase, get_app_db
from fichero.models import AccountUser, Device

PAIRING_CODE_TTL = timedelta(seconds=60)
PAIRING_RATE_LIMIT = 5
PAIRING_RATE_WINDOW = timedelta(minutes=1)
_PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"

router = APIRouter(prefix="/pair", tags=["pairing"])


@dataclass
class _PairingCode:
    code: str
    user_id: str
    expires_at: datetime
    used: bool = False


_PAIRING_CODES: dict[str, _PairingCode] = {}
_PAIRING_ATTEMPTS: dict[str, list[datetime]] = {}


class PairCodeResponse(BaseModel):
    code: str
    expires_at: datetime


class PairRequest(BaseModel):
    code: str = Field(min_length=1)
    device_name: str = Field(min_length=1)


class PairResponse(BaseModel):
    device_id: str
    device_token: str


class DeviceResponse(BaseModel):
    id: str
    name: str
    user_id: str
    created_at: datetime
    last_seen: datetime
    revoked: bool


class DeviceListResponse(BaseModel):
    items: list[DeviceResponse]
    count: int


class StatusResponse(BaseModel):
    status: str


class DeviceListParams(BaseModel):
    pass


class DeviceRevokeParams(BaseModel):
    device_id: str = Field(min_length=1)


def get_app_database() -> AppDatabase:
    return get_app_db()


def _multiuser_disabled() -> None:
    if not _use_multiuser_auth():
        raise HTTPException(status_code=404, detail="multi-user auth is disabled")


def _to_public_device(device: Device) -> DeviceResponse:
    return DeviceResponse(
        id=device.id,
        name=device.name,
        user_id=device.user_id,
        created_at=device.created_at,
        last_seen=device.last_seen,
        revoked=device.revoked,
    )


def _owner_for_pairing(request: Request, app_db: AppDatabase) -> AccountUser:
    user = _current_session_user(request)
    if user is not None and user.is_owner:
        return user
    if getattr(request.state, "bootstrap_auth", False):
        owners = [candidate for candidate in app_db.list_users() if candidate.is_owner and candidate.active]
        if len(owners) == 1:
            return owners[0]
    raise HTTPException(status_code=403, detail="owner access required")


def _new_pairing_code() -> str:
    return "-".join(
        "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(4))
        for _ in range(2)
    )


def _prune_pairing_codes(now: datetime) -> None:
    expired = [
        code
        for code, record in _PAIRING_CODES.items()
        if record.used or record.expires_at <= now
    ]
    for code in expired:
        _PAIRING_CODES.pop(code, None)


def _check_pair_rate_limit(request: Request, now: datetime) -> None:
    host = request.client.host if request.client else "unknown"
    window_start = now - PAIRING_RATE_WINDOW
    attempts = [
        attempt
        for attempt in _PAIRING_ATTEMPTS.get(host, [])
        if attempt >= window_start
    ]
    if len(attempts) >= PAIRING_RATE_LIMIT:
        _PAIRING_ATTEMPTS[host] = attempts
        raise HTTPException(status_code=429, detail="pairing rate limit exceeded")
    attempts.append(now)
    _PAIRING_ATTEMPTS[host] = attempts


@router.post("/code", response_model=PairCodeResponse)
def create_pairing_code(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairCodeResponse:
    """Mint a short-lived one-time pairing code for an owner."""
    _multiuser_disabled()
    user = _owner_for_pairing(request, app_db)
    now = datetime.now()
    _prune_pairing_codes(now)
    code = _new_pairing_code()
    expires_at = now + PAIRING_CODE_TTL
    _PAIRING_CODES[code] = _PairingCode(
        code=code,
        user_id=user.id,
        expires_at=expires_at,
    )
    return PairCodeResponse(code=code, expires_at=expires_at)


@router.post("", response_model=PairResponse)
def pair_device(
    request: Request,
    body: PairRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Exchange a valid one-time pairing code for a device token."""
    _multiuser_disabled()
    now = datetime.now()
    _prune_pairing_codes(now)
    _check_pair_rate_limit(request, now)

    code = body.code.strip().upper()
    record = _PAIRING_CODES.get(code)
    if record is None or record.used or record.expires_at <= now:
        raise HTTPException(status_code=401, detail="invalid or expired pairing code")

    name = body.device_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="device_name is required")

    user = app_db.get_user(record.user_id)
    if user is None or not user.active:
        record.used = True
        _PAIRING_CODES.pop(code, None)
        raise HTTPException(status_code=401, detail="invalid or expired pairing code")

    raw_token = accounts.new_session_token()
    device = app_db.create_device(
        name=name,
        user_id=user.id,
        token_hash=accounts.hash_token(raw_token),
    )
    record.used = True
    _PAIRING_CODES.pop(code, None)
    return PairResponse(device_id=device.id, device_token=raw_token)


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> DeviceListResponse:
    """List paired devices for owners."""
    _multiuser_disabled()
    _owner_for_pairing(request, app_db)
    devices = app_db.list_devices()
    items = [_to_public_device(device) for device in devices]
    return DeviceListResponse(items=items, count=len(items))


@router.post("/devices/{device_id}/revoke", response_model=StatusResponse)
def revoke_device(
    request: Request,
    device_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    """Revoke one paired device token."""
    _multiuser_disabled()
    _owner_for_pairing(request, app_db)
    device = app_db.revoke_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return StatusResponse(status="ok")


@action("device.list", DeviceListParams, domains=["device"], undoable=False)
def _device_list_action(_db, _params: DeviceListParams, _ctx: ActionContext):
    """Registry read action for the app-wide paired-device list."""
    devices = [
        _to_public_device(device).model_dump(mode="json")
        for device in get_app_db().list_devices()
    ]
    result = {"items": devices, "count": len(devices)}
    return (
        result,
        ChangeSpec(
            domains=["device"],
            after=result,
        ),
    )


@action("device.revoke", DeviceRevokeParams, domains=["device"], undoable=False)
def _device_revoke_action(_db, params: DeviceRevokeParams, _ctx: ActionContext):
    """Registry mutation action for revoking an app-wide paired device."""
    app_db = get_app_db()
    before = app_db.get_device(params.device_id)
    device = app_db.revoke_device(params.device_id)
    if device is None:
        raise ValueError("device not found")
    result = _to_public_device(device).model_dump(mode="json")
    return (
        result,
        ChangeSpec(
            domains=["device"],
            target_ids=[params.device_id],
            before=before.model_dump(mode="json") if before is not None else None,
            after=result,
            emit_type="device.revoked",
        ),
    )
