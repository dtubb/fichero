"""Per-device pairing routes for multi-user auth."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from fichero_server.core.timeutil import ensure_utc, utc_now
import logging
import os
import secrets
import sys

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from fichero_server.security import accounts
from fichero_server.actions import ActionContext, ChangeSpec, action, registry
from fichero_server.actions.registry import ActionRefused
from fichero_server.api.auth import action_context, _has_proxy_origin_headers, _rate_limit_scope_from_request, _use_multiuser_auth, actor_from_request, ensure_owner_account
from fichero_server.api.routes.auth.accounts import _current_session_user
from fichero_server.api.main import get_library_database_for_write
from fichero_server.db import Database
from fichero_server.db.app import AppDatabase, get_app_db
from fichero_server.models import AccountUser, ActionAudit, Device
from fichero_server.security.remote_access_tls import validate_spki_pin, validate_tailnet_url

logger = logging.getLogger(__name__)

PAIRING_CODE_TTL = timedelta(minutes=10)
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
    paired_by_device_id: str | None = None  # the paired device that minted it (#5351)
    ambient: bool = False  # minted by the host app (no signed-in person): the device must say who it is

    def __post_init__(self) -> None:
        # This table is a store, so it gets the same hydration seam as a DB row
        # (#4347): whatever a caller hands us is normalized to aware UTC once,
        # here, so every later comparison against ``utc_now()`` is type-consistent.
        self.expires_at = ensure_utc(self.expires_at)


# Pairing codes and rate-limit attempts are intentionally process-local.
# The engine manager clamps uvicorn to one worker, so one in-memory table is
# authoritative. If the API is launched outside that path with multiple workers,
# codes minted in one process will not be visible to another.
_PAIRING_CODES: dict[str, _PairingCode] = {}
_PAIRING_ATTEMPTS: dict[str, list[datetime]] = {}
_PAIRING_RENEW_ATTEMPTS: dict[str, list[datetime]] = {}
_PAIRING_WORKER_WARNING_EMITTED = False
_LOCAL_PAIRING_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient", "testserver"}


class PairCodeResponse(BaseModel):
    code: str
    expires_at: datetime
    tailnet_url: str | None = None
    spki_pin: str | None = None


class TailnetOfferResponse(BaseModel):
    tailnet_url: str | None = None


class SharingStateResponse(BaseModel):
    multiuser_enabled: bool
    tailnet_url: str | None = None
    # The one command to paste in Terminal when this engine cannot make the tailnet forward itself
    # (a sandboxed app cannot run the Tailscale CLI, #5317); None when nothing is missing.
    tailnet_serve_command: str | None = None
    paired_device_count: int
    # The audit row of a change this answer follows (PUT /multiuser): what ⌘Z takes back.
    audit_id: str | None = None


class MultiuserRequest(BaseModel):
    enabled: bool


def _tailnet_serve_command() -> str | None:
    import shlex
    import subprocess

    from fichero_server.security import tailscale_serve  # lazy: app-import budget (#3950)

    if not tailscale_serve.tailnet_url():
        return None
    from fichero_server.security.bind_host import listen_port

    port = listen_port()
    cli = tailscale_serve.tailscale_cli()
    want = tailscale_serve.wanted_target(port)
    try:
        already_serving = bool(cli) and tailscale_serve.forward_target(tailscale_serve.serve_status(cli), port) == want
    except (OSError, subprocess.SubprocessError, ValueError):
        already_serving = False  # CLI refused, timed out or printed no JSON: we cannot tell, so show the command
    if already_serving:
        return None
    return shlex.join([cli or "tailscale", "serve", "--bg", f"--https={port}", want])


def _sharing_state(app_db: AppDatabase) -> SharingStateResponse:
    from fichero_server.security import tailscale_serve  # lazy: app-import budget (#3950)
    from fichero_server.security.multiuser import multiuser_enabled

    return SharingStateResponse(
        multiuser_enabled=multiuser_enabled(),
        tailnet_url=tailscale_serve.detected_tailnet_url() or None,
        tailnet_serve_command=_tailnet_serve_command(),
        paired_device_count=sum(1 for d in app_db.list_devices() if not d.revoked),
    )


class PairRequest(BaseModel):
    code: str = Field(min_length=1)
    device_name: str = Field(min_length=1)
    # Multi-user on: the device chooses and authenticates a person; it is bound to them, not to
    # whoever minted the code (sharing.device-chooses-person, #2403).
    username: str | None = None
    password: str | None = None


class EnrollmentRequest(BaseModel):
    enrollment_secret: str = Field(min_length=1)
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
    paired_by_device_id: str | None = None


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


def _to_public_device(device: Device, paired_by: str | None = None) -> DeviceResponse:
    return DeviceResponse(
        paired_by_device_id=paired_by,
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
        session_owner = getattr(request.state, "user", None)
        if getattr(request.state, "session", None) is not None and isinstance(session_owner, AccountUser) and session_owner.is_owner:
            return session_owner  # the owner's own key session (the middleware lets one through only for the Multi-user switch)
        if getattr(request.state, "bootstrap_auth", False):
            owner_accounts = [candidate for candidate in app_db.list_users() if candidate.is_owner]
            active_owners = [candidate for candidate in owner_accounts if candidate.active]
            if active_owners:
                # Single-user mode authenticates the local bootstrap owner. Old
                # account rows must not make local device pairing impossible.
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


def _pairing_user(request: Request, app_db: AppDatabase) -> AccountUser:
    if not _use_multiuser_auth():
        return _owner_for_pairing(request, app_db)
    user = _current_session_user(request)
    if user is None and getattr(request.state, "bootstrap_auth", False):
        # The host app is the owner (loopback + bootstrap, ruled), Multi-user on or off: it must be
        # able to list and revoke the devices it shared with, not only mint codes (#5346).
        return _owner_for_pairing(request, app_db)
    if user is None or not user.active:
        raise HTTPException(status_code=401, detail="missing or invalid Authorization header")
    return user


def _can_manage_device(request: Request, device: Device) -> bool:
    if getattr(request.state, "bootstrap_auth", False):
        return True  # the host app, as above (#5346)
    user = _current_session_user(request)
    return bool(user and (user.is_owner or user.id == device.user_id))


def _single_user_pairing_owner(app_db: AppDatabase) -> AccountUser:
    """Compatibility name for the shared canonical owner resolver."""
    return ensure_owner_account(app_db)


def _new_pairing_code() -> str:
    return "-".join(
        "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(4))
        for _ in range(2)
    )


def _prune_pairing_codes(now: datetime) -> None:
    now = ensure_utc(now)
    expired = [
        code
        for code, record in _PAIRING_CODES.items()
        if record.used or record.expires_at <= now
    ]
    for code in expired:
        _PAIRING_CODES.pop(code, None)


def _prune_attempt_table(attempts_by_host: dict[str, list[datetime]], now: datetime) -> None:
    window_start = ensure_utc(now) - PAIRING_RATE_WINDOW
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
    record_attempt: bool = True,
) -> None:
    _prune_attempt_table(attempts_by_host, now)
    host = _rate_limit_scope_from_request(request)
    attempts = attempts_by_host.get(host, [])
    if len(attempts) >= PAIRING_RATE_LIMIT:
        attempts_by_host[host] = attempts
        raise HTTPException(status_code=429, detail=detail)
    if record_attempt:
        attempts.append(ensure_utc(now))
        attempts_by_host[host] = attempts


def _record_rate_limit_attempt(
    attempts_by_host: dict[str, list[datetime]],
    request: Request,
    now: datetime,
) -> None:
    _prune_attempt_table(attempts_by_host, now)
    host = _rate_limit_scope_from_request(request)
    attempts = attempts_by_host.get(host, [])
    attempts.append(ensure_utc(now))
    attempts_by_host[host] = attempts


def _check_pair_rate_limit(
    request: Request,
    now: datetime,
    *,
    record_attempt: bool = True,
) -> None:
    _check_rate_limit(
        _PAIRING_ATTEMPTS,
        request,
        now,
        detail="pairing rate limit exceeded",
        record_attempt=record_attempt,
    )


def _record_pair_attempt(request: Request, now: datetime) -> None:
    _record_rate_limit_attempt(_PAIRING_ATTEMPTS, request, now)


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


def _require_secure_pairing_transport(request: Request) -> None:
    # The app's own private Unix socket: stamped by uds_transport, no client
    # IP, plaintext by design (no network listener exists on it). Without
    # this, Sharing ON showed "HTTP 400: remote pairing requires https" the
    # moment the app minted a QR over UDS (found live 2026-08-27).
    if request.scope.get("fichero.transport") == "uds":
        return
    host = ((request.client.host if request.client else "") or "").lower()
    if host in _LOCAL_PAIRING_CLIENT_HOSTS and not _has_proxy_origin_headers(request):
        return
    if request.url.scheme != "https":
        raise HTTPException(status_code=400, detail="remote pairing requires https")
    # Sharing at a .ts.net name means Tailscale's publicly trusted certificate: system trust, no pin
    # (#5753). Decided by what this engine shares at, not by the caller-supplied Host header.
    if _shares_at_ts_net():
        return
    try:
        validate_spki_pin(os.environ.get("FICHERO_TLS_SPKI_HASH", ""))
    except ValueError as exc:
        raise HTTPException(
            status_code=503,
            detail="remote pairing unavailable without configured SPKI pin",
        ) from exc


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
        created_at=utc_now(),
    )
    get_app_db().save_action_audit(audit)
    return audit


def _owner_only(request: Request, app_db: AppDatabase) -> None:
    if not _pairing_user(request, app_db).is_owner:
        raise HTTPException(status_code=403, detail="only the owner can change Sharing settings")


@router.get("/sharing", response_model=SharingStateResponse)
def sharing_state(request: Request, app_db: AppDatabase = Depends(get_app_database)) -> SharingStateResponse:
    """Read Sharing state: Multi-user, the detected tailnet address, paired device count (#5751)."""
    _owner_only(request, app_db)
    return _sharing_state(app_db)


@router.put("/multiuser", response_model=SharingStateResponse)
def set_multiuser(
    request: Request,
    body: MultiuserRequest,
    app_db: AppDatabase = Depends(get_app_database),
    db: Database = Depends(get_library_database_for_write),
    ctx: ActionContext = Depends(action_context),
) -> SharingStateResponse:
    """Set the persisted Multi-user switch through the audited action layer (#5751); the Settings
    switch, the CLI and MCP share this route. While Multi-user is off only the owner's signed-in session may
    (`multiuser.owner-session-sets-the-switch`, #5908): never the start-up credential."""
    if not _use_multiuser_auth() and getattr(request.state, "session", None) is None:
        raise HTTPException(status_code=403, detail="sign in as the owner to change Multi-user")
    _owner_only(request, app_db)
    try:
        result = registry.invoke(db, "sharing.set_multiuser", body.model_dump(), ctx)
    except ActionRefused as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _sharing_state(app_db).model_copy(update={"audit_id": result.audit_id})


class MultiuserParams(BaseModel):
    enabled: bool


def _multiuser_invert(before: dict | None, after: dict | None, ctx: ActionContext) -> tuple[str, dict] | None:
    return ("sharing.set_multiuser", {"enabled": before["enabled"]}) if before else None


@action("sharing.set_multiuser", MultiuserParams, domains=["sharing"], undoable=True, invert=_multiuser_invert, owner_only=True)
def _set_multiuser_action(_db, params: MultiuserParams, ctx: ActionContext):
    """Who sees every library: audited and undoable. Owner only at the route; the environment wins."""
    from fichero_server.security.authz import AuthorizationError
    from fichero_server.security.multiuser import MULTIUSER_SETTING_KEY, multiuser_enabled

    # Owner-only HERE, not only at the route: POST /api/actions/invoke, MCP and chat reach this action
    # with library WRITE alone, and an editor who turned Multi-user off would own every library (review 58).
    if not ctx.is_bootstrap:
        person = next((u for u in get_app_db().list_users() if u.username == ctx.actor), None)
        if not (person and person.active and person.is_owner):
            raise AuthorizationError("only the owner can change Multi-user", required="owner")
    if (os.environ.get("FICHERO_MULTIUSER") or "").strip():
        raise ActionRefused("Multi-user is set by FICHERO_MULTIUSER; unset it to change it here")
    app_db = get_app_db()
    if params.enabled:  # turning it on: someone must be able to sign in with a password (#5908)
        from fichero_server.security.multiuser import owner_password_gap

        if gap := owner_password_gap(app_db):
            raise ActionRefused(gap)  # the route answers 409 in these words
    before = {"enabled": multiuser_enabled()}
    app_db.set_setting(MULTIUSER_SETTING_KEY, "true" if params.enabled else "false")
    after = {"enabled": params.enabled}
    return after, ChangeSpec(domains=["sharing"], before=before, after=after)


def _shares_at_ts_net() -> bool:
    from urllib.parse import urlparse

    public = (os.environ.get("FICHERO_PUBLIC_BASE_URL") or "").strip()
    return (urlparse(public).hostname or "").lower().endswith(".ts.net")


@router.get("/tailnet", response_model=TailnetOfferResponse)
def detected_tailnet(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> TailnetOfferResponse:
    """This Mac's `.ts.net` address when Tailscale is running, for the share sheet to offer (#5318)."""
    _pairing_user(request, app_db)
    from fichero_server.security import tailscale_serve  # lazy: app-import budget (#3950)

    return TailnetOfferResponse(tailnet_url=tailscale_serve.detected_tailnet_url() or None)


@router.post("/code", response_model=PairCodeResponse)
def create_pairing_code(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairCodeResponse:
    """Mint a short-lived one-time pairing code for the authenticated caller."""
    _require_secure_pairing_transport(request)
    user = _pairing_user(request, app_db)
    from fichero_server.api.transport_diagnostics import network_listener_gap, tcp_listeners

    # A link never names an address nothing listens on (`sharing.link-names-a-listener`).
    if gap := network_listener_gap(os.environ.get("FICHERO_PUBLIC_BASE_URL") or "", tcp_listeners()):
        raise HTTPException(status_code=409, detail=gap)
    now = utc_now()
    _prune_pairing_codes(now)
    code = _new_pairing_code()
    expires_at = now + PAIRING_CODE_TTL
    _PAIRING_CODES[code] = _PairingCode(
        code=code,
        user_id=user.id,
        expires_at=expires_at,
        paired_by_device_id=getattr(getattr(request.state, "device", None), "id", None),
        ambient=_use_multiuser_auth() and _current_session_user(request) is None,
    )
    # FICHERO_TAILNET_URL, else a `.ts.net` sharing address -- which is all the app sets (#2603).
    from fichero_server.security import tailscale_serve  # lazy: app-import budget (#3950)

    tailnet_url = tailscale_serve.tailnet_url()
    if tailnet_url:
        try:
            tailnet_url = validate_tailnet_url(tailnet_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PairCodeResponse(
        code=code,
        expires_at=expires_at,
        tailnet_url=tailnet_url or None,
        # By the sharing address the guest uses, not by whether Tailscale is up: .ts.net is system
        # trust (no pin), anything else (.local, an IP) is pinned (#5753).
        spki_pin=None if _shares_at_ts_net() else (os.environ.get("FICHERO_TLS_SPKI_HASH") or "").strip() or None,
    )


@router.post("", response_model=PairResponse)
def pair_device(
    request: Request,
    body: PairRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Exchange a valid one-time pairing code for a device token."""
    _require_secure_pairing_transport(request)
    now = utc_now()
    _prune_pairing_codes(now)
    _check_pair_rate_limit(request, now, record_attempt=False)

    try:
        code = body.code.strip().upper()
        record = _PAIRING_CODES.get(code)
        if record is None or record.used or record.expires_at <= now:
            raise HTTPException(status_code=401, detail="invalid or expired pairing code")

        name = body.device_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="device_name is required")

        user_id = record.user_id
        chosen = None
        if body.username is not None:
            if not _use_multiuser_auth():
                raise HTTPException(status_code=422, detail="choosing a person needs Multi-user on")
            chosen = app_db.get_user_by_username(body.username.strip())
            if chosen is None or not accounts.verify_password(
                body.password or "", chosen.password_hash if chosen else accounts.hash_password("x")
            ):
                raise HTTPException(status_code=401, detail="invalid username or password")
            if not chosen.active:
                raise HTTPException(status_code=403, detail="user is disabled")
            user_id = chosen.id
        if _use_multiuser_auth():
            if chosen is None and record.ambient:
                # The host owner is never ambient on a remote device: the device says who it is.
                raise HTTPException(
                    status_code=401, detail="person required: this library uses Multi-user, sign in as a person"
                )
            user = chosen or app_db.get_user(record.user_id)
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
        if record.paired_by_device_id:
            app_db.set_device_paired_by(device.id, record.paired_by_device_id)
        # Through `tailscale serve` (its identity headers) vs straight onto the .local/LAN listener.
        app_db.set_device_route(device.id, "tailnet" if _has_proxy_origin_headers(request) else "lan")
        record.used = True
        _PAIRING_CODES.pop(code, None)
        return _to_pair_response(device, raw_token)
    except HTTPException:
        _record_pair_attempt(request, now)
        raise


@router.post("/enroll", response_model=PairResponse)
def enroll_device(
    request: Request,
    body: EnrollmentRequest,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Exchange one owner's synced enrollment secret for a new device token."""
    _require_secure_pairing_transport(request)
    now = utc_now()
    _check_pair_rate_limit(request, now, record_attempt=False)

    try:
        secret = app_db.get_enrollment_secret_by_token_hash(
            accounts.hash_token(body.enrollment_secret.strip())
        )
        if secret is None or secret.revoked:
            raise HTTPException(status_code=401, detail="invalid enrollment secret")
        user = app_db.get_user(secret.user_id)
        if user is None or not user.active:
            raise HTTPException(status_code=401, detail="invalid enrollment secret")

        name = body.device_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="device_name is required")
        raw_token = accounts.new_session_token()
        device = app_db.create_device(
            name=name,
            user_id=user.id,
            token_hash=accounts.hash_token(raw_token),
        )
        app_db.set_device_route(device.id, "tailnet" if _has_proxy_origin_headers(request) else "lan")
        _record_device_audit(
            action_name="device.enroll",
            actor=f"enrollment:{secret.id}",
            params={"device_name": name},
            device_id=device.id,
            after=_to_public_device(device).model_dump(mode="json"),
        )
        logger.warning("Device enrolled for %s: %s", user.username, name)
        return _to_pair_response(device, raw_token)
    except HTTPException:
        _record_pair_attempt(request, now)
        raise


@router.get("/devices", response_model=DeviceListResponse)
def list_devices(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> DeviceListResponse:
    """List paired devices for owners or one caller's own account."""
    user = _pairing_user(request, app_db)
    devices = app_db.list_devices()
    if not user.is_owner:
        devices = [device for device in devices if device.user_id == user.id]
    paired_by = app_db.device_paired_by()
    items = [_to_public_device(device, paired_by.get(device.id)) for device in devices]
    return DeviceListResponse(items=items, count=len(items))


@router.post("/devices/renew", response_model=PairResponse)
def renew_device_token(
    request: Request,
    app_db: AppDatabase = Depends(get_app_database),
) -> PairResponse:
    """Rotate one valid paired-device token and extend its expiry."""
    now = utc_now()
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
    _pairing_user(request, app_db)
    device = app_db.get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    if not _can_manage_device(request, device):
        raise HTTPException(status_code=403, detail="owner access required")
    device = app_db.revoke_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="device not found")
    return StatusResponse(status="ok")


def _ctx_may_manage(ctx: ActionContext, device: Device) -> bool:
    """The action twin of `_can_manage_device` (#5345). Reached through `/api/actions/invoke`, the
    device actions used to need only library write access, so any editor could list every device
    and revoke the owner's. The host app (bootstrap) may; with Multi-user on, so may an owner, or the
    person who paired this device. With Multi-user off only the host app may, as over REST."""
    if ctx.is_bootstrap:
        return True
    if not _use_multiuser_auth():
        return False
    user = next((u for u in get_app_db().list_users() if u.username == ctx.actor), None)
    return bool(user and user.active and (user.is_owner or user.id == device.user_id))


@action("device.list", DeviceListParams, domains=["device"], undoable=False)
def _device_list_action(_db, _params: DeviceListParams, ctx: ActionContext):
    """Registry read action for the app-wide paired-device list."""
    devices = [
        _to_public_device(device).model_dump(mode="json")
        for device in get_app_db().list_devices()
        if _ctx_may_manage(ctx, device)
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
def _device_revoke_action(_db, params: DeviceRevokeParams, ctx: ActionContext):
    """Registry mutation action for revoking an app-wide paired device."""
    app_db = get_app_db()
    before = app_db.get_device(params.device_id)
    if before is not None and not _ctx_may_manage(ctx, before):
        from fichero_server.security.authz import AuthorizationError

        raise AuthorizationError("only the owner, or the person who paired it, can revoke a device", required="owner")
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
