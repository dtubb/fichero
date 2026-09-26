"""#5074: deleting a claim writes the rule that stops the next extraction recreating it, in the SAME
audited action. Every test runs the full round trip through the real verb and the real writer:

    run the verb -> the rule row exists -> re-extract -> the correction held
"""

from __future__ import annotations

import asyncio

import pytest
from starlette.requests import Request

import fichero_server.api.routes.claim.claims  # noqa: F401  (registers claim.*)
import fichero_server.api.routes.entity.entities  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.system.actions_registry import undo_action
from fichero_server.models.knowledge import (
    ClaimCurationState,
    ClaimSuppressionRule,
    ClaimSuppressionRuleAction,
    EntityType,
    KnowledgeClaim,
)

LIB = "/lib/test.fichero"


def _ctx() -> ActionContext:
    return ActionContext(actor="ui", library_path=LIB)


def _undo(db, audit_id: str):
    request = Request(
        {
            "type": "http",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "https",
            "server": ("testserver", 443),
            "path": f"/api/actions/audit/{audit_id}/undo",
            "query_string": b"",
        }
    )
    return asyncio.run(
        undo_action(audit_id, request=request, db=db, x_fichero_library_path=LIB, x_fichero_origin_window=None)
    )


def _extract(db, doc: str = "a", name: str = "Ana Ruiz", verb: str = "signed", obj: str = "a deed") -> None:
    """The real extraction writer (`_write_kg_rows`, which every extractor writes through)."""
    from fichero_server.workflows.tools.extractors import _write_kg_rows

    _write_kg_rows(
        db,
        section={"name": "people", "entity_type": EntityType.person},
        items=[{"name": name, "verb": verb, "object": obj}],
        container_id=doc,
        page_label="1",
        source_excerpt=f"{name} {verb} {obj}.",
    )


def _claims(db, doc: str | None = None) -> list[KnowledgeClaim]:
    return [c for c in db.query(KnowledgeClaim) if doc is None or c.source_document_id == doc]


def _rules(db) -> list[ClaimSuppressionRule]:
    return db.all(ClaimSuppressionRule)


def _delete(db, claim: KnowledgeClaim, **extra):
    return registry.invoke(db, "claim.delete", {"claim_id": claim.id, **extra}, _ctx())


class TestClaimDeleteWritesAPruneRule:
    def test_the_deleted_claim_is_not_recreated_by_the_next_extraction(self, db):
        _extract(db)
        (claim,) = _claims(db)
        _delete(db, claim)

        # the middle step: the rule exists and says what it is for
        (rule,) = _rules(db)
        assert rule.action == ClaimSuppressionRuleAction.prune
        assert rule.match_source_document_id == "a"
        assert (rule.match_subject_name, rule.match_predicate_verb, rule.match_object_phrase) == (
            claim.subject_canonical or claim.svo_subject,
            claim.predicate_verb or claim.svo_verb,
            claim.object_phrase or claim.svo_object,
        )
        assert rule.created_by == "ui"
        assert _claims(db) == []

        # the last step: the correction held (it used to come back as `unreviewed`)
        _extract(db)
        assert _claims(db) == []

    def test_the_rule_is_scoped_to_the_deleted_claims_document(self, db):
        """The same statement on ANOTHER page is a different piece of evidence."""
        _extract(db, doc="a")
        (claim,) = _claims(db)
        _delete(db, claim)

        _extract(db, doc="b")
        assert [c.source_document_id for c in _claims(db)] == ["b"]

    def test_a_claim_without_a_complete_triple_writes_no_rule(self, db):
        """A hand-authored, text-only claim cannot be recreated by the extractor, and an
        incomplete pattern would match far more than this claim."""
        claim = KnowledgeClaim(text="A note a person wrote.", source_document_id="a")
        db.save(claim)
        _delete(db, claim)
        assert _rules(db) == []
        assert _claims(db) == []

    def test_a_second_delete_of_the_same_statement_does_not_pile_up_rules(self, db):
        _extract(db)
        (claim,) = _claims(db)
        _delete(db, claim)
        # restore it by hand (as a person re-adding it would) and delete again
        again = KnowledgeClaim.model_validate({**claim.model_dump(mode="json"), "id": "again"})
        db.save(again)
        _delete(db, again)
        assert len(_rules(db)) == 1

    def test_undo_removes_the_rule_and_the_restored_claim_is_not_pruned(self, db):
        _extract(db)
        (claim,) = _claims(db)
        forward = _delete(db, claim)
        assert len(_rules(db)) == 1

        _undo(db, forward.audit_id)

        assert _rules(db) == []
        assert [c.id for c in _claims(db)] == [claim.id]
        _extract(db)
        assert [c.id for c in _claims(db)] == [claim.id], "a duplicate was written, or the claim was pruned"

    def test_undoing_a_create_does_not_write_a_rule(self, db):
        """The delete that is the inverse of a create is an undo, not a correction. The claim is
        given a complete triple after creation, so a rule WOULD be written if the inverse asked
        for one; without `record_rule=False` this test fails."""
        from fichero_server.models import DocType, Document

        doc = Document(name="d.txt", doc_type=DocType.file)
        db.save(doc, auto_embed=False)
        forward = registry.invoke(
            db, "claim.create", {"text": "Ana Ruiz signed a deed.", "source_document_id": doc.id}, _ctx()
        )
        (claim,) = _claims(db)
        claim.subject_canonical, claim.predicate_verb, claim.object_phrase = "Ana Ruiz", "signed", "a deed"
        db.save(claim)

        _undo(db, forward.audit_id)

        assert _rules(db) == []
        assert _claims(db) == []

    def test_a_rejected_claim_still_survives_a_re_extraction_without_any_rule(self, db):
        """Control: state verbs never needed a rule. Rejecting is not deleting."""
        from fichero_server.api.routes.claim.curation import (
            BatchClaimCurationRequest,
            batch_set_claim_curation_state_impl,
        )

        _extract(db)
        (claim,) = _claims(db)
        batch_set_claim_curation_state_impl(
            db, BatchClaimCurationRequest(claim_ids=[claim.id], curation_state=ClaimCurationState.rejected), "ui"
        )
        _extract(db)
        assert [(c.id, c.curation_state) for c in _claims(db)] == [(claim.id, ClaimCurationState.rejected)]
        assert _rules(db) == []

    def test_a_rule_that_cannot_be_written_fails_the_delete_and_the_claim_stays(self, db, monkeypatch):
        _extract(db)
        (claim,) = _claims(db)
        real_save = type(db).save

        def failing_save(self, obj, *args, **kwargs):
            if isinstance(obj, ClaimSuppressionRule):
                raise RuntimeError("rule store unavailable")
            return real_save(self, obj, *args, **kwargs)

        monkeypatch.setattr(type(db), "save", failing_save)
        with pytest.raises(RuntimeError, match="rule store unavailable"):
            _delete(db, claim)
        monkeypatch.undo()

        assert [c.id for c in _claims(db)] == [claim.id], "the claim was deleted without its rule"
        assert _rules(db) == []
