from __future__ import annotations

import asyncio
from datetime import datetime
import json
import threading

import pytest
from pydantic import BaseModel

from fichero_server.actions.audit_chain import (
    _audit_chain_key_file_path,
    _compute_legacy_action_audit_hash,
    _load_chain_anchor,
    action_audit_hash_payload,
    current_audit_chain_head,
    save_chained_audit,
    verify_audit_chain,
)
from fichero_server.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models import ActionAudit


class _ChainParams(BaseModel):
    value: str


@pytest.fixture
def chain_actions():
    forward = "test.chain_forward"
    inverse = "test.chain_inverse"

    def _execute(_db, params: _ChainParams, _ctx: ActionContext):
        return (
            {"value": params.value},
            ChangeSpec(
                domains=["test"],
                target_ids=[params.value],
                before={"value": "before"},
                after={"value": params.value},
            ),
        )

    def _invert(_before, after, _ctx: ActionContext):
        return (inverse, {"value": after["value"]})

    registry.register(
        ActionRegistration(
            name=forward,
            params_model=_ChainParams,
            execute=_execute,
            domains=["test"],
            undoable=True,
            invert=_invert,
        )
    )
    registry.register(
        ActionRegistration(
            name=inverse,
            params_model=_ChainParams,
            execute=_execute,
            domains=["test"],
            undoable=False,
        )
    )
    yield forward
    registry._actions.pop(forward, None)
    registry._actions.pop(inverse, None)


def _invoke(db, name: str, value: str):
    return registry.invoke(
        db,
        name,
        {"value": value},
        ActionContext(actor="alice", run_id="run-1"),
    )


def _audit_rows(db) -> list[ActionAudit]:
    return sorted(
        db.all(ActionAudit),
        key=lambda a: (a.chain_seq if a.chain_seq is not None else -1, a.id),
    )


def _seed_audit(
    db,
    *,
    audit_id: str,
    action_name: str,
    value: str,
    created_at: datetime,
    prev_hash: str | None,
    chain_seq: int,
) -> ActionAudit:
    audit = ActionAudit(
        id=audit_id,
        action_name=action_name,
        actor="alice",
        target_ids=[value],
        params={"value": value},
        before={"value": "before"},
        after={"value": value},
        run_id="run-1",
        created_at=created_at,
        chain_seq=chain_seq,
        prev_hash=prev_hash,
    )
    audit.row_hash = _compute_legacy_action_audit_hash(audit)
    db.save(audit)
    return audit


def test_appended_actions_verify_and_link_contiguously(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    result = verify_audit_chain(db)
    assert result.ok is True
    assert result.checked == 3
    assert result.status == "ok"
    assert result.hmac_rows == 3
    assert result.legacy_rows == 0
    assert result.anchored is True

    anchor = _load_chain_anchor(db)
    assert anchor is not None
    assert anchor["chain_count"] == 3

    rows = _audit_rows(db)
    assert [row.chain_seq for row in rows] == [1, 2, 3]
    assert rows[0].prev_hash is None
    assert anchor["head_row_hash"] == rows[-1].row_hash
    for prev, current in zip(rows, rows[1:]):
        assert current.prev_hash == prev.row_hash
        assert current.row_hash


def test_action_audit_hash_payload_canonicalizes_datetimes_nested_keys_and_tuples():
    created_at = datetime(2026, 6, 13, 10, 30, 0)
    audit = ActionAudit(
        id="audit-1",
        action_name="test.chain_forward",
        actor="alice",
        target_ids=("doc-1", "doc-2"),
        params={
            "when": created_at,
            9: {"nested": created_at},
            "tuple": ("x", created_at),
        },
        before={"state": created_at},
        after={"items": [created_at]},
        run_id="run-1",
        created_at=created_at,
        inverse_of=None,
        prev_hash=None,
    )

    payload = action_audit_hash_payload(audit)

    assert payload["created_at"] == created_at.isoformat()
    assert payload["target_ids"] == ["doc-1", "doc-2"]
    assert payload["params"]["when"] == created_at.isoformat()
    assert payload["params"]["9"]["nested"] == created_at.isoformat()
    assert payload["params"]["tuple"] == ["x", created_at.isoformat()]
    assert payload["before"]["state"] == created_at.isoformat()
    assert payload["after"]["items"] == [created_at.isoformat()]


def test_current_head_and_save_chained_audit_track_latest_row_and_anchor(db):
    assert current_audit_chain_head(db) is None

    first = ActionAudit(
        id="manual-1",
        action_name="test.chain_manual",
        actor="alice",
        target_ids=["one"],
        params={"value": "one"},
        before={"value": "before"},
        after={"value": "one"},
        run_id="run-1",
    )
    save_chained_audit(db, first)
    assert first.chain_seq == 1
    assert first.prev_hash is None
    assert current_audit_chain_head(db) == first.row_hash

    second = ActionAudit(
        id="manual-2",
        action_name="test.chain_manual",
        actor="alice",
        target_ids=["two"],
        params={"value": "two"},
        before={"value": "before"},
        after={"value": "two"},
        run_id="run-1",
    )
    save_chained_audit(db, second)

    anchor = _load_chain_anchor(db)
    assert second.chain_seq == 2
    assert second.prev_hash == first.row_hash
    assert current_audit_chain_head(db) == second.row_hash
    assert anchor is not None
    assert anchor["chain_count"] == 2
    assert anchor["head_row_hash"] == second.row_hash


def test_same_microsecond_rows_verify_via_chain_seq_order(db):
    shared_created_at = datetime(2026, 6, 11, 12, 0, 0, 123456)
    first = _seed_audit(
        db,
        audit_id="same-ts-first",
        action_name="test.chain_forward",
        value="one",
        created_at=shared_created_at,
        prev_hash=None,
        chain_seq=1,
    )
    _seed_audit(
        db,
        audit_id="same-ts-second",
        action_name="test.chain_forward",
        value="two",
        created_at=shared_created_at,
        prev_hash=first.row_hash,
        chain_seq=2,
    )

    result = verify_audit_chain(db)
    assert result.ok is True
    assert result.checked == 2
    assert result.status == "ok_legacy"
    assert result.legacy_rows == 2
    assert result.hmac_rows == 0
    assert result.anchored is False

    rows = _audit_rows(db)
    assert rows[0].created_at == rows[1].created_at == shared_created_at
    assert [row.chain_seq for row in rows] == [1, 2]


def test_verification_detects_edited_historical_row(db, chain_actions):
    _invoke(db, chain_actions, "one")
    _invoke(db, chain_actions, "two")

    last = _audit_rows(db)[-1]
    db._execute(
        'UPDATE "actionaudits" SET actor = $actor, row_hash = $row_hash WHERE id = $id',
        {
            "actor": "mallory",
            "row_hash": _compute_legacy_action_audit_hash(
                ActionAudit(
                    **{
                        **last.model_dump(),
                        "actor": "mallory",
                    }
                )
            ),
            "id": last.id,
        },
    )

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == last.id
    assert result.reason == "legacy row_hash after HMAC cutover"
    assert result.status == "tampered"


def test_verification_detects_deleted_middle_row(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    rows = _audit_rows(db)
    db._execute('DELETE FROM "actionaudits" WHERE id = $id', {"id": rows[1].id})

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == rows[2].id
    assert result.reason == "prev_hash mismatch"


def test_verification_detects_reordered_chain_seq(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    rows = _audit_rows(db)
    db._execute(
        'UPDATE "actionaudits" SET chain_seq = $chain_seq WHERE id = $id',
        {"chain_seq": 3, "id": rows[0].id},
    )
    db._execute(
        'UPDATE "actionaudits" SET chain_seq = $chain_seq WHERE id = $id',
        {"chain_seq": 1, "id": rows[2].id},
    )

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == rows[2].id
    assert result.reason == "prev_hash mismatch"
    assert result.status == "tampered"


def test_verification_detects_forged_row_with_wrong_prev_hash(db, chain_actions):
    first = _invoke(db, chain_actions, "one")
    forged = db.get(ActionAudit, first.audit_id)
    assert forged is not None
    forged.id = "forged-audit-row"
    forged.action_name = chain_actions
    forged.actor = "mallory"
    forged.target_ids = ["forged"]
    forged.params = {"value": "forged"}
    forged.before = {"value": "before"}
    forged.after = {"value": "forged"}
    forged.prev_hash = "not-the-real-prev"
    forged.row_hash = "not-a-real-row-hash"
    db.save(forged)

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == forged.id
    assert result.reason == "prev_hash mismatch"
    assert result.status == "tampered"


def test_verification_detects_plain_sha256_rehash_without_secret(db, chain_actions):
    _invoke(db, chain_actions, "one")
    _invoke(db, chain_actions, "two")

    last = _audit_rows(db)[-1]
    tampered = ActionAudit(
        **{
            **last.model_dump(),
            "after": {"value": "tampered"},
            "params": {"value": "tampered"},
            "target_ids": ["tampered"],
        }
    )
    db._execute(
        'UPDATE "actionaudits" SET target_ids = $target_ids, params = $params, after = $after, row_hash = $row_hash WHERE id = $id',
        {
            "target_ids": json.dumps(tampered.target_ids),
            "params": json.dumps(tampered.params),
            "after": json.dumps(tampered.after),
            "row_hash": _compute_legacy_action_audit_hash(tampered),
            "id": last.id,
        },
    )

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == last.id
    assert result.reason == "legacy row_hash after HMAC cutover"
    assert result.status == "tampered"


def test_verification_detects_truncated_tail_via_external_anchor(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    rows = _audit_rows(db)
    db._execute('DELETE FROM "actionaudits" WHERE id = $id', {"id": rows[-1].id})

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.status == "truncated"
    assert result.reason is not None
    assert "expected 3 rows" in result.reason
    assert "found 2 rows" in result.reason


def test_verification_detects_forged_middle_insert_with_plain_hash(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    rows = _audit_rows(db)
    db._execute(
        'UPDATE "actionaudits" SET chain_seq = $chain_seq WHERE id = $id',
        {"chain_seq": 3, "id": rows[1].id},
    )
    db._execute(
        'UPDATE "actionaudits" SET chain_seq = $chain_seq WHERE id = $id',
        {"chain_seq": 4, "id": rows[2].id},
    )

    forged = ActionAudit(
        id="forged-middle",
        action_name=chain_actions,
        actor="mallory",
        target_ids=["forged"],
        params={"value": "forged"},
        before={"value": "before"},
        after={"value": "forged"},
        run_id="run-1",
        created_at=datetime(2026, 6, 11, 12, 0, 1),
        chain_seq=2,
        prev_hash=rows[0].row_hash,
    )
    forged.row_hash = _compute_legacy_action_audit_hash(forged)
    db.save(forged)

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == forged.id
    assert result.reason == "legacy row_hash after HMAC cutover"
    assert result.status == "tampered"


def test_undo_mutates_undone_without_breaking_chain(db, chain_actions):
    forward = _invoke(db, chain_actions, "one")

    result = asyncio.run(
        undo_action(
            forward.audit_id,
            request=None,
            db=db,
            ctx=ActionContext(actor="alice"),
        )
    )
    assert result.ok is True

    original = db.get(ActionAudit, forward.audit_id)
    assert original is not None
    assert original.undone is True

    chain = verify_audit_chain(db)
    assert chain.ok is True
    assert chain.checked == 2


def test_missing_secret_path_fails_closed_without_crashing_and_anchor_round_trips(
    db, chain_actions
):
    _invoke(db, chain_actions, "one")

    rows = _audit_rows(db)
    anchor = _load_chain_anchor(db)
    assert anchor is not None
    assert anchor["chain_count"] == 1
    assert anchor["head_row_hash"] == rows[-1].row_hash

    key_path = _audit_chain_key_file_path()
    if key_path.exists():
        key_path.unlink()

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.status == "tampered"
    assert result.reason == "audit-chain secret unavailable for keyed rows"


def test_near_simultaneous_invokes_produce_linear_chain(db):
    name = "test.chain_threaded"
    barrier = threading.Barrier(3)

    def _execute(_db, params: _ChainParams, _ctx: ActionContext):
        barrier.wait(timeout=5)
        return (
            {"value": params.value},
            ChangeSpec(
                domains=["test"],
                target_ids=[params.value],
                before={"value": "before"},
                after={"value": params.value},
            ),
        )

    registry.register(
        ActionRegistration(
            name=name,
            params_model=_ChainParams,
            execute=_execute,
            domains=["test"],
        )
    )
    try:
        results = []
        errors = []

        def _worker(value: str) -> None:
            try:
                results.append(_invoke(db, name, value))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [
            threading.Thread(target=_worker, args=(value,))
            for value in ("one", "two")
        ]
        for thread in threads:
            thread.start()
        barrier.wait(timeout=5)
        for thread in threads:
            thread.join(timeout=5)

        assert errors == []
        assert len(results) == 2
        assert verify_audit_chain(db).ok is True

        rows = _audit_rows(db)
        assert len(rows) == 2
        assert [row.chain_seq for row in rows] == [1, 2]
        assert len({row.chain_seq for row in rows}) == 2
        assert rows[0].prev_hash is None
        assert rows[1].prev_hash == rows[0].row_hash
        assert len({json.dumps(row.prev_hash) for row in rows}) == 2
    finally:
        registry._actions.pop(name, None)
