"""Integration tests for the aggregate inspector endpoints.

These are the highest-velocity Swift surfaces — one call to
populate the entire right-side inspector. Tests run the route
handlers in-process (sidesteps the pre-existing TestClient auth-
loopback issue) so they exercise the full payload assembly.
"""

from __future__ import annotations

import asyncio

from fichero.hermeneutics_models import FrameworkType, Interpretation, InterpretiveActType, InterpretiveFramework
from fichero.knowledge_models import (
    Annotation,
    AnnotationKind,
    DocumentCitation,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
    Project,
    ProjectInclusion,
)
from fichero.models import Document, DocType


# -----------------------------------------------------------------------------
# Document inspector
# -----------------------------------------------------------------------------


class TestDocumentInspector:
    def test_empty_document_returns_zero_counts(self, db):
        from fichero.api.routes import document_inspector

        doc = Document(name="empty.pdf", doc_type=DocType.file)
        db.save(doc)
        result = asyncio.run(document_inspector.inspector(doc.id, db=db))
        assert result.document_id == doc.id
        assert result.claim_count == 0
        assert result.claims == []
        assert result.entities == []
        assert result.annotations == []
        assert result.notes == []
        assert result.citations_outbound == []
        assert result.citations_inbound == []
        assert result.interpretations == []
        assert result.projects == []

    def test_rich_document_aggregates_everything(self, db):
        from fichero.api.routes import document_inspector

        doc = Document(name="rich.pdf", doc_type=DocType.file)
        db.save(doc)

        # Two entities + a claim mentioning both
        e1 = KnowledgeEntity(canonical_name="Davidson", entity_type=EntityType.person)
        e2 = KnowledgeEntity(canonical_name="Popayán", entity_type=EntityType.location)
        db.save(e1)
        db.save(e2)
        claim = KnowledgeClaim(
            text="Davidson lived in Popayán.",
            source_document_id=doc.id,
            entity_ids=[e1.id, e2.id],
        )
        db.save(claim)

        # Annotation on the doc
        ann = Annotation(
            document_id=doc.id, kind=AnnotationKind.highlight,
            char_start=0, char_end=10,
        )
        db.save(ann)

        # Note that references the doc
        note = Note(
            title="Davidson context", body="...",
            linked_document_ids=[doc.id],
        )
        db.save(note)

        # Citation OUT from this doc
        target_doc = Document(name="target.pdf", doc_type=DocType.file)
        db.save(target_doc)
        citation_out = DocumentCitation(
            source_document_id=doc.id,
            target_document_id=target_doc.id,
            target_citation_text="Smith 2020",
        )
        db.save(citation_out)

        # Citation IN to this doc
        citing_doc = Document(name="citing.pdf", doc_type=DocType.file)
        db.save(citing_doc)
        citation_in = DocumentCitation(
            source_document_id=citing_doc.id,
            target_document_id=doc.id,
            target_citation_text="(this doc)",
        )
        db.save(citation_in)

        # Interpretation attached to the claim
        framework = InterpretiveFramework(
            name="Marxist", description="Historical materialism",
            framework_type=FrameworkType.theoretical,
        )
        db.save(framework)
        interp = Interpretation(
            framework_id=framework.id,
            claim_id=claim.id,
            interpretation_text="Class dimension",
            act=InterpretiveActType.contextualizing,
        )
        db.save(interp)

        # Project the doc is part of
        project = Project(name="Chapter 3")
        db.save(project)
        db.save(ProjectInclusion(
            project_id=project.id,
            target_id=doc.id,
            target_type="document",
        ))

        result = asyncio.run(document_inspector.inspector(doc.id, db=db))
        assert result.claim_count == 1
        assert len(result.claims) == 1
        assert len(result.entities) == 2
        assert {e.canonical_name for e in result.entities} == {"Davidson", "Popayán"}
        assert len(result.annotations) == 1
        assert len(result.notes) == 1
        assert len(result.citations_outbound) == 1
        assert len(result.citations_inbound) == 1
        assert len(result.interpretations) == 1
        assert len(result.projects) == 1


# -----------------------------------------------------------------------------
# Entity inspector
# -----------------------------------------------------------------------------


class TestEntityInspector:
    def test_unknown_entity_404s(self, db):
        from fastapi import HTTPException
        from fichero.api.routes import entity_inspector

        try:
            asyncio.run(entity_inspector.inspector("no-such-id", db=db))
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404

    def test_entity_aggregates_claims_and_documents(self, db):
        from fichero.api.routes import entity_inspector

        entity = KnowledgeEntity(canonical_name="Davidson", entity_type=EntityType.person)
        db.save(entity)

        doc_a = Document(name="a.pdf", doc_type=DocType.file)
        doc_b = Document(name="b.pdf", doc_type=DocType.file)
        db.save(doc_a)
        db.save(doc_b)

        # Two claims in different docs both reference the entity.
        db.save(KnowledgeClaim(
            text="Davidson signed.",
            source_document_id=doc_a.id,
            entity_ids=[entity.id],
            metadata={"verb": "signed", "object": "the deed"},
        ))
        db.save(KnowledgeClaim(
            text="Davidson was named.",
            source_document_id=doc_b.id,
            entity_ids=[entity.id],
            metadata={"verb": "was", "object": "named alcalde"},
        ))

        result = asyncio.run(entity_inspector.inspector(entity.id, db=db))
        assert result.entity_id == entity.id
        assert result.claim_count == 2
        assert len(result.documents) == 2
        # Triangulated facts surface as ranked triples.
        assert isinstance(result.triangulated_facts, list)
        # similar_entities best-effort — depends on LanceDB availability.
        assert isinstance(result.similar_entities, list)
