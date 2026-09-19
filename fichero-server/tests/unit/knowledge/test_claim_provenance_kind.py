"""kg.claim.provenance-kind-is-server-stated (#4869, closes what #4868 found).

`KnowledgeClaim.created_by` used to default to `"human"` -- a default no
write path had to override, so every machine writer that forgot to set it
(both extraction paths did) got a free, false claim of human authorship.
This is the fix: a new closed field, `provenance_kind`, set by the SERVER
at the point of writing, never accepted from a client; each write path
sets exactly one value; a legacy row with no value gets one DERIVED at
read time (never trusting the old "human" default); `created_by`'s own
model default is now "unknown".
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

import fichero_server.api.routes.claim.claims  # noqa: F401 -- registers claim.* actions
import fichero_server.api.routes.document.annotations  # noqa: F401 -- registers annotation.* actions
from fichero_server.actions.registry import ActionContext, registry
from fichero_server.api.routes.claim.claims import ClaimCreateRequest, create_claim_impl
from fichero_server.api.routes.mcp.tools import (
    KnowledgeClaimCreateRequest,
    mcp_knowledge_claim_create,
)
from fichero_server.knowledge._common import resolve_claim_provenance_kind
from fichero_server.models import Document, DocType
from fichero_server.models.knowledge import KnowledgeClaim, ProvenanceKind
from fichero_server.workflows.tools._entity_writer import save_claim


def _ctx(actor: str = "alice", via_mcp: bool = False) -> ActionContext:
    return ActionContext(actor=actor, library_path="/lib/test.fichero", via_mcp=via_mcp)


def _doc(db) -> Document:
    doc = Document(name="src", path="/tmp/src.pdf", doc_type=DocType.file)
    db.save(doc)
    return doc


# ===========================================================================
# The model default (#4868's actual bug)
# ===========================================================================


def test_created_by_no_longer_defaults_to_human():
    claim = KnowledgeClaim(text="t", source_document_id="doc-1")
    assert claim.created_by == "unknown"
    assert claim.provenance_kind is None


# ===========================================================================
# One test per write path for the value it sets
# ===========================================================================


class TestEachWritePathSetsItsOwnValue:
    def test_save_claim_extraction_path_sets_workflow(self, db):
        claim_id = save_claim(
            db,
            text="Alicia sold the mine.",
            source_document_id="doc-1",
            provider="anthropic",
            model="claude-x",
        )
        claim = db.get(KnowledgeClaim, claim_id)
        assert claim.provenance_kind == ProvenanceKind.workflow
        assert claim.created_by == "extractor"

    def test_claim_create_action_sets_human_by_default(self, db):
        doc = _doc(db)
        result = registry.invoke(
            db,
            "claim.create",
            {"text": "A hand-written claim.", "source_document_id": doc.id},
            _ctx(actor="alice", via_mcp=False),
        )
        claim = db.get(KnowledgeClaim, result.result["id"])
        assert claim.provenance_kind == ProvenanceKind.human
        assert claim.created_by == "alice"

    def test_claim_create_via_mcp_sets_agent(self, db):
        doc = _doc(db)
        request = KnowledgeClaimCreateRequest(
            text="An agent-created claim.", source_document_id=doc.id
        )
        result = asyncio.run(
            mcp_knowledge_claim_create(request, db=db, actor="agent-session")
        )
        claim = db.get(KnowledgeClaim, result.claim_id)
        assert claim.provenance_kind == ProvenanceKind.agent
        assert claim.created_by == "agent-session"

    def test_enrich_import_sets_external_import(self, db):
        from fichero_server.models.knowledge import ProvenanceKind as PK

        request = ClaimCreateRequest(
            text="Wikidata-sourced claim.",
            source_document_id=None,
            created_by="wikidata",
            provenance_kind=PK.external_import,
        )
        claim = create_claim_impl(db, request)
        assert claim.provenance_kind == ProvenanceKind.external_import
        assert claim.created_by == "wikidata"

    def test_annotation_promote_to_claim_sets_human_by_default(self, db):
        from fichero_server.models import Document as DocModel
        from fichero_server.models.knowledge import Annotation, AnnotationKind

        doc = DocModel(name="d", path="/tmp/d.pdf", doc_type=DocType.file, page_content="hello world")
        db.save(doc)
        ann = Annotation(document_id=doc.id, kind=AnnotationKind.highlight, text="hello")
        db.save(ann)

        result = registry.invoke(
            db,
            "annotation.promote_to_claim",
            {"annotation_id": ann.id},
            _ctx(actor="alice", via_mcp=False),
        )
        claim = db.get(KnowledgeClaim, result.result["claim_id"])
        assert claim.provenance_kind == ProvenanceKind.human


# ===========================================================================
# A client-supplied value is ignored
# ===========================================================================


class TestClientSuppliedValueIsIgnored:
    def test_forged_provenance_kind_via_action_invoke_is_ignored(self, db):
        doc = _doc(db)
        result = registry.invoke(
            db,
            "claim.create",
            {
                "text": "t",
                "source_document_id": doc.id,
                "provenance_kind": "external_import",  # forged
            },
            _ctx(actor="alice", via_mcp=False),
        )
        claim = db.get(KnowledgeClaim, result.result["id"])
        assert claim.provenance_kind == ProvenanceKind.human  # server decided, not the body

    def test_forged_provenance_kind_via_mcp_is_ignored(self, db):
        doc = _doc(db)
        request = KnowledgeClaimCreateRequest(text="t", source_document_id=doc.id)
        result = asyncio.run(
            mcp_knowledge_claim_create(request, db=db, actor="agent-session")
        )
        # The MCP request model has no client-facing provenance_kind field
        # at all -- an agent write is ALWAYS `agent`, never anything the
        # client could claim instead.
        claim = db.get(KnowledgeClaim, result.claim_id)
        assert claim.provenance_kind == ProvenanceKind.agent


# ===========================================================================
# Legacy-row derivation (resolve_claim_provenance_kind)
# ===========================================================================


class TestLegacyRowDerivation:
    def test_legacy_row_with_provider_derives_workflow(self):
        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", provider="openai", provenance_kind=None
        )
        assert resolve_claim_provenance_kind(legacy) == ProvenanceKind.workflow

    def test_legacy_row_with_model_only_derives_workflow(self):
        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", model="spacy_ner", provenance_kind=None
        )
        assert resolve_claim_provenance_kind(legacy) == ProvenanceKind.workflow

    def test_legacy_row_with_wikidata_created_by_derives_external_import(self):
        legacy = KnowledgeClaim(
            text="t", source_document_id=None, created_by="wikidata", provenance_kind=None
        )
        assert resolve_claim_provenance_kind(legacy) == ProvenanceKind.external_import

    def test_legacy_row_with_human_created_by_and_no_provider_derives_unknown_never_human(self):
        """The exact case #4868/#4869 exist to fix: a legacy row's
        `created_by` being the literal string "human" must NEVER be read
        as proof of human authorship -- it was the model's own default,
        asserted by nobody."""
        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", created_by="human", provenance_kind=None
        )
        assert resolve_claim_provenance_kind(legacy) == ProvenanceKind.unknown
        assert resolve_claim_provenance_kind(legacy) != ProvenanceKind.human

    def test_new_row_with_explicit_kind_is_returned_unchanged(self):
        claim = KnowledgeClaim(
            text="t",
            source_document_id="doc-1",
            provenance_kind=ProvenanceKind.human,
            provider="openai",  # would derive workflow if the explicit value were ignored
        )
        assert resolve_claim_provenance_kind(claim) == ProvenanceKind.human


# ===========================================================================
# Serialization sites apply the resolved value
# ===========================================================================


class TestSerializationSitesApplyTheDerivation:
    def test_get_claim_route_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.claim.claims import get_claim

        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", provider="openai", provenance_kind=None
        )
        db.save(legacy)
        result = asyncio.run(get_claim(legacy.id, db=db))
        assert result.provenance_kind == ProvenanceKind.workflow
        # The STORED row is untouched -- no backfill.
        assert db.get(KnowledgeClaim, legacy.id).provenance_kind is None

    def test_list_claims_impl_resolves_every_item(self, db):
        from fichero_server.api.routes.claim.claims import list_claims_impl

        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", created_by="human", provenance_kind=None
        )
        db.save(legacy)
        items = list_claims_impl(db)
        found = next(c for c in items if c.id == legacy.id)
        assert found.provenance_kind == ProvenanceKind.unknown
        assert db.get(KnowledgeClaim, legacy.id).provenance_kind is None

    def test_mcp_claim_get_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.mcp.tools import mcp_knowledge_claim_get

        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", created_by="wikidata", provenance_kind=None
        )
        db.save(legacy)
        result = asyncio.run(mcp_knowledge_claim_get(legacy.id, db=db))
        assert result.provenance_kind == ProvenanceKind.external_import

    def test_search_claim_hit_resolves_a_legacy_row(self):
        """#4869 follow-up: team-lead's regen diff showed `SearchClaimHit`
        (search/core.py) also embeds a full claim row and was missed in the
        first sweep. Tested at the same boundary the codebase already uses
        for this response (see test_search_header_matches_body.py): the raw
        row dict `_run_claim_semantic_queries` would hand back, validated
        the way the route does, never the full route with its retrieval/ACL
        machinery mocked out."""
        from fichero_server.api.routes.search.core import _resolved_search_claim_hits

        legacy_row = {
            "id": "c-1",
            "text": "t",
            "source_document_id": "doc-1",
            "provider": "openai",
            "provenance_kind": None,
        }
        hits = _resolved_search_claim_hits([legacy_row])
        assert hits[0].provenance_kind == ProvenanceKind.workflow

    def test_entity_inspector_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.entity.inspector import inspector as entity_inspector
        from fichero_server.models.knowledge import EntityType, KnowledgeEntity

        entity = KnowledgeEntity(canonical_name="Alicia", entity_type=EntityType.person)
        db.save(entity)
        legacy = KnowledgeClaim(
            text="t",
            source_document_id="doc-1",
            entity_ids=[entity.id],
            created_by="human",
            provenance_kind=None,
        )
        db.save(legacy)
        result = asyncio.run(entity_inspector(entity.id, db=db))
        assert result.claims[0].provenance_kind == ProvenanceKind.unknown
        assert db.get(KnowledgeClaim, legacy.id).provenance_kind is None

    def test_document_inspector_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.document.inspector import inspector as doc_inspector

        doc = _doc(db)
        legacy = KnowledgeClaim(
            text="t", source_document_id=doc.id, model="spacy_ner", provenance_kind=None
        )
        db.save(legacy)
        result = asyncio.run(doc_inspector(doc.id, db=db))
        assert result.claims[0].provenance_kind == ProvenanceKind.workflow

    def test_document_knowledge_graph_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.document.inspector import knowledge_graph

        doc = _doc(db)
        legacy = KnowledgeClaim(
            text="t", source_document_id=doc.id, created_by="wikidata", provenance_kind=None
        )
        db.save(legacy)
        result = asyncio.run(knowledge_graph(doc.id, db=db))
        assert result.claims[0].provenance_kind == ProvenanceKind.external_import

    def test_related_claims_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.claim.links import get_related_claims
        from fichero_server.models.knowledge import ClaimRelationType, KnowledgeClaimLink

        source = KnowledgeClaim(text="source", source_document_id="doc-1")
        db.save(source)
        legacy = KnowledgeClaim(
            text="related", source_document_id="doc-1", provider="anthropic", provenance_kind=None
        )
        db.save(legacy)
        db.save(
            KnowledgeClaimLink(
                claim_id=source.id,
                related_claim_id=legacy.id,
                relation_type=ClaimRelationType.supports,
            )
        )
        result = asyncio.run(get_related_claims(source.id, db=db))
        assert result.items[0].provenance_kind == ProvenanceKind.workflow

    def test_citation_usage_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.citation.usages import list_citation_usages
        from fichero_server.models.knowledge import DocumentCitation

        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", created_by="human", provenance_kind=None
        )
        db.save(legacy)
        citation = DocumentCitation(
            source_document_id="doc-1",
            target_document_id="doc-2",
            target_citation_text="see doc-2",
            detector="llm-usage",
            metadata={"claim_id": legacy.id, "matched_reference_id": None, "stance": None},
        )
        db.save(citation)
        result = asyncio.run(
            list_citation_usages(
                source_document_id=None,
                target_document_id=None,
                reference_id=None,
                stance=None,
                db=db,
            )
        )
        found = next(i for i in result.items if i.claim is not None)
        assert found.claim.provenance_kind == ProvenanceKind.unknown

    def test_entity_biography_resolves_a_legacy_row(self, db):
        from fichero_server.api.routes.entity.entities import assemble_entity_biography
        from fichero_server.models.knowledge import EntityType, KnowledgeEntity

        entity = KnowledgeEntity(canonical_name="Alicia", entity_type=EntityType.person)
        db.save(entity)
        legacy = KnowledgeClaim(
            text="t", source_document_id="doc-1", entity_ids=[entity.id], provider="openai", provenance_kind=None
        )
        db.save(legacy)
        response = assemble_entity_biography(entity.id, db)
        assert response.claims[0].provenance_kind == ProvenanceKind.workflow
        assert db.get(KnowledgeClaim, legacy.id).provenance_kind is None


def test_a_library_created_before_the_field_upgrades_without_rewriting_its_rows(tmp_path):
    """kg.claim.provenance-kind-is-server-stated (#4869): the field's tests above all
    build FRESH tables, which would pass even if an existing library could not take the
    new column. Here a real table LOSES the column, as a library created before the
    field has it, and is reopened: the column comes back, the old row keeps exactly what
    it stored, its kind is derived on read, and a new row saves with its own kind."""
    from fichero_server.db import Database
    from fichero_server.knowledge._common import resolve_claim_provenance_kind
    from fichero_server.models.knowledge import KnowledgeClaim, ProvenanceKind

    path = tmp_path / "old-library.duckdb"
    db = Database(path)
    old = KnowledgeClaim(text="Juan vendió la mina.", provider="anthropic", created_by="human")
    db.save(old)
    db.conn.execute("ALTER TABLE knowledgeclaims DROP COLUMN provenance_kind")
    db.close()

    reopened = Database(path)
    legacy = reopened.get(KnowledgeClaim, old.id)
    assert legacy.provenance_kind is None
    assert legacy.created_by == "human"  # stored value untouched
    assert resolve_claim_provenance_kind(legacy) is ProvenanceKind.workflow

    fresh = KnowledgeClaim(text="Nueva.", provenance_kind=ProvenanceKind.workflow)
    reopened.save(fresh)
    assert reopened.get(KnowledgeClaim, fresh.id).provenance_kind is ProvenanceKind.workflow
    again = reopened.get(KnowledgeClaim, old.id)
    assert again.provenance_kind is None and again.created_by == "human"
