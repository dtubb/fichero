"""Direct tests for the audit-chain hashing/secret primitives (#2043).

`test_action_audit_chain.py` exercises the end-to-end chain (append, verify,
tamper detection, undo, concurrency). This file targets the lower-level
building blocks that the whole tamper-evidence rests on and that no test
referenced directly:

- `_encode_secret` / `_decode_secret` (base64 codec + invalid-input handling)
- `_canonical_hash_bytes` (deterministic canonical JSON, `undone` exclusion,
  field sensitivity)
- `compute_action_audit_hash` (HMAC determinism + key/field sensitivity)

Focus is edge / validation / security behaviour, not the happy path.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from fichero_server.actions.audit_chain import (
    _canonical_hash_bytes,
    _decode_secret,
    _encode_secret,
    compute_action_audit_hash,
)
from fichero_server.models import ActionAudit


def _audit(**overrides) -> ActionAudit:
    base = dict(
        id="audit-1",
        action_name="test.do_thing",
        actor="alice",
        target_ids=["doc-1", "doc-2"],
        params={"k": "v"},
        before={"name": "old"},
        after={"name": "new"},
        run_id="run-1",
        created_at=datetime(2026, 6, 27, 12, 0, 0),
        inverse_of=None,
        prev_hash=None,
    )
    base.update(overrides)
    return ActionAudit(**base)


# ---------------------------------------------------------------------------
# Secret codec: round-trip + invalid input
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret",
    [
        b"\x00" * 32,
        b"\xff" * 32,
        bytes(range(32)),
        b"\x00\x01\xfe\xff",  # includes bytes that need urlsafe (-/_) alphabet
        b"a",
    ],
)
def test_secret_encode_decode_round_trip_is_lossless(secret: bytes) -> None:
    assert _decode_secret(_encode_secret(secret)) == secret


def test_decode_empty_string_is_none() -> None:
    assert _decode_secret("") is None


def test_encode_empty_then_decode_is_none() -> None:
    # encode(b"") -> "" and decode("") -> None: an all-empty file must never be
    # mistaken for a real (zero-length) secret.
    assert _encode_secret(b"") == ""
    assert _decode_secret(_encode_secret(b"")) is None


def test_decode_rejects_non_base64_garbage() -> None:
    # Not valid base64 -> None, never an exception (callers fall back to file/keychain).
    assert _decode_secret("!!!not base64!!!") is None


def test_decode_rejects_non_ascii() -> None:
    assert _decode_secret("kÃ©y-with-unicode-—") is None


def test_decode_of_value_that_base64s_to_empty_is_none() -> None:
    # "=" / "====" decode to b"" under urlsafe_b64decode; treat as no secret.
    assert _decode_secret("====") is None


# ---------------------------------------------------------------------------
# Canonical hash bytes: determinism, `undone` exclusion, field sensitivity
# ---------------------------------------------------------------------------


def test_canonical_hash_bytes_is_deterministic_and_valid_ascii_json() -> None:
    a = _audit()
    b = _audit()
    assert _canonical_hash_bytes(a) == _canonical_hash_bytes(b)
    # Must be compact, sorted, ascii-safe JSON the chain can re-derive anywhere.
    import json

    decoded = json.loads(_canonical_hash_bytes(a))
    assert decoded["actor"] == "alice"
    raw = _canonical_hash_bytes(a)
    assert b", " not in raw and b": " not in raw  # compact separators


def test_canonical_hash_bytes_excludes_undone_flag() -> None:
    # undo flips `undone` in place after creation; it must NOT be part of the
    # creation-history hash, or every undo would "tamper" the chain.
    not_undone = _canonical_hash_bytes(_audit(undone=False))
    undone = _canonical_hash_bytes(_audit(undone=True))
    assert not_undone == undone


def test_canonical_hash_bytes_changes_when_a_hashed_field_changes() -> None:
    base = _canonical_hash_bytes(_audit())
    assert _canonical_hash_bytes(_audit(actor="mallory")) != base
    assert _canonical_hash_bytes(_audit(after={"name": "tampered"})) != base
    assert _canonical_hash_bytes(_audit(target_ids=["doc-1"])) != base


def test_canonical_hash_bytes_independent_of_dict_insertion_order() -> None:
    # sort_keys=True means logically-equal payloads hash identically regardless
    # of how the dict was built.
    a = _audit(params={"a": 1, "b": 2})
    b = _audit(params={"b": 2, "a": 1})
    assert _canonical_hash_bytes(a) == _canonical_hash_bytes(b)


# ---------------------------------------------------------------------------
# compute_action_audit_hash: HMAC determinism + key/field sensitivity
# ---------------------------------------------------------------------------


def test_hmac_is_deterministic_for_same_audit_and_key() -> None:
    key = b"k" * 32
    h1 = compute_action_audit_hash(_audit(), key=key)
    h2 = compute_action_audit_hash(_audit(), key=key)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hexdigest
    assert all(c in "0123456789abcdef" for c in h1)


def test_hmac_changes_with_key() -> None:
    a = _audit()
    assert compute_action_audit_hash(a, key=b"k" * 32) != compute_action_audit_hash(
        a, key=b"j" * 32
    )


def test_hmac_changes_when_hashed_field_changes_but_not_when_undone_flips() -> None:
    key = b"k" * 32
    base = compute_action_audit_hash(_audit(), key=key)
    # A real edit to a hashed field must move the hash (tamper-evident).
    assert compute_action_audit_hash(_audit(actor="mallory"), key=key) != base
    # Flipping `undone` must NOT move the hash (undo keeps the chain intact).
    assert compute_action_audit_hash(_audit(undone=True), key=key) == base


def test_hmac_changes_with_prev_hash_so_reordering_is_detectable() -> None:
    key = b"k" * 32
    unlinked = compute_action_audit_hash(_audit(prev_hash=None), key=key)
    linked = compute_action_audit_hash(_audit(prev_hash="deadbeef"), key=key)
    assert unlinked != linked
