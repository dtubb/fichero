"""Tests for the hosted document knowledge-surface HTML route (#1228)."""

from fichero.knowledge_models import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero.models import Document, DocType, FileType, Status


def _make_document(*, doc_id: str, name: str, doc_type: DocType, page_content: str | None = None, parent_id: str | None = None, sequence: int | None = None, file_type: FileType | None = None) -> Document:
    return Document(
        id=doc_id,
        name=name,
        doc_type=doc_type,
        file_type=file_type,
        parent_id=parent_id,
        page_content=page_content,
        sequence=sequence,
        status=Status.completed,
    )


class TestDocumentViewRoute:
    def test_html_route_seeds_document_entities_and_claims(self, client, db):
        doc = _make_document(
            doc_id="doc-1",
            name="Letter.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Alice signed the deed.",
        )
        db.save(doc)

        entity = KnowledgeEntity(
            id="entity-1",
            canonical_name="Alice",
            entity_type=EntityType.person,
            aliases=[],
        )
        db.save(entity)

        claim = KnowledgeClaim(
            id="claim-1",
            text="Alice signed the deed.",
            source_document_id=doc.id,
            source_page_label="p.4",
            source_excerpt="signed the deed",
            entity_ids=[entity.id],
            subject_canonical="Alice",
            predicate_verb="signed",
            object_phrase="the deed",
        )
        db.save(claim)

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        assert "Knowledge Surface" in response.text
        assert '"id": "claim-1"' in response.text
        assert '"canonical_name": "Alice"' in response.text
        assert "Transcript" in response.text
        assert "Digest" in response.text
        assert "Graph" in response.text

    def test_html_uses_apple_system_fonts_and_native_tab_bridge(self, client, db):
        # #1228 follow-up: fonts are Apple system defaults, the in-page tab bar
        # is hidden (the native Swift toolbar owns it), and `fichero.showTab`
        # exists so the toolbar can drive the web content.
        doc = _make_document(
            doc_id="doc-fonts",
            name="Fonts.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Body text.",
        )
        db.save(doc)

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        # Apple system font stack present; the old serif stack is gone.
        assert "-apple-system" in response.text
        assert "ui-serif, Georgia, serif" not in response.text
        # Native toolbar drives the tabs; in-page tab bar is hidden but its
        # showTab hook is available.
        assert "showTab(tab)" in response.text

    def test_page_children_are_folded_into_transcript_when_parent_has_none(self, client, db):
        doc = _make_document(
            doc_id="pdf-1",
            name="Bundle.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        page1 = _make_document(
            doc_id="page-1",
            name="Page 1",
            doc_type=DocType.page,
            page_content="First page transcript",
            parent_id=doc.id,
            sequence=1,
        )
        page2 = _make_document(
            doc_id="page-2",
            name="Page 2",
            doc_type=DocType.page,
            page_content="Second page transcript",
            parent_id=doc.id,
            sequence=2,
        )
        db.save(doc)
        db.save(page1)
        db.save(page2)

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        assert "Page 1" in response.text
        assert "First page transcript" in response.text
        assert "Page 2" in response.text
        assert "Second page transcript" in response.text

    def test_page_child_claims_appear_in_parent_view(self, client, db):
        """Claims stored on page child docs must surface in the parent document view (#1249)."""
        doc = _make_document(
            doc_id="pdf-parent",
            name="Archive.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        page = _make_document(
            doc_id="page-child-1",
            name="Page 1",
            doc_type=DocType.page,
            page_content="Hernández sold the estate.",
            parent_id=doc.id,
            sequence=1,
        )
        db.save(doc)
        db.save(page)

        entity = KnowledgeEntity(
            id="entity-pg1",
            canonical_name="Hernández",
            entity_type=EntityType.person,
            aliases=[],
        )
        db.save(entity)

        # Claim is scoped to the PAGE child doc, not the parent.
        claim = KnowledgeClaim(
            id="claim-pg1",
            text="Hernández sold the estate.",
            source_document_id=page.id,
            source_page_label="p.1",
            source_excerpt="sold the estate",
            entity_ids=[entity.id],
            subject_canonical="Hernández",
            predicate_verb="sold",
            object_phrase="the estate",
        )
        db.save(claim)

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        assert '"id": "claim-pg1"' in response.text
        assert '"canonical_name": "Hernández"' in response.text

    def test_missing_document_returns_404(self, client):
        response = client.get("/view/document/no-such-document")
        assert response.status_code == 404
