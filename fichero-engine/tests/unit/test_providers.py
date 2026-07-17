"""
Unit tests for the provider system.

Tests providers.py, llm.py, and the provider API routes.
"""

import pytest
from unittest.mock import patch


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
        assert ProviderType.omlx.value == "omlx"

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

    def test_omlx_provider_uses_decided_user_facing_label(self):
        from fichero.providers import PROVIDERS, ProviderType

        assert PROVIDERS[ProviderType.omlx].name == "MLX (Local)"

    def test_ocr_htr_provider_defaults_use_recommended_models(self):
        """Vision/transcription defaults should prefer the OCR/HTR-recommended models."""
        from fichero.providers import PROVIDERS, ProviderType

        assert PROVIDERS[ProviderType.huggingface].default_model == "Qwen/Qwen3-VL-8B-Instruct"
        assert PROVIDERS[ProviderType.google].default_model == "gemini-3-pro-preview"
        assert PROVIDERS[ProviderType.openai].default_model == "gpt-5"

    def test_local_providers(self):
        """Test local providers are correctly marked."""
        from fichero.providers import get_local_providers

        local = get_local_providers()
        assert len(local) >= 3  # ollama, lmstudio, and omlx

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

    @pytest.fixture(autouse=True)
    def _clear_api_key_cache(self):
        # get_api_key caches resolved keys process-wide (#2545); clear between
        # tests so each case observes its own mocked Keychain/env result.
        from fichero.llm import clear_api_key_cache

        clear_api_key_cache()
        yield
        clear_api_key_cache()

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

        with patch("fichero.llm_models._get_litellm") as mock_litellm:
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

        with patch("fichero.llm_models._get_litellm") as mock_litellm:
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

        with patch("fichero.llm_models._get_litellm") as mock_litellm:
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
            data = response.json()["items"]
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
        with patch("fichero.api.routes.providers.set_api_key") as mock_set_key:
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
            assert data["enabled"] is True
            assert "id" in data
            assert "created_at" in data

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
        data = response.json()["items"]
        # Should return our curated list
        assert len(data) >= 5  # We have at least 5 OpenAI models
        model_ids = [m["model_id"] for m in data]
        assert "gpt-4o" in model_ids
        assert "gpt-4o-mini" in model_ids
        # Check recommended flag
        gpt4o = next(m for m in data if m["model_id"] == "gpt-4o")
        assert gpt4o["is_recommended"] is True
        assert gpt4o["supports_vision"] is True

        openai_curated = next(m for m in data if m["model_id"] == "gpt-5")
        assert openai_curated["is_recommended"] is True
        assert openai_curated["supports_vision"] is True
        assert openai_curated["supports_pdf_input"] is True

        google_response = client.get("/api/providers/models/google")
        assert google_response.status_code == 200
        google_data = google_response.json()["items"]
        gemini3 = next(m for m in google_data if m["model_id"] == "gemini-3-pro-preview")
        assert gemini3["is_recommended"] is True
        assert gemini3["supports_vision"] is True
        assert gemini3["supports_pdf_input"] is True

        hf_response = client.get("/api/providers/models/huggingface")
        assert hf_response.status_code == 200
        hf_data = hf_response.json()["items"]
        hf_ids = {m["model_id"] for m in hf_data}
        assert "Qwen/Qwen3-VL-8B-Instruct" in hf_ids
        assert "datalab-to/chandra-ocr-2" in hf_ids
        assert "nanonets/Nanonets-OCR-s" in hf_ids
        qwen3 = next(m for m in hf_data if m["model_id"] == "Qwen/Qwen3-VL-8B-Instruct")
        assert qwen3["is_recommended"] is True
        assert qwen3["supports_vision"] is True
        assert qwen3["supports_pdf_input"] is True

    def test_list_models_for_provider_openrouter(self, client):
        """Test GET /api/providers/models/openrouter returns LiteLLM's catalog.

        Regression lock for the "No models configured" / "can't add openrouter
        models" report: OpenRouter has no entry in RECOMMENDED_MODELS (unlike
        openai/google/huggingface above), so it falls through to LiteLLM's
        static registry via ``is_provider_model``, which matches on the
        ``openrouter/`` prefix. This asserts that path actually surfaces
        models instead of silently returning an empty list.
        """
        response = client.get("/api/providers/models/openrouter")

        assert response.status_code == 200
        data = response.json()["items"]
        assert len(data) > 0, "OpenRouter model browser should not be empty"

        model_ids = [m["model_id"] for m in data]
        # Display id has the "openrouter/" prefix stripped...
        assert any(model_id.startswith("anthropic/") for model_id in model_ids)
        assert not any(model_id.startswith("openrouter/") for model_id in model_ids)

        # ...while full_name retains the LiteLLM-routable identifier.
        sample = next(m for m in data if m["model_id"].startswith("anthropic/"))
        assert sample["full_name"].startswith("openrouter/")
        assert sample["provider"] == "openrouter"

    def test_list_models_preserves_unknown_pricing_without_marking_free(self, client):
        from fichero.api.routes.provider_models import generate_model_description

        fake_models = [{
            "model_id": "gpt-opaque",
            "full_name": "openai/gpt-opaque",
            "description": None,
            "input_cost_per_million": None,
            "output_cost_per_million": 10.0,
            "supports_vision": False,
            "supports_function_calling": False,
            "supports_audio_input": False,
            "supports_audio_output": False,
            "supports_pdf_input": False,
            "supports_prompt_caching": False,
            "supports_reasoning": False,
            "supports_web_search": False,
            "supports_streaming": True,
            "supports_batch_api": False,
            "provider": "openai",
            "mode": "chat",
        }]

        with patch("fichero.llm.list_models_for_provider", return_value=fake_models):
            response = client.get("/api/providers/models/openai")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] >= 1
        opaque = next(item for item in payload["items"] if item["model_id"] == "gpt-opaque")
        assert opaque["input_cost_per_million"] is None
        assert opaque["output_cost_per_million"] == 10.0
        assert opaque["description"] is None
        assert generate_model_description(opaque) is None

    def test_api_key_status(self, client):
        """Test GET /api/providers/{provider_type}/api-key/status"""
        with patch("fichero.api.routes.provider_keys.has_api_key") as mock_has:
            with patch("fichero.api.routes.provider_keys.keychain_available") as mock_avail:
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


# =============================================================================
# AppDatabase Tests - App-Wide Provider Storage
# =============================================================================

class TestAppDatabase:
    """Test app-wide database for providers and models."""

    class _TrackingLock:
        def __init__(self):
            self.enter_count = 0

        def __enter__(self):
            self.enter_count += 1
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def test_create_app_database(self, app_db):
        """Test app database initialization."""
        assert app_db is not None
        assert app_db.path.exists()
        assert app_db.conn is not None

    def test_get_setting_uses_connection_lock(self, app_db):
        """Reads must acquire AppDatabase RLock to avoid pending-query races (#709)."""
        app_db.set_setting("test_lock_key", "v")
        lock = self._TrackingLock()
        app_db._lock = lock

        assert app_db.get_setting("test_lock_key") == "v"
        assert lock.enter_count == 1

    def test_save_and_get_provider(self, app_db):
        """Test saving and retrieving a provider."""
        from fichero.models import Provider, ProviderType

        provider = Provider(
            name="OpenAI",
            provider_type=ProviderType.openai,
            api_base="https://api.openai.com",
            enabled=True,
            sort_order=0,
        )

        # Save
        app_db.save_provider(provider)

        # Retrieve
        retrieved = app_db.get_provider(provider.id)
        assert retrieved is not None
        assert retrieved.id == provider.id
        assert retrieved.name == "OpenAI"
        assert retrieved.provider_type == ProviderType.openai
        assert retrieved.enabled is True

    def test_list_providers(self, app_db):
        """Test listing all providers."""
        from fichero.models import Provider, ProviderType

        # Create multiple providers
        provider1 = Provider(
            name="OpenAI",
            provider_type=ProviderType.openai,
            sort_order=1,
        )
        provider2 = Provider(
            name="Anthropic",
            provider_type=ProviderType.anthropic,
            sort_order=0,
        )

        app_db.save_provider(provider1)
        app_db.save_provider(provider2)

        # List should return both, sorted by sort_order
        providers = app_db.list_providers()
        assert len(providers) == 2
        assert providers[0].name == "Anthropic"  # sort_order=0
        assert providers[1].name == "OpenAI"     # sort_order=1

    def test_delete_provider(self, app_db):
        """Test deleting a provider."""
        from fichero.models import Provider, ProviderType

        provider = Provider(
            name="OpenAI",
            provider_type=ProviderType.openai,
        )
        app_db.save_provider(provider)

        # Delete
        app_db.delete_provider(provider.id)

        # Verify deletion
        retrieved = app_db.get_provider(provider.id)
        assert retrieved is None

    def test_delete_provider_deletes_models(self, app_db):
        """Test that deleting a provider also deletes its models."""
        from fichero.models import Provider, Model, ProviderType

        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        # Create two models
        model1 = Model(provider_id=provider.id, name="GPT-4o", model_id="gpt-4o")
        model2 = Model(provider_id=provider.id, name="GPT-4", model_id="gpt-4")
        app_db.save_model(model1)
        app_db.save_model(model2)

        # Delete provider
        app_db.delete_provider(provider.id)

        # Verify models are also deleted
        models = app_db.list_models(provider.id)
        assert len(models) == 0

    def test_save_and_get_model(self, app_db):
        """Test saving and retrieving a model."""
        from fichero.models import Provider, Model, ProviderType

        # First create a provider
        provider = Provider(
            name="OpenAI",
            provider_type=ProviderType.openai,
        )
        app_db.save_provider(provider)

        # Create a model
        model = Model(
            provider_id=provider.id,
            name="GPT-4o",
            model_id="gpt-4o",
            capabilities=["vision", "function_calling"],
            is_default=True,
            enabled=True,
            input_cost=2.50,
            output_cost=10.00,
        )

        # Save
        app_db.save_model(model)

        # Retrieve via list_models
        models = app_db.list_models(provider.id)
        assert len(models) == 1
        assert models[0].id == model.id
        assert models[0].name == "GPT-4o"
        assert models[0].model_id == "gpt-4o"
        assert models[0].capabilities == ["vision", "function_calling"]
        assert models[0].is_default is True
        assert models[0].input_cost == 2.50
        assert models[0].output_cost == 10.00


# =============================================================================
# Library Database Provider References Tests
# =============================================================================

class TestProviderRefs:
    """Test library-specific provider references."""

    def test_save_and_get_provider_ref(self, db):
        """Test saving and retrieving a provider reference."""
        from fichero.models import ProviderRef

        ref = ProviderRef(
            provider_id="test-provider-123",
            enabled=True,
            sort_order=0,
        )

        # Save
        db.save(ref)

        # Retrieve
        retrieved = db.get(ProviderRef, ref.id)
        assert retrieved is not None
        assert retrieved.id == ref.id
        assert retrieved.provider_id == "test-provider-123"
        assert retrieved.enabled is True

    def test_query_provider_refs_by_provider_id(self, db):
        """Test querying provider refs by provider_id."""
        from fichero.models import ProviderRef

        ref1 = ProviderRef(provider_id="provider-1")
        ref2 = ProviderRef(provider_id="provider-1")
        ref3 = ProviderRef(provider_id="provider-2")

        db.save(ref1)
        db.save(ref2)
        db.save(ref3)

        # Query for provider-1
        refs = db.query(ProviderRef, provider_id="provider-1")
        assert len(refs) == 2

        # Query for provider-2
        refs = db.query(ProviderRef, provider_id="provider-2")
        assert len(refs) == 1

    def test_delete_provider_ref(self, db):
        """Test deleting a provider reference."""
        from fichero.models import ProviderRef

        ref = ProviderRef(provider_id="test-provider-123")
        db.save(ref)

        # Delete
        db.delete(ref)

        # Verify deletion
        retrieved = db.get(ProviderRef, ref.id)
        assert retrieved is None


# =============================================================================
# Provider Reference API Routes Tests
# =============================================================================

class TestProviderRefRoutes:
    """Test library-specific provider reference API routes."""

    def test_list_provider_refs_empty(self, client, db, app_db):
        """Test listing provider refs when none exist."""
        response = client.get("/api/providers/refs")
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_add_provider_ref(self, client, db, app_db):
        """Test adding a provider reference to a library."""
        from fichero.models import Provider, ProviderType

        # Create a provider in app database
        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        # Add reference via API
        response = client.post("/api/providers/refs", json={
            "provider_id": provider.id,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["provider_id"] == provider.id
        assert data["provider_name"] == "OpenAI"
        assert data["provider_type"] == "openai"
        assert data["enabled"] is True

    def test_add_provider_ref_nonexistent_provider(self, client, db, app_db):
        """Test adding a reference to a non-existent provider."""
        response = client.post("/api/providers/refs", json={
            "provider_id": "nonexistent-id",
        })

        assert response.status_code == 404

    def test_add_duplicate_provider_ref(self, client, db, app_db):
        """Test adding a duplicate provider reference."""
        from fichero.models import Provider, ProviderType

        # Create provider
        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        # Add reference
        client.post("/api/providers/refs", json={"provider_id": provider.id})

        # Try to add again
        response = client.post("/api/providers/refs", json={"provider_id": provider.id})
        assert response.status_code == 400

    def test_list_provider_refs(self, client, db, app_db):
        """Test listing provider references."""
        from fichero.models import Provider, ProviderType

        # Create two providers
        provider1 = Provider(name="OpenAI", provider_type=ProviderType.openai)
        provider2 = Provider(name="Anthropic", provider_type=ProviderType.anthropic)
        app_db.save_provider(provider1)
        app_db.save_provider(provider2)

        # Add references
        client.post("/api/providers/refs", json={"provider_id": provider1.id})
        client.post("/api/providers/refs", json={"provider_id": provider2.id})

        # List references
        response = client.get("/api/providers/refs")
        assert response.status_code == 200
        data = response.json()["items"]
        assert len(data) == 2

    def test_update_provider_ref(self, client, db, app_db):
        """Test updating a provider reference."""
        from fichero.models import Provider, ProviderType

        # Create provider and reference
        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        ref_response = client.post("/api/providers/refs", json={"provider_id": provider.id})
        ref_id = ref_response.json()["id"]

        # Update reference
        response = client.patch(f"/api/providers/refs/{ref_id}", json={
            "enabled": False,
            "sort_order": 5,
        })

        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["sort_order"] == 5

    def test_delete_provider_ref(self, client, db, app_db):
        """Test deleting a provider reference."""
        from fichero.models import Provider, ProviderType

        # Create provider and reference
        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        ref_response = client.post("/api/providers/refs", json={"provider_id": provider.id})
        ref_id = ref_response.json()["id"]

        # Delete reference
        response = client.delete(f"/api/providers/refs/{ref_id}")
        assert response.status_code == 200

        # Verify deletion
        response = client.get("/api/providers/refs")
        assert len(response.json()["items"]) == 0

    def test_list_refs_excludes_deleted_providers(self, client, db, app_db):
        """Test that listing refs excludes references to deleted providers."""
        from fichero.models import Provider, ProviderType

        # Create provider and reference
        provider = Provider(name="OpenAI", provider_type=ProviderType.openai)
        app_db.save_provider(provider)

        client.post("/api/providers/refs", json={"provider_id": provider.id})

        # Delete the provider from app database
        app_db.delete_provider(provider.id)

        # List refs should return empty (provider no longer exists)
        response = client.get("/api/providers/refs")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 0


class TestCollapseDuplicateProviders:
    """Issue #704 — startup cleanup that merges duplicate provider rows
    sharing (name, provider_type). Earliest row wins; models attached to
    duplicates get reparented to the canonical row before deletion.
    """

    def test_collapses_duplicates_by_name_and_type(self, app_db, monkeypatch):
        from datetime import datetime, timedelta
        from fichero.models import Provider, ProviderType
        from fichero.api import main as api_main

        early = Provider(
            name="My OpenAI",
            provider_type=ProviderType.openai,
            created_at=datetime.now() - timedelta(hours=2),
        )
        late = Provider(
            name="My OpenAI",
            provider_type=ProviderType.openai,
            created_at=datetime.now(),
        )
        app_db.save_provider(early)
        app_db.save_provider(late)

        # Patch get_app_db so the startup function operates on our test db.
        monkeypatch.setattr(
            "fichero.app_db.get_app_db", lambda: app_db, raising=False
        )

        api_main._collapse_duplicate_providers()

        survivors = [
            p for p in app_db.list_providers()
            if p.name == "My OpenAI" and p.provider_type == ProviderType.openai
        ]
        assert len(survivors) == 1
        assert survivors[0].id == early.id  # earliest created_at wins

    def test_leaves_distinct_providers_alone(self, app_db, monkeypatch):
        from fichero.models import Provider, ProviderType
        from fichero.api import main as api_main

        a = Provider(name="My OpenAI", provider_type=ProviderType.openai)
        b = Provider(name="Work OpenAI", provider_type=ProviderType.openai)
        c = Provider(name="My OpenAI", provider_type=ProviderType.anthropic)
        for p in (a, b, c):
            app_db.save_provider(p)

        monkeypatch.setattr(
            "fichero.app_db.get_app_db", lambda: app_db, raising=False
        )

        api_main._collapse_duplicate_providers()

        # Different name OR different provider_type → not duplicates.
        ids = {p.id for p in app_db.list_providers()}
        assert {a.id, b.id, c.id}.issubset(ids)

    def test_reparent_model(self, app_db):
        """Test reparent_model re-parents a model to a different provider."""
        from fichero.models import Provider, ProviderType, Model

        prov_a = Provider(name="Provider A", provider_type=ProviderType.openai)
        prov_b = Provider(name="Provider B", provider_type=ProviderType.anthropic)
        app_db.save_provider(prov_a)
        app_db.save_provider(prov_b)

        model = Model(
            provider_id=prov_a.id,
            name="Test Model",
            model_id="test-model",
        )
        app_db.save_model(model)

        # Re-parent model from prov_a to prov_b
        reparented = app_db.reparent_model(model.id, prov_b.id)
        assert reparented is not None
        assert reparented.provider_id == prov_b.id

        # Verify model now lists under prov_b, not prov_a
        models_a = app_db.list_models(prov_a.id)
        models_b = app_db.list_models(prov_b.id)
        assert not any(m.id == model.id for m in models_a)
        assert any(m.id == model.id for m in models_b)


# =============================================================================
# Capability Derivation Tests (#1290)
# =============================================================================

class TestCapabilityDerivation:
    """Cloud models must carry registry-derived capabilities so the
    Settings → Defaults pickers can filter them into the right slot
    instead of rejecting the saved choice as "(saved — wrong capability)".
    """

    @staticmethod
    def _registry(rows):
        return patch(
            "fichero.llm.list_models_for_provider",
            return_value=rows,
        )

    def test_chat_model_derives_text_and_tools(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        rows = [{
            "model_id": "gpt-4o-mini",
            "mode": "chat",
            "supports_vision": False,
            "supports_function_calling": True,
            "supports_audio_input": False,
        }]
        with self._registry(rows):
            caps = _derive_capabilities_from_registry("openai", "gpt-4o-mini")
        assert caps == ["text", "tools"]

    def test_omlx_vision_model_derives_text_and_vision(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        caps = _derive_capabilities_from_registry("omlx", "Nanonets-OCR")
        assert caps == ["text", "vision"]

    def test_vision_chat_model_derives_text_and_vision(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        rows = [{
            "model_id": "gpt-4o",
            "mode": "chat",
            "supports_vision": True,
            "supports_function_calling": True,
            "supports_audio_input": False,
        }]
        with self._registry(rows):
            caps = _derive_capabilities_from_registry("openai", "gpt-4o")
        # text (chat) fits $small/$large/Text; vision fits the Vision slot.
        assert "text" in caps
        assert "vision" in caps
        assert "tools" in caps

    def test_transcription_model_derives_audio_and_transcription(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        rows = [{
            "model_id": "whisper-1",
            "mode": "audio_transcription",
            "supports_vision": False,
            "supports_function_calling": False,
            "supports_audio_input": False,
        }]
        with self._registry(rows):
            caps = _derive_capabilities_from_registry("openai", "whisper-1")
        # The Audio slot accepts either "audio" or "transcription".
        assert caps == ["audio", "transcription"]

    def test_embedding_model_is_not_text(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        rows = [{
            "model_id": "text-embedding-3-small",
            "mode": "embedding",
            "supports_vision": False,
            "supports_function_calling": False,
            "supports_audio_input": False,
        }]
        with self._registry(rows):
            caps = _derive_capabilities_from_registry(
                "openai", "text-embedding-3-small"
            )
        # Embeddings are not chat models — must NOT claim the text tier.
        assert "text" not in caps
        assert caps == ["embedding"]

    def test_unknown_model_returns_empty(self):
        from fichero.api.routes.providers import (
            _derive_capabilities_from_registry,
        )

        with self._registry([]):
            caps = _derive_capabilities_from_registry("openai", "not-a-real-model")
        assert caps == []


class TestProviderModelDiscoveryHelpers:
    def test_openai_models_url_accepts_base_with_or_without_v1(self):
        from fichero.api.routes.provider_models import _openai_models_url

        assert (
            _openai_models_url("http://localhost:8000")
            == "http://localhost:8000/v1/models"
        )
        assert (
            _openai_models_url("http://localhost:8000/v1")
            == "http://localhost:8000/v1/models"
        )

    def test_local_server_root_strips_openai_compatible_suffix(self):
        from fichero.api.routes.provider_models import _local_server_root

        assert _local_server_root("http://localhost:11434/v1") == "http://localhost:11434"
