"""Tests for the hosted document knowledge-surface HTML route (#1228)."""

import json
import re
from pathlib import Path

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


class TestPagesFilter:
    """`?pages=` narrows the assembled transcript to a SELECTION of child
    pages (2026-08-25: the multi-select reader rides the same renderer)."""

    def _bundle(self, db):
        doc = _make_document(
            doc_id="pf-doc", name="Bundle.pdf", doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        pages = [
            _make_document(
                doc_id=f"pf-page-{n}", name=f"Page {n}", doc_type=DocType.page,
                page_content=f"Transcript {n}", parent_id=doc.id, sequence=n,
            )
            for n in (1, 2, 3)
        ]
        db.save(doc)
        for page in pages:
            db.save(page)
        return doc

    def test_filter_renders_only_the_selected_pages(self, client, db):
        doc = self._bundle(db)
        response = client.get(f"/view/document/{doc.id}?pages=pf-page-1,pf-page-3")
        assert response.status_code == 200
        assert "Transcript 1" in response.text
        assert "Transcript 3" in response.text
        assert "Transcript 2" not in response.text

    def test_filter_ignores_the_parents_own_page_content(self, client, db):
        """A parent with its own page_content must NOT widen a filtered view
        back to the whole document."""
        doc = self._bundle(db)
        doc.page_content = "WHOLE DOCUMENT TEXT"
        db.save(doc)
        response = client.get(f"/view/document/{doc.id}?pages=pf-page-2")
        assert response.status_code == 200
        assert "Transcript 2" in response.text
        assert "WHOLE DOCUMENT TEXT" not in response.text

    def test_unknown_ids_are_ignored_not_404(self, client, db):
        doc = self._bundle(db)
        response = client.get(f"/view/document/{doc.id}?pages=pf-page-2,gone")
        assert response.status_code == 200
        assert "Transcript 2" in response.text

    def test_no_filter_is_unchanged(self, client, db):
        doc = self._bundle(db)
        response = client.get(f"/view/document/{doc.id}")
        assert response.status_code == 200
        for n in (1, 2, 3):
            assert f"Transcript {n}" in response.text


class TestRegionScopedView:
    """A region-scoped reader shows ALL regions of that view (Daniel,
    2026-08-29) — same page, same output type — through the ONE renderer."""

    def _page_with_regions(self, db):
        from fichero_server.models import NodeRegion

        page = _make_document(
            doc_id="rg-page", name="Sheet 4", doc_type=DocType.file,
            file_type=FileType.image, page_content="THE WHOLE SHEET TEXT",
        )
        db.save(page)
        regions = []
        for n in (1, 2, 3):
            region = Document(
                id=f"rg-entry-{n}", name=f"1933-01-0{n}", parent_id=page.id,
                doc_type=DocType.file, node_kind="entry", sequence=n,
                page_content=f"Entry text {n}", status=Status.completed,
                region_in_parent=NodeRegion(rect=[0.0, 0.1 * n, 1.0, 0.1]),
            )
            db.save(region)
            regions.append(region)
        return page, regions

    def test_region_children_fold_into_the_transcript(self, client, db):
        page, _ = self._page_with_regions(db)
        response = client.get(f"/view/document/{page.id}")
        assert response.status_code == 200
        for n in (1, 2, 3):
            assert f"Entry text {n}" in response.text
        # The parent's own flat text must not double the region list.
        assert "THE WHOLE SHEET TEXT" not in response.text
        # Region sections are marked so the reader shows their NAMES —
        # ordinary sheets stay numbers only.
        assert '"is_region": true' in response.text

    def test_requesting_one_region_shows_the_whole_cohort(self, client, db):
        page, regions = self._page_with_regions(db)
        response = client.get(f"/view/document/{regions[1].id}")
        assert response.status_code == 200
        for n in (1, 2, 3):
            assert f"Entry text {n}" in response.text

    def test_cohort_excludes_other_producers_and_deleted_regions(self, client, db):
        from fichero_server.core.timeutil import utc_now
        from fichero_server.models import NodeRegion

        page, regions = self._page_with_regions(db)
        other = Document(
            id="rg-segment", name="Segment", parent_id=page.id,
            doc_type=DocType.file, node_kind="segment", sequence=9,
            page_content="A segment from a different tool",
            status=Status.completed,
            region_in_parent=NodeRegion(rect=[0.0, 0.5, 1.0, 0.1]),
        )
        db.save(other)
        regions[2].deleted_at = utc_now()
        db.save(regions[2])
        response = client.get(f"/view/document/{regions[0].id}")
        assert response.status_code == 200
        assert "Entry text 1" in response.text
        assert "Entry text 2" in response.text
        # Removed by a re-run: soft-deleted regions stay out.
        assert "Entry text 3" not in response.text
        # A different producer's output is a different view, not this cohort.
        assert "A segment from a different tool" not in response.text

    def test_pages_filter_applies_to_regions_too(self, client, db):
        page, _ = self._page_with_regions(db)
        response = client.get(f"/view/document/{page.id}?pages=rg-entry-2")
        assert response.status_code == 200
        assert "Entry text 2" in response.text
        assert "Entry text 1" not in response.text

    def test_region_cohort_is_pure(self):
        from fichero_server.api.routes.system.views import region_cohort
        from fichero_server.models import NodeRegion

        region = NodeRegion(rect=[0.0, 0.0, 1.0, 0.5])
        anchor = Document(
            id="a", name="a", doc_type=DocType.file, node_kind="entry",
            status=Status.completed, region_in_parent=region,
        )
        sibling = Document(
            id="b", name="b", doc_type=DocType.file, node_kind="entry",
            status=Status.completed, region_in_parent=region,
        )
        stranger = Document(
            id="c", name="c", doc_type=DocType.file, node_kind="segment",
            status=Status.completed, region_in_parent=region,
        )
        cohort = region_cohort([anchor, sibling, stranger], anchor)
        assert [doc.id for doc in cohort] == ["a", "b"]


class TestRepresentationParameter:
    """`?representation=` flips the SAME page to another reading of the same
    scope (Daniel, 2026-08-29): each page's content becomes its latest
    artifact of that type; pages without one stay in sequence, empty."""

    def _bundle_with_artifacts(self, db):
        from fichero_server.models import Artifact

        doc = _make_document(
            doc_id="rp-doc", name="Letters.pdf", doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        db.save(doc)
        for n in (1, 2):
            db.save(_make_document(
                doc_id=f"rp-page-{n}", name=f"Page {n}", doc_type=DocType.page,
                page_content=f"Live content {n}", parent_id=doc.id, sequence=n,
            ))
        db.save(Artifact(
            id="rp-art-old", document_id="rp-page-1",
            artifact_type="translation", content="OLD translation 1", version=1,
        ))
        db.save(Artifact(
            id="rp-art-new", document_id="rp-page-1",
            artifact_type="translation", content="NEW translation 1", version=2,
        ))
        return doc

    def test_representation_substitutes_latest_artifact_content(self, client, db):
        doc = self._bundle_with_artifacts(db)
        response = client.get(f"/view/document/{doc.id}?representation=translation")
        assert response.status_code == 200
        assert "NEW translation 1" in response.text
        assert "OLD translation 1" not in response.text
        # The live text does not leak into a representation view.
        assert "Live content 1" not in response.text

    def test_page_without_that_representation_stays_in_sequence_empty(self, client, db):
        doc = self._bundle_with_artifacts(db)
        response = client.get(f"/view/document/{doc.id}?representation=translation")
        match = re.search(r'"pages": (\[.*?\])[,}]', response.text, re.S)
        assert match is not None
        pages = json.loads(match.group(1))
        assert [p["number"] for p in pages] == [1, 2]
        assert pages[1]["has_content"] is False
        assert '"representation": "translation"' in response.text

    def test_content_representation_is_the_default_reading(self, client, db):
        doc = self._bundle_with_artifacts(db)
        response = client.get(f"/view/document/{doc.id}?representation=content")
        assert response.status_code == 200
        assert "Live content 1" in response.text
        assert "NEW translation 1" not in response.text

    def test_represented_pages_is_pure(self):
        from fichero_server.api.routes.system.views import represented_pages
        from fichero_server.models import Artifact

        pages = [
            {"id": "p1", "number": 1, "label": "Page 1", "content": "live", "has_content": True},
            {"id": "p2", "number": 2, "label": "Page 2", "content": "live", "has_content": True},
        ]
        artifacts = [
            Artifact(document_id="p1", artifact_type="translation", content="hola"),
            Artifact(document_id="p1", artifact_type="summary", content="not this type"),
            Artifact(document_id="p2", artifact_type="translation", content="   "),
        ]
        result = represented_pages(pages, artifacts, "translation")
        assert result[0]["content"] == "hola"
        assert result[0]["has_content"] is True
        # Whitespace-only artifact content is not a reading.
        assert result[1]["content"] == ""
        assert result[1]["has_content"] is False


class TestTableRepresentation:
    """Table-family artifacts render as a REAL table (Daniel, 2026-08-29
    bedtime): ?representation=table parses the artifact server-side — stdlib
    csv, never a hand-rolled split — and ships headers + rows."""

    def _page(self):
        return {"id": "p1", "number": 1, "label": "Page 1", "content": "live", "has_content": True}

    def test_quoted_comma_csv_keeps_its_columns(self):
        from fichero_server.api.routes.system.views import represented_pages
        from fichero_server.models import Artifact

        csv_text = (
            '"entry_text","amount_original","notes"\n'
            '"Cash, on hand","iiiUdcccxx","carried, then checked"\n'
            '"He said ""monta""","78.13",""\n'
        )
        artifact = Artifact(document_id="p1", artifact_type="table", content=csv_text)
        result = represented_pages([self._page()], [artifact], "table")
        table = result[0]["table"]
        assert table["headers"] == ["entry_text", "amount_original", "notes"]
        # The quoted comma stays INSIDE its field — the whole point.
        assert table["rows"][0] == ["Cash, on hand", "iiiUdcccxx", "carried, then checked"]
        # Doubled quotes decode to a literal quote.
        assert table["rows"][1][0] == 'He said "monta"'

    def test_ragged_rows_are_padded_never_dropped(self):
        from fichero_server.api.routes.system.views import represented_pages
        from fichero_server.models import Artifact

        artifact = Artifact(
            document_id="p1", artifact_type="table",
            content="a,b,c\n1,2\n4,5,6,7\n",
        )
        result = represented_pages([self._page()], [artifact], "table")
        table = result[0]["table"]
        # Width follows the widest row; short rows pad with empty cells.
        assert table["headers"] == ["a", "b", "c", ""]
        assert table["rows"] == [["1", "2", "", ""], ["4", "5", "6", "7"]]

    def test_json_rows_payload_renders_through_the_same_table(self):
        from fichero_server.api.routes.system.views import represented_pages
        from fichero_server.models import Artifact

        artifact = Artifact(
            document_id="p1", artifact_type="table", content=None,
            data={"headers": ["date", "amount"], "rows": [["1933-01-01", 78.13]]},
        )
        result = represented_pages([self._page()], [artifact], "table")
        table = result[0]["table"]
        assert table["headers"] == ["date", "amount"]
        # Cells stringify — the template escapes strings, not floats.
        assert table["rows"] == [["1933-01-01", "78.13"]]
        # A data-only table IS content.
        assert result[0]["has_content"] is True

    def test_untabular_table_artifact_falls_back_to_text(self):
        from fichero_server.api.routes.system.views import represented_pages
        from fichero_server.models import Artifact

        artifact = Artifact(
            document_id="p1", artifact_type="table",
            content="MEMORANDA\nCash On Hand Jan. 1, 1933\n",
        )
        result = represented_pages([self._page()], [artifact], "table")
        # Plain-text output (the Marshall v4 pre-CSV runs look like this)
        # still parses: lines become rows, padded to one consistent width —
        # never an exception, never a dropped line.
        table = result[0]["table"]
        assert table is not None
        # First line heads (include_headers defaults on), the rest are rows,
        # all padded to one consistent width.
        assert table["headers"] is not None
        assert len({len(row) for row in [table["headers"], *table["rows"]]}) == 1

    def test_table_view_ships_the_parsed_table_over_the_route(self, client, db):
        from fichero_server.models import Artifact

        doc = _make_document(
            doc_id="tb-doc", name="Ledger.pdf", doc_type=DocType.file,
            file_type=FileType.pdf,
        )
        db.save(doc)
        db.save(_make_document(
            doc_id="tb-page-1", name="Page 1", doc_type=DocType.page,
            page_content="live text", parent_id=doc.id, sequence=1,
        ))
        db.save(Artifact(
            id="tb-art", document_id="tb-page-1", artifact_type="table",
            content='"date","amount"\n"Jan 1, 1933","78.13"\n',
        ))
        response = client.get(f"/view/document/{doc.id}?representation=table")
        assert response.status_code == 200
        assert '"headers": ["date", "amount"]' in response.text
        assert '"Jan 1, 1933"' in response.text
        # A prose representation never grows a table key.
        plain = client.get(f"/view/document/{doc.id}?representation=transcription")
        assert '"table"' not in plain.text

    def test_template_renders_a_real_table_with_scroll_wrap(self):
        template = (
            Path(__file__).resolve().parents[3]
            / "src" / "fichero_server" / "api" / "templates" / "document_view.html"
        ).read_text()
        assert "function tableMarkup(table)" in template
        assert '<div class="table-scroll">' in template
        assert "overflow-x: auto" in template
        # Every cell goes through escapeHtml — table data is model output.
        assert "`<td>${escapeHtml(cell)}</td>`" in template
        assert "`<th>${escapeHtml(cell)}</th>`" in template


class TestArtifactView:
    """?artifact_id renders exactly ONE artifact (Daniel, 2026-08-30: the
    reader needs an artifact view — "the extract csv, rendered. or a
    translation"). Pure-function coverage for artifact_pages."""

    def _pages(self):
        return [
            {"id": "p1", "number": 1, "label": "Page 1", "content": "live1", "has_content": True},
            {"id": "p2", "number": 2, "label": "Page 2", "content": "live2", "has_content": True},
        ]

    def test_owner_page_carries_the_artifact_others_go_quiet(self):
        from fichero_server.api.routes.system.views import artifact_pages
        from fichero_server.models import Artifact

        artifact = Artifact(document_id="p2", artifact_type="translation", content="hola")
        result = artifact_pages(self._pages(), artifact)
        assert [p["content"] for p in result] == ["", "hola"]
        assert [p["has_content"] for p in result] == [False, True]
        # The sequence still matches the preview (#4356) — no page dropped.
        assert [p["id"] for p in result] == ["p1", "p2"]

    def test_table_artifact_parses_on_its_page(self):
        from fichero_server.api.routes.system.views import artifact_pages
        from fichero_server.models import Artifact

        artifact = Artifact(
            document_id="p1", artifact_type="table",
            content='"a","b"\n"1","2"\n',
        )
        result = artifact_pages(self._pages(), artifact)
        assert result[0]["table"]["headers"] == ["a", "b"]
        assert result[0]["table"]["rows"] == [["1", "2"]]
        assert "table" not in result[1]

    def test_parent_anchored_artifact_becomes_one_section(self):
        from fichero_server.api.routes.system.views import artifact_pages
        from fichero_server.models import Artifact

        # A document-level CSV names no listed page — one section, not a
        # silent all-empty page walk.
        artifact = Artifact(
            document_id="parent-doc", artifact_type="table",
            content='"x"\n"1"\n', step_name="Extract Accounts",
        )
        result = artifact_pages(self._pages(), artifact)
        assert len(result) == 1
        assert result[0]["id"] == "parent-doc"
        assert result[0]["name"] == "Extract Accounts"
        assert result[0]["has_content"] is True
        assert result[0]["table"]["headers"] == ["x"]

    def test_route_404s_on_unknown_artifact(self, client, db):
        from fichero_server.models import DocType
        doc = _make_document(doc_id="av-doc", name="A.pdf", doc_type=DocType.file)
        db.save(doc)
        response = client.get(f"/view/document/{doc.id}", params={"artifact_id": "nope"})
        assert response.status_code == 404

    def test_route_renders_the_named_artifact(self, client, db):
        from fichero_server.models import Artifact, DocType
        doc = _make_document(doc_id="av-doc2", name="B.pdf", doc_type=DocType.file)
        db.save(doc)
        db.save(_make_document(
            doc_id="av-page-1", name="Page 1", doc_type=DocType.page,
            page_content="Live content", parent_id=doc.id, sequence=1,
        ))
        db.save(Artifact(
            id="av-art-1", document_id="av-page-1",
            artifact_type="translation", content="AV translated text",
        ))
        response = client.get(f"/view/document/{doc.id}", params={"artifact_id": "av-art-1"})
        assert response.status_code == 200
        assert "AV translated text" in response.text
        assert "Live content" not in response.text
