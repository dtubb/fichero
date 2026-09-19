"""``entity.purge_nlp_draft`` (#4823 S3, team-lead review) -- the way back.

The free NLP draft stage writes into real libraries; this action is what
takes those rows back, scoped to one document or the whole library, with a
dry-run default. Drives it the same way `test_provider_actions.py` drives
every other action: through `registry.invoke`, the one audited choke point.

F2 (team-lead review): `curation_state` alone does not prove a row was
never touched -- renaming/aliasing/linking/merging an entity, or linking a
claim, never changes it. `TestSurvivorsAreNeverTouched` (F2 additions at
the bottom) drives the ACTUAL update/link/merge paths -- not a hand-set
metadata flag -- so the protection is proven against real code, not
against this file's own assumptions about what those paths do.
"""

from __future__ import annotations


# Importing the route module registers entity.purge_nlp_draft via @action.
import fichero_server.api.routes.kg.nlp_draft_purge  # noqa: F401
# Importing these registers entity.update / entity.merge / claim.create_link
# for the F2 tests below to drive directly.
import fichero_server.api.routes.entity.entities  # noqa: F401
import fichero_server.api.routes.claim.links  # noqa: F401
import fichero_server.api.routes.kg.entity_curation  # noqa: F401
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.importers.nlp_draft import run_nlp_draft
from fichero_server.knowledge.spacy_ner import EntitySpan
from fichero_server.knowledge.spacy_svo import ProposedTriple
from fichero_server.models import Document, DocType, FileType, Status
from fichero_server.models.knowledge import (
    ClaimType,
    EntityCurationState,
    EntityMergeAudit,
    EntityMergeOperationType,
    EntityType,
    EpistemicStatus,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
)


def _ctx() -> ActionContext:
    return ActionContext(actor="test", library_path="/lib/test.fichero")


def _stub_ner(text, language=None):
    return [
        EntitySpan(text="Juan Perez", fichero_type="person", start=0, end=10, label="PERSON")
    ]


def _stub_svo(text, language=None):
    return [
        ProposedTriple(
            subject="Juan Perez", verb="firmó", object="la escritura",
            sentence=text, char_start=0, char_end=len(text),
        )
    ]


def _stub_filter(proposals, text):
    return proposals, []


def _draft_doc(db, text="Juan Perez firmó la escritura.") -> Document:
    doc = Document(
        name="a.md", doc_type=DocType.file, file_type=FileType.text,
        status=Status.pending, page_content=text,
    )
    db.save(doc)
    return doc


def _seed_draft(db, doc=None):
    doc = doc or _draft_doc(db)
    run_nlp_draft(db, doc, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=_stub_filter)
    return doc


class TestDryRunIsTheDefault(object):
    def test_dry_run_counts_but_deletes_nothing(self, db, test_package):
        doc = _seed_draft(db)

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id}, _ctx()
        )

        assert result.result["dry_run"] is True
        assert result.result["entity_count"] == 1
        assert result.result["claim_count"] == 2  # "is a person" + "firmó"
        assert db.query(KnowledgeEntity, canonical_name="Juan Perez")
        assert db.query(KnowledgeClaim, source_document_id=doc.id)


class TestRealPurgeRemovesDraftRows:
    def test_document_scoped_purge_removes_the_draft(self, db, test_package):
        doc = _seed_draft(db)

        result = registry.invoke(
            db,
            "entity.purge_nlp_draft",
            {"document_id": doc.id, "dry_run": False},
            _ctx(),
        )

        assert result.result["entity_count"] == 1
        assert result.result["claim_count"] == 2
        assert db.query(KnowledgeEntity, canonical_name="Juan Perez") == []
        assert db.query(KnowledgeClaim, source_document_id=doc.id) == []

    def test_purge_clears_nlp_processed_at_so_a_rerun_is_possible(self, db, test_package):
        doc = _seed_draft(db)
        from fichero_server.importers import derivatives

        derivatives._nlp_stage(doc.id, test_package)
        assert "nlp_processed_at" in db.get(Document, doc.id).metadata

        registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        after = db.get(Document, doc.id)
        assert "nlp_processed_at" not in (after.metadata or {})

    def test_idempotent_second_purge_finds_nothing(self, db, test_package):
        doc = _seed_draft(db)
        registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        second = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert second.result["entity_count"] == 0
        assert second.result["claim_count"] == 0

    def test_library_scoped_purge_spans_every_document(self, db, test_package):
        doc_a = _draft_doc(db, text="Juan Perez firmó la escritura.")
        doc_b = _draft_doc(db, text="Juan Perez firmó otra escritura.")
        run_nlp_draft(db, doc_a, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=_stub_filter)
        run_nlp_draft(db, doc_b, ner_fn=_stub_ner, svo_fn=_stub_svo, filter_fn=_stub_filter)

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"dry_run": False}, _ctx(),
        )

        assert result.result["document_id"] is None
        assert db.query(KnowledgeClaim, source_document_id=doc_a.id) == []
        assert db.query(KnowledgeClaim, source_document_id=doc_b.id) == []


class TestSurvivorsAreNeverTouched:
    def test_a_human_reviewed_entity_survives_the_purge(self, db, test_package):
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        entity.curation_state = EntityCurationState.verified
        db.save(entity)

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        # The entity survives; its "is a person" claim is STILL draft-only
        # on its own terms (unreviewed, provider=spacy, uncorroborated) and
        # is removed -- reviewing the ENTITY doesn't retroactively review
        # every claim about it. Only the entity's survival is asserted here.
        assert db.get(KnowledgeEntity, entity.id) is not None
        assert result.result["entity_count"] == 0

    def test_an_entity_also_evidenced_by_a_non_draft_claim_survives(self, db, test_package):
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        # An LLM/VLM pass corroborated the SAME entity with its own claim.
        db.save(
            KnowledgeClaim(
                text="Juan Perez firmó la escritura ante notario.",
                source_document_id=doc.id,
                entity_ids=[entity.id],
                claim_type=ClaimType.fact,
                epistemic_status=EpistemicStatus.confirmed,
                provider="anthropic",
                model="claude",
            )
        )

        registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        llm_claim = [
            c for c in db.query(KnowledgeClaim, source_document_id=doc.id)
            if c.provider == "anthropic"
        ]
        assert llm_claim  # the LLM-sourced claim itself also survives

    def test_a_claim_corroborated_by_another_extractor_survives(self, db, test_package):
        doc = _seed_draft(db)
        claim = [
            c for c in db.query(KnowledgeClaim, source_document_id=doc.id)
            if c.svo_verb == "firmó"
        ][0]
        claim.metadata = {**(claim.metadata or {}), "also_extracted_by": ["anthropic/claude"]}
        db.save(claim)

        registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeClaim, claim.id) is not None

    def test_a_reviewed_claim_survives(self, db, test_package):
        from fichero_server.models.knowledge import ClaimCurationState

        doc = _seed_draft(db)
        claim = [
            c for c in db.query(KnowledgeClaim, source_document_id=doc.id)
            if c.svo_verb == "firmó"
        ][0]
        claim.curation_state = ClaimCurationState.curated
        db.save(claim)

        registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeClaim, claim.id) is not None

    def test_an_entity_with_no_referencing_claim_is_never_guessed_at(self, db, test_package):
        """No draft claim references it -> unprovable provenance -> untouched."""
        bare = KnowledgeEntity(canonical_name="Untethered Entity", entity_type=EntityType.person)
        db.save(bare)

        registry.invoke(
            db, "entity.purge_nlp_draft", {"dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, bare.id) is not None


# =============================================================================
# F2 (team-lead review): curation_state alone is not proof a row was never
# touched -- these drive the REAL update/link/merge/authority-link paths
# and confirm the purge refuses to touch what they produced, even though
# none of them changes curation_state.
# =============================================================================


def _update_params(entity_id: str, canonical_name: str) -> dict:
    return {
        "entity_id": entity_id,
        "canonical_name": canonical_name,
        "entity_type": "person",
        "aliases": [],
        "source_document_ids": [],
    }


class TestF2IndependentTouchProtection:
    def test_entity_update_leaves_curation_state_unreviewed(self, db, test_package):
        """Ground truth for the whole F2 fix, verified at the code: a
        rename does NOT flip curation_state. If this assumption ever stops
        holding, the protection below stays correct but redundant -- this
        test is what would tell us that changed."""
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]

        registry.invoke(
            db, "entity.update", _update_params(entity.id, "Juan Pérez"), _ctx(),
        )

        assert (
            db.get(KnowledgeEntity, entity.id).curation_state
            == EntityCurationState.unreviewed
        )

    def test_a_renamed_but_unreviewed_entity_survives(self, db, test_package):
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        registry.invoke(
            db, "entity.update", _update_params(entity.id, "Juan Pérez (renamed)"), _ctx(),
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert result.result["protected_count"] >= 1
        assert any(
            "entity.update" in reason for reason in result.result["protected_reasons"]
        )

    def test_an_entity_with_a_note_survives(self, db, test_package):
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        db.save(Note(body="Remember to check this person", linked_entity_ids=[entity.id]))

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert result.result["protected_reasons"].get("linked from a note") == 1

    def test_an_entity_with_an_authority_link_survives(self, db, test_package):
        """Mirrors exactly what `kg/entity_curation.py::link_external_
        authority` writes -- an `EntityMergeAudit(operation_type=
        authority_link)` row plus `entity.metadata["authority_links"]` --
        verified at that route's code. Constructed directly here rather
        than driving its full HTTP dependency chain (a LibrarySetting to
        enable external authority + a cached AuthoritySnapshot row), which
        would test FastAPI wiring this suite has no other stake in."""
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        entity.metadata = {
            **(entity.metadata or {}),
            "authority_links": [{"authority": "wikidata", "authority_id": "Q1"}],
        }
        db.save(entity)
        db.save(
            EntityMergeAudit(
                operation_type=EntityMergeOperationType.authority_link,
                source_entity_ids=[],
                target_entity_id=entity.id,
                alias_changes={
                    "authority_link": {"authority": "wikidata", "authority_id": "Q1"}
                },
                created_by="human",
            )
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, entity.id) is not None
        assert result.result["protected_count"] >= 1

    def test_a_merge_survivor_survives(self, db, test_package):
        doc = _seed_draft(db)
        survivor = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        absorbed = KnowledgeEntity(canonical_name="J. Perez", entity_type=EntityType.person)
        db.save(absorbed)

        registry.invoke(
            db, "entity.merge",
            {"absorbing_entity_id": survivor.id, "absorbed_entity_ids": [absorbed.id]},
            _ctx(),
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeEntity, survivor.id) is not None
        # `entity.merge` is itself a registered action, so the ActionAudit
        # check (checked first in `_protected_ids`) is what actually names
        # it here -- "acted on by entity.merge" is a MORE precise reason
        # than the EntityMergeAudit-table fallback would give, and both are
        # correct; this asserts protection happened, not which layer named it.
        assert result.result["protected_count"] >= 1
        assert any(
            "entity.merge" in reason for reason in result.result["protected_reasons"]
        )

    def test_a_claim_with_a_link_survives(self, db, test_package):
        doc = _seed_draft(db)
        claim = [
            c for c in db.query(KnowledgeClaim, source_document_id=doc.id)
            if c.svo_verb == "firmó"
        ][0]
        other = KnowledgeClaim(
            text="A second, unrelated claim.", source_document_id=doc.id,
            claim_type=ClaimType.fact, epistemic_status=EpistemicStatus.confirmed,
        )
        db.save(other)

        registry.invoke(
            db, "claim.create_link",
            {
                "claim_id": claim.id,
                "link": {"related_claim_id": other.id, "relation_type": "related_to"},
            },
            _ctx(),
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id, "dry_run": False}, _ctx(),
        )

        assert db.get(KnowledgeClaim, claim.id) is not None
        assert result.result["protected_reasons"].get("has a claim link") == 1

    def test_dry_run_reports_protected_breakdown(self, db, test_package):
        doc = _seed_draft(db)
        entity = db.query(KnowledgeEntity, canonical_name="Juan Perez")[0]
        registry.invoke(
            db, "entity.update", _update_params(entity.id, "Juan Pérez (renamed)"), _ctx(),
        )

        result = registry.invoke(
            db, "entity.purge_nlp_draft", {"document_id": doc.id}, _ctx(),
        )

        assert result.result["dry_run"] is True
        assert result.result["protected_count"] >= 1
        assert (
            sum(result.result["protected_reasons"].values())
            == result.result["protected_count"]
        )
        # Nothing was actually touched -- dry run.
        assert db.get(KnowledgeEntity, entity.id) is not None
