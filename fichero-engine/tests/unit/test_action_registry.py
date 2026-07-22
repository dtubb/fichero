"""Unit tests for the audited action layer keystone (EPIC #1848 / #2013).

Covers:
  * the registry choke point — register a dummy action, invoke it, and assert
    (a) the returned ActionResult, (b) a persisted ActionAudit row, and
    (c) that emit_change fired (monkeypatched spy, mirroring test_change_stream).
  * the entity.merge pilot via the registry — the merge effect lands, an
    ActionAudit row is written, and undo (entity.unmerge via invert) reverses it.
  * GET /api/actions/registry lists entity.merge.

Uses the shared conftest fixtures: ``db`` (a real Database on a temp .fichero
package) and ``client`` (TestClient with the library-path header).
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

# Importing the route module registers the entity.merge / entity.unmerge actions
# via the @action decorator at import time.
import fichero.api.routes.kg_entity_curation  # noqa: F401
from fichero.actions.registry import ActionContext, ChangeSpec, registry
from fichero.models import ActionAudit
from fichero.models.knowledge import KnowledgeEntity


# ---------------------------------------------------------------------------
# Registry choke point — dummy action
# ---------------------------------------------------------------------------


class _DummyParams(BaseModel):
    value: str


@pytest.fixture
def dummy_action():
    """Register a throwaway action and clean it out of the global registry."""
    name = "test.dummy"

    def _execute(db, params: _DummyParams, ctx: ActionContext):
        return (
            {"echo": params.value},
            ChangeSpec(
                domains=["test"],
                target_ids=["dummy-1"],
                before={"v": "old"},
                after={"v": params.value},
                emit_type="test.changed",
                entity_ids=["dummy-1"],
            ),
        )

    from fichero.actions.registry import ActionRegistration

    registry.register(
        ActionRegistration(
            name=name,
            params_model=_DummyParams,
            execute=_execute,
            domains=["test"],
            undoable=False,
        )
    )
    yield name
    registry._actions.pop(name, None)


class TestRegistryInvoke:
    def test_invoke_returns_result_writes_audit_and_emits(
        self, db, dummy_action, monkeypatch
    ):
        # Spy on emit_change as referenced inside the registry module.
        calls = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )

        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")
        result = registry.invoke(db, dummy_action, {"value": "hello"}, ctx)

        # (a) ActionResult shape
        assert result.ok is True
        assert result.result == {"echo": "hello"}
        assert result.changed_domains == ["test"]
        assert result.audit_id

        # (b) an ActionAudit row was persisted
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "test.dummy"
        assert audit.actor == "ui"
        assert audit.target_ids == ["dummy-1"]
        assert audit.params == {"value": "hello"}
        assert audit.before == {"v": "old"}
        assert audit.after == {"v": "hello"}
        assert audit.undone is False

        # (c) emit_change fired once with the typed change event
        assert len(calls) == 1
        _args, kwargs = calls[0]
        assert kwargs["type"] == "test.changed"
        assert kwargs["entity_ids"] == ["dummy-1"]
        assert kwargs["actor"] == "ui"

    def test_invoke_validates_params(self, db, dummy_action):
        from pydantic import ValidationError

        ctx = ActionContext(library_path="/lib/test.fichero")
        with pytest.raises(ValidationError):
            registry.invoke(db, dummy_action, {"wrong": "field"}, ctx)

    def test_invoke_unknown_action_raises(self, db):
        from fichero.actions.registry import ActionNotFoundError

        ctx = ActionContext(library_path="/lib/test.fichero")
        with pytest.raises(ActionNotFoundError):
            registry.invoke(db, "does.not.exist", {}, ctx)

    def test_emit_skipped_without_library_path(self, db, dummy_action, monkeypatch):
        calls = []
        monkeypatch.setattr(
            "fichero.api.change_stream.emit_change",
            lambda *a, **k: calls.append((a, k)),
        )
        ctx = ActionContext(actor="ui", library_path=None)
        registry.invoke(db, dummy_action, {"value": "x"}, ctx)
        # No library path -> nothing to broadcast to, but the audit still wrote.
        assert calls == []


# ---------------------------------------------------------------------------
# entity.merge pilot via the registry
# ---------------------------------------------------------------------------


class TestEntityMergeAction:
    def _two_entities(self, db) -> tuple[KnowledgeEntity, KnowledgeEntity]:
        absorber = KnowledgeEntity(canonical_name="Davidson", aliases=["D. Davidson"])
        absorbed = KnowledgeEntity(canonical_name="Davidson, D.", aliases=["DD"])
        db.save(absorber)
        db.save(absorbed)
        return absorber, absorbed

    def test_merge_via_registry_effect_and_audit(self, db):
        absorber, absorbed = self._two_entities(db)
        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")

        result = registry.invoke(
            db,
            "entity.merge",
            {
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
            ctx,
        )

        # merge effect: absorbed entity now points at the absorber
        reloaded = db.get(KnowledgeEntity, absorbed.id)
        assert reloaded.merged_into_id == absorber.id

        # an ActionAudit row exists for entity.merge
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "entity.merge"
        assert absorber.id in audit.target_ids
        # the after-payload carries the EntityMergeAudit id used by undo
        assert audit.after and audit.after.get("entity_merge_audit_id")

    def test_undo_reverses_merge(self, db):
        absorber, absorbed = self._two_entities(db)
        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")

        merge_result = registry.invoke(
            db,
            "entity.merge",
            {
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
            ctx,
        )
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id == absorber.id

        # Drive undo the way the generic undo endpoint does: read the audit,
        # ask the action for its inverse, invoke the inverse.
        audit = db.get(ActionAudit, merge_result.audit_id)
        reg = registry.get(audit.action_name)
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(audit.before, audit.after, ctx)
        assert inverse is not None
        inv_name, inv_params = inverse
        assert inv_name == "entity.unmerge"

        registry.invoke(db, inv_name, inv_params, ctx)

        # merge reversed: merged_into_id cleared
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id is None

    def test_unmerge_undo_remerges_same_entities(self, db):
        absorber, absorbed = self._two_entities(db)
        ctx = ActionContext(actor="ui", library_path="/lib/test.fichero")

        merge_result = registry.invoke(
            db,
            "entity.merge",
            {
                "absorbing_entity_id": absorber.id,
                "absorbed_entity_ids": [absorbed.id],
            },
            ctx,
        )
        merge_audit = db.get(ActionAudit, merge_result.audit_id)
        unmerge_name, unmerge_params = registry.get("entity.merge").invert(
            merge_audit.before,
            merge_audit.after,
            ctx,
        )
        assert unmerge_name == "entity.unmerge"

        unmerge_result = registry.invoke(db, unmerge_name, unmerge_params, ctx)
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id is None

        unmerge_audit = db.get(ActionAudit, unmerge_result.audit_id)
        reg = registry.get(unmerge_audit.action_name)
        assert reg.undoable and reg.invert is not None
        inverse = reg.invert(unmerge_audit.before, unmerge_audit.after, ctx)
        assert inverse is not None
        inv_name, inv_params = inverse
        assert inv_name == "entity.merge"

        registry.invoke(db, inv_name, inv_params, ctx)
        assert db.get(KnowledgeEntity, absorbed.id).merged_into_id == absorber.id


# ---------------------------------------------------------------------------
# Generic listing endpoint
# ---------------------------------------------------------------------------


class TestActionsRegistryRoute:
    def test_get_registry_lists_entity_merge(self, client):
        resp = client.get("/api/actions/registry")
        assert resp.status_code == 200
        body = resp.json()
        names = {item["name"] for item in body["items"]}
        assert "entity.merge" in names
        assert body["count"] == len(body["items"])
        # entity.merge advertises its params schema + undoable flag
        merge = next(i for i in body["items"] if i["name"] == "entity.merge")
        assert merge["undoable"] is True
        assert "absorbing_entity_id" in merge["params_schema"]["properties"]

    def test_invoke_via_route_writes_audit(self, client, db):
        absorber = KnowledgeEntity(canonical_name="Smith")
        absorbed = KnowledgeEntity(canonical_name="Smith, J.")
        db.save(absorber)
        db.save(absorbed)

        resp = client.post(
            "/api/actions/invoke",
            json={
                "name": "entity.merge",
                "params": {
                    "absorbing_entity_id": absorber.id,
                    "absorbed_entity_ids": [absorbed.id],
                },
            },
        )
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["ok"] is True
        assert payload["audit_id"]
        assert set(payload["changed_domains"]) == {"entity", "claim"}
        assert db.get(ActionAudit, payload["audit_id"]) is not None
