"""Unit tests for the CLAIM-domain audited actions (EPIC #1848 / #2014).

The claim sweep registers every mutating claim endpoint as an action that WRAPS
the route's proven ``*_impl`` (iterate-not-replace) and runs through
``registry.invoke`` — the single audited write path. These tests drive each
action via the registry (the same path chat tools / App Intents / the
``/api/actions/invoke`` route use) and, per the project test bar
([[would-more-tests-catch-more-issues]]), assert MORE than the happy path:

  (a) the effect lands AND an ActionAudit row is written (actor/target_ids/
      before/after correct);
  (b) undo reverses it (for undoable actions) and undo-of-undo is sane;
  (c) param validation rejects bad input (ValidationError);
  (d) >=1 edge/failure case a naive impl would get wrong (unknown id,
      self-reference, already-merged, idempotent no-op, link restoration);
  (e) the emit fires with the right type + ids (emit_change monkeypatched at
      the SOURCE module, mirroring test_action_registry).

The MANAGER runs the full suite; this worker only writes the tests.

Importing the three claim route modules registers their @action decorators.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

# Importing the route modules registers the claim.* actions at import time.
import fichero.api.routes.claims  # noqa: F401
import fichero.api.routes.claim_links  # noqa: F401
import fichero.api.routes.claim_curation  # noqa: F401
from fichero.actions.registry import ActionContext, registry
from fichero.models import ActionAudit, Document, DocType
from fichero.knowledge_models import (
    ClaimCurationState,
    ClaimRelationType,
    KnowledgeClaim,
    KnowledgeClaimLink,
    KnowledgeEntity,
)


LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


@pytest.fixture
def spy_emit(monkeypatch):
    """Capture emit_change calls from both claim emit paths."""
    calls: list[tuple] = []

    def spy(*a, **k):
        calls.append((a, k))

    monkeypatch.setattr("fichero.api.routes.claims.emit_change", spy)
    monkeypatch.setattr("fichero.api.change_stream.emit_change", spy)
    return calls


def _save_claim(db, text="A claim", **kwargs) -> KnowledgeClaim:
    # KnowledgeClaim requires text + source_document_id; default the source here
    # (a placeholder id is fine — _save_claim writes the row directly, bypassing
    # the create_claim_impl source-doc-exists check).
    kwargs.setdefault("source_document_id", "doc-claim-src")
    claim = KnowledgeClaim(text=text, **kwargs)
    db.save(claim)
    return claim


def _invoke_inverse(db, audit_id, ctx):
    """Drive undo the way the generic undo endpoint does: read the audit, ask
    the action for its inverse, invoke the inverse. Returns the inverse name."""
    audit = db.get(ActionAudit, audit_id)
    reg = registry.get(audit.action_name)
    assert reg.undoable and reg.invert is not None
    inverse = reg.invert(audit.before, audit.after, ctx)
    assert inverse is not None
    inv_name, inv_params = inverse
    registry.invoke(db, inv_name, inv_params, ctx)
    return inv_name


# ===========================================================================
# claim.create / claim.patch / claim.delete / claim.restore
# ===========================================================================


class TestClaimCrudActions:
    def test_create_effect_audit_and_emit(self, db, spy_emit):
        ent = KnowledgeEntity(canonical_name="Davidson")
        db.save(ent)
        src = Document(name="src", path="/tmp/src.pdf", doc_type=DocType.file)
        db.save(src)

        result = registry.invoke(
            db,
            "claim.create",
            {
                "text": "Davidson wrote about meaning",
                "entity_ids": [ent.id],
                "source_document_id": src.id,
            },
            _ctx(),
        )

        # (a) effect: the claim is persisted
        new_id = result.result["id"]
        persisted = db.get(KnowledgeClaim, new_id)
        assert persisted is not None
        assert persisted.text == "Davidson wrote about meaning"

        # (a) audit row written with the right shape
        audit = db.get(ActionAudit, result.audit_id)
        assert audit is not None
        assert audit.action_name == "claim.create"
        assert audit.actor == "ui"
        assert audit.target_ids == [new_id]
        assert audit.after == {"claim_id": new_id}

        # (e) emit fired with claim.updated + the new id
        assert len(spy_emit) == 1
        _args, kwargs = spy_emit[0]
        assert kwargs["type"] == "claim.updated"
        assert kwargs["claim_ids"] == [new_id]
        assert ent.id in kwargs["entity_ids"]

    def test_create_undo_deletes_then_undo_of_undo_restores(self, db):
        """(b) create -> undo (delete) removes it; the delete is itself undoable,
        so undo-of-undo (restore) brings it back — redo/undo chain is sane."""
        ctx = _ctx()
        src = Document(name="src", path="/tmp/src.pdf", doc_type=DocType.file)
        db.save(src)
        result = registry.invoke(
            db, "claim.create", {"text": "ephemeral", "source_document_id": src.id}, ctx
        )
        new_id = result.result["id"]
        assert db.get(KnowledgeClaim, new_id) is not None

        # undo create -> claim.delete
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.delete"
        assert db.get(KnowledgeClaim, new_id) is None

        # undo-of-undo: the delete audit inverts to claim.restore -> claim back
        del_audit = next(
            a for a in db.all(ActionAudit)
            if a.action_name == "claim.delete" and a.target_ids == [new_id]
        )
        reg = registry.get("claim.delete")
        inverse = reg.invert(del_audit.before, del_audit.after, ctx)
        registry.invoke(db, inverse[0], inverse[1], ctx)
        assert db.get(KnowledgeClaim, new_id) is not None

    def test_create_validation_rejects_missing_text(self, db):
        # (c) text is required
        with pytest.raises(ValidationError):
            registry.invoke(db, "claim.create", {"entity_ids": []}, _ctx())

    def test_create_unknown_entity_404(self, db):
        # (d) a naive impl would silently create a claim pointing at a ghost entity
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "claim.create", {"text": "x", "entity_ids": ["nope"]}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_create_manual_claim_without_source_persists(self, db):
        # (d) manually-asserted claims have no source document (#2019) — the model
        # allows a null source and create_claim_impl persists it.
        result = registry.invoke(db, "claim.create", {"text": "manual assertion"}, _ctx())
        persisted = db.get(KnowledgeClaim, result.result["id"])
        assert persisted is not None
        assert persisted.source_document_id is None
        assert db.get(ActionAudit, result.audit_id) is not None

    def test_patch_effect_audit_and_undo(self, db):
        claim = _save_claim(db, text="old text", confidence=0.4)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.patch",
            {"claim_id": claim.id, "patch": {"text": "new text", "confidence": 0.9}},
            ctx,
        )
        reloaded = db.get(KnowledgeClaim, claim.id)
        assert reloaded.text == "new text"
        assert reloaded.confidence == 0.9

        # audit captured the before-snapshot (the undo payload)
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.patch"
        assert audit.before["text"] == "old text"
        assert audit.before["confidence"] == 0.4

        # (b) undo (restore) reverts BOTH changed fields
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.restore"
        restored = db.get(KnowledgeClaim, claim.id)
        assert restored.text == "old text"
        assert restored.confidence == 0.4

    def test_patch_only_touches_provided_fields(self, db):
        """(d) exclude-unset semantics: a field omitted from the patch must be
        left untouched (a naive full-replace impl would wipe it)."""
        claim = _save_claim(db, text="keep me", confidence=0.7)
        registry.invoke(
            db, "claim.patch", {"claim_id": claim.id, "patch": {"confidence": 0.1}}, _ctx()
        )
        reloaded = db.get(KnowledgeClaim, claim.id)
        assert reloaded.text == "keep me"  # untouched
        assert reloaded.confidence == 0.1

    def test_patch_unknown_claim_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "claim.patch", {"claim_id": "ghost", "patch": {"text": "x"}}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_patch_validation_rejects_bad_confidence(self, db):
        claim = _save_claim(db, text="t")
        # (c) confidence is bounded 0..1
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "claim.patch",
                {"claim_id": claim.id, "patch": {"confidence": 5.0}},
                _ctx(),
            )

    def test_delete_effect_audit_and_undo_restores_links(self, db):
        """(d) delete also removes orphaning links; undo (restore) must bring
        BOTH the claim and its deleted links back — the corruption a naive
        restore-claim-only impl would miss."""
        a = _save_claim(db, text="claim A")
        b = _save_claim(db, text="claim B")
        link = KnowledgeClaimLink(
            claim_id=a.id, related_claim_id=b.id, relation_type=ClaimRelationType.supports
        )
        db.save(link)
        ctx = _ctx()

        result = registry.invoke(db, "claim.delete", {"claim_id": a.id}, ctx)
        assert db.get(KnowledgeClaim, a.id) is None
        assert db.get(KnowledgeClaimLink, link.id) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.delete"
        assert audit.before["claim"]["id"] == a.id
        assert any(s["id"] == link.id for s in audit.before["deleted_links"])

        # (b) undo -> claim.restore brings claim + link back
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.restore"
        assert db.get(KnowledgeClaim, a.id) is not None
        assert db.get(KnowledgeClaimLink, link.id) is not None

    def test_delete_unknown_claim_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "claim.delete", {"claim_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404

    def test_delete_emit_type_is_deleted(self, db, spy_emit):
        claim = _save_claim(db, text="bye")
        registry.invoke(db, "claim.delete", {"claim_id": claim.id}, _ctx())
        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "claim.deleted"
        assert kwargs["claim_ids"] == [claim.id]


# ===========================================================================
# claim.assign_time_period
# ===========================================================================


class TestAssignTimePeriodAction:
    def _doc(self, db) -> Document:
        doc = Document(name="Diary")
        db.save(doc)
        return doc

    def test_assign_effect_and_audit(self, db, spy_emit):
        doc = self._doc(db)
        c1 = _save_claim(db, text="c1", source_document_id=doc.id)
        c2 = _save_claim(db, text="c2", source_document_id=doc.id)

        result = registry.invoke(
            db,
            "claim.assign_time_period",
            {"source_document_id": doc.id, "time_start": "1850-01-01"},
            _ctx(),
        )
        assert result.result["updated_count"] == 2
        assert db.get(KnowledgeClaim, c1.id).time_start == "1850-01-01"
        assert db.get(KnowledgeClaim, c2.id).time_start == "1850-01-01"

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.assign_time_period"
        assert set(audit.target_ids) == {c1.id, c2.id}
        assert spy_emit[-1][1]["type"] == "claim.updated"

    def test_assign_unknown_document_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.assign_time_period",
                {"source_document_id": "ghost", "time_start": "1850-01-01"},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_assign_inverted_page_range_422(self, db):
        # (d) page_start > page_end is a logic error the impl guards
        doc = self._doc(db)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.assign_time_period",
                {
                    "source_document_id": doc.id,
                    "time_start": "1850-01-01",
                    "page_start": 9,
                    "page_end": 2,
                },
                _ctx(),
            )
        assert exc.value.status_code == 422

    def test_assign_from_metadata_effect_and_audit(self, db):
        # Sibling op: dates come from the doc metadata rather than the request.
        doc = Document(name="Diary", metadata={"date": "1912"})
        db.save(doc)
        c1 = _save_claim(db, text="c1", source_document_id=doc.id)

        result = registry.invoke(
            db,
            "claim.assign_time_period_from_metadata",
            {"source_document_id": doc.id},
            _ctx(),
        )
        assert result.result["updated_count"] == 1
        assert result.result["source_field"] == "date"
        assert db.get(KnowledgeClaim, c1.id).time_start == "1912-01-01"
        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.assign_time_period_from_metadata"
        assert audit.target_ids == [c1.id]

    def test_assign_from_metadata_no_date_422(self, db):
        # (d) a document with no usable date field is a 422, not a silent no-op
        doc = Document(name="Undated")
        db.save(doc)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.assign_time_period_from_metadata",
                {"source_document_id": doc.id},
                _ctx(),
            )
        assert exc.value.status_code == 422

    def test_assign_no_matches_skips_emit(self, db, spy_emit):
        # (d) empty result set -> no emit_type, so emit_change is NOT called
        doc = self._doc(db)
        registry.invoke(
            db,
            "claim.assign_time_period",
            {"source_document_id": doc.id, "time_start": "1850-01-01"},
            _ctx(),
        )
        assert spy_emit == []


# ===========================================================================
# claim.create_link / claim.update_link / claim.delete_link / claim.restore_link
# ===========================================================================


class TestClaimLinkActions:
    def _two_claims(self, db):
        a = _save_claim(db, text="claim A")
        b = _save_claim(db, text="claim B")
        return a, b

    def test_create_link_effect_audit_emit_and_undo(self, db, spy_emit):
        a, b = self._two_claims(db)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.create_link",
            {
                "claim_id": a.id,
                "link": {
                    "related_claim_id": b.id,
                    "relation_type": "supports",
                },
            },
            ctx,
        )
        link_id = result.result["id"]
        assert db.get(KnowledgeClaimLink, link_id) is not None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.create_link"
        assert audit.after == {"link_id": link_id}

        # (e) emit type claim.linked carries both endpoints
        _args, kwargs = spy_emit[-1]
        assert kwargs["type"] == "claim.linked"
        assert set(kwargs["claim_ids"]) == {a.id, b.id}

        # (b) undo -> claim.delete_link removes it
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.delete_link"
        assert db.get(KnowledgeClaimLink, link_id) is None

    def test_create_link_unknown_related_claim_404(self, db):
        a = _save_claim(db, text="claim A")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.create_link",
                {"claim_id": a.id, "link": {"related_claim_id": "ghost", "relation_type": "supports"}},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_create_link_validation_rejects_bad_relation(self, db):
        a, b = self._two_claims(db)
        # (c) relation_type must be a valid ClaimRelationType
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "claim.create_link",
                {"claim_id": a.id, "link": {"related_claim_id": b.id, "relation_type": "not_a_relation"}},
                _ctx(),
            )

    def test_update_link_effect_audit_and_undo(self, db):
        a, b = self._two_claims(db)
        link = KnowledgeClaimLink(
            claim_id=a.id,
            related_claim_id=b.id,
            relation_type=ClaimRelationType.supports,
            link_quality=0.3,
        )
        db.save(link)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.update_link",
            {"link_id": link.id, "patch": {"link_quality": 0.95}},
            ctx,
        )
        assert db.get(KnowledgeClaimLink, link.id).link_quality == 0.95

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["link_quality"] == 0.3

        # (b) undo -> restore_link reverts the quality
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.restore_link"
        assert db.get(KnowledgeClaimLink, link.id).link_quality == 0.3

    def test_update_link_validation_rejects_bad_quality(self, db):
        a, b = self._two_claims(db)
        link = KnowledgeClaimLink(
            claim_id=a.id, related_claim_id=b.id, relation_type=ClaimRelationType.supports
        )
        db.save(link)
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "claim.update_link",
                {"link_id": link.id, "patch": {"link_quality": 2.0}},
                _ctx(),
            )

    def test_delete_link_effect_audit_and_undo(self, db):
        a, b = self._two_claims(db)
        link = KnowledgeClaimLink(
            claim_id=a.id, related_claim_id=b.id, relation_type=ClaimRelationType.supports
        )
        db.save(link)
        ctx = _ctx()

        result = registry.invoke(db, "claim.delete_link", {"link_id": link.id}, ctx)
        assert db.get(KnowledgeClaimLink, link.id) is None

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.before["id"] == link.id

        # (b) undo -> restore_link brings it back with the same id
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.restore_link"
        assert db.get(KnowledgeClaimLink, link.id) is not None

    def test_delete_link_unknown_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "claim.delete_link", {"link_id": "ghost"}, _ctx())
        assert exc.value.status_code == 404


# ===========================================================================
# claim.transition / batch_transition / batch_curation
# ===========================================================================


class TestClaimTransitionActions:
    def test_transition_effect_audit_and_undo(self, db, spy_emit):
        claim = _save_claim(db, text="t", curation_state=ClaimCurationState.unreviewed)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.transition",
            {"claim_id": claim.id, "to_state": "curated"},
            ctx,
        )
        assert db.get(KnowledgeClaim, claim.id).curation_state == ClaimCurationState.curated

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.transition"
        assert audit.before == {"claim_id": claim.id, "from_state": "unreviewed"}
        assert spy_emit[-1][1]["type"] == "claim.updated"

        # (b) undo -> transition back to unreviewed
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.transition"
        assert db.get(KnowledgeClaim, claim.id).curation_state == ClaimCurationState.unreviewed

    def test_transition_unknown_claim_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "claim.transition", {"claim_id": "ghost", "to_state": "curated"}, _ctx()
            )
        assert exc.value.status_code == 404

    def test_transition_invalid_state_400(self, db):
        # (d) an unknown target state is a 400, not a silent no-op
        claim = _save_claim(db, text="t")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db, "claim.transition", {"claim_id": claim.id, "to_state": "banana"}, _ctx()
            )
        assert exc.value.status_code == 400

    def test_batch_transition_mixed_ids_counts_and_audit(self, db):
        good = _save_claim(db, text="good", curation_state=ClaimCurationState.unreviewed)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.batch_transition",
            {"claim_ids": [good.id, "ghost"], "to_state": "shortlisted"},
            ctx,
        )
        # (d) partial success: one transitioned, one reported failed (not raised)
        assert result.result["succeeded"] == 1
        assert result.result["failed"] == 1
        assert db.get(KnowledgeClaim, good.id).curation_state == ClaimCurationState.shortlisted

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.batch_transition"
        assert audit.target_ids == [good.id]
        # batch transition is non-undoable (partial batches have no clean inverse)
        assert registry.get("claim.batch_transition").undoable is False

    def test_batch_transition_validation_requires_non_empty(self, db):
        # (c) claim_ids has min_length=1
        with pytest.raises(ValidationError):
            registry.invoke(
                db, "claim.batch_transition", {"claim_ids": [], "to_state": "curated"}, _ctx()
            )

    def test_batch_curation_idempotent_noop(self, db, spy_emit):
        """(d) a claim already in the target state must be skipped — updated_ids
        empty and NO emit (a naive impl re-saves + broadcasts every row)."""
        claim = _save_claim(db, text="c", curation_state=ClaimCurationState.curated)
        result = registry.invoke(
            db,
            "claim.batch_curation",
            {"claim_ids": [claim.id], "curation_state": "curated"},
            _ctx(),
        )
        assert result.result["updated"] == 0
        assert spy_emit == []

    def test_batch_curation_unknown_id_404(self, db):
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.batch_curation",
                {"claim_ids": ["ghost"], "curation_state": "curated"},
                _ctx(),
            )
        assert exc.value.status_code == 404


# ===========================================================================
# claim.merge / claim.unmerge
# ===========================================================================


class TestClaimMergeActions:
    def _two_claims(self, db):
        survivor = _save_claim(db, text="survivor", confidence=0.6)
        absorbed = _save_claim(db, text="dup", confidence=0.9)
        return survivor, absorbed

    def test_merge_effect_audit_and_undo(self, db, spy_emit):
        survivor, absorbed = self._two_claims(db)
        ctx = _ctx()

        result = registry.invoke(
            db,
            "claim.merge",
            {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [absorbed.id]},
            ctx,
        )
        # effect: absorbed points at the survivor and is rejected
        reloaded = db.get(KnowledgeClaim, absorbed.id)
        assert reloaded.merged_into_id == survivor.id
        assert reloaded.curation_state == ClaimCurationState.rejected

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.merge"
        assert survivor.id in audit.target_ids
        assert audit.after.get("claim_merge_audit_id")
        assert spy_emit[-1][1]["type"] == "claim.merged"

        # (b) undo -> claim.unmerge clears merged_into_id
        inv = _invoke_inverse(db, result.audit_id, ctx)
        assert inv == "claim.unmerge"
        assert db.get(KnowledgeClaim, absorbed.id).merged_into_id is None

    def test_merge_self_reference_400(self, db):
        # (d) survivor cannot also be in absorbed list
        survivor = _save_claim(db, text="s")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.merge",
                {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [survivor.id]},
                _ctx(),
            )
        assert exc.value.status_code == 400

    def test_merge_already_merged_409(self, db):
        # (d) double-merge of an already-absorbed claim is a 409, not silent corruption
        survivor, absorbed = self._two_claims(db)
        ctx = _ctx()
        registry.invoke(
            db,
            "claim.merge",
            {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [absorbed.id]},
            ctx,
        )
        other = _save_claim(db, text="other")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.merge",
                {"surviving_claim_id": other.id, "absorbed_claim_ids": [absorbed.id]},
                ctx,
            )
        assert exc.value.status_code == 409

    def test_merge_unknown_absorbed_404(self, db):
        survivor = _save_claim(db, text="s")
        with pytest.raises(HTTPException) as exc:
            registry.invoke(
                db,
                "claim.merge",
                {"surviving_claim_id": survivor.id, "absorbed_claim_ids": ["ghost"]},
                _ctx(),
            )
        assert exc.value.status_code == 404

    def test_merge_validation_requires_absorbed(self, db):
        # (c) absorbed_claim_ids has min_length=1
        survivor = _save_claim(db, text="s")
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "claim.merge",
                {"surviving_claim_id": survivor.id, "absorbed_claim_ids": []},
                _ctx(),
            )

    def test_unmerge_already_unmerged_409(self, db):
        # (d) unmerging twice is a 409 (idempotency guard)
        survivor, absorbed = self._two_claims(db)
        ctx = _ctx()
        merge = registry.invoke(
            db,
            "claim.merge",
            {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [absorbed.id]},
            ctx,
        )
        merge_audit_id = db.get(ActionAudit, merge.audit_id).after["claim_merge_audit_id"]
        registry.invoke(db, "claim.unmerge", {"audit_id": merge_audit_id}, ctx)
        with pytest.raises(HTTPException) as exc:
            registry.invoke(db, "claim.unmerge", {"audit_id": merge_audit_id}, ctx)
        assert exc.value.status_code == 409

    def test_unmerge_undo_remerges_same_claims(self, db):
        survivor, absorbed = self._two_claims(db)
        ctx = _ctx()
        merge = registry.invoke(
            db,
            "claim.merge",
            {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [absorbed.id]},
            ctx,
        )
        merge_audit = db.get(ActionAudit, merge.audit_id)
        merge_audit_id = merge_audit.after["claim_merge_audit_id"]

        unmerge = registry.invoke(db, "claim.unmerge", {"audit_id": merge_audit_id}, ctx)
        assert db.get(KnowledgeClaim, absorbed.id).merged_into_id is None

        audit = db.get(ActionAudit, unmerge.audit_id)
        assert audit is not None
        assert audit.action_name == "claim.unmerge"
        assert registry.get("claim.unmerge").undoable is True

        inv = _invoke_inverse(db, unmerge.audit_id, ctx)
        assert inv == "claim.merge"
        assert db.get(KnowledgeClaim, absorbed.id).merged_into_id == survivor.id

    def test_unmerge_undo_remerges_after_later_absorbed_edit(self, db):
        survivor, absorbed = self._two_claims(db)
        ctx = _ctx()
        merge = registry.invoke(
            db,
            "claim.merge",
            {"surviving_claim_id": survivor.id, "absorbed_claim_ids": [absorbed.id]},
            ctx,
        )
        merge_audit = db.get(ActionAudit, merge.audit_id)
        merge_audit_id = merge_audit.after["claim_merge_audit_id"]

        unmerge = registry.invoke(db, "claim.unmerge", {"audit_id": merge_audit_id}, ctx)
        edited = db.get(KnowledgeClaim, absorbed.id)
        assert edited is not None
        edited.text = "edited after unmerge"
        db.save(edited)

        inv = _invoke_inverse(db, unmerge.audit_id, ctx)
        assert inv == "claim.merge"
        remerged = db.get(KnowledgeClaim, absorbed.id)
        assert remerged is not None
        assert remerged.merged_into_id == survivor.id
        assert remerged.curation_state == ClaimCurationState.rejected


# ===========================================================================
# claim.prune_trivial
# ===========================================================================


class TestPruneTrivialAction:
    def test_prune_suppresses_trivial_copula_and_audits(self, db):
        # A bare "is-a" copula claim is trivial; a substantive one is not.
        trivial = _save_claim(
            db,
            text="Andagoya is a place",
            subject_canonical="Andagoya",
            predicate_verb="is",
            predicate_canonical="is_a",
            object_phrase="a place",
            curation_state=ClaimCurationState.unreviewed,
        )
        substantive = _save_claim(
            db,
            text="Andagoya founded the settlement in 1510",
            subject_canonical="Andagoya",
            predicate_verb="founded",
            object_phrase="the settlement",
            curation_state=ClaimCurationState.unreviewed,
        )

        result = registry.invoke(
            db, "claim.prune_trivial", {"library_wide": True}, _ctx()
        )
        assert trivial.id in result.result["suppressed_claim_ids"]
        assert substantive.id not in result.result["suppressed_claim_ids"]
        assert db.get(KnowledgeClaim, trivial.id).curation_state == ClaimCurationState.rejected
        # the substantive claim is untouched
        assert db.get(KnowledgeClaim, substantive.id).curation_state == ClaimCurationState.unreviewed

        audit = db.get(ActionAudit, result.audit_id)
        assert audit.action_name == "claim.prune_trivial"
        assert trivial.id in audit.target_ids

    def test_prune_validation_requires_exactly_one_scope(self, db):
        # (c) the model_validator enforces exactly one of doc/folder/library_wide
        with pytest.raises(ValidationError):
            registry.invoke(db, "claim.prune_trivial", {}, _ctx())
        with pytest.raises(ValidationError):
            registry.invoke(
                db,
                "claim.prune_trivial",
                {"document_id": "d", "library_wide": True},
                _ctx(),
            )
