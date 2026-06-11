from __future__ import annotations

import asyncio
import json
import threading

import pytest
from pydantic import BaseModel

from fichero.actions.audit_chain import verify_audit_chain
from fichero.actions.registry import (
    ActionContext,
    ActionRegistration,
    ChangeSpec,
    registry,
)
from fichero.api.routes.actions_registry import undo_action
from fichero.models import ActionAudit


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
    return sorted(db.all(ActionAudit), key=lambda a: (a.created_at, a.id))


def test_appended_actions_verify_and_link_contiguously(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    result = verify_audit_chain(db)
    assert result.ok is True
    assert result.checked == 3

    rows = _audit_rows(db)
    assert rows[0].prev_hash is None
    for prev, current in zip(rows, rows[1:]):
        assert current.prev_hash == prev.row_hash
        assert current.row_hash


def test_verification_detects_edited_historical_row(db, chain_actions):
    _invoke(db, chain_actions, "one")
    _invoke(db, chain_actions, "two")

    first = _audit_rows(db)[0]
    db._execute(
        'UPDATE "actionaudits" SET actor = $actor WHERE id = $id',
        {"actor": "mallory", "id": first.id},
    )

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == first.id
    assert result.reason == "row_hash mismatch"


def test_verification_detects_deleted_middle_row(db, chain_actions):
    for value in ["one", "two", "three"]:
        _invoke(db, chain_actions, value)

    rows = _audit_rows(db)
    db._execute('DELETE FROM "actionaudits" WHERE id = $id', {"id": rows[1].id})

    result = verify_audit_chain(db)
    assert result.ok is False
    assert result.broken_audit_id == rows[2].id
    assert result.reason == "prev_hash mismatch"


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


def test_undo_mutates_undone_without_breaking_chain(db, chain_actions):
    forward = _invoke(db, chain_actions, "one")

    result = asyncio.run(
        undo_action(
            forward.audit_id,
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
        assert rows[0].prev_hash is None
        assert rows[1].prev_hash == rows[0].row_hash
        assert len({json.dumps(row.prev_hash) for row in rows}) == 2
    finally:
        registry._actions.pop(name, None)
