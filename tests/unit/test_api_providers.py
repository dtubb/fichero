"""
API tests for the provider system.

Tests the provider and model API endpoints against a running server.
These are integration tests that require the API to be running on localhost:8765.
"""

import pytest
import httpx
from typing import Optional

# Base URL for the running API
API_BASE = "http://127.0.0.1:8765/api"


def api_available() -> bool:
    """Check if API is running."""
    try:
        response = httpx.get(f"{API_BASE}/health", timeout=2.0)
        return response.status_code == 200
    except Exception:
        return False


# Skip all tests if API not running
pytestmark = pytest.mark.skipif(
    not api_available(),
    reason="API not running at localhost:8765"
)


# =============================================================================
# Provider Catalog Tests
# =============================================================================

class TestProviderCatalog:
    """Tests for GET /providers/catalog"""

    def test_catalog_returns_all_providers(self):
        """Test that catalog returns all expected providers."""
        response = httpx.get(f"{API_BASE}/providers/catalog")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 12  # We have 12+ providers

        # Check we have both local and cloud providers
        types = [p["type"] for p in data]
        assert "openai" in types
        assert "anthropic" in types
        assert "ollama" in types
        assert "apple_vision" in types
        assert "huggingface" in types

    def test_catalog_has_required_fields(self):
        """Test that each provider has all required fields."""
        response = httpx.get(f"{API_BASE}/providers/catalog")
        data = response.json()

        required_fields = [
            "type", "name", "description", "api_key_env", "api_key_url",
            "is_local", "supports_vision", "supports_embeddings",
            "supports_streaming", "default_model", "has_api_key",
            "icon", "color", "sort_order"
        ]

        for provider in data:
            for field in required_fields:
                assert field in provider, f"Missing {field} in {provider['type']}"

    def test_catalog_has_is_builtin_field(self):
        """Test that is_builtin field is present for Apple providers."""
        response = httpx.get(f"{API_BASE}/providers/catalog")
        data = response.json()

        for provider in data:
            assert "is_builtin" in provider, f"Missing is_builtin in {provider['type']}"

        # Apple providers should be builtin
        apple_vision = next((p for p in data if p["type"] == "apple_vision"), None)
        assert apple_vision is not None
        assert apple_vision["is_builtin"] is True

        apple_intel = next((p for p in data if p["type"] == "apple_intelligence"), None)
        assert apple_intel is not None
        assert apple_intel["is_builtin"] is True

        # Non-Apple providers should not be builtin
        openai = next((p for p in data if p["type"] == "openai"), None)
        assert openai is not None
        assert openai["is_builtin"] is False

    def test_catalog_has_logo_asset_field(self):
        """Test that logo_asset field is present."""
        response = httpx.get(f"{API_BASE}/providers/catalog")
        data = response.json()

        for provider in data:
            assert "logo_asset" in provider, f"Missing logo_asset in {provider['type']}"

        # Most providers should have logo assets
        openai = next((p for p in data if p["type"] == "openai"), None)
        assert openai["logo_asset"] == "Providers/OpenAI"

        # Apple providers use SF Symbols (no logo asset)
        apple_vision = next((p for p in data if p["type"] == "apple_vision"), None)
        assert apple_vision["logo_asset"] is None

    def test_catalog_sorted_by_order(self):
        """Test that catalog is sorted by sort_order."""
        response = httpx.get(f"{API_BASE}/providers/catalog")
        data = response.json()

        # Get sort orders
        sort_orders = [p["sort_order"] for p in data]

        # Should be sorted
        assert sort_orders == sorted(sort_orders)

        # Apple Vision should be first (sort_order 0)
        assert data[0]["type"] == "apple_vision"
        assert data[0]["sort_order"] == 0

    def test_catalog_local_providers(self):
        """Test local providers are correctly marked."""
        response = httpx.get(f"{API_BASE}/providers/catalog")
        data = response.json()

        local_types = {"apple_vision", "apple_intelligence", "ollama", "lmstudio"}

        for provider in data:
            if provider["type"] in local_types:
                assert provider["is_local"] is True, f"{provider['type']} should be local"
                assert provider["api_key_env"] is None
            else:
                assert provider["is_local"] is False, f"{provider['type']} should not be local"
                assert provider["api_key_env"] is not None

    def test_get_single_provider_catalog_entry(self):
        """Test GET /providers/catalog/{provider_type}"""
        response = httpx.get(f"{API_BASE}/providers/catalog/openai")

        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "openai"
        assert data["name"] == "OpenAI"
        assert data["supports_vision"] is True

    def test_get_invalid_provider_returns_404(self):
        """Test that invalid provider type returns 404."""
        response = httpx.get(f"{API_BASE}/providers/catalog/invalid_provider")
        assert response.status_code == 404


# =============================================================================
# Provider Connection Test
# =============================================================================

class TestProviderConnectionTest:
    """Tests for POST /providers/{provider_type}/test"""

    def test_test_apple_vision(self):
        """Test connection test for Apple Vision (always available on macOS)."""
        response = httpx.post(f"{API_BASE}/providers/apple_vision/test", timeout=10.0)

        assert response.status_code == 200
        data = response.json()
        assert data["provider_type"] == "apple_vision"
        assert data["success"] is True
        assert "Vision Framework" in data["message"]

    def test_test_invalid_provider(self):
        """Test connection test for invalid provider."""
        response = httpx.post(f"{API_BASE}/providers/invalid/test")

        assert response.status_code == 404

    def test_test_response_structure(self):
        """Test that connection test response has correct structure."""
        response = httpx.post(f"{API_BASE}/providers/apple_vision/test", timeout=10.0)
        data = response.json()

        required_fields = ["success", "provider_type", "message"]
        for field in required_fields:
            assert field in data

        # Optional fields
        assert "latency_ms" in data or data.get("latency_ms") is None
        assert "model_tested" in data or data.get("model_tested") is None


# =============================================================================
# Models API Tests
# =============================================================================

class TestModelsAPI:
    """Tests for /models endpoints"""

    def test_list_available_models(self):
        """Test GET /providers/models/{provider_type}"""
        response = httpx.get(f"{API_BASE}/providers/models/openai")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have at least some OpenAI models
        assert len(data) > 0

        # Check structure
        if data:
            model = data[0]
            assert "model_id" in model
            assert "full_name" in model
            assert "input_cost_per_million" in model
            assert "output_cost_per_million" in model


# =============================================================================
# HuggingFace Model Browser Tests
# =============================================================================

class TestHuggingFaceModelBrowser:
    """Tests for /models/huggingface endpoints"""

    def test_search_hf_models(self):
        """Test GET /models/huggingface"""
        response = httpx.get(
            f"{API_BASE}/models/huggingface",
            params={"limit": 5}
        )

        assert response.status_code == 200
        data = response.json()

        assert "models" in data
        assert "total" in data
        assert "has_more" in data
        assert isinstance(data["models"], list)

    def test_search_hf_models_by_task(self):
        """Test searching HF models by task."""
        response = httpx.get(
            f"{API_BASE}/models/huggingface",
            params={"task": "text-generation", "limit": 5}
        )

        assert response.status_code == 200
        data = response.json()

        # Should return models
        assert len(data["models"]) > 0

    def test_search_hf_models_structure(self):
        """Test that HF model response has correct structure."""
        response = httpx.get(
            f"{API_BASE}/models/huggingface",
            params={"limit": 1}
        )

        data = response.json()

        if data["models"]:
            model = data["models"][0]
            required_fields = ["id", "downloads", "likes", "tags"]
            for field in required_fields:
                assert field in model, f"Missing {field}"

    def test_list_hf_tasks(self):
        """Test GET /models/huggingface/tasks"""
        response = httpx.get(f"{API_BASE}/models/huggingface/tasks")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if data:
            task = data[0]
            assert "id" in task
            assert "label" in task


# =============================================================================
# Provider CRUD Tests
# =============================================================================

class TestProviderCRUD:
    """Tests for provider create/read/update/delete"""

    def test_list_configured_providers(self):
        """Test GET /providers"""
        response = httpx.get(f"{API_BASE}/providers")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_provider_response_structure(self):
        """Test that provider response has correct structure."""
        response = httpx.get(f"{API_BASE}/providers")
        data = response.json()

        if data:
            provider = data[0]
            required_fields = [
                "id", "name", "provider_type", "enabled",
                "sort_order", "has_api_key", "created_at"
            ]
            for field in required_fields:
                assert field in provider, f"Missing {field}"


# =============================================================================
# API Health and Stats
# =============================================================================

class TestAPIHealth:
    """Basic API health tests"""

    def test_health_check(self):
        """Test GET /health"""
        response = httpx.get(f"{API_BASE}/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_stats(self):
        """Test GET /stats"""
        response = httpx.get(f"{API_BASE}/stats")

        assert response.status_code == 200
        data = response.json()
        assert "documents" in data
        assert "artifacts" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
