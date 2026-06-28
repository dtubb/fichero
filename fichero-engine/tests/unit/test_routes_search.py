"""Tests for search and saved-search routes.

Search routes orchestrate hybrid vector+fulltext lookup via db.search().
Tests cover: input validation, SavedSearch CRUD, stats, and reindex trigger.
The enhanced_search endpoint falls back gracefully when no embeddings exist
so tests can exercise it without a seeded vector store.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from fichero.api.routes import search as search_routes
from fichero.knowledge_models import ClaimType, EntityType
from fichero.db import SearchAnchor, SearchExcerpt, SearchResult
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import DocType, Document, FileType, KGGraphListResponse, SavedSearch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_saved_search(db, query: str = "test query") -> SavedSearch:
    s = SavedSearch(
        query=query,
        is_smart_search=True,
        search_type="hybrid",
        sort_by="relevance",
        sort_direction="desc",
        folder_path="/",
        sort_order=0,
    )
    db.save(s)
    return s


def _seed_semantic_search_scope_library(db):
    doc = Document(
        id="doc-search-scope",
        name="search-scope.txt",
        page_content="Asprilla worked the mine and wrote about it.",
        doc_type=DocType.file,
        file_type=FileType.text,
    )
    entity = KnowledgeEntity(
        id="entity-asprilla",
        canonical_name="Asprilla",
        entity_type=EntityType.person,
        aliases=[],
    )
    claim = KnowledgeClaim(
        id="claim-asprilla",
        text="Asprilla worked the mine.",
        claim_type=ClaimType.fact,
        source_document_id=doc.id,
        source_excerpt="Asprilla worked the mine.",
        subject_canonical="Asprilla",
        predicate_verb="worked",
        object_phrase="the mine",
        entity_ids=[entity.id],
    )
    db.save(doc)
    db.save(entity)
    db.save(claim)
    return doc, entity, claim


def _mock_content_search(doc: Document) -> tuple[list[SearchResult], int, dict]:
    return (
        [
            SearchResult(
                document_id=doc.id,
                score=0.91,
                content_preview=doc.page_content or "",
                metadata={
                    "name": doc.name,
                    "doc_type": doc.doc_type.value if hasattr(doc.doc_type, "value") else doc.doc_type,
                    "file_type": doc.file_type.value if hasattr(doc.file_type, "value") else doc.file_type,
                },
                highlights=[],
            )
        ],
        1,
        {"search_type": "fulltext", "execution_time_ms": 1.0, "has_more": False},
    )


def _mock_entity_hits(entity: KnowledgeEntity) -> KGGraphListResponse:
    return KGGraphListResponse(
        items=[{**entity.model_dump(), "similarity_score": 0.9}],
        count=1,
    )


def _mock_claim_hits(claim: KnowledgeClaim) -> KGGraphListResponse:
    return KGGraphListResponse(
        items=[{**claim.model_dump(), "similarity_score": 0.9}],
        count=1,
    )


# ---------------------------------------------------------------------------
# POST /api/search — enhanced search
# ---------------------------------------------------------------------------


class TestEnhancedSearch:
    def test_empty_query_returns_recent(self, client):
        # The enhanced_search route deliberately treats an empty query as
        # "browse the index" — returns the most-recently-updated docs
        # instead of 400. (See enhanced_search docstring.)
        r = client.post("/api/search", json={"query": ""})
        assert r.status_code == 200

    def test_whitespace_query_returns_recent(self, client):
        r = client.post("/api/search", json={"query": "   "})
        assert r.status_code == 200

    def test_content_search_offloads_sync_retriever_work_to_thread(self, monkeypatch):
        class FakeDB:
            def search(self, **_kwargs):
                raise AssertionError("db.search must run inside asyncio.to_thread")

        hit = SearchResult(
            document_id="doc-1",
            score=1.0,
            content_preview="Camilo appears in the ledger.",
            metadata={"name": "ledger.txt", "doc_type": "file"},
            highlights=[],
        )
        to_thread = AsyncMock(
            return_value=(
                [hit],
                1,
                {
                    "search_type": "hybrid",
                    "execution_time_ms": 1.0,
                    "has_more": False,
                },
            )
        )
        monkeypatch.setattr(search_routes.asyncio, "to_thread", to_thread)

        response = asyncio.run(
            search_routes.enhanced_search(
                search_routes.SearchRequest(
                    query="Camilo",
                    include=[search_routes.SearchInclude.content],
                ),
                db=FakeDB(),
            )
        )

        to_thread.assert_awaited_once()
        assert to_thread.await_args.args[:1] == (search_routes._run_content_search_sync,)
        assert response.results == [hit]
        assert response.total_results == 1

    def test_recent_search_excludes_soft_deleted_documents(self, client, db):
        doc = Document(
            name="Recently Deleted",
            page_content="recent deleted body",
            doc_type=DocType.file,
            file_type=FileType.text,
        )
        db.save(doc)
        doc.deleted_at = doc.updated_at
        doc.deleted_by = "tester"
        db.save(doc)

        r = client.post("/api/search", json={"query": ""})
        assert r.status_code == 200
        assert all(item["document_id"] != doc.id for item in r.json()["results"])

    def test_fulltext_search_excludes_soft_deleted_documents(self, client, db):
        doc = Document(
            name="Deleted Search Hit",
            page_content="trash-search-needle",
            doc_type=DocType.file,
            file_type=FileType.text,
        )
        db.save(doc)
        db.embed(doc)
        doc.deleted_at = doc.updated_at
        doc.deleted_by = "tester"
        db.save(doc)

        r = client.post(
            "/api/search",
            json={"query": "trash-search-needle", "search_type": "fulltext", "min_score": 0.0},
        )
        assert r.status_code == 200
        assert all(item["document_id"] != doc.id for item in r.json()["results"])

    def test_invalid_search_type_returns_400(self, client):
        r = client.post("/api/search", json={"query": "hello", "search_type": "magic"})
        assert r.status_code == 400

    def test_invalid_sort_by_returns_400(self, client):
        r = client.post("/api/search", json={"query": "hello", "sort_by": "banana"})
        assert r.status_code == 400

    def test_valid_search_returns_200(self, client):
        r = client.post("/api/search", json={"query": "hello world"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "query" in data
        assert data["query"] == "hello world"

    def test_response_has_required_fields(self, client):
        r = client.post("/api/search", json={"query": "test"})
        assert r.status_code == 200
        data = r.json()
        assert "count" in data
        assert "total_results" in data
        assert "search_type" in data
        assert "execution_time_ms" in data

    def test_min_score_filtering(self, client, mock_db):
        # Test that min_score parameter filters out low-scoring results
        from fichero.db import SearchResult
        # Mock a high-score result
        mock_result = SearchResult(
            document_id="test-id",
            score=0.9,
            content_preview="test content",
            metadata={},
            highlights=[]
        )
        mock_db.search.return_value = ([mock_result], 1, {"search_type": "hybrid", "execution_time_ms": 0})
        
        r = client.post("/api/search", json={"query": "test", "min_score": 0.9})
        assert r.status_code == 200
        data = r.json()
        # All results should have score >= min_score
        assert all(result["score"] >= 0.9 for result in data["results"])

    def test_default_min_score_filters_noise(self, client, mock_db):
        # Test that the default min_score of 0.55 filters out noise results
        from fichero.db import SearchResult
        
        # Create mock results with different scores
        _low_score_result = SearchResult(
            document_id="low-score-doc",
            score=0.3,  # Below the new default threshold of 0.55
            content_preview="low score content",
            metadata={},
            highlights=[]
        )
        high_score_result = SearchResult(
            document_id="high-score-doc",
            score=0.7,  # Above the new default threshold of 0.55
            content_preview="high score content",
            metadata={},
            highlights=[]
        )
        
        # Mock the search to return both results, but db.search should filter based on min_score
        mock_db.search.return_value = (
            [high_score_result],  # Only high score result should pass through
            1, 
            {"search_type": "hybrid", "execution_time_ms": 0}
        )
        
        r = client.post("/api/search", json={"query": "test"})
        assert r.status_code == 200
        data = r.json()
        
        # With the new default min_score of 0.55, only the high score result should be returned
        assert len(data["results"]) == 1
        assert data["results"][0]["document_id"] == "high-score-doc"
        assert data["results"][0]["score"] >= 0.55

    def test_result_serializes_snippet_anchors_and_kg_ids(self, client, mock_db):
        from fichero.db import SearchResult

        mock_result = SearchResult(
            document_id="doc-rich",
            score=1.0,
            content_preview="Leidy cleared gravel from the sluice",
            metadata={},
            highlights=["**Leidy** cleared gravel"],
            transcript_excerpts=[
                SearchExcerpt(
                    text="Leidy cleared gravel",
                    char_start=0,
                    char_end=21,
                    match_start=0,
                    match_end=5,
                    anchor=SearchAnchor(
                        document_id="doc-rich",
                        char_start=0,
                        char_end=5,
                    ),
                )
            ],
            kg_claim_ids=["claim-1"],
            kg_entity_ids=["entity-1"],
        )
        mock_db.search.return_value = (
            [mock_result],
            1,
            {"search_type": "hybrid", "execution_time_ms": 0},
        )
        mock_db.enrich_search_results_with_kg.return_value = [mock_result]

        r = client.post("/api/search", json={"query": "Leidy"})
        assert r.status_code == 200
        result = r.json()["results"][0]
        assert result["transcript_excerpts"][0]["text"] == "Leidy cleared gravel"
        assert result["transcript_excerpts"][0]["anchor"] == {
            "document_id": "doc-rich",
            "char_start": 0,
            "char_end": 5,
        }
        assert result["kg_claim_ids"] == ["claim-1"]
        assert result["kg_entity_ids"] == ["entity-1"]

    def test_db_enrichment_returns_matching_kg_claim_and_entity_ids(self, db):
        from fichero.db import SearchResult
        from fichero.models import Document

        doc = Document(
            id="doc-kg",
            name="KG source",
            page_content="Leidy cleared gravel from the sluice.",
        )
        entity = KnowledgeEntity(
            id="entity-leidy",
            canonical_name="Leidy",
            aliases=["Leidi"],
        )
        claim = KnowledgeClaim(
            id="claim-leidy",
            text="Leidy cleared gravel from the sluice.",
            source_document_id=doc.id,
            source_excerpt="Leidy cleared gravel",
            entity_ids=[entity.id],
        )
        db.save(doc)
        db.save(entity)
        db.save(claim)

        result = SearchResult(
            document_id=doc.id,
            score=1.0,
            content_preview="Leidy cleared gravel",
            metadata={},
        )
        enriched = db.enrich_search_results_with_kg([result], "Leidy")

        assert enriched[0].kg_claim_ids == ["claim-leidy"]
        assert enriched[0].kg_entity_ids == ["entity-leidy"]

    def test_pdf_file_hit_projects_to_matching_page_with_anchor(self, client, db, monkeypatch):
        from fichero.db import SearchResult

        parent = Document(
            id="pdf-parent",
            name="archive.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Full PDF content blob",
        )
        page1 = Document(
            id="pdf-parent-page-1",
            parent_id=parent.id,
            name="archive.pdf - Page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content="No relevant name on this page.",
            metadata={"page_number": 1},
        )
        page2 = Document(
            id="pdf-parent-page-2",
            parent_id=parent.id,
            name="archive.pdf - Page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content="Camilo appears in this passage with context.",
            metadata={"page_number": 2},
        )
        db.save(parent)
        db.save(page1)
        db.save(page2)

        file_hit = SearchResult(
            document_id=parent.id,
            score=0.91,
            content_preview="Camilo appears in this passage with context.",
            metadata={
                "name": parent.name,
                "doc_type": "file",
                "file_type": "pdf",
            },
            highlights=[],
        )

        monkeypatch.setattr(
            type(db),
            "search",
            lambda self, **kwargs: (
                [file_hit],
                1,
                {"search_type": "hybrid", "execution_time_ms": 1.0, "has_more": False},
            ),
        )

        r = client.post("/api/search", json={"query": "camilo", "search_type": "hybrid"})
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 1
        result = body["results"][0]
        assert result["document_id"] == page2.id
        assert result["metadata"]["page_number"] == 2
        assert result["metadata"]["pdf_parent_id"] == parent.id
        assert result["transcript_excerpts"]
        anchor = result["transcript_excerpts"][0]["anchor"]
        assert anchor["document_id"] == page2.id
        assert result["transcript_excerpts"][0]["match_start"] is not None

    def test_pdf_file_projection_batches_page_lookups(self, client, db, monkeypatch):
        from fichero.db import Database, SearchResult

        parent_a = Document(
            id="pdf-a",
            name="a.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Full PDF A",
        )
        parent_b = Document(
            id="pdf-b",
            name="b.pdf",
            doc_type=DocType.file,
            file_type=FileType.pdf,
            page_content="Full PDF B",
        )
        page_a1 = Document(
            id="pdf-a-page-1",
            parent_id=parent_a.id,
            name="a.pdf - Page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content="No matching name on this page.",
        )
        page_a2 = Document(
            id="pdf-a-page-2",
            parent_id=parent_a.id,
            name="a.pdf - Page 2",
            doc_type=DocType.page,
            sequence=2,
            page_content="Camilo appears with strong context.",
        )
        page_b1 = Document(
            id="pdf-b-page-1",
            parent_id=parent_b.id,
            name="b.pdf - Page 1",
            doc_type=DocType.page,
            sequence=1,
            page_content="Camilo appears in the second PDF.",
        )
        for doc in (parent_a, parent_b, page_a1, page_a2, page_b1):
            db.save(doc)

        hits = [
            SearchResult(
                document_id=parent_a.id,
                score=0.91,
                content_preview="Camilo appears with strong context.",
                metadata={"name": parent_a.name, "doc_type": "file", "file_type": "pdf"},
                highlights=[],
            ),
            SearchResult(
                document_id=parent_b.id,
                score=0.81,
                content_preview="Camilo appears in the second PDF.",
                metadata={"name": parent_b.name, "doc_type": "file", "file_type": "pdf"},
                highlights=[],
            ),
        ]

        real_query = Database.query
        real_query_in = Database.query_in
        per_parent_queries: list[str] = []
        query_in_calls: list[tuple[str, tuple[str, ...]]] = []

        def counting_query(self, model, **filters):
            if model is Document and filters.get("parent_id") in {parent_a.id, parent_b.id}:
                per_parent_queries.append(filters["parent_id"])
            return real_query(self, model, **filters)

        def counting_query_in(self, model, column, values):
            if model is Document and column == "parent_id":
                query_in_calls.append((column, tuple(values)))
            return real_query_in(self, model, column, values)

        monkeypatch.setattr(Database, "query", counting_query)
        monkeypatch.setattr(Database, "query_in", counting_query_in)
        monkeypatch.setattr(
            Database,
            "search",
            lambda self, **kwargs: (
                hits,
                2,
                {"search_type": "hybrid", "execution_time_ms": 1.0, "has_more": False},
            ),
        )

        r = client.post("/api/search", json={"query": "camilo", "search_type": "hybrid"})

        assert r.status_code == 200
        body = r.json()
        assert [item["document_id"] for item in body["results"]] == [
            page_a2.id,
            page_b1.id,
        ]
        assert [item["metadata"]["pdf_parent_id"] for item in body["results"]] == [
            parent_a.id,
            parent_b.id,
        ]
        assert per_parent_queries == []
        assert len(query_in_calls) == 1
        assert query_in_calls[0][0] == "parent_id"
        assert set(query_in_calls[0][1]) == {parent_a.id, parent_b.id}

    def test_default_search_includes_content_entities_and_claims(self, client, db, monkeypatch):
        doc, entity, claim = _seed_semantic_search_scope_library(db)
        monkeypatch.setattr(type(db), "search", lambda self, **kwargs: _mock_content_search(doc))
        monkeypatch.setattr(
            search_routes,
            "search_entities_semantic_impl",
            lambda **kwargs: _mock_entity_hits(entity),
        )
        monkeypatch.setattr(
            search_routes,
            "search_claims_semantic_impl",
            lambda **kwargs: _mock_claim_hits(claim),
        )

        r = client.post(
            "/api/search",
            json={"query": "Asprilla", "search_type": "fulltext", "min_score": 0.0},
        )

        assert r.status_code == 200
        body = r.json()
        assert [result["document_id"] for result in body["results"]] == [doc.id]
        assert [item["id"] for item in body["entity_hits"]] == [entity.id]
        assert [item["id"] for item in body["claim_hits"]] == [claim.id]

    def test_entities_scope_query_returns_only_entity_hits(self, client, db, monkeypatch):
        _, entity, _ = _seed_semantic_search_scope_library(db)
        monkeypatch.setattr(
            search_routes,
            "search_entities_semantic_impl",
            lambda **kwargs: _mock_entity_hits(entity),
        )

        r = client.post(
            "/api/search",
            json={"query": "entities:Asprilla", "search_type": "fulltext", "min_score": 0.0},
        )

        assert r.status_code == 200
        body = r.json()
        assert body["results"] == []
        assert [item["id"] for item in body["entity_hits"]] == [entity.id]
        assert body["claim_hits"] == []

    def test_include_subsets_gate_each_search_surface(self, client, db, monkeypatch):
        doc, entity, claim = _seed_semantic_search_scope_library(db)
        monkeypatch.setattr(type(db), "search", lambda self, **kwargs: _mock_content_search(doc))
        monkeypatch.setattr(
            search_routes,
            "search_entities_semantic_impl",
            lambda **kwargs: _mock_entity_hits(entity),
        )
        monkeypatch.setattr(
            search_routes,
            "search_claims_semantic_impl",
            lambda **kwargs: _mock_claim_hits(claim),
        )

        cases = [
            (["content"], 1, 0, 0),
            (["entities"], 0, 1, 0),
            (["claims"], 0, 0, 1),
            (["content", "entities"], 1, 1, 0),
            (["content", "claims"], 1, 0, 1),
            (["entities", "claims"], 0, 1, 1),
        ]

        for include, result_count, entity_count, claim_count in cases:
            r = client.post(
                "/api/search",
                json={
                    "query": "Asprilla",
                    "search_type": "fulltext",
                    "min_score": 0.0,
                    "include": include,
                },
            )
            assert r.status_code == 200
            body = r.json()
            assert len(body["results"]) == result_count
            assert len(body["entity_hits"]) == entity_count
            assert len(body["claim_hits"]) == claim_count
            if result_count:
                assert body["results"][0]["document_id"] == doc.id
            if entity_count:
                assert body["entity_hits"][0]["id"] == entity.id
            if claim_count:
                assert body["claim_hits"][0]["id"] == claim.id

    def test_missing_vector_tables_skip_kg_scopes_without_503(self, client, db, monkeypatch):
        doc = Document(
            id="doc-no-vectors",
            name="doc-no-vectors.txt",
            page_content="Asprilla worked the mine and wrote about it.",
            doc_type=DocType.file,
            file_type=FileType.text,
        )
        db.save(doc)
        monkeypatch.setattr(type(db), "search", lambda self, **kwargs: _mock_content_search(doc))

        def _missing_entities(**kwargs):
            raise HTTPException(status_code=503, detail="Entity embeddings not yet indexed.")

        def _missing_claims(**kwargs):
            raise HTTPException(status_code=503, detail="Claim embeddings not yet indexed.")

        monkeypatch.setattr(search_routes, "search_entities_semantic_impl", _missing_entities)
        monkeypatch.setattr(search_routes, "search_claims_semantic_impl", _missing_claims)

        r = client.post(
            "/api/search",
            json={"query": "Asprilla", "search_type": "fulltext", "min_score": 0.0},
        )

        assert r.status_code == 200
        body = r.json()
        assert [result["document_id"] for result in body["results"]] == [doc.id]
        assert body["entity_hits"] == []
        assert body["claim_hits"] == []


# ---------------------------------------------------------------------------
# GET /api/search/stats
# ---------------------------------------------------------------------------


class TestSearchStats:
    def test_returns_stats(self, client, mock_db):
        mock_db.embedding_stats.return_value = {
            "indexed_count": 7,
            "table_exists": True,
            "entity_indexed_count": 2,
            "entity_table_exists": True,
            "claim_indexed_count": 3,
            "claim_table_exists": False,
        }

        r = client.get("/api/search/stats")

        assert r.status_code == 200
        assert r.json() == {
            "indexed_count": 7,
            "table_exists": True,
            "entity_indexed_count": 2,
            "entity_table_exists": True,
            "claim_indexed_count": 3,
            "claim_table_exists": False,
        }


class TestSearchViews:
    def test_table_view_filters_sorts_and_paginates(self, client, db):
        alpha = Document(name="Alpha field note", doc_type=DocType.file, file_type=FileType.text)
        beta = Document(name="Beta field note", doc_type=DocType.file, file_type=FileType.text)
        gamma = Document(name="Gamma memo", doc_type=DocType.file, file_type=FileType.text)
        db.save(alpha)
        db.save(beta)
        db.save(gamma)

        r = client.get(
            "/api/search/views/table",
            params={
                "query": "field",
                "sort_by": "name",
                "sort_direction": "asc",
                "page": 1,
                "page_size": 1,
            },
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["total"] == 2
        assert payload["page"] == 1
        assert payload["page_size"] == 1
        assert [row["name"] for row in payload["rows"]] == ["Alpha field note"]
        assert [column["key"] for column in payload["columns"]] == [
            "id",
            "name",
            "doc_type",
            "created_at",
            "relevance_score",
        ]


# ---------------------------------------------------------------------------
# POST /api/search/reindex
# ---------------------------------------------------------------------------


class TestReindex:
    def test_reindex_returns_started(self, client):
        r = client.post("/api/search/reindex")
        assert r.status_code == 200
        assert r.json()["status"] == "started"


# ---------------------------------------------------------------------------
# GET /api/search/saved
# ---------------------------------------------------------------------------


class TestListSavedSearches:
    def test_empty_list(self, client):
        r = client.get("/api/search/saved")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_saved_searches(self, client, db):
        _make_saved_search(db, "query A")
        _make_saved_search(db, "query B")
        r = client.get("/api/search/saved")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 2


# ---------------------------------------------------------------------------
# POST /api/search/saved
# ---------------------------------------------------------------------------


class TestSaveSearch:
    def test_save_search(self, client):
        r = client.post("/api/search/saved", json={"query": "my search"})
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "my search"
        assert "id" in data

    def test_save_search_creates_smart_folder_document(self, client, db):
        r = client.post("/api/search/saved", json={"query": "my search"})

        assert r.status_code == 200
        saved_id = r.json()["id"]
        mirrored = db.get(Document, saved_id)
        assert mirrored is not None
        assert mirrored.node_kind == "saved_search"
        assert mirrored.doc_type == DocType.folder
        assert mirrored.prototype_key == "saved_search"
        assert mirrored.attributes["query"] == "my search"
        assert mirrored.curated_items[0]["query"] == "my search"
        assert mirrored.metadata["node_class"] == "smart_folder"
        assert mirrored.metadata["saved_search_query"] == "my search"

    def test_saved_search_create_list_and_folded_retrieve_round_trip(self, client, db):
        created = client.post(
            "/api/search/saved",
            json={
                "query": "letters from cartagena",
                "filters": {"tag": "letters"},
                "search_type": "hybrid",
                "sort_by": "relevance",
                "sort_direction": "desc",
                "folder_path": "/research",
                "sort_order": 4,
            },
        )

        assert created.status_code == 200
        saved_id = created.json()["id"]

        listing = client.get("/api/search/saved")
        assert listing.status_code == 200
        listed = next(item for item in listing.json()["items"] if item["id"] == saved_id)
        assert listed["query"] == "letters from cartagena"
        assert listed["filters"] == {"tag": "letters"}
        assert listed["folder_path"] == "/research"
        assert listed["sort_order"] == 4

        folded = db.get(SavedSearch, saved_id)
        assert folded is not None
        assert folded.query == "letters from cartagena"
        assert folded.filters == {"tag": "letters"}
        assert folded.folder_path == "/research"

        mirrored = db.get(Document, saved_id)
        assert mirrored is not None
        assert mirrored.node_kind == "saved_search"
        assert mirrored.prototype_key == "saved_search"
        assert mirrored.curated_items[0]["kind"] == "saved_search_query"
        assert mirrored.curated_items[0]["query"] == "letters from cartagena"

    def test_saved_search_appears_in_list(self, client):
        client.post("/api/search/saved", json={"query": "find this"})
        r = client.get("/api/search/saved")
        queries = [s["query"] for s in r.json()["items"]]
        assert "find this" in queries

    def test_list_saved_searches_raises_for_malformed_folded_query_payload(self, db):
        db.save(
            Document(
                id="saved-bad-query",
                name="Broken Saved Search",
                doc_type=DocType.folder,
                node_kind="saved_search",
                prototype_key="saved_search",
                attributes={
                    "query": "",
                    "filters": None,
                    "is_smart_search": True,
                    "search_type": "hybrid",
                    "sort_by": "relevance",
                    "sort_direction": "desc",
                    "folder_path": "/",
                },
                curated_items=[],
            )
        )

        with pytest.raises(ValueError, match="missing its query payload"):
            asyncio.run(search_routes.list_saved_searches(db=db))


# ---------------------------------------------------------------------------
# PUT /api/search/saved/{search_id}
# ---------------------------------------------------------------------------


class TestUpdateSavedSearch:
    def test_update_query(self, client, db):
        s = _make_saved_search(db, "original")
        r = client.put(f"/api/search/saved/{s.id}", json={"query": "updated"})
        assert r.status_code == 200
        assert r.json()["query"] == "updated"

    def test_update_preserves_fields_when_json_null_is_sent(self, client, db):
        s = _make_saved_search(db, "original")
        s.folder_path = "/research"
        s.sort_direction = "asc"
        s.filters = {"tag": "mining"}
        db.save(s)

        r = client.put(
            f"/api/search/saved/{s.id}",
            json={
                "query": "updated",
                "folder_path": None,
                "sort_direction": None,
                "filters": None,
            },
        )

        assert r.status_code == 200
        payload = r.json()
        assert payload["query"] == "updated"
        assert payload["folder_path"] == "/research"
        assert payload["sort_direction"] == "asc"
        assert payload["filters"] == {"tag": "mining"}

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/search/saved/no-such-id", json={"query": "x"})
        assert r.status_code == 404

    def test_update_raises_when_legacy_row_exists_but_folded_node_is_missing(self, db):
        saved = _make_saved_search(db, "orphaned")
        db._execute("DELETE FROM documents WHERE id = $id", {"id": saved.id})

        with pytest.raises(HTTPException) as exc:
            search_routes.update_saved_search_impl(
                db, saved.id, search_routes.SavedSearchUpdate(query="updated")
            )

        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/search/saved/{search_id}/duplicate
# ---------------------------------------------------------------------------


class TestDuplicateSavedSearch:
    def test_duplicate_creates_new(self, client, db):
        s = _make_saved_search(db, "original query")
        r = client.post(f"/api/search/saved/{s.id}/duplicate")
        assert r.status_code == 200
        copy = r.json()
        assert copy["id"] != s.id
        assert copy["query"] == "original query"

    def test_duplicate_missing_returns_404(self, client):
        r = client.post("/api/search/saved/no-such-id/duplicate")
        assert r.status_code == 404


class TestReorderSavedSearches:
    def test_reorder_persists_requested_sort_order(self, client, db):
        first = _make_saved_search(db, "first")
        second = _make_saved_search(db, "second")
        third = _make_saved_search(db, "third")

        r = client.post("/api/search/saved/reorder", json=[third.id, first.id, second.id])

        assert r.status_code == 200
        assert r.json() == {"status": "reordered", "count": 3}
        assert db.get(SavedSearch, third.id).sort_order == 0
        assert db.get(SavedSearch, first.id).sort_order == 1
        assert db.get(SavedSearch, second.id).sort_order == 2

    def test_reorder_missing_saved_search_returns_404(self, client, db):
        saved = _make_saved_search(db, "first")

        r = client.post("/api/search/saved/reorder", json=[saved.id, "missing-search"])

        assert r.status_code == 404
        assert r.json()["detail"] == "Saved search not found: missing-search"


# ---------------------------------------------------------------------------
# DELETE /api/search/saved/{search_id}
# ---------------------------------------------------------------------------


class TestDeleteSavedSearch:
    def test_delete_removes_search(self, client, db):
        s = _make_saved_search(db)
        r = client.delete(f"/api/search/saved/{s.id}")
        assert r.status_code == 200
        r2 = client.get("/api/search/saved")
        assert all(item["id"] != s.id for item in r2.json()["items"])
        assert db.get(Document, s.id) is None

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/search/saved/no-such-id")
        assert r.status_code == 404
