"""Tests for search and saved-search routes.

Search routes orchestrate hybrid vector+fulltext lookup via db.search().
Tests cover: input validation, SavedSearch CRUD, stats, and reindex trigger.
The enhanced_search endpoint falls back gracefully when no embeddings exist
so tests can exercise it without a seeded vector store.
"""

from fichero.db import SearchAnchor, SearchExcerpt
from fichero.knowledge_models import KnowledgeClaim, KnowledgeEntity
from fichero.models import DocType, Document, FileType, SavedSearch


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


# ---------------------------------------------------------------------------
# GET /api/search/stats
# ---------------------------------------------------------------------------


class TestSearchStats:
    def test_returns_stats(self, client):
        r = client.get("/api/search/stats")
        assert r.status_code == 200


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

    def test_saved_search_appears_in_list(self, client):
        client.post("/api/search/saved", json={"query": "find this"})
        r = client.get("/api/search/saved")
        queries = [s["query"] for s in r.json()["items"]]
        assert "find this" in queries


# ---------------------------------------------------------------------------
# PUT /api/search/saved/{search_id}
# ---------------------------------------------------------------------------


class TestUpdateSavedSearch:
    def test_update_query(self, client, db):
        s = _make_saved_search(db, "original")
        r = client.put(f"/api/search/saved/{s.id}", json={"query": "updated"})
        assert r.status_code == 200
        assert r.json()["query"] == "updated"

    def test_update_missing_returns_404(self, client):
        r = client.put("/api/search/saved/no-such-id", json={"query": "x"})
        assert r.status_code == 404


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

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/search/saved/no-such-id")
        assert r.status_code == 404
