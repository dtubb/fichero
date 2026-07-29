"""Unit tests for the ACTION-LIBRARY audited actions (EPIC #1848 / sweep #2014).

The workflow Action Library's two mutating ops (create / delete) are wrapped by
registered, audited actions named ``actionlib.*`` (NOT ``action.*`` — these
mutate the DuckDB-backed workflow Action Library via ``ActionStore``, not the
knowledge graph). This suite drives each one through ``registry.invoke`` (the
single audited choke point) and asserts, per the test bar:

  (a) the effect lands + an ActionAudit row is written (actor/target/before/after);
  (b) undo reverses it (undoable actions) AND undo-of-undo / restore round-trips;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id -> 404,
      built-in delete -> 403, double-delete idempotency);
  (e) emit fires with the right type + ids (monkeypatched at the change_stream
      source).

The MANAGER runs the suite — workers do not execute pytest (RAM economy).
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# Importing the route module registers the actionlib.* actions via @action.
import fichero_server.api.routes.actions  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit
from fichero_server.workflows.action_store import ActionStore


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path="/lib/test.fichero")


def _create_params(name: str = "My Custom Action", **overrides) -> dict:
    params = {
        "name": name,
        "description": "does a thing",
        "category": "custom",
        "tags": ["x", "y"],
        "node_template": {"type": "llm", "data": {"prompt": "hi"}},
    }
    params.update(overrides)
    return params


@pytest.fixture
def emit_spy(monkeypatch):
    """Collect emit_change calls fired by the registry (best-effort broadcast)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _emit_types(calls: list[tuple]) -> set[str]:
    return {k.get("type") for _a, k in calls}


# ===========================================================================
# actionlib.create  (undoable: the inverse deletes the inserted row)
# ===========================================================================


class TestActionlibCreate:
    def test_create_effect_audit_and_emit(self, db, emit_spy):
        result = registry.invoke(db, "actionlib.create", _create_params(), _ctx())
        store = ActionStore(db)

        # (a) effect landed in the store
        new_id = result.result["id"]
        persisted = store.get(new_id)
        assert persisted is not None
        assert persisted.name == "My Custom Action"
        assert persisted.is_builtin is False

        # (a) audit row written with the right shape
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "actionlib.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.after == {"action_id": new_id, "created": True}
        assert audit.before is None
        assert result.changed_domains == ["action"]

        # (e) emit fired with the action.created type + the new id
        assert "action.created" in _emit_types(emit_spy)
        assert any(k.get("entity_ids") == [new_id] for _a, k in emit_spy)

    def test_undo_create_deletes_action(self, db, emit_spy):
        result = registry.invoke(db, "actionlib.create", _create_params("Temp"), _ctx())
        store = ActionStore(db)
        new_id = result.result["id"]
        assert store.get(new_id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("actionlib.create")
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None and inverse[0] == "actionlib.delete"
        assert inverse[1] == {"action_id": new_id}

        registry.invoke(db, inverse[0], inverse[1], _ctx())
        assert store.get(new_id) is None

    def test_undo_of_undo_restores_created_action(self, db, emit_spy):
        # create -> undo(=delete) -> undo-of-undo(=restore) should round-trip.
        create = registry.invoke(db, "actionlib.create", _create_params("RoundTrip"), _ctx())
        store = ActionStore(db)
        new_id = create.result["id"]

        # undo the create (delete)
        del_result = registry.invoke(
            db, "actionlib.delete", {"action_id": new_id}, _ctx()
        )
        assert store.get(new_id) is None

        # undo the delete (restore) -> the action comes back with its id
        del_audit = db.get(ActionAudit, del_result.audit_id)
        reg = registry.get("actionlib.delete")
        inverse = reg.invert(del_audit.before, del_audit.after, _ctx())
        assert inverse is not None and inverse[0] == "actionlib.restore"
        registry.invoke(db, inverse[0], inverse[1], _ctx())

        restored = store.get(new_id)
        assert restored is not None
        assert restored.name == "RoundTrip"

    def test_create_param_validation_rejects_missing_name(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "actionlib.create", {}, _ctx())


# ===========================================================================
# actionlib.delete  (undoable: the inverse re-inserts the snapshot)
# ===========================================================================


class TestActionlibDelete:
    def _seed_custom(self, db, name: str = "ToDelete") -> str:
        result = registry.invoke(db, "actionlib.create", _create_params(name), _ctx())
        return result.result["id"]

    def test_delete_effect_audit_and_emit(self, db, emit_spy):
        action_id = self._seed_custom(db)
        store = ActionStore(db)
        assert store.get(action_id) is not None

        result = registry.invoke(db, "actionlib.delete", {"action_id": action_id}, _ctx())

        # (a) effect: gone from the store
        assert store.get(action_id) is None

        # (a) audit row with the full before-snapshot (the undo payload)
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "actionlib.delete"
        assert audit.target_ids == [action_id]
        assert audit.before and audit.before["action"]["id"] == action_id
        assert audit.after == {"action_id": action_id, "deleted": True}

        # (e) emit fired with action.deleted + the id
        assert "action.deleted" in _emit_types(emit_spy)
        assert any(k.get("entity_ids") == [action_id] for _a, k in emit_spy)

    def test_undo_delete_restores_action(self, db, emit_spy):
        action_id = self._seed_custom(db, "Recoverable")
        store = ActionStore(db)
        before_snapshot = store.get(action_id).model_dump(mode="json")

        result = registry.invoke(db, "actionlib.delete", {"action_id": action_id}, _ctx())
        assert store.get(action_id) is None

        audit = db.get(ActionAudit, result.audit_id)
        reg = registry.get("actionlib.delete")
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, _ctx())
        assert inverse is not None and inverse[0] == "actionlib.restore"

        registry.invoke(db, inverse[0], inverse[1], _ctx())
        restored = store.get(action_id)
        assert restored is not None
        # same id + name + content survive the round trip
        assert restored.id == action_id
        assert restored.name == before_snapshot["name"]
        assert restored.node_template == before_snapshot["node_template"]

    def test_delete_unknown_id_raises_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "actionlib.delete", {"action_id": "does-not-exist"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_builtin_raises_403(self, db):
        # Built-ins are seeded by ActionStore(db); they must never be deletable.
        ActionStore(db)  # ensures builtins exist
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "actionlib.delete", {"action_id": "builtin-llm-prompt"}, _ctx()
            )
        assert exc.value.status_code == 403

    def test_double_delete_is_404_not_silent_noop(self, db, emit_spy):
        # A naive impl might silently no-op the second delete; ours 404s because
        # the row is already gone — and crucially writes NO audit for the failure.
        action_id = self._seed_custom(db, "DeleteTwice")
        registry.invoke(db, "actionlib.delete", {"action_id": action_id}, _ctx())
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "actionlib.delete", {"action_id": action_id}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_param_validation_rejects_missing_id(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "actionlib.delete", {}, _ctx())


# ===========================================================================
# actionlib.restore  (the delete inverse — not itself undoable)
# ===========================================================================


class TestActionlibRestore:
    def test_restore_reinserts_snapshot(self, db, emit_spy):
        create = registry.invoke(db, "actionlib.create", _create_params("Snap"), _ctx())
        store = ActionStore(db)
        action_id = create.result["id"]
        snapshot = store.get(action_id).model_dump(mode="json")

        # remove it directly, then restore via the action
        store.delete(action_id)
        assert store.get(action_id) is None

        result = registry.invoke(db, "actionlib.restore", {"action": snapshot}, _ctx())
        assert store.get(action_id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "actionlib.restore"
        assert audit.target_ids == [action_id]
        assert audit.after == {"action_id": action_id, "restored": True}
        assert "action.created" in _emit_types(emit_spy)

    def test_restore_param_validation_rejects_missing_action(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(db, "actionlib.restore", {}, _ctx())


# ===========================================================================
# Registry wiring
# ===========================================================================


class TestActionlibRegistration:
    def test_actions_registered_with_expected_flags(self, db):
        names = set(registry.names())
        assert {"actionlib.create", "actionlib.delete", "actionlib.restore"} <= names
        assert registry.get("actionlib.create").undoable is True
        assert registry.get("actionlib.delete").undoable is True
        assert registry.get("actionlib.restore").undoable is False
