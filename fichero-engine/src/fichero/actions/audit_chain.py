"""Tamper-evident hash chain for ActionAudit rows (#2043)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any

from fichero.models import ActionAudit


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
    broken_audit_id: str | None = None
    reason: str | None = None
    expected: str | None = None
    actual: str | None = None


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
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


def compute_action_audit_hash(audit: ActionAudit) -> str:
    payload = action_audit_hash_payload(audit)
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


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
    """Append ``audit`` under the database lock as one linear chain step."""
    with db._lock:
        # One ordered load (also backfills legacy rows) gives both the max
        # chain_seq and the current head — no raw SQL needed (#1876).
        rows = _audit_rows_in_chain_order(db)
        audit.created_at = datetime.now()
        head = rows[-1] if rows else None
        audit.chain_seq = (head.chain_seq or 0) + 1 if head else 1
        audit.prev_hash = head.row_hash or None if head else None
        audit.row_hash = compute_action_audit_hash(audit)
        db.save(audit)


def verify_audit_chain(db) -> AuditChainVerificationResult:
    """Walk ActionAudit rows and return the first broken chain link, if any."""
    with db._lock:
        rows = _audit_rows_in_chain_order(db)
        expected_prev: str | None = None
        for index, audit in enumerate(rows):
            if audit.prev_hash != expected_prev:
                return AuditChainVerificationResult(
                    ok=False,
                    checked=index,
                    broken_audit_id=audit.id,
                    reason="prev_hash mismatch",
                    expected=expected_prev,
                    actual=audit.prev_hash,
                )
            expected_hash = compute_action_audit_hash(audit)
            if audit.row_hash != expected_hash:
                return AuditChainVerificationResult(
                    ok=False,
                    checked=index,
                    broken_audit_id=audit.id,
                    reason="row_hash mismatch",
                    expected=expected_hash,
                    actual=audit.row_hash,
                )
            expected_prev = audit.row_hash
        return AuditChainVerificationResult(ok=True, checked=len(rows))
