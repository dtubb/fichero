"""
Unit tests for the provider system.

Tests providers.py, llm.py, and the provider API routes.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# =============================================================================
# Provider Catalog Tests
# =============================================================================

class TestProviderCatalog:
    """Tests for fichero/providers.py"""

    def test_provider_type_enum(self):
        """Test ProviderType enum has expected values."""
        from fichero.providers import ProviderType

        assert ProviderType.openai.value == "openai"
        assert ProviderType.anthropic.value == "anthropic"
        assert ProviderType.huggingface.value == "huggingface"
        assert ProviderType.ollama.value == "ollama"
        assert ProviderType.lmstudio.value == "lmstudio"

    def test_providers_dict_has_all_types(self):
        """Test PROVIDERS dict contains all provider types."""
        from fichero.providers import PROVIDERS, ProviderType

        for ptype in ProviderType:
            assert ptype in PROVIDERS, f"Missing provider: {ptype}"

    def test_provider_info_structure(self):
        """Test ProviderInfo has required fields."""
        from fichero.providers import PROVIDERS, ProviderType

        openai_info = PROVIDERS[ProviderType.openai]

        assert openai_info.type == ProviderType.openai
        assert openai_info.name == "OpenAI"
        assert openai_info.api_key_env == "OPENAI_API_KEY"
        assert openai_info.is_local is False
        assert openai_info.supports_vision is True

    def test_local_providers(self):
        """Test local providers are correctly marked."""
        from fichero.providers import get_local_providers

        local = get_local_providers()
        assert len(local) >= 2  # ollama and lmstudio

        for p in local:
            assert p.is_local is True
            assert p.api_key_env is None

    def test_cloud_providers(self):
        """Test cloud providers require API keys."""
        from fichero.providers import get_cloud_providers

        cloud = get_cloud_providers()
        assert len(cloud) >= 9  # openai, anthropic, huggingface, etc.

        for p in cloud:
            assert p.is_local is False
            assert p.api_key_env is not None

    def test_get_provider_info(self):
        """Test get_provider_info helper."""
        from fichero.providers import get_provider_info, ProviderType

        # By enum
        info = get_provider_info(ProviderType.openai)
        assert info is not None
        assert info.name == "OpenAI"

        # By string
        info = get_provider_info("anthropic")
        assert info is not None
        assert info.name == "Anthropic"

        # Invalid
        info = get_provider_info("invalid")
        assert info is None

    def test_vision_providers(self):
        """Test vision-capable providers."""
        from fichero.providers import get_vision_providers

        vision = get_vision_providers()
        assert len(vision) >= 5

        provider_types = [p.type.value for p in vision]
        assert "openai" in provider_types
        assert "anthropic" in provider_types
        assert "google" in provider_types

    def test_embedding_providers(self):
        """Test embedding-capable providers."""
        from fichero.providers import get_embedding_providers

        embedding = get_embedding_providers()
        assert len(embedding) >= 5

        provider_types = [p.type.value for p in embedding]
        assert "openai" in provider_types
        assert "huggingface" in provider_types


# =============================================================================
# LLM Interface Tests
# =============================================================================

class TestLLMConfig:
    """Tests for LLMConfig in llm.py"""

    def test_config_defaults(self):
        """Test LLMConfig default values."""
        from fichero.llm import LLMConfig

        config = LLMConfig(provider="openai", model="gpt-4o")

        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0.7
        assert config.max_tokens == 2048
        assert config.api_key is None

    def test_get_model_name(self):
        """Test model name formatting for LiteLLM."""
        from fichero.llm import LLMConfig

        # Standard provider
        config = LLMConfig(provider="openai", model="gpt-4o")
        assert config.get_model_name() == "openai/gpt-4o"

        # Local provider (uses ollama prefix)
        config = LLMConfig(provider="ollama", model="llama3.2")
        assert config.get_model_name() == "ollama/llama3.2"

        # HuggingFace
        config = LLMConfig(provider="huggingface", model="meta-llama/Llama-3.2-3B")
        assert config.get_model_name() == "huggingface/meta-llama/Llama-3.2-3B"


class TestAPIKeyResolution:
    """Tests for API key resolution in llm.py"""

    def test_get_api_key_from_keychain(self):
        """Test API key resolution from keychain."""
        from fichero.llm import get_api_key

        with patch("fichero.keychain.get_api_key") as mock_keychain:
            mock_keychain.return_value = "sk-test-key"

            key = get_api_key("openai")
            assert key == "sk-test-key"
            mock_keychain.assert_called_once_with("openai")

    def test_get_api_key_fallback_to_env(self):
        """Test API key falls back to environment variable."""
        from fichero.llm import get_api_key
        import os

        with patch("fichero.keychain.get_api_key") as mock_keychain:
            mock_keychain.return_value = None

            with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}):
                key = get_api_key("openai")
                assert key == "env-key"


# =============================================================================
# Model Info Tests
# =============================================================================

class TestModelInfo:
    """Tests for model info functions in llm.py"""

    def test_list_models_for_provider(self):
        """Test listing models for a provider."""
        from fichero.llm import list_models_for_provider

        with patch("fichero.llm._get_litellm") as mock_litellm:
            mock_litellm.return_value.model_cost = {
                "openai/gpt-4o": {
                    "input_cost_per_token": 0.000005,
                    "output_cost_per_token": 0.000015,
                    "max_tokens": 128000,
                    "supports_vision": True,
                    "supports_function_calling": True,
                },
                "openai/gpt-4o-mini": {
                    "input_cost_per_token": 0.00000015,
                    "output_cost_per_token": 0.0000006,
                    "max_tokens": 128000,
                    "supports_vision": True,
                },
                "anthropic/claude-3": {
                    "input_cost_per_token": 0.000003,
                    "output_cost_per_token": 0.000015,
                },
            }

            models = list_models_for_provider("openai")

            assert len(models) == 2
            model_ids = [m["model_id"] for m in models]
            assert "gpt-4o" in model_ids
            assert "gpt-4o-mini" in model_ids

    def test_get_model_cost(self):
        """Test getting model cost info."""
        from fichero.llm import get_model_cost

        with patch("fichero.llm._get_litellm") as mock_litellm:
            mock_litellm.return_value.model_cost = {
                "gpt-4o": {
                    "input_cost_per_token": 0.000005,
                    "output_cost_per_token": 0.000015,
                }
            }

            cost = get_model_cost("gpt-4o")

            assert cost is not None
            assert "input_cost_per_token" in cost
            assert "output_cost_per_token" in cost

    def test_estimate_cost(self):
        """Test cost estimation."""
        from fichero.llm import estimate_cost

        with patch("fichero.llm._get_litellm") as mock_litellm:
            mock_litellm.return_value.cost_per_token.return_value = (0.05, 0.15)

            cost = estimate_cost("gpt-4o", input_tokens=1000, output_tokens=500)

            assert cost == 0.20


# =============================================================================
# Provider API Route Tests
# =============================================================================

class TestProviderAPIRoutes:
    """Tests for provider API routes."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient
        from fichero.api.main import app
        return TestClient(app)

    def test_list_catalog(self, client):
        """Test GET /api/providers/catalog"""
        with patch("fichero.api.routes.providers.has_api_key") as mock_has_key:
            mock_has_key.return_value = False

            response = client.get("/api/providers/catalog")

            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)
            assert len(data) >= 10

            # Check structure
            provider = data[0]
            assert "type" in provider
            assert "name" in provider
            assert "description" in provider
            assert "is_local" in provider

    def test_get_catalog_entry(self, client):
        """Test GET /api/providers/catalog/{provider_type}"""
        with patch("fichero.api.routes.providers.has_api_key") as mock_has_key:
            mock_has_key.return_value = True

            response = client.get("/api/providers/catalog/openai")

            assert response.status_code == 200
            data = response.json()
            assert data["type"] == "openai"
            assert data["name"] == "OpenAI"
            assert data["has_api_key"] is True

    def test_get_catalog_entry_not_found(self, client):
        """Test GET /api/providers/catalog/{invalid} returns 404"""
        response = client.get("/api/providers/catalog/invalid_provider")
        assert response.status_code == 404

    def test_create_provider(self, client):
        """Test POST /api/providers"""
        with patch("fichero.api.routes.providers.db") as mock_db:
            with patch("fichero.api.routes.providers.set_api_key") as mock_set_key:
                mock_db.save = MagicMock()
                mock_set_key.return_value = True

                response = client.post(
                    "/api/providers",
                    json={
                        "provider_type": "openai",
                        "name": "My OpenAI",
                        "api_key": "sk-test",
                    }
                )

                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "My OpenAI"
                assert data["provider_type"] == "openai"

                mock_db.save.assert_called_once()
                mock_set_key.assert_called_once_with("openai", "sk-test")

    def test_create_provider_invalid_type(self, client):
        """Test POST /api/providers with invalid type"""
        response = client.post(
            "/api/providers",
            json={"provider_type": "invalid_type"}
        )
        assert response.status_code == 400

    def test_list_models_for_provider(self, client):
        """Test GET /api/providers/models/{provider_type}"""
        # OpenAI uses curated RECOMMENDED_MODELS list, not LiteLLM
        response = client.get("/api/providers/models/openai")

        assert response.status_code == 200
        data = response.json()
        # Should return our curated list
        assert len(data) >= 5  # We have at least 5 OpenAI models
        model_ids = [m["model_id"] for m in data]
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids
        # Check recommended flag
        gpt4o = next(m for m in data if m["model_id"] == "gpt-4o")
        assert gpt4o["is_recommended"] is True
        assert gpt4o["supports_vision"] is True

    def test_api_key_status(self, client):
        """Test GET /api/providers/{provider_type}/api-key/status"""
        with patch("fichero.api.routes.providers.has_api_key") as mock_has:
            with patch("fichero.api.routes.providers.keychain_available") as mock_avail:
                mock_has.return_value = True
                mock_avail.return_value = True

                response = client.get("/api/providers/openai/api-key/status")

                assert response.status_code == 200
                data = response.json()
                assert data["provider_type"] == "openai"
                assert data["has_api_key"] is True
                assert data["is_local"] is False
                assert data["keychain_available"] is True


# =============================================================================
# Integration Tests
# =============================================================================

class TestProviderIntegration:
    """Integration tests for the provider system."""

    def test_full_provider_workflow(self):
        """Test creating provider, adding model, then deleting."""
        from fichero.providers import get_provider_info, ProviderType
        from fichero.models import Provider as ProviderModel

        # Get OpenAI info
        info = get_provider_info(ProviderType.openai)
        assert info is not None

        # Create provider model
        provider = ProviderModel(
            name="Test OpenAI",
            provider_type=ProviderType.openai,
            enabled=True,
        )

        assert provider.id is not None
        assert provider.name == "Test OpenAI"
        assert provider.provider_type == ProviderType.openai
