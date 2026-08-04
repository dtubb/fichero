"""Tests for the hosted document knowledge-surface HTML route (#1228)."""

import json
import re

from fichero_server.models.knowledge import EntityType, KnowledgeClaim, KnowledgeEntity
from fichero_server.db import Database
from fichero_server.models import Document, DocType, FileType, Status


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
        # The page no longer carries an eyebrow/title header — the app's
        # selection already says what's shown (#1244). The document name lives
        # only in the browser <title>, and the redundant in-page chrome is gone.
        assert "<title>Letter.pdf</title>" in response.text
        assert '<div class="eyebrow">' not in response.text
        assert '"id": "claim-1"' in response.text
        assert '"canonical_name": "Alice"' in response.text
        assert "Transcript" in response.text
        assert "Digest" in response.text
        assert "Graph" in response.text
        assert "Timeline" in response.text
        assert "Map" in response.text

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

    def test_document_view_uses_scoped_queries_not_full_table_scans(
        self, client, db, monkeypatch
    ):
        doc = _make_document(
            doc_id="scoped-parent", name="Scoped.pdf", doc_type=DocType.file
        )
        page = _make_document(
            doc_id="scoped-page",
            name="Page 1",
            doc_type=DocType.page,
            parent_id=doc.id,
        )
        db.save(doc)
        db.save(page)
        db.save(
            KnowledgeClaim(
                id="scoped-claim", text="Scoped claim", source_document_id=page.id
            )
        )

        original_all = Database.all

        def no_full_scan(self, model):
            if model in {Document, KnowledgeClaim, KnowledgeEntity}:
                raise AssertionError(f"unexpected full scan of {model.__name__}")
            return original_all(self, model)

        monkeypatch.setattr(Database, "all", no_full_scan)

        response = client.get(f"/view/document/{doc.id}")

        assert response.status_code == 200
        assert '"id": "scoped-claim"' in response.text

    def test_document_view_includes_doc_scoped_event_entities_without_claim_links(self, client, db):
        doc = _make_document(
            doc_id="doc-events",
            name="Diary.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Friday, October 19, 1923. Andagoya.",
        )
        db.save(doc)

        event = KnowledgeEntity(
            id="event-1",
            canonical_name="Friday, October 19, 1923",
            entity_type=EntityType.event,
            source_document_ids=[doc.id],
            date_values=[{
                "start": "1923-10-19",
                "label": "Friday, October 19, 1923",
                "basis": "asserted",
            }],
        )
        place = KnowledgeEntity(
            id="place-1",
            canonical_name="Andagoya",
            entity_type=EntityType.location,
            source_document_ids=[doc.id],
            place_values=[{
                "label": "Andagoya",
                "lat": 5.093,
                "lon": -76.695,
                "basis": "asserted",
            }],
        )
        db.save(event)
        db.save(place)

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        assert '"id": "event-1"' in response.text
        assert '"entity_type": "event"' in response.text
        assert '"date_values": [{"id":' in response.text
        assert '"id": "place-1"' in response.text
        assert '"place_values": [{"id":' in response.text

    def test_page_payload_carries_every_page_including_untranscribed(self, client, db):
        """The reader's page list is the page CHILDREN, gaps included (#4356)."""
        doc = _make_document(
            doc_id="pdf-gaps",
            name="Gappy.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        db.save(doc)
        db.save(
            _make_document(
                doc_id="gap-page-1",
                name="Page 1",
                doc_type=DocType.page,
                page_content="First page transcript",
                parent_id=doc.id,
                sequence=1,
            )
        )
        # Page 2 has NO transcription — it must still appear, in position.
        db.save(
            _make_document(
                doc_id="gap-page-2",
                name="Page 2",
                doc_type=DocType.page,
                parent_id=doc.id,
                sequence=2,
            )
        )
        db.save(
            _make_document(
                doc_id="gap-page-3",
                name="Page 3",
                doc_type=DocType.page,
                page_content="Third page transcript",
                parent_id=doc.id,
                sequence=3,
            )
        )

        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        payload = json.loads(
            re.search(r"const documentData = (\{.*?\});\n", response.text, re.S).group(1)
        )
        pages = payload["pages"]
        assert [page["number"] for page in pages] == [1, 2, 3]
        assert [page["has_content"] for page in pages] == [True, False, True]
        assert pages[1]["content"] == ""
        # The flat transcript keeps carrying only pages WITH content: claim
        # char offsets index into it, so empty pages must not shift them.
        # The transcript is now DERIVED from these pages rather than shipped
        # alongside them (it was on the wire twice), so the invariant is
        # asserted against the derived string — same rule, one copy.
        from fichero_server.api.routes.system.views import (
            TRANSCRIPT_FROM_PAGES,
            transcript_text,
        )

        assert payload["transcript_source"] == TRANSCRIPT_FROM_PAGES
        assert payload["page_content"] is None
        assert "Page 2\n" not in transcript_text(pages)

    def test_transcript_pages_is_pure_over_loaded_documents(self):
        """Ordering + the empty-page rule are testable without a database."""
        from fichero_server.api.routes.system.views import transcript_pages, transcript_text

        parent = _make_document(doc_id="p", name="Deed.pdf", doc_type=DocType.file)
        children = [
            _make_document(
                doc_id="c2", name="Page 2", doc_type=DocType.page, sequence=2, parent_id="p"
            ),
            _make_document(
                doc_id="c1",
                name="Page 1",
                doc_type=DocType.page,
                sequence=1,
                parent_id="p",
                page_content="only text",
            ),
        ]
        # Callers hand pages in sequence; the payload preserves that order.
        pages = transcript_pages(parent, sorted(children, key=lambda d: d.sequence or 0))
        assert [page["number"] for page in pages] == [1, 2]
        assert pages[1]["has_content"] is False
        assert transcript_text(pages) == "Page 1\nonly text"

    def test_transcript_pages_of_leaf_document_is_its_own_page(self):
        from fichero_server.api.routes.system.views import transcript_pages

        leaf = _make_document(
            doc_id="leaf",
            name="Note.txt",
            doc_type=DocType.file,
            page_content="body text",
        )
        pages = transcript_pages(leaf, [])
        assert len(pages) == 1
        assert pages[0]["has_content"] is True
        # A leaf with no content at all yields no pages — the reader then shows
        # its own "nothing here yet" state rather than a fake page 1.
        empty = _make_document(doc_id="leaf2", name="Empty.txt", doc_type=DocType.file)
        assert transcript_pages(empty, []) == []

    def test_missing_document_returns_404(self, client):
        response = client.get("/view/document/no-such-document")
        assert response.status_code == 404

    def test_global_kg_view_returns_shared_graph_payload(self, client, db):
        entity = KnowledgeEntity(
            id="entity-global-1",
            canonical_name="Canal Company",
            entity_type=EntityType.organization,
            aliases=[],
        )
        db.save(entity)
        claim = KnowledgeClaim(
            id="claim-global-1",
            text="Canal Company financed the works.",
            source_document_id="doc-any",
            entity_ids=[entity.id],
            subject_canonical="Canal Company",
            predicate_verb="financed",
            object_phrase="the works",
        )
        db.save(claim)

        response = client.get("/view/kg/global")
        assert response.status_code == 200
        assert "<title>Knowledge Graph</title>" in response.text
        assert '"id": "entity-global-1"' in response.text
        assert '"id": "claim-global-1"' in response.text

    def test_global_kg_view_caps_embedded_graph_payload(self, client, db, monkeypatch):
        db.save(
            KnowledgeEntity(
                id="global-capped-entity",
                canonical_name="Global Capped Entity",
                entity_type=EntityType.person,
            )
        )
        calls: list[tuple[type, int]] = []
        original_query_page = Database.query_page
        original_count = Database.count

        def counting_query_page(self, model, *, limit, offset=0):
            calls.append((model, limit))
            return original_query_page(self, model, limit=limit, offset=offset)

        def large_count(self, model, **filters):
            if model is KnowledgeEntity:
                return 251
            return original_count(self, model, **filters)

        from fichero_server.api.routes.system.views import _GLOBAL_KG_LIMIT

        monkeypatch.setattr(Database, "query_page", counting_query_page)
        monkeypatch.setattr(Database, "count", large_count)

        response = client.get("/view/kg/global")

        assert response.status_code == 200
        assert calls == [
            (KnowledgeEntity, _GLOBAL_KG_LIMIT),
            (KnowledgeClaim, _GLOBAL_KG_LIMIT),
        ]
        assert '"shown_entities": 1' in response.text
        assert '"total_entities": 251' in response.text
        assert "select a node to load its neighborhood" in response.text


class TestTranscriptIsNotSentTwice:
    """The document text rode the wire twice: once as `pages[].content` and
    again as the `page_content` transcript that is a pure re-join of those same
    strings. Measured on a 20-page document: 135.7 KB of document JSON for
    68 KB of unique text, exactly 2x — and the transcript is ~96% of the payload
    for a document with no claims yet.

    The client rebuilds it. These tests pin the two things that makes safe:
    the join must be byte-identical, and the reader must be told which reading
    applies rather than inferring it from a null.
    """

    @staticmethod
    def _payload(response):
        return json.loads(
            re.search(r"const documentData = (\{.*?\});\n", response.text, re.S).group(1)
        )

    @staticmethod
    def _js_join(pages):
        """The template's join, transcribed. If this and `transcript_text`
        disagree by one byte, every claim highlight in the document shifts.
        """
        return "\n\n".join(
            f"Page {page['number']}\n{page['content']}"
            for page in pages
            if page["has_content"]
        )

    def _seed_pdf(self, db, *, pages, doc_id="pdf-dedupe"):
        parent = _make_document(
            doc_id=doc_id, name="Diary.pdf", doc_type=DocType.file, file_type=FileType.pdf
        )
        db.save(parent)
        for number, text in enumerate(pages, start=1):
            db.save(
                _make_document(
                    doc_id=f"{doc_id}-p{number}",
                    name=f"Page {number}",
                    doc_type=DocType.page,
                    parent_id=parent.id,
                    sequence=number,
                    page_content=text,
                )
            )
        return parent

    def test_a_page_derived_transcript_is_not_shipped(self, client, db):
        parent = self._seed_pdf(db, pages=["First page text.", "Second page text."])

        payload = self._payload(client.get(f"/view/document/{parent.id}"))

        assert payload["transcript_source"] == "pages"
        assert payload["page_content"] is None, "the transcript must not ride along when it is derivable"
        assert [page["content"] for page in payload["pages"]] == [
            "First page text.",
            "Second page text.",
        ]

    def test_the_client_join_is_byte_identical_to_the_server_one(self, client, db):
        """The whole change rests on this. Claim `source_char_start`/`_end` are
        offsets into the flat transcript, so a single differing byte silently
        mis-highlights every claim rather than failing loudly.
        """
        from fichero_server.api.routes.system.views import transcript_text

        pages = ["Alice signed the deed.", "", "Bearing witness: Bob.", "  ", "Final page."]
        parent = self._seed_pdf(db, pages=pages, doc_id="pdf-identical")

        payload = self._payload(client.get(f"/view/document/{parent.id}"))
        rebuilt = self._js_join(payload["pages"])

        assert rebuilt == transcript_text(payload["pages"])
        # And the empty/whitespace-only pages are excluded from BOTH, so the
        # offsets are the same ones the claims were extracted against.
        assert "Page 2\n" not in rebuilt
        assert "Page 4\n" not in rebuilt
        assert rebuilt.startswith("Page 1\nAlice signed the deed.")

    def test_a_document_that_owns_its_text_still_ships_it(self, client, db):
        """A leaf document's transcript is NOT derivable from page children —
        there are none. It must still travel, and say so.
        """
        doc = _make_document(
            doc_id="leaf-1",
            name="Letter.txt",
            doc_type=DocType.file,
            page_content="A single letter, no pages.",
        )
        db.save(doc)

        payload = self._payload(client.get(f"/view/document/{doc.id}"))

        assert payload["transcript_source"] == "document"
        assert payload["page_content"] == "A single letter, no pages."

    def test_the_reading_is_stated_not_inferred_from_a_null(self, client, db):
        """`page_content: null` alone is ambiguous — "derive it" and "this
        document has no text" are different facts. The discriminator is explicit.
        """
        empty = _make_document(doc_id="empty-1", name="Blank.pdf", doc_type=DocType.file)
        db.save(empty)

        payload = self._payload(client.get(f"/view/document/{empty.id}"))

        assert payload["transcript_source"] in {"document", "pages"}
        assert "transcript_source" in payload

    def test_the_template_join_matches_the_python_one(self):
        """Guard the actual template text, not a copy of it: the JS join is the
        thing that has to stay in step, and it lives in HTML where no Python
        test would otherwise look.
        """
        from pathlib import Path

        import fichero_server

        template = (
            Path(fichero_server.__file__).parent / "api" / "templates" / "document_view.html"
        ).read_text()

        assert "const documentTranscript" in template, "the derived transcript is gone"
        assert '.filter((page) => page.has_content)' in template, "empty pages must stay excluded"
        assert '`Page ${page.number}\\n${page.content}`' in template, "the join shape must match transcript_text"
        assert '.join("\\n\\n")' in template, "pages are separated by a blank line, as on the server"
