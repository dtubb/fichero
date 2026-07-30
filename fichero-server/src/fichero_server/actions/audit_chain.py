"""Tamper-evident hash chain for ActionAudit rows (#2043)."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime
from fichero_server.core.timeutil import ensure_utc, utc_now
import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
import secrets
import stat
import threading
from typing import Any

from fichero_server.db.paths import server_state_dir
from fichero_server.db.storage import settings
from fichero_server.models import ActionAudit

logger = logging.getLogger(__name__)

_AUDIT_CHAIN_KEY_ACCOUNT = "action-audit-chain-hmac"
_AUDIT_CHAIN_HASH_MODE = "hmac-sha256-v1"
_AUDIT_CHAIN_ANCHOR_KEY_PREFIX = "audit_chain_anchor:"
_AUDIT_CHAIN_SECRET_FILE = ".action-audit-chain.key"
_AUDIT_CHAIN_ANCHOR_DIR = "audit-chain-anchors"

_HASH_FIELDS: tuple[str, ...] = (
    "id",
    "action_name",
    "actor",
    "target_ids",
    "params",
    "before",
    "after",
    "run_id",
    "created_at",
    "inverse_of",
    "prev_hash",
)


@dataclass(frozen=True)
class AuditChainVerificationResult:
    ok: bool
    checked: int
    status: str = "ok"
    broken_audit_id: str | None = None
    reason: str | None = None
    expected: str | None = None
    actual: str | None = None
    legacy_rows: int = 0
    hmac_rows: int = 0
    anchored: bool = False


def _canonical_hash_bytes(audit: ActionAudit) -> bytes:
    payload = action_audit_hash_payload(audit)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return canonical.encode("utf-8")


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        # Offset-STRIPPED UTC, deliberately (#4347). Rows written before the
        # timezone sweep were hashed from a naive datetime; rows written after it
        # carry ``+00:00``. Canonicalizing to the naive UTC wall clock makes both
        # hash to the same bytes, so the sweep does not retroactively mark every
        # historical audit row as tampered. ``ensure_utc`` first, so an aware
        # non-UTC value is converted rather than merely truncated.
        return ensure_utc(value).replace(tzinfo=None).isoformat()
    if isinstance(value, dict):
        return {str(k): _canonical_json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(v) for v in value]
    return value


def action_audit_hash_payload(audit: ActionAudit) -> dict[str, Any]:
    """Return the stable hash payload for an audit row.

    ``undone`` is deliberately excluded: undo mutates that bit in place after
    creation. The chain proves creation history is intact; ``undone`` remains a
    separate mutable state flag for the undo stack.
    """
    return {
        field: _canonical_json_value(getattr(audit, field))
        for field in _HASH_FIELDS
    }


def _compute_legacy_action_audit_hash(audit: ActionAudit) -> str:
    return hashlib.sha256(_canonical_hash_bytes(audit)).hexdigest()


def _use_keychain_for_audit_secret() -> bool:
    if threading.current_thread() is not threading.main_thread():
        return False
    try:
        return settings.base_path.resolve() == server_state_dir().resolve()
    except OSError:
        return False


def _audit_chain_key_file_path() -> Path:
    return settings.base_path / _AUDIT_CHAIN_SECRET_FILE


def _decode_secret(raw: str) -> bytes | None:
    if not raw:
        return None
    try:
        decoded = base64.urlsafe_b64decode(raw.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return None
    return decoded if decoded else None


def _encode_secret(secret: bytes) -> str:
    return base64.urlsafe_b64encode(secret).decode("ascii")


def _read_secret_file(path: Path) -> bytes | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return _decode_secret(raw)


def _write_secret_file(path: Path, secret: bytes) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _encode_secret(secret).encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, encoded)
    finally:
        os.close(fd)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    return secret


def _audit_chain_key(*, create: bool) -> bytes | None:
    if _use_keychain_for_audit_secret():
        try:
            from fichero_server.security.keychain import get_api_key, set_api_key

            existing = _decode_secret(get_api_key(_AUDIT_CHAIN_KEY_ACCOUNT) or "")
            if existing:
                return existing
            if create:
                secret = secrets.token_bytes(32)
                if set_api_key(_AUDIT_CHAIN_KEY_ACCOUNT, _encode_secret(secret)):
                    return secret
                logger.warning(
                    "Falling back to file-backed audit-chain secret after keychain write failed"
                )
        except Exception as exc:  # pragma: no cover - defensive fallback
            logger.warning("Audit-chain keychain lookup failed: %s", exc)

    path = _audit_chain_key_file_path()
    existing = _read_secret_file(path)
    if existing or not create:
        return existing
    return _write_secret_file(path, secrets.token_bytes(32))


def compute_action_audit_hash(audit: ActionAudit, *, key: bytes | None = None) -> str:
    if key is None:
        key = _audit_chain_key(create=True)
    if key is None:  # pragma: no cover - create=True should prevent this
        raise RuntimeError("audit-chain secret unavailable")
    return hmac.new(key, _canonical_hash_bytes(audit), hashlib.sha256).hexdigest()


def _anchor_setting_key(db) -> str:
    library_path = str(Path(db.path).resolve())
    library_id = hashlib.sha256(library_path.encode("utf-8")).hexdigest()
    return f"{_AUDIT_CHAIN_ANCHOR_KEY_PREFIX}{library_id}"


def _anchor_file_path(db) -> Path:
    library_path = str(Path(db.path).resolve())
    library_id = hashlib.sha256(library_path.encode("utf-8")).hexdigest()
    return settings.base_path / _AUDIT_CHAIN_ANCHOR_DIR / f"{library_id}.json"


def _load_chain_anchor(db) -> dict[str, Any] | None:
    path = _anchor_file_path(db)
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        from fichero_server.db.app import get_app_db

        raw = get_app_db().get_setting(_anchor_setting_key(db))
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    return payload


def _store_chain_anchor(db, *, chain_count: int, head_row_hash: str | None) -> dict[str, Any]:
    payload = {
        "library_path": str(Path(db.path).resolve()),
        "chain_count": chain_count,
        "head_row_hash": head_row_hash,
        "hash_mode": _AUDIT_CHAIN_HASH_MODE,
        "updated_at": utc_now().isoformat(),
    }
    path = _anchor_file_path(db)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return payload


def _backfill_chain_seq(db) -> None:
    db._ensure_table(ActionAudit)
    rows = db.all(ActionAudit)
    if not rows or all(row.chain_seq is not None for row in rows):
        return

    for chain_seq, audit in enumerate(
        sorted(rows, key=lambda a: (a.created_at, a.id)),
        start=1,
    ):
        if audit.chain_seq == chain_seq:
            continue
        # Persist via the typed upsert, not raw SQL (#1876 persistence-layer rule).
        audit.chain_seq = chain_seq
        db.save(audit)


def _audit_rows_in_chain_order(db) -> list[ActionAudit]:
    _backfill_chain_seq(db)
    return sorted(db.all(ActionAudit), key=lambda a: (a.chain_seq, a.id))


def current_audit_chain_head(db) -> str | None:
    rows = _audit_rows_in_chain_order(db)
    if not rows:
        return None
    return rows[-1].row_hash or None


def save_chained_audit(db, audit: ActionAudit) -> None:
    """Append ``audit`` as one linear chain step inside the caller's unit of work."""
    # One ordered load (also backfills legacy rows) gives both the max chain_seq
    # and the current head — no raw SQL needed (#1876).
    rows = _audit_rows_in_chain_order(db)
    audit.created_at = utc_now()
    head = rows[-1] if rows else None
    audit.chain_seq = (head.chain_seq or 0) + 1 if head else 1
    audit.prev_hash = head.row_hash or None if head else None
    audit.row_hash = compute_action_audit_hash(audit)
    db.save(audit)
    db.add_after_commit_hook(
        lambda: _store_chain_anchor(
            db,
            chain_count=len(rows) + 1,
            head_row_hash=audit.row_hash,
        )
    )


def verify_audit_chain(db) -> AuditChainVerificationResult:
    """Walk ActionAudit rows and return the first broken chain link, if any."""
    with db._lock:
        rows = _audit_rows_in_chain_order(db)
        secret = _audit_chain_key(create=False)
        anchor = _load_chain_anchor(db)
        expected_prev: str | None = None
        legacy_rows = 0
        hmac_rows = 0
        seen_hmac = False
        for index, audit in enumerate(rows):
            if audit.prev_hash != expected_prev:
                return AuditChainVerificationResult(
                    ok=False,
                    checked=index,
                    status="tampered",
                    broken_audit_id=audit.id,
                    reason="prev_hash mismatch",
                    expected=expected_prev,
                    actual=audit.prev_hash,
                    legacy_rows=legacy_rows,
                    hmac_rows=hmac_rows,
                    anchored=anchor is not None,
                )
            expected_hmac = (
                compute_action_audit_hash(audit, key=secret)
                if secret is not None
                else None
            )
            expected_legacy = _compute_legacy_action_audit_hash(audit)
            if expected_hmac is not None and audit.row_hash == expected_hmac:
                hmac_rows += 1
                seen_hmac = True
            elif audit.row_hash == expected_legacy:
                if seen_hmac:
                    return AuditChainVerificationResult(
                        ok=False,
                        checked=index,
                        status="tampered",
                        broken_audit_id=audit.id,
                        reason="legacy row_hash after HMAC cutover",
                        expected="HMAC row_hash",
                        actual="legacy SHA-256 row_hash",
                        legacy_rows=legacy_rows,
                        hmac_rows=hmac_rows,
                        anchored=anchor is not None,
                    )
                legacy_rows += 1
            else:
                reason = (
                    "audit-chain secret unavailable for keyed rows"
                    if secret is None
                    else "row_hash mismatch"
                )
                return AuditChainVerificationResult(
                    ok=False,
                    checked=index,
                    status="tampered",
                    broken_audit_id=audit.id,
                    reason=reason,
                    expected=expected_hmac or expected_legacy,
                    actual=audit.row_hash,
                    legacy_rows=legacy_rows,
                    hmac_rows=hmac_rows,
                    anchored=anchor is not None,
                )
            expected_prev = audit.row_hash

        actual_head = rows[-1].row_hash if rows else None
        if anchor is None:
            if hmac_rows > 0:
                return AuditChainVerificationResult(
                    ok=False,
                    checked=len(rows),
                    status="anchor_missing",
                    reason="missing external anchor for keyed audit chain",
                    expected="external head/count anchor",
                    actual="no anchor",
                    legacy_rows=legacy_rows,
                    hmac_rows=hmac_rows,
                )
            return AuditChainVerificationResult(
                ok=True,
                checked=len(rows),
                status="ok_legacy" if legacy_rows else "ok",
                legacy_rows=legacy_rows,
                hmac_rows=hmac_rows,
                anchored=False,
            )

        expected_count = int(anchor.get("chain_count", 0))
        expected_head = anchor.get("head_row_hash")
        actual_count = len(rows)
        if expected_count != actual_count or expected_head != actual_head:
            return AuditChainVerificationResult(
                ok=False,
                checked=len(rows),
                status="truncated",
                reason=(
                    "chain truncated: expected "
                    f"{expected_count} rows / head {expected_head}, "
                    f"found {actual_count} rows / head {actual_head}"
                ),
                expected=f"rows={expected_count}, head={expected_head}",
                actual=f"rows={actual_count}, head={actual_head}",
                legacy_rows=legacy_rows,
                hmac_rows=hmac_rows,
                anchored=True,
            )
        return AuditChainVerificationResult(
            ok=True,
            checked=len(rows),
            status="ok_legacy" if legacy_rows else "ok",
            legacy_rows=legacy_rows,
            hmac_rows=hmac_rows,
            anchored=True,
        )
