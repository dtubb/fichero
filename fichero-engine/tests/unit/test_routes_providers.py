"""Tests for LLM provider management routes.

Providers are the LiteLLM-backed LLM backends users configure (Anthropic,
OpenAI, Ollama, etc.). Routes handle: catalog discovery (read-only, no
external calls), provider CRUD (stored in app_db), and library provider refs.
Complex endpoints (api-key, model test) are excluded — they require live
external APIs.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from fichero.models import Provider, ProviderType
from fichero.api.routes.providers import get_app_database


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def use_test_app_db(app_db, monkeypatch):
    """Override the get_app_database FastAPI dependency with test app_db."""
    from fichero.api.main import app
    app.dependency_overrides[get_app_database] = lambda: app_db
    yield
    app.dependency_overrides.pop(get_app_database, None)


def _make_provider(app_db, name: str = "Test Provider", ptype: str = "anthropic") -> Provider:
    p = Provider(
        name=name,
        provider_type=ProviderType(ptype),
        enabled=True,
    )
    app_db.save_provider(p)
    return p


# ---------------------------------------------------------------------------
# GET /api/providers/catalog
# ---------------------------------------------------------------------------


class TestProviderCatalog:
    def test_returns_catalog_list(self, client):
        r = client.get("/api/providers/catalog")
        assert r.status_code == 200
        data = r.json()["items"]
        assert isinstance(data, list)
        assert len(data) > 0  # At least one built-in provider

    def test_catalog_has_required_fields(self, client):
        r = client.get("/api/providers/catalog")
        assert r.status_code == 200
        first = r.json()["items"][0]
        assert "type" in first
        assert "name" in first
        assert "is_local" in first

    def test_catalog_specific_provider(self, client):
        r = client.get("/api/providers/catalog/anthropic")
        assert r.status_code == 200
        data = r.json()
        assert data["type"] == "anthropic"

    def test_catalog_unknown_provider_returns_404(self, client):
        r = client.get("/api/providers/catalog/does-not-exist")
        assert r.status_code == 404


class TestAppleAvailability:
    def test_reports_available_probe(self, client):
        with patch(
            "fichero.api.routes.providers.probe_apple_intelligence_bridge",
            new=AsyncMock(return_value=(True, None)),
        ):
            r = client.get("/api/providers/apple/availability")
        assert r.status_code == 200
        assert r.json() == {"available": True, "reason": None}

    def test_reports_bridge_failure_reason(self, client):
        with patch(
            "fichero.api.routes.providers.probe_apple_intelligence_bridge",
            new=AsyncMock(return_value=(False, "fm-bridge binary not found")),
        ):
            r = client.get("/api/providers/apple/availability")
        assert r.status_code == 200
        assert r.json() == {
            "available": False,
            "reason": "fm-bridge binary not found",
        }


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------


class TestListProviders:
    def test_empty_list(self, client):
        r = client.get("/api/providers")
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_returns_configured_providers(self, client, app_db):
        _make_provider(app_db, "Claude Provider")
        r = client.get("/api/providers")
        assert r.status_code == 200
        assert len(r.json()["items"]) == 1
        assert r.json()["items"][0]["name"] == "Claude Provider"


# ---------------------------------------------------------------------------
# POST /api/providers
# ---------------------------------------------------------------------------


class TestCreateProvider:
    def test_create_provider(self, client):
        with patch("fichero.api.routes.providers.set_api_key"):
            r = client.post("/api/providers", json={
                "name": "My Anthropic",
                "provider_type": "anthropic",
                "api_key": "sk-ant-test-key-123456",
            })
        assert r.status_code == 200
        data = r.json()
        assert data["provider_type"] == "anthropic"
        assert "id" in data

    def test_invalid_provider_type_returns_400(self, client):
        r = client.post("/api/providers", json={
            "name": "Bad",
            "provider_type": "made-up-llm",
        })
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/providers/{provider_id}
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_get_existing(self, client, app_db):
        p = _make_provider(app_db)
        r = client.get(f"/api/providers/{p.id}")
        assert r.status_code == 200
        assert r.json()["id"] == p.id

    def test_get_missing_returns_404(self, client):
        r = client.get("/api/providers/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/providers/{provider_id}
# ---------------------------------------------------------------------------


class TestPatchProvider:
    def test_patch_name(self, client, app_db):
        p = _make_provider(app_db, "Old Name")
        r = client.patch(f"/api/providers/{p.id}", json={"name": "New Name"})
        assert r.status_code == 200
        assert r.json()["name"] == "New Name"

    def test_patch_missing_returns_404(self, client):
        r = client.patch("/api/providers/no-such-id", json={"name": "x"})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/providers/{provider_id}
# ---------------------------------------------------------------------------


class TestDeleteProvider:
    def test_delete_removes_provider(self, client, app_db):
        p = _make_provider(app_db)
        r = client.delete(f"/api/providers/{p.id}")
        assert r.status_code == 200
        r2 = client.get(f"/api/providers/{p.id}")
        assert r2.status_code == 404

    def test_delete_missing_returns_404(self, client):
        r = client.delete("/api/providers/no-such-id")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/providers/refs
# ---------------------------------------------------------------------------


class TestProviderRefs:
    def test_empty_refs_list(self, client):
        r = client.get("/api/providers/refs")
        assert r.status_code == 200
        assert r.json()["items"] == []
