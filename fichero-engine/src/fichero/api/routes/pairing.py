"""Per-device pairing routes for multi-user auth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import os
import secrets
import sys

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from fichero import accounts
from fichero.actions import ActionContext, ChangeSpec, action
from fichero.api.auth import _use_multiuser_auth, actor_from_request
from fichero.api.routes.auth_accounts import _current_session_user
from fichero.app_db import AppDatabase, get_app_db
from fichero.models import AccountUser, ActionAudit, Device
from fichero.remote_access_tls import validate_tailnet_url

logger = logging.getLogger(__name__)

PAIRING_CODE_TTL = timedelta(seconds=60)
PAIRING_RATE_LIMIT = 5
PAIRING_RATE_WINDOW = timedelta(minutes=1)
_PAIRING_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class _PairingValidationRoute(APIRoute):
    """Route-local validation scrub for pairing secrets.

    Keep FastAPI's default 422 shape everywhere else; only /api/pair* gets a
    scrubbed response so malformed pairing submissions never reflect the code.
    """

    def get_route_handler(self):
        original = super().get_route_handler()

        async def custom_route_handler(request: Request):
            try:
                return await original(request)
            except RequestValidationError:
                return JSONResponse(
                    status_code=422,
                    content={"detail": "invalid pairing request"},
                )

        return custom_route_handler


router = APIRouter(
    prefix="/pair",
    tags=["pairing"],
    route_class=_PairingValidationRoute,
)


@dataclass
class _PairingCode:
    code: str
    user_id: str
    expires_at: datetime
    used: bool = False


# Pairing codes and rate-limit attempts are intentionally process-local.
# The engine manager clamps uvicorn to one worker, so one in-memory table is
# authoritative. If the API is launched outside that path with multiple workers,
# codes minted in one process will not be visible to another.
_PAIRING_CODES: dict[str, _PairingCode] = {}
_PAIRING_ATTEMPTS: dict[str, list[datetime]] = {}
_PAIRING_RENEW_ATTEMPTS: dict[str, list[datetime]] = {}
_PAIRING_WORKER_WARNING_EMITTED = False
_SINGLE_USER_PAIRING_OWNER = "__paired_device_owner__"


class PairCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    tailnet_url: str | None = None


class PairRequest(BaseModel):
    code: str = Field(min_length=1)
    device_name: str = Field(min_length=1)


class PairResponse(BaseModel):
    device_id: str
    device_token: str
    expires_at: datetime


class DeviceResponse(BaseModel):
    id: str
    name: str
    user_id: str
    created_at: datetime
    last_seen: datetime
    expires_at: datetime
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
        expires_at=device.expires_at,
        revoked=device.revoked,
    )


def _to_pair_response(device: Device, raw_token: str) -> PairResponse:
    return PairResponse(
        device_id=device.id,
        device_token=raw_token,
        expires_at=device.expires_at,
    )


def _owner_for_pairing(request: Request, app_db: AppDatabase) -> AccountUser:
    if not _use_multiuser_auth():
        if getattr(request.state, "bootstrap_auth", False):
            owner_accounts = [candidate for candidate in app_db.list_users() if candidate.is_owner]
            active_owners = [candidate for candidate in owner_accounts if candidate.active]
            if len(active_owners) == 1:
                return active_owners[0]
            if len(owner_accounts) == 0:
                return _single_user_pairing_owner(app_db)
        raise HTTPException(status_code=403, detail="owner access required")
    user = _current_session_user(request)
    if user is not None and user.is_owner:
        return user
    if getattr(request.state, "bootstrap_auth", False):
        owners = [candidate for candidate in app_db.list_users() if candidate.is_owner and candidate.active]
        if len(owners) == 1:
            return owners[0]
    raise HTTPException(status_code=403, detail="owner access required")


def _single_user_pairing_owner(app_db: AppDatabase) -> AccountUser:
    owner = app_db.get_user_by_username(_SINGLE_USER_PAIRING_OWNER)
    if owner is not None:
        if not owner.active:
            owner = app_db.set_active(owner.id, True) or owner
        return owner
    return app_db.create_user(
        username=_SINGLE_USER_PAIRING_OWNER,
        display_name="Paired Device Owner",
        password_hash=accounts.hash_password(secrets.token_urlsafe(16)),
        is_owner=True,
        active=True,
    )


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


def _prune_attempt_table(attempts_by_host: dict[str, list[datetime]], now: datetime) -> None:
    window_start = now - PAIRING_RATE_WINDOW
    stale_hosts: list[str] = []
    for host, attempts in attempts_by_host.items():
        current = [attempt for attempt in attempts if attempt >= window_start]
        if current:
            attempts_by_host[host] = current
        else:
            stale_hosts.append(host)
    for host in stale_hosts:
        attempts_by_host.pop(host, None)


def _prune_pairing_attempts(now: datetime) -> None:
    _prune_attempt_table(_PAIRING_ATTEMPTS, now)


def _prune_pairing_renew_attempts(now: datetime) -> None:
    _prune_attempt_table(_PAIRING_RENEW_ATTEMPTS, now)


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


def warn_pairing_single_process_invariant() -> None:
    """Log loudly if pairing is launched with a detectable multi-worker config."""
    global _PAIRING_WORKER_WARNING_EMITTED
    if _PAIRING_WORKER_WARNING_EMITTED:
        return
    _PAIRING_WORKER_WARNING_EMITTED = True
    workers = _detect_configured_worker_count()
    if workers is not None and workers != 1:
        logger.warning(
            "Pairing codes are process-local, but worker count appears to be %s. "
            "Run Fichero with one uvicorn worker or pairing codes may fail across workers.",
            workers,
        )


def _check_rate_limit(
    attempts_by_host: dict[str, list[datetime]],
    request: Request,
    now: datetime,
    *,
    detail: str,
) -> None:
    _prune_attempt_table(attempts_by_host, now)
    host = request.client.host if request.client else "unknown"
    attempts = attempts_by_host.get(host, [])
    if len(attempts) >= PAIRING_RATE_LIMIT:
        attempts_by_host[host] = attempts
        raise HTTPException(status_code=429, detail=detail)
    attempts.append(now)
    attempts_by_host[host] = attempts


def _check_pair_rate_limit(request: Request, now: datetime) -> None:
    _check_rate_limit(
        _PAIRING_ATTEMPTS,
        request,
        now,
        detail="pairing rate limit exceeded",
    )


def _check_pair_renew_rate_limit(request: Request, now: datetime) -> None:
    _check_rate_limit(
        _PAIRING_RENEW_ATTEMPTS,
        request,
        now,
        detail="pairing renew rate limit exceeded",
    )


def _current_paired_device(request: Request) -> Device:
    device = getattr(request.state, "device", None)
    if device is None:
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")
    return device


def _record_device_audit(
    *,
    action_name: str,
    actor: str,
    params: dict,
    device_id: str,
    before: dict | None = None,
    after: dict | None = None,
) -> ActionAudit:
    audit = ActionAudit(
        action_name=action_name,
        actor=actor,
        target_ids=[device_id],
        params=params,
        before=before,
        after=after,
        created_at=datetime.now(),
    )
    get_app_db().save_action_audit(audit)
    return audit


@router.post("/code", response_model=PairCodeResponse)
def create_pairing_code(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairCodeResponse:
    """Mint a short-lived one-time pairing code for an owner."""
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
    tailnet_url = (os.environ.get("FICHERO_TAILNET_URL") or "").strip()
    if tailnet_url:
        try:
            tailnet_url = validate_tailnet_url(tailnet_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PairCodeResponse(
        code=code,
        expires_at=expires_at,
        tailnet_url=tailnet_url or None,
    )


@router.post("", response_model=PairResponse)
def pair_device(
    request: Request,
    body: PairRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Exchange a valid one-time pairing code for a device token."""
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

    user_id = record.user_id
    if _use_multiuser_auth():
        user = app_db.get_user(record.user_id)
        if user is None or not user.active:
            record.used = True
            _PAIRING_CODES.pop(code, None)
            raise HTTPException(status_code=401, detail="invalid or expired pairing code")
        user_id = user.id

    raw_token = accounts.new_session_token()
    device = app_db.create_device(
        name=name,
        user_id=user_id,
        token_hash=accounts.hash_token(raw_token),
    )
    record.used = True
    _PAIRING_CODES.pop(code, None)
    return _to_pair_response(device, raw_token)


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> DeviceListResponse:
    """List paired devices for owners."""
    _owner_for_pairing(request, app_db)
    devices = app_db.list_devices()
    items = [_to_public_device(device) for device in devices]
    return DeviceListResponse(items=items, count=len(items))


@router.post("/devices/renew", response_model=PairResponse)
def renew_device_token(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Rotate one valid paired-device token and extend its expiry."""
    now = datetime.now()
    _check_pair_renew_rate_limit(request, now)
    current = _current_paired_device(request)
    raw_token = accounts.new_session_token()
    renewed = app_db.renew_device(
        current.id,
        token_hash=accounts.hash_token(raw_token),
        when=now,
    )
    if renewed is None:
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")
    _record_device_audit(
        action_name="device.renew",
        actor=actor_from_request(request),
        params={"device_id": renewed.id},
        device_id=renewed.id,
        before=_to_public_device(current).model_dump(mode="json"),
        after=_to_public_device(renewed).model_dump(mode="json"),
    )
    return _to_pair_response(renewed, raw_token)


@router.post("/devices/{device_id}/revoke", response_model=StatusResponse)
def revoke_device(
    request: Request,
    device_id: str,
    app_db: AppDatabase = Depends(get_app_database),
) -> StatusResponse:
    """Revoke one paired device token."""
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
