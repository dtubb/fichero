"""Integration tests for the aggregate inspector endpoints.

These are the highest-velocity Swift surfaces — one call to
populate the entire right-side inspector. Tests run the route
handlers in-process (sidesteps the pre-existing TestClient auth-
loopback issue) so they exercise the full payload assembly.
"""

from __future__ import annotations

import asyncio

from fichero_server.models.hermeneutics import FrameworkType, Interpretation, InterpretiveActType, InterpretiveFramework
from fichero_server.models.knowledge import (
    Annotation,
    AnnotationKind,
    BookStructureNode,
    DocumentCitation,
    EntityType,
    KnowledgeClaim,
    KnowledgeEntity,
    Note,
    Project,
    ProjectInclusion,
)
from fichero_server.models import Artifact, Document, DocType


# -----------------------------------------------------------------------------
# Document inspector
# -----------------------------------------------------------------------------


class TestDocumentInspector:
    def test_empty_document_returns_zero_counts(self, db):
        from fichero_server.api.routes.document import inspector as document_inspector

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
        from fichero_server.api.routes.document import inspector as document_inspector

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

    def test_page_returns_own_entities_and_parent_rolls_up_pages(self, db):
        from fichero_server.api.routes.document import inspector as document_inspector

        parent = Document(name="Preface.pdf", doc_type=DocType.file)
        db.save(parent)
        page1 = Document(name="page 1", doc_type=DocType.page, parent_id=parent.id)
        page2 = Document(name="page 2", doc_type=DocType.page, parent_id=parent.id)
        db.save(page1)
        db.save(page2)

        person = KnowledgeEntity(
            canonical_name="Louise Livingstone", entity_type=EntityType.person
        )
        place = KnowledgeEntity(canonical_name="Deloro", entity_type=EntityType.location)
        db.save(person)
        db.save(place)
        db.save(
            KnowledgeClaim(
                text="Livingstone signed.",
                source_document_id=page1.id,
                entity_ids=[person.id],
            )
        )
        db.save(
            KnowledgeClaim(
                text="Deloro appears.",
                source_document_id=page2.id,
                entity_ids=[place.id],
            )
        )

        page_result = asyncio.run(document_inspector.inspector(page1.id, db=db))
        assert page_result.claim_count == 1
        assert [entity.canonical_name for entity in page_result.entities] == [
            "Louise Livingstone"
        ]

        parent_result = asyncio.run(document_inspector.inspector(parent.id, db=db))
        assert parent_result.claim_count == 2
        assert {entity.canonical_name for entity in parent_result.entities} == {
            "Deloro",
            "Louise Livingstone",
        }


# -----------------------------------------------------------------------------
# Document knowledge-graph (canonical grouping endpoint, #1068)
# -----------------------------------------------------------------------------


class TestDocumentKnowledgeGraph:
    def test_unknown_document_404s(self, db):
        from fastapi import HTTPException
        from fichero_server.api.routes.document import inspector as document_inspector

        try:
            asyncio.run(document_inspector.knowledge_graph("no-such-id", db=db))
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404

    def test_empty_document_returns_no_groups(self, db):
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="empty.pdf", doc_type=DocType.file)
        db.save(doc)
        result = asyncio.run(document_inspector.knowledge_graph(doc.id, db=db))
        assert result.document_id == doc.id
        assert result.groups == []
        assert result.entity_count == 0
        assert result.claim_count == 0

    def test_groups_all_kinds_including_dates(self, db):
        """The Dates section must be present — its omission was #1068."""
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="page12.pdf", doc_type=DocType.file)
        db.save(doc)

        person = KnowledgeEntity(canonical_name="Louise Livingstone", entity_type=EntityType.person)
        place = KnowledgeEntity(canonical_name="Deloro", entity_type=EntityType.location)
        event = KnowledgeEntity(canonical_name="Filing of the Petition", entity_type=EntityType.event)
        keyword = KnowledgeEntity(canonical_name="mining", entity_type=EntityType.concept)
        for e in (person, place, event, keyword):
            db.save(e)

        db.save(KnowledgeClaim(text="Louise Livingstone signed.", source_document_id=doc.id, entity_ids=[person.id]))
        db.save(KnowledgeClaim(text="Deloro is in Ontario.", source_document_id=doc.id, entity_ids=[place.id]))
        db.save(KnowledgeClaim(text="The petition was filed.", source_document_id=doc.id, entity_ids=[event.id]))
        db.save(KnowledgeClaim(text="Mining was the industry.", source_document_id=doc.id, entity_ids=[keyword.id]))
        # Date-style claim — no entity, normalized date in metadata.
        db.save(KnowledgeClaim(
            text="1923-1945",
            source_document_id=doc.id,
            entity_ids=[],
            metadata={"date_normalized": "1923/1945"},
        ))

        result = asyncio.run(document_inspector.knowledge_graph(doc.id, db=db))
        kinds = [g.kind for g in result.groups]
        assert "date" in kinds, "Dates group must be surfaced (#1068)"
        assert set(kinds) == {"concept", "person", "location", "event", "date"}
        # Display order: concept first, date after event.
        assert kinds == ["concept", "person", "location", "event", "date"]
        assert result.entity_count == 5
        assert result.claim_count == 5
        date_group = next(g for g in result.groups if g.kind == "date")
        assert date_group.items[0].canonical_name == "1923-1945"
        assert date_group.items[0].entity_id is None

    def test_dedups_within_kind_and_keeps_all_claim_ids(self, db):
        """Multiple claims for the same canonical entity collapse to one row."""
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="dupes.pdf", doc_type=DocType.file)
        db.save(doc)
        entity = KnowledgeEntity(canonical_name="Davidson", entity_type=EntityType.person)
        db.save(entity)
        c1 = KnowledgeClaim(text="Davidson arrived.", source_document_id=doc.id, entity_ids=[entity.id])
        c2 = KnowledgeClaim(text="Davidson left.", source_document_id=doc.id, entity_ids=[entity.id])
        db.save(c1)
        db.save(c2)

        result = asyncio.run(document_inspector.knowledge_graph(doc.id, db=db))
        people = next(g for g in result.groups if g.kind == "person")
        assert len(people.items) == 1, "same canonical entity must dedup to one row"
        assert set(people.items[0].claim_ids) == {c1.id, c2.id}
        assert result.entity_count == 1
        assert result.claim_count == 2

    def test_merged_entity_claims_resolve_to_canonical_not_dropped(self, db):
        """Absorbed entities' claims attribute to the canonical entity.

        The old SwiftUI code skipped merged entities outright, silently
        dropping their claims — a cause of the #1068 under-counting.
        """
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="merged.pdf", doc_type=DocType.file)
        db.save(doc)
        canonical = KnowledgeEntity(canonical_name="J. Davidson", entity_type=EntityType.person)
        db.save(canonical)
        absorbed = KnowledgeEntity(
            canonical_name="Davidson",
            entity_type=EntityType.person,
            merged_into_id=canonical.id,
        )
        db.save(absorbed)

        # A claim still points at the absorbed entity.
        db.save(KnowledgeClaim(text="Davidson signed.", source_document_id=doc.id, entity_ids=[absorbed.id]))
        # And one points at the canonical directly.
        db.save(KnowledgeClaim(text="J. Davidson arrived.", source_document_id=doc.id, entity_ids=[canonical.id]))

        result = asyncio.run(document_inspector.knowledge_graph(doc.id, db=db))
        people = next(g for g in result.groups if g.kind == "person")
        # Both claims collapse onto the canonical entity — none dropped.
        assert len(people.items) == 1
        assert people.items[0].canonical_name == "J. Davidson"
        assert people.items[0].entity_id == canonical.id
        assert len(people.items[0].claim_ids) == 2


class TestDocumentOutline:
    def test_outline_aggregates_pages_structure_and_groups(self, db):
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(id="outline-doc", name="Book", doc_type=DocType.file)
        page1 = Document(id="outline-page-1", name="Page 1", doc_type=DocType.page, parent_id=doc.id, sequence=1)
        page2 = Document(id="outline-page-2", name="Page 2", doc_type=DocType.page, parent_id=doc.id, sequence=2)
        chunk = Document(id="outline-chunk", name="Chunk A", doc_type=DocType.chunk, parent_id=page1.id)
        db.save(doc)
        db.save(page1)
        db.save(page2)
        db.save(chunk)

        chapter = BookStructureNode(
            source_document_id=doc.id,
            title="Chapter 1",
            level=1,
            kind="chapter",
            start_sequence=1,
            end_sequence=2,
        )
        section = BookStructureNode(
            source_document_id=doc.id,
            title="Section 1.1",
            level=2,
            kind="section",
            start_sequence=1,
            end_sequence=1,
            parent_structure_id=chapter.id,
        )
        db.save(chapter)
        db.save(section)

        entity = KnowledgeEntity(canonical_name="Davidson", entity_type=EntityType.person)
        db.save(entity)
        db.save(KnowledgeClaim(text="Davidson signed.", source_document_id=page1.id, entity_ids=[entity.id]))
        db.save(Annotation(document_id=page1.id, kind=AnnotationKind.note, text="check this"))
        db.save(Artifact(document_id=page1.id, artifact_type="transcription", content="text"))
        db.save(DocumentCitation(source_document_id=page1.id, target_citation_text="cite"))

        result = asyncio.run(document_inspector.document_outline(doc.id, db=db))
        assert result.document_id == doc.id
        kinds = {row.kind for row in result.rows}
        assert {"page", "chapter", "section", "chunk", "annotation-group", "entity-group"} <= kinds
        rows = {row.id: row for row in result.rows}
        assert rows[page1.id].parent_id == doc.id
        assert rows[page1.id].source_document_id == page1.id
        assert rows[chunk.id].parent_id == page1.id
        assert rows[f"{doc.id}:annotations"].source_capability == "group"
        chapter_row = next(row for row in result.rows if row.kind == "chapter")
        assert chapter_row.label == "Chapter 1"
        assert chapter_row.depth == 1
        page_row = next(row for row in result.rows if row.kind == "page" and row.label == "Page 1")
        assert page_row.count >= 1

    def test_parent_pdf_rolls_up_page_claims_by_default(self, db):
        """Page-level KG rows surface when the parent PDF is selected."""
        from fichero_server.api.routes.document import inspector as document_inspector

        parent = Document(name="Preface.pdf", doc_type=DocType.file)
        db.save(parent)
        page = Document(name="Preface.pdf — page 1", doc_type=DocType.page, parent_id=parent.id)
        db.save(page)
        entity = KnowledgeEntity(canonical_name="Louise Livingstone", entity_type=EntityType.person)
        db.save(entity)
        db.save(KnowledgeClaim(text="Livingstone signed.", source_document_id=page.id, entity_ids=[entity.id]))

        result = asyncio.run(document_inspector.knowledge_graph(parent.id, db=db))
        assert result.include_children is True
        assert result.claim_count == 1
        assert result.groups[0].items[0].canonical_name == "Louise Livingstone"

    def test_leaf_document_has_empty_catalogue(self, db):
        """A plain document carries no catalogue artifacts (#1047)."""
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="leaf.pdf", doc_type=DocType.file)
        db.save(doc)
        result = asyncio.run(document_inspector.knowledge_graph(doc.id, db=db))
        assert result.catalogue == []

    def test_catalogue_artifacts_surface_narrative_first(self, db):
        """A catalogued folder surfaces its catalogue artifacts, narrative-first (#1047)."""
        from fichero_server.api.routes.document import inspector as document_inspector

        folder = Document(name="Letters", doc_type=DocType.folder)
        db.save(folder)
        # Saved out of display order — narrative must still come back first.
        db.save(Artifact(
            document_id=folder.id,
            artifact_type="catalogue.keywords",
            content="mining, water rights",
        ))
        db.save(Artifact(
            document_id=folder.id,
            artifact_type="catalogue.timeline",
            content="1923 — petition filed",
        ))
        db.save(Artifact(
            document_id=folder.id,
            artifact_type="catalogue.narrative",
            content="A folder of letters concerning a mining dispute.",
        ))
        # An unrelated artifact on the same folder must NOT be included.
        db.save(Artifact(
            document_id=folder.id,
            artifact_type="transcription",
            content="raw text",
        ))

        result = asyncio.run(document_inspector.knowledge_graph(folder.id, db=db))
        types = [a.artifact_type for a in result.catalogue]
        assert types == ["catalogue.narrative", "catalogue.timeline", "catalogue.keywords"]
        assert result.catalogue[0].content.startswith("A folder of letters")

    def test_legacy_catalogue_artifact_included(self, db):
        """The legacy single-output 'catalogue' type still surfaces (#1047)."""
        from fichero_server.api.routes.document import inspector as document_inspector

        folder = Document(name="Old Letters", doc_type=DocType.folder)
        db.save(folder)
        db.save(Artifact(
            document_id=folder.id,
            artifact_type="catalogue",
            content="Legacy catalogue narrative.",
        ))
        result = asyncio.run(document_inspector.knowledge_graph(folder.id, db=db))
        assert [a.artifact_type for a in result.catalogue] == ["catalogue"]

    def test_include_children_aggregates_page_claims_onto_parent(self, db):
        """include_children walks the doc tree and surfaces page-child KG (#1069)."""
        from fichero_server.api.routes.document import inspector as document_inspector

        parent = Document(name="Preface.pdf", doc_type=DocType.file)
        db.save(parent)
        page1 = Document(name="page 1", doc_type=DocType.page, parent_id=parent.id)
        page2 = Document(name="page 2", doc_type=DocType.page, parent_id=parent.id)
        db.save(page1)
        db.save(page2)

        person = KnowledgeEntity(canonical_name="Louise Livingstone", entity_type=EntityType.person)
        place = KnowledgeEntity(canonical_name="Deloro", entity_type=EntityType.location)
        db.save(person)
        db.save(place)
        # Same entity mentioned on both pages — must dedup to one row.
        db.save(KnowledgeClaim(text="Livingstone arrived.", source_document_id=page1.id, entity_ids=[person.id]))
        db.save(KnowledgeClaim(text="Livingstone departed.", source_document_id=page2.id, entity_ids=[person.id]))
        db.save(KnowledgeClaim(text="Deloro is north.", source_document_id=page2.id, entity_ids=[place.id]))

        result = asyncio.run(
            document_inspector.knowledge_graph(parent.id, include_children=True, db=db)
        )
        assert result.include_children is True
        assert result.claim_count == 3
        kinds = {g.kind for g in result.groups}
        assert kinds == {"person", "location"}
        people = next(g for g in result.groups if g.kind == "person")
        assert len(people.items) == 1, "cross-page same entity must dedup"
        assert len(people.items[0].claim_ids) == 2


# -----------------------------------------------------------------------------
# Entity inspector
# -----------------------------------------------------------------------------


class TestEntityInspector:
    def test_unknown_entity_404s(self, db):
        from fastapi import HTTPException
        from fichero_server.api.routes.entity import inspector as entity_inspector

        try:
            asyncio.run(entity_inspector.inspector("no-such-id", db=db))
            raise AssertionError("expected 404")
        except HTTPException as exc:
            assert exc.status_code == 404

    def test_entity_aggregates_claims_and_documents(self, db):
        from fichero_server.api.routes.entity import inspector as entity_inspector

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
        # Summary is entity-level facts, not a claim echo (#1050).
        assert result.summary == "Person · 2 claims across 2 documents"

    def test_summary_is_not_a_claim_duplicate(self, db):
        """The header summary must never echo claim #1 (#1050)."""
        from fichero_server.api.routes.entity import inspector as entity_inspector

        # Extractor overloads description with one claim's predicate —
        # the exact bug #1050 describes.
        entity = KnowledgeEntity(
            canonical_name="Leidy",
            entity_type=EntityType.person,
            description="cleared gravel and stones from a wooden sluice",
        )
        db.save(entity)
        doc = Document(name="page3.pdf", doc_type=DocType.file)
        db.save(doc)
        db.save(KnowledgeClaim(
            text="cleared gravel and stones from a wooden sluice",
            source_document_id=doc.id,
            entity_ids=[entity.id],
        ))

        result = asyncio.run(entity_inspector.inspector(entity.id, db=db))
        assert result.summary != entity.description
        assert result.summary != result.claims[0].text
        assert result.summary == "Person · 1 claim"

    def test_summary_handles_no_claims_and_aliases(self, db):
        """Zero-claim entity and alias rendering (#1050)."""
        from fichero_server.api.routes.entity import inspector as entity_inspector

        bare = KnowledgeEntity(canonical_name="Deloro", entity_type=EntityType.location)
        db.save(bare)
        result = asyncio.run(entity_inspector.inspector(bare.id, db=db))
        assert result.summary == "Place · no claims yet"

        aliased = KnowledgeEntity(
            canonical_name="J. Davidson",
            entity_type=EntityType.person,
            aliases=["Davidson", "John Davidson"],
        )
        db.save(aliased)
        result = asyncio.run(entity_inspector.inspector(aliased.id, db=db))
        assert result.summary == "Person · no claims yet · also known as Davidson, John Davidson"

        # More than 3 aliases — cap at 3 with an ellipsis, never silent truncation.
        many = KnowledgeEntity(
            canonical_name="Robert",
            entity_type=EntityType.person,
            aliases=["Bob", "Rob", "Bobby", "Roberto"],
        )
        db.save(many)
        result = asyncio.run(entity_inspector.inspector(many.id, db=db))
        assert result.summary == "Person · no claims yet · also known as Bob, Rob, Bobby…"


# -----------------------------------------------------------------------------
# Document rollup (#2258) — cheap per-type child counts for a collapsed row
# -----------------------------------------------------------------------------


class TestDocumentRollup:
    def test_empty_document_returns_zero_counts(self, db):
        from fichero_server.api.routes.document import inspector as document_inspector

        doc = Document(name="empty.pdf", doc_type=DocType.file)
        db.save(doc)
        result = asyncio.run(document_inspector.document_rollup(doc.id, db=db))
        assert result.document_id == doc.id
        assert result.artifacts == 0
        assert result.entities == 0
        assert result.notes == 0
        assert result.claims == 0
        assert result.pages == 0

    def test_nonexistent_document_404s(self, db):
        import pytest
        from fastapi import HTTPException

        from fichero_server.api.routes.document import inspector as document_inspector

        with pytest.raises(HTTPException) as excinfo:
            asyncio.run(document_inspector.document_rollup("does-not-exist", db=db))
        assert excinfo.value.status_code == 404

    def test_rollup_counts_children_across_descendants(self, db):
        """Counts roll up the document and its descendant pages (#2258)."""
        from fichero_server.api.routes.document import inspector as document_inspector

        parent = Document(name="Book.pdf", doc_type=DocType.file)
        page1 = Document(name="page 1", doc_type=DocType.page, parent_id=parent.id, sequence=1)
        page2 = Document(name="page 2", doc_type=DocType.page, parent_id=parent.id, sequence=2)
        db.save(parent)
        db.save(page1)
        db.save(page2)

        # Entity linked via a claim on a page child.
        person = KnowledgeEntity(canonical_name="Livingstone", entity_type=EntityType.person)
        db.save(person)
        # Entity surfaced only by per-page scope (no claim) — must still count.
        scoped = KnowledgeEntity(
            canonical_name="Deloro",
            entity_type=EntityType.location,
            source_document_ids=[page2.id],
        )
        db.save(scoped)

        db.save(KnowledgeClaim(text="Livingstone signed.", source_document_id=page1.id, entity_ids=[person.id]))
        db.save(KnowledgeClaim(text="Another claim.", source_document_id=page2.id, entity_ids=[person.id]))
        db.save(Artifact(document_id=page1.id, artifact_type="transcription", content="text"))
        db.save(Note(title="a note", body="a note", linked_document_ids=[parent.id]))

        result = asyncio.run(document_inspector.document_rollup(parent.id, db=db))
        assert result.document_id == parent.id
        assert result.pages == 2
        assert result.claims == 2
        assert result.artifacts == 1
        assert result.notes == 1
        # person (via claims) + scoped (via per-page source scope), deduped.
        assert result.entities == 2
