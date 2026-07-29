"""Tests for search explanation routes.

Search explain provides transparency into RAG search operations — how results
were ranked, source attribution, and available RAG modes. Routes live at
/api/search/... (router prefix="/search" mounted at "/api").
"""
from fichero_server.models import Document

# ---------------------------------------------------------------------------
# GET /api/search/modes
# ---------------------------------------------------------------------------


class TestListRagModes:
    def test_returns_modes(self, client):
        r = client.get("/api/search/modes")
        assert r.status_code == 200
        data = r.json()
        assert "modes" in data
        assert "current_default" in data
        assert len(data["modes"]) == 3

    def test_modes_have_required_fields(self, client):
        r = client.get("/api/search/modes")
        assert r.status_code == 200
        for mode in r.json()["modes"]:
            assert "mode" in mode
            assert "name" in mode
            assert "min_score_threshold" in mode


# ---------------------------------------------------------------------------
# GET /api/search/metrics
# ---------------------------------------------------------------------------


class TestGetSearchMetrics:
    def test_returns_metrics(self, client):
        r = client.get("/api/search/metrics")
        assert r.status_code == 200
        data = r.json()
        assert "total_searches" in data
        assert "avg_execution_time_ms" in data
        assert "popular_queries" in data
        assert "timestamp" in data


# ---------------------------------------------------------------------------
# POST /api/search/explain
# ---------------------------------------------------------------------------


class TestExplainSearch:
    def test_explain_returns_structure(self, client):
        r = client.post("/api/search/explain", json={
            "query": "test query",
            "search_type": "hybrid",
            "rag_mode": "balanced",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["query"] == "test query"
        assert "explanation" in data
        assert "sources" in data
        assert "metrics" in data
        assert "suggested_refinements" in data

    def test_explain_fulltext_search(self, client):
        r = client.post("/api/search/explain", json={
            "query": "historical documents",
            "search_type": "fulltext",
            "rag_mode": "conservative",
        })
        assert r.status_code == 200
        assert r.json()["search_type"] == "fulltext"

    def test_explain_semantic_search(self, client):
        r = client.post("/api/search/explain", json={
            "query": "philosophy of science",
            "search_type": "semantic",
            "rag_mode": "speculative",
        })
        assert r.status_code == 200
        assert r.json()["rag_mode"] == "speculative"

    def test_explain_fulltext_includes_source_attribution(self, client, db):
        doc = Document(
            id="doc-camilo",
            name="Camilo ledger note",
            page_content="Camilo appears in this archival passage.",
        )
        db.save(doc)

        r = client.post("/api/search/explain", json={
            "query": "camilo",
            "search_type": "fulltext",
            "rag_mode": "balanced",
        })
        assert r.status_code == 200
        body = r.json()
        assert body["sources"], "Expected at least one attributed source"
        first = body["sources"][0]
        assert first["source_id"] == doc.id
        assert first["title"] == doc.name
        assert first["excerpt"]


# ---------------------------------------------------------------------------
# GET /api/search/explain/{query}
# ---------------------------------------------------------------------------


class TestExplainSearchPath:
    def test_explain_via_get(self, client):
        r = client.get("/api/search/explain/my+query")
        assert r.status_code == 200
        data = r.json()
        assert "explanation" in data
        assert "metrics" in data
