"""Tests for provider validation and error handling."""

import pytest

from fichero.llm.provider_validation import (
    ProviderValidationError,
    validate_provider_config,
    _validate_api_key_format,
    _validate_api_base,
)


class TestValidateAPIKeyFormat:
    """Tests for API key format validation."""

    def test_openai_key_valid(self):
        """Valid OpenAI key should pass."""
        _validate_api_key_format("openai", "sk-proj-abc123def456")

    def test_openai_key_invalid_format(self):
        """Invalid OpenAI key format should raise."""
        with pytest.raises(ProviderValidationError, match="Invalid OpenAI API key format"):
            _validate_api_key_format("openai", "invalid_key_123")

    @pytest.mark.parametrize(
        ("provider", "api_key"),
        [
            ("openai", "invalid_key_123"),
            ("anthropic", "sk-abc123"),
        ],
    )
    def test_invalid_key_errors_do_not_echo_api_key_prefix(self, provider, api_key):
        with pytest.raises(ProviderValidationError) as excinfo:
            _validate_api_key_format(provider, api_key)

        message = str(excinfo.value)
        assert api_key[:10] not in message
        assert "got:" not in message

    def test_anthropic_key_valid(self):
        """Valid Anthropic key should pass."""
        _validate_api_key_format("anthropic", "sk-ant-abc123def456")

    def test_anthropic_key_invalid_format(self):
        """Invalid Anthropic key format should raise."""
        with pytest.raises(ProviderValidationError, match="Invalid Anthropic API key format"):
            _validate_api_key_format("anthropic", "sk-abc123")

    def test_google_key_too_short(self):
        """Google key that's too short should raise."""
        with pytest.raises(ProviderValidationError, match="too short"):
            _validate_api_key_format("google", "short")

    def test_api_key_with_whitespace(self):
        """API key with whitespace should raise."""
        with pytest.raises(ProviderValidationError, match="whitespace"):
            _validate_api_key_format("openai", "sk-abc123 trailing")

    def test_api_key_with_newline(self):
        """API key with newline should raise."""
        with pytest.raises(ProviderValidationError, match="whitespace"):
            _validate_api_key_format("openai", "sk-abc123\n")


class TestValidateAPIBase:
    """Tests for API base URL validation."""

    def test_valid_https_url(self):
        """Valid HTTPS URL should pass."""
        _validate_api_base("https://api.openai.com")

    def test_valid_http_localhost(self):
        """Valid HTTP localhost URL should pass."""
        _validate_api_base("http://localhost:8000")

    def test_missing_scheme(self):
        """URL missing scheme should raise."""
        with pytest.raises(ProviderValidationError, match="missing scheme"):
            _validate_api_base("api.example.com")

    def test_invalid_scheme(self):
        """URL with invalid scheme should raise."""
        with pytest.raises(ProviderValidationError, match="must use http or https"):
            _validate_api_base("ftp://api.example.com")

    def test_empty_url(self):
        """Empty URL should pass (optional field)."""
        _validate_api_base("")
        _validate_api_base(None)


class TestValidateProviderConfig:
    """Tests for full provider configuration validation."""

    def test_unknown_provider_type(self):
        """Unknown provider type should raise."""
        with pytest.raises(ProviderValidationError, match="Unknown provider type"):
            validate_provider_config("unknown_provider")

    def test_local_provider_no_key_required(self):
        """Local providers shouldn't require API keys."""
        validate_provider_config("apple")
        validate_provider_config("ollama")
        validate_provider_config("omlx")

    def test_omlx_accepts_arbitrary_local_key(self):
        """oMLX is local OpenAI-compatible and must not require sk- keys."""
        validate_provider_config(
            "omlx",
            api_key="local-omlx-key",
            api_base="http://localhost:8000/v1",
        )

    def test_cloud_provider_requires_key(self):
        """Cloud providers should require API keys."""
        with pytest.raises(ProviderValidationError, match="requires an API key"):
            validate_provider_config("openai")

    def test_valid_openai_config(self):
        """Valid OpenAI config should pass."""
        validate_provider_config(
            "openai",
            api_key="sk-proj-abc123def456",
        )

    def test_invalid_openai_key_format(self):
        """Invalid OpenAI key should raise."""
        with pytest.raises(ProviderValidationError, match="Invalid OpenAI"):
            validate_provider_config(
                "openai",
                api_key="invalid_key",
            )

    def test_valid_anthropic_config(self):
        """Valid Anthropic config should pass."""
        validate_provider_config(
            "anthropic",
            api_key="sk-ant-abc123def456",
        )

    def test_invalid_api_base_url(self):
        """Invalid API base URL should raise."""
        with pytest.raises(ProviderValidationError, match="missing scheme"):
            validate_provider_config(
                "openai",
                api_key="sk-proj-abc123",
                api_base="invalid_url",
            )

    def test_azure_requires_api_base(self):
        """Azure should require API base."""
        with pytest.raises(ProviderValidationError, match="requires an API base"):
            validate_provider_config(
                "azure",
                api_key="sk-proj-abc123",
            )

    def test_azure_with_valid_config(self):
        """Azure with valid config should pass."""
        validate_provider_config(
            "azure",
            api_key="sk-proj-abc123",
            api_base="https://myresource.openai.azure.com/",
        )
