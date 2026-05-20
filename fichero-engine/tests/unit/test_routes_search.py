"""Tests for search and saved-search routes.

Search routes orchestrate hybrid vector+fulltext lookup via db.search().
Tests cover: input validation, SavedSearch CRUD, stats, and reindex trigger.
The enhanced_search endpoint falls back gracefully when no embeddings exist
so tests can exercise it without a seeded vector store.
"""

import pytest
from fichero.models import SavedSearch


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
