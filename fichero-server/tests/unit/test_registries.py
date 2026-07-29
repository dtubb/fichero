"""Unit tests for user-extensible epistemic status and claim kind registries (#1102).

Covers:
- GET /api/registries/epistemic-statuses returns built-in defaults after seed
- POST creates a custom epistemic status, GET returns it
- POST duplicate key -> 409
- DELETE built-in -> 409
- DELETE custom with no claims -> 204
- Same CRUD coverage for /api/registries/claim-kinds
"""

from __future__ import annotations



# ---------------------------------------------------------------------------
# Epistemic-status endpoints
# ---------------------------------------------------------------------------


class TestEpistemicStatusList:
    def test_get_returns_builtin_defaults_after_seed(self, client):
        """GET /api/registries/epistemic-statuses seeds + returns built-ins."""
        r = client.get("/api/registries/epistemic-statuses")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["count"] >= 3  # tentative, confirmed, rejected
        keys = {item["key"] for item in data["items"]}
        assert {"tentative", "confirmed", "rejected"}.issubset(keys)

    def test_get_includes_custom_after_create(self, client):
        """Custom value appears in the GET list after POST."""
        client.post(
            "/api/registries/epistemic-statuses",
            json={"key": "rumoured", "label": "Rumoured"},
        )
        r = client.get("/api/registries/epistemic-statuses")
        assert r.status_code == 200
        keys = {item["key"] for item in r.json()["items"]}
        assert "rumoured" in keys

    def test_get_is_idempotent_on_reseed(self, client):
        """Calling GET twice does not duplicate built-in rows."""
        r1 = client.get("/api/registries/epistemic-statuses")
        r2 = client.get("/api/registries/epistemic-statuses")
        assert r1.json()["count"] == r2.json()["count"]


class TestEpistemicStatusCreate:
    def test_post_creates_custom_status(self, client):
        """POST /api/registries/epistemic-statuses creates a custom entry."""
        r = client.post(
            "/api/registries/epistemic-statuses",
            json={"key": "court-testimony", "label": "Court Testimony"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["key"] == "court-testimony"
        assert body["label"] == "Court Testimony"
        assert body["is_builtin"] is False

    def test_post_with_optional_fields(self, client):
        """POST accepts icon, color, description, parent_key."""
        r = client.post(
            "/api/registries/epistemic-statuses",
            json={
                "key": "corroborated",
                "label": "Corroborated",
                "description": "Two independent sources confirm",
                "icon": "checkmark.seal",
                "color": "#00FF00",
                "parent_key": "confirmed",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["description"] == "Two independent sources confirm"
        assert body["color"] == "#00FF00"

    def test_post_duplicate_key_returns_409(self, client):
        """POST with an already-existing key returns 409 Conflict."""
        payload = {"key": "speculative", "label": "Speculative"}
        r1 = client.post("/api/registries/epistemic-statuses", json=payload)
        assert r1.status_code == 201
        r2 = client.post("/api/registries/epistemic-statuses", json=payload)
        assert r2.status_code == 409

    def test_post_duplicate_builtin_key_returns_409(self, client):
        """POST with a key that collides with a built-in returns 409."""
        # Seed built-ins
        client.get("/api/registries/epistemic-statuses")
        r = client.post(
            "/api/registries/epistemic-statuses",
            json={"key": "tentative", "label": "Tentative (duplicate)"},
        )
        assert r.status_code == 409


class TestEpistemicStatusDelete:
    def test_delete_builtin_returns_409(self, client):
        """DELETE /api/registries/epistemic-statuses/{id} on a built-in returns 409."""
        # Seed and find a built-in
        r = client.get("/api/registries/epistemic-statuses")
        items = r.json()["items"]
        builtin = next(i for i in items if i["is_builtin"])
        dr = client.delete(f"/api/registries/epistemic-statuses/{builtin['id']}")
        assert dr.status_code == 409

    def test_delete_custom_with_no_claims_returns_204(self, client):
        """DELETE a custom epistemic status with no referencing claims returns 204."""
        cr = client.post(
            "/api/registries/epistemic-statuses",
            json={"key": "anecdotal", "label": "Anecdotal"},
        )
        assert cr.status_code == 201
        value_id = cr.json()["id"]
        dr = client.delete(f"/api/registries/epistemic-statuses/{value_id}")
        assert dr.status_code == 204
        # Verify it's gone
        lr = client.get("/api/registries/epistemic-statuses")
        keys = {item["key"] for item in lr.json()["items"]}
        assert "anecdotal" not in keys

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE on a nonexistent id returns 404."""
        dr = client.delete("/api/registries/epistemic-statuses/does-not-exist")
        assert dr.status_code == 404


# ---------------------------------------------------------------------------
# Claim-kind endpoints
# ---------------------------------------------------------------------------


class TestClaimKindList:
    def test_get_returns_builtin_defaults_after_seed(self, client):
        """GET /api/registries/claim-kinds seeds + returns built-ins."""
        r = client.get("/api/registries/claim-kinds")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] >= 6  # fact, analysis, interpretation, argument, historiography, theory
        keys = {item["key"] for item in data["items"]}
        assert {"fact", "analysis", "interpretation"}.issubset(keys)

    def test_get_includes_custom_after_create(self, client):
        """Custom claim kind appears in the GET list after POST."""
        client.post(
            "/api/registries/claim-kinds",
            json={"key": "oral-testimony", "label": "Oral Testimony"},
        )
        r = client.get("/api/registries/claim-kinds")
        assert r.status_code == 200
        keys = {item["key"] for item in r.json()["items"]}
        assert "oral-testimony" in keys

    def test_get_is_idempotent_on_reseed(self, client):
        """Calling GET twice does not duplicate built-in rows."""
        r1 = client.get("/api/registries/claim-kinds")
        r2 = client.get("/api/registries/claim-kinds")
        assert r1.json()["count"] == r2.json()["count"]


class TestClaimKindCreate:
    def test_post_creates_custom_kind(self, client):
        """POST /api/registries/claim-kinds creates a custom entry."""
        r = client.post(
            "/api/registries/claim-kinds",
            json={"key": "citation", "label": "Citation"},
        )
        assert r.status_code == 201
        body = r.json()
        assert body["key"] == "citation"
        assert body["is_builtin"] is False

    def test_post_with_optional_fields(self, client):
        """POST accepts icon, color, description, parent_key."""
        r = client.post(
            "/api/registries/claim-kinds",
            json={
                "key": "epigraph",
                "label": "Epigraph",
                "description": "Quoted passage as chapter header",
                "icon": "text.quote",
                "color": "#8888FF",
            },
        )
        assert r.status_code == 201
        assert r.json()["icon"] == "text.quote"

    def test_post_duplicate_key_returns_409(self, client):
        """POST with an already-existing key returns 409 Conflict."""
        payload = {"key": "legend", "label": "Legend"}
        r1 = client.post("/api/registries/claim-kinds", json=payload)
        assert r1.status_code == 201
        r2 = client.post("/api/registries/claim-kinds", json=payload)
        assert r2.status_code == 409

    def test_post_duplicate_builtin_key_returns_409(self, client):
        """POST with a key that collides with a built-in returns 409."""
        client.get("/api/registries/claim-kinds")
        r = client.post(
            "/api/registries/claim-kinds",
            json={"key": "fact", "label": "Fact (duplicate)"},
        )
        assert r.status_code == 409


class TestClaimKindDelete:
    def test_delete_builtin_returns_409(self, client):
        """DELETE /api/registries/claim-kinds/{id} on a built-in returns 409."""
        r = client.get("/api/registries/claim-kinds")
        items = r.json()["items"]
        builtin = next(i for i in items if i["is_builtin"])
        dr = client.delete(f"/api/registries/claim-kinds/{builtin['id']}")
        assert dr.status_code == 409

    def test_delete_custom_with_no_claims_returns_204(self, client):
        """DELETE a custom claim kind with no referencing claims returns 204."""
        cr = client.post(
            "/api/registries/claim-kinds",
            json={"key": "marginal-note", "label": "Marginal Note"},
        )
        assert cr.status_code == 201
        value_id = cr.json()["id"]
        dr = client.delete(f"/api/registries/claim-kinds/{value_id}")
        assert dr.status_code == 204
        # Verify it's gone
        lr = client.get("/api/registries/claim-kinds")
        keys = {item["key"] for item in lr.json()["items"]}
        assert "marginal-note" not in keys

    def test_delete_nonexistent_returns_404(self, client):
        """DELETE on a nonexistent id returns 404."""
        dr = client.delete("/api/registries/claim-kinds/does-not-exist")
        assert dr.status_code == 404
