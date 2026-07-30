"""Unit tests for the classification / ontology audited actions (EPIC #1848 / #2014).

Domain: CLASSIFICATION + ONTOLOGY. Covers, for every registered action:
  (a) the effect lands AND an ActionAudit row is written (actor / target_ids /
      before / after correct);
  (b) undo reverses it (for undoable actions) and the delete<->restore redo
      chain is sane;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id, duplicate
      key, built-in protection, inactive framework, missing claim, idempotent
      add);
  (e) emit_change fires with the right type + ids (spy monkeypatched at the
      source ``fichero_server.api.change_stream.emit_change``).

These tests are MANAGER-run (workers don't run pytest). They mirror
``test_action_registry.py`` and reuse the shared ``db`` fixture (a real Database
on a temp .fichero package). Importing the route modules below registers the
actions via the ``@action`` decorator at import time.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from fastapi import HTTPException

# Importing the route modules registers their actions (classification.* /
# framework.* / interpretation.* / pattern.*) on the process-global registry.
import fichero_server.api.routes.document.classifications  # noqa: F401
import fichero_server.api.routes.interpretation.hermeneutics  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.models import ActionAudit, KnowledgeClaim
from fichero_server.models.knowledge import ClassificationDimension, ClassificationValue
from fichero_server.models.hermeneutics import (
    FrameworkType,
    InterpretiveActType,
    InterpretiveFramework,
    Interpretation,
    PatternInstance,
)


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def emit_spy(monkeypatch):
    """Spy on emit_change at the SOURCE module (where registry._emit imports it)."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        "fichero_server.api.change_stream.emit_change",
        lambda *a, **k: calls.append((a, k)),
    )
    return calls


def _undo(db, audit_id, ctx):
    """Drive undo exactly as the generic undo endpoint would: read the audit,
    ask the action for its inverse, invoke the inverse. Returns the inverse name."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None, f"{audit.action_name} not undoable"
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name


# ===========================================================================
# Classification actions (claim-kinds, epistemic-statuses, entity-types, …)
# ===========================================================================


class TestClassificationActions:
    def _custom_value(self, db, key="ethnographic") -> ClassificationValue:
        v = ClassificationValue(
            dimension=ClassificationDimension.claim_type,
            key=key,
            label="Ethnographic",
            color="#FF8800",
            is_builtin=False,
        )
        db.save(v)
        return v

    # -- create --------------------------------------------------------------

    def test_create_effect_and_audit(self, db, emit_spy):
        result = registry.invoke(
            db,
            "classification.create",
            {
                "dimension": "claim_type",
                "key": "ethnographic",
                "label": "Ethnographic",
                "color": "#FF8800",
            },
            _ctx(),
        )
        assert result.ok and result.changed_domains == ["classification"]

        # effect: a non-builtin value now exists
        rows = [
            v
            for v in db.query(ClassificationValue)
            if v.dimension == ClassificationDimension.claim_type and v.key == "ethnographic"
        ]
        assert len(rows) == 1
        created = rows[0]
        assert created.is_builtin is False

        # audit row written, with the produced id in target_ids + after
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "classification.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [created.id]
        assert audit.before is None
        assert audit.after and audit.after["key"] == "ethnographic"
        assert audit.undone is False

        # (e) emit fired with the right type
        assert len(emit_spy) == 1
        assert emit_spy[0][1]["type"] == "classification.created"

    def test_create_undo_deletes(self, db):
        ctx = _ctx()
        result = registry.invoke(
            db,
            "classification.create",
            {"dimension": "entity_type", "key": "plant_species", "label": "Plant species"},
            ctx,
        )
        created_id = result.result["id"]
        assert db.get(ClassificationValue, created_id) is not None

        inv = _undo(db, result.audit_id, ctx)
        assert inv == "classification.delete"
        assert db.get(ClassificationValue, created_id) is None

    def test_create_validation_rejects_bad_input(self, db):
        ctx = _ctx()
        # missing required 'label'
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "classification.create", {"dimension": "claim_type", "key": "x"}, ctx
            )
        # invalid dimension enum
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "classification.create",
                {"dimension": "not_a_dimension", "key": "x", "label": "X"},
                ctx,
            )

    def test_create_duplicate_key_rejected(self, db):
        """A naive create would let two (dimension, key) rows accumulate."""
        self._custom_value(db, key="ethnographic")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "classification.create",
                {"dimension": "claim_type", "key": "ethnographic", "label": "Dup"},
                _ctx(),
            )
        assert exc.value.status_code == 409

    # -- patch ---------------------------------------------------------------

    def test_patch_effect_audit_and_undo(self, db):
        ctx = _ctx()
        value = self._custom_value(db, key="contested")
        result = registry.invoke(
            db,
            "classification.patch",
            {"value_id": value.id, "label": "Contested!", "color": "#000000"},
            ctx,
        )
        reloaded = db.get(ClassificationValue, value.id)
        assert reloaded.label == "Contested!"
        assert reloaded.color == "#000000"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "classification.patch"
        assert audit.before["label"] == "Ethnographic"
        assert audit.after["label"] == "Contested!"

        # undo restores the prior label + color
        _undo(db, result.audit_id, ctx)
        restored = db.get(ClassificationValue, value.id)
        assert restored.label == "Ethnographic"
        assert restored.color == "#FF8800"

    def test_patch_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "classification.patch", {"value_id": "nope", "label": "X"}, _ctx()
            )
        assert exc.value.status_code == 404

    # -- delete --------------------------------------------------------------

    def test_delete_effect_audit_and_undo_restores_same_id(self, db):
        ctx = _ctx()
        value = self._custom_value(db, key="folkloric")
        vid = value.id
        result = registry.invoke(db, "classification.delete", {"value_id": vid}, ctx)
        assert db.get(ClassificationValue, vid) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "classification.delete"
        assert audit.before and audit.before["id"] == vid
        assert audit.after is None

        # undo -> classification.restore re-materializes the SAME id
        inv = _undo(db, result.audit_id, ctx)
        assert inv == "classification.restore"
        back = db.get(ClassificationValue, vid)
        assert back is not None and back.key == "folkloric"

    def test_delete_builtin_rejected(self, db):
        """Built-in values must never be deletable (409), even via the action."""
        builtin = ClassificationValue(
            dimension=ClassificationDimension.epistemic_status,
            key="confirmed",
            label="Confirmed",
            is_builtin=True,
        )
        db.save(builtin)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "classification.delete", {"value_id": builtin.id}, _ctx())
        assert exc.value.status_code == 409
        assert db.get(ClassificationValue, builtin.id) is not None

    def test_delete_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "classification.delete", {"value_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_restore_then_undo_deletes_redo_chain(self, db):
        """delete -> restore -> undo(restore) == delete again (redo is sane)."""
        ctx = _ctx()
        value = self._custom_value(db, key="liminal")
        vid = value.id
        del_res = registry.invoke(db, "classification.delete", {"value_id": vid}, ctx)
        restore_name = _undo(db, del_res.audit_id, ctx)
        assert restore_name == "classification.restore"
        assert db.get(ClassificationValue, vid) is not None

        # the restore is itself audited + undoable -> undoing it deletes again
        restore_audit = [
            a for a in db.all(ActionAudit) if a.action_name == "classification.restore"
        ][-1]
        _undo(db, restore_audit.id, ctx)
        assert db.get(ClassificationValue, vid) is None


class TestClassificationRoutesWriteActionAudit:
    def test_create_patch_delete_routes_write_action_audit(self, client, db):
        created = client.post(
            "/api/classifications",
            json={
                "dimension": "node_class",
                "key": "route-audit",
                "label": "Route Audit",
                "color": "#123456",
            },
        )
        assert created.status_code == 200
        value_id = created.json()["id"]
        assert db.all(ActionAudit)[-1].action_name == "classification.create"
        assert db.all(ActionAudit)[-1].target_ids == [value_id]

        patched = client.patch(
            f"/api/classifications/{value_id}",
            json={"label": "Route Audit Updated", "sort_order": 3},
        )
        assert patched.status_code == 200
        assert db.all(ActionAudit)[-1].action_name == "classification.patch"
        assert db.all(ActionAudit)[-1].target_ids == [value_id]

        deleted = client.delete(f"/api/classifications/{value_id}")
        assert deleted.status_code == 204
        assert db.all(ActionAudit)[-1].action_name == "classification.delete"
        assert db.all(ActionAudit)[-1].target_ids == [value_id]


# ===========================================================================
# Interpretive-framework / interpretation / pattern actions (ontology)
# ===========================================================================


class TestInterpretationOntologyActions:
    def _framework(self, db, fid="fwk-1", active=True) -> InterpretiveFramework:
        fw = InterpretiveFramework(
            id=fid,
            name="Marxist Lens",
            framework_type=FrameworkType.theoretical,
            description="Materialist analysis",
            is_active=active,
        )
        db.save(fw)
        return fw

    def _claim(self, db, cid="claim-1") -> KnowledgeClaim:
        c = KnowledgeClaim(id=cid, text="Labor is alienated.", source_document_id="d", entity_ids=[])
        db.save(c)
        return c

    def _interpretation(self, db, iid="interp-1", fid="fwk-1", cid="claim-1") -> Interpretation:
        it = Interpretation(
            id=iid,
            framework_id=fid,
            claim_id=cid,
            interpretation_text="Reflects class struggle.",
            act=InterpretiveActType.contextualizing,
            predicate="reflects",
        )
        db.save(it)
        return it

    def _pattern(self, db, pid="pat-1") -> PatternInstance:
        p = PatternInstance(
            id=pid,
            name="Recurring alienation",
            description="Alienation motif recurs",
            pattern_type="thematic",
            claim_ids=[],
        )
        db.save(p)
        return p

    # -- framework.create ----------------------------------------------------

    def test_framework_create_effect_audit_emit(self, db, emit_spy):
        result = registry.invoke(
            db,
            "framework.create",
            {
                "name": "Postcolonial Theory",
                "framework_type": "theoretical",
                "description": "Examines colonial legacies.",
            },
            _ctx(),
        )
        fid = result.result["id"]
        saved = db.get(InterpretiveFramework, fid)
        assert saved is not None and saved.is_active is True

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "framework.create"
        assert audit.target_ids == [fid]
        # create is not undoable (no clean hard-delete)
        assert registry.get("framework.create").undoable is False

        assert len(emit_spy) == 1
        _a, kw = emit_spy[0]
        assert kw["type"] == "interpretation.created"
        assert kw["interpretation_ids"] == [fid]

    def test_framework_create_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "framework.create", {"name": "X", "framework_type": "bogus", "description": "d"}, _ctx()
            )

    # -- framework.update ----------------------------------------------------

    def test_framework_update_effect_audit_undo(self, db):
        ctx = _ctx()
        self._framework(db, "fwk-u")
        result = registry.invoke(
            db, "framework.update", {"framework_id": "fwk-u", "name": "Renamed Lens"}, ctx
        )
        assert db.get(InterpretiveFramework, "fwk-u").name == "Renamed Lens"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["name"] == "Marxist Lens"
        assert audit.after["name"] == "Renamed Lens"

        _undo(db, result.audit_id, ctx)
        assert db.get(InterpretiveFramework, "fwk-u").name == "Marxist Lens"

    def test_framework_update_unknown_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "framework.update", {"framework_id": "ghost", "name": "X"}, _ctx())
        assert exc.value.status_code == 404

    # -- framework.delete (soft) ---------------------------------------------

    def test_framework_delete_deactivates_and_undo_reactivates(self, db):
        ctx = _ctx()
        self._framework(db, "fwk-d", active=True)
        result = registry.invoke(db, "framework.delete", {"framework_id": "fwk-d"}, ctx)
        assert db.get(InterpretiveFramework, "fwk-d").is_active is False

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "framework.delete"
        assert audit.before["is_active"] is True

        inv = _undo(db, result.audit_id, ctx)
        assert inv == "framework.update"
        assert db.get(InterpretiveFramework, "fwk-d").is_active is True

    def test_framework_delete_unknown_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "framework.delete", {"framework_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    # -- interpretation.create -----------------------------------------------

    def test_interpretation_create_effect_audit_emit(self, db, emit_spy):
        self._framework(db, "fwk-i")
        self._claim(db, "claim-i")
        result = registry.invoke(
            db,
            "interpretation.create",
            {
                "framework_id": "fwk-i",
                "claim_id": "claim-i",
                "interpretation_text": "Reflects class struggle.",
                "act": "contextualizing",
            },
            _ctx(),
        )
        iid = result.result["id"]
        assert db.get(Interpretation, iid) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "interpretation.create"
        assert audit.target_ids == [iid]

        _a, kw = emit_spy[0]
        assert kw["type"] == "interpretation.created"
        assert kw["interpretation_ids"] == [iid]
        assert kw["claim_ids"] == ["claim-i"]

    def test_interpretation_create_inactive_framework_400(self, db):
        self._framework(db, "fwk-off", active=False)
        self._claim(db, "claim-x")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "interpretation.create",
                {
                    "framework_id": "fwk-off",
                    "claim_id": "claim-x",
                    "interpretation_text": "t",
                    "act": "reading",
                },
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_interpretation_create_missing_claim_400(self, db):
        self._framework(db, "fwk-nc")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "interpretation.create",
                {"framework_id": "fwk-nc", "interpretation_text": "t", "act": "reading"},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_interpretation_create_unknown_claim_404(self, db):
        self._framework(db, "fwk-uc")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "interpretation.create",
                {
                    "framework_id": "fwk-uc",
                    "claim_id": "ghost-claim",
                    "interpretation_text": "t",
                    "act": "reading",
                },
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_interpretation_create_unknown_framework_404(self, db):
        self._claim(db, "claim-of")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "interpretation.create",
                {
                    "framework_id": "ghost-fwk",
                    "claim_id": "claim-of",
                    "interpretation_text": "t",
                    "act": "reading",
                },
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_interpretation_create_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "interpretation.create",
                {"framework_id": "f", "claim_id": "c", "act": "reading"},  # no interpretation_text
                _ctx(),
            )

    # -- interpretation.update -----------------------------------------------

    def test_interpretation_update_effect_audit_undo(self, db):
        ctx = _ctx()
        self._framework(db, "fwk-iu")
        self._claim(db, "claim-iu")
        self._interpretation(db, "interp-u", "fwk-iu", "claim-iu")
        result = registry.invoke(
            db,
            "interpretation.update",
            {"interpretation_id": "interp-u", "interpretation_text": "Revised reading.", "predicate": "reveals"},
            ctx,
        )
        updated = db.get(Interpretation, "interp-u")
        assert updated.interpretation_text == "Revised reading."
        # predicate edit recomputes predicate_canonical (side effect preserved);
        # "reveals" is a recognized hermeneutic predicate -> canonicalizes to itself.
        assert updated.predicate == "reveals"
        assert updated.predicate_canonical == "reveals"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["interpretation_text"] == "Reflects class struggle."

        _undo(db, result.audit_id, ctx)
        reverted = db.get(Interpretation, "interp-u")
        assert reverted.interpretation_text == "Reflects class struggle."
        assert reverted.predicate == "reflects"

    def test_interpretation_update_unknown_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "interpretation.update", {"interpretation_id": "ghost", "interpretation_text": "x"}, _ctx()
            )
        assert exc.value.status_code == 404

    # -- pattern.create / update / add_claim ---------------------------------

    def test_pattern_create_effect_audit_emit(self, db, emit_spy):
        result = registry.invoke(
            db,
            "pattern.create",
            {"name": "Motif A", "description": "desc", "pattern_type": "thematic"},
            _ctx(),
        )
        pid = result.result["id"]
        assert db.get(PatternInstance, pid) is not None
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "pattern.create"
        _a, kw = emit_spy[0]
        assert kw["type"] == "interpretation.created"
        assert kw["interpretation_ids"] == [pid]

    def test_pattern_create_validation(self, db):
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "pattern.create", {"name": "X", "pattern_type": "thematic"}, _ctx()  # no description
            )

    def test_pattern_update_effect_audit_undo(self, db):
        ctx = _ctx()
        self._pattern(db, "pat-u")
        result = registry.invoke(
            db, "pattern.update", {"pattern_id": "pat-u", "name": "Renamed motif"}, ctx
        )
        assert db.get(PatternInstance, "pat-u").name == "Renamed motif"
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["name"] == "Recurring alienation"

        _undo(db, result.audit_id, ctx)
        assert db.get(PatternInstance, "pat-u").name == "Recurring alienation"

    def test_pattern_update_unknown_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "pattern.update", {"pattern_id": "ghost", "name": "X"}, _ctx())
        assert exc.value.status_code == 404

    def test_pattern_add_claim_appends_and_emits(self, db, emit_spy):
        self._pattern(db, "pat-a")
        result = registry.invoke(
            db, "pattern.add_claim", {"pattern_id": "pat-a", "claim_id": "c-99"}, _ctx()
        )
        p = db.get(PatternInstance, "pat-a")
        assert "c-99" in p.claim_ids
        assert p.frequency == 1
        assert db.get(ActionAudit, result.audit_id) is not None
        assert len(emit_spy) == 1
        assert emit_spy[0][1]["type"] == "interpretation.updated"
        assert emit_spy[0][1]["claim_ids"] == ["c-99"]

    def test_pattern_add_claim_idempotent_no_emit(self, db, emit_spy):
        """Adding the same claim twice must not duplicate it NOR re-emit."""
        self._pattern(db, "pat-idem")
        registry.invoke(db, "pattern.add_claim", {"pattern_id": "pat-idem", "claim_id": "c-1"}, _ctx())
        emit_spy.clear()
        # second add is a no-op
        result = registry.invoke(
            db, "pattern.add_claim", {"pattern_id": "pat-idem", "claim_id": "c-1"}, _ctx()
        )
        p = db.get(PatternInstance, "pat-idem")
        assert p.claim_ids == ["c-1"]  # not duplicated
        # the action still audited (it ran) but emitted nothing (no change)
        assert db.get(ActionAudit, result.audit_id) is not None
        assert emit_spy == []

    def test_pattern_add_claim_unknown_pattern_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "pattern.add_claim", {"pattern_id": "ghost", "claim_id": "c"}, _ctx())
        assert exc.value.status_code == 404
