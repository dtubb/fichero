"""Provider validation and error handling.

Validates provider configurations at save time and provides graceful error
handling at call time to prevent provider failures from destabilizing the app.
"""

import logging
from urllib.parse import urlparse

from fichero_server.llm.providers import ProviderType, get_provider_info

logger = logging.getLogger(__name__)


class ProviderValidationError(ValueError):
    """Raised when provider configuration validation fails."""

    pass


class ProviderCallError(Exception):
    """Raised when a provider call fails (wraps runtime errors from LiteLLM/LangChain)."""

    def __init__(self, provider: str, model: str, message: str, original_error: Exception | None = None):
        self.provider = provider
        self.model = model
        self.original_error = original_error
        super().__init__(message)


def _validate_api_key_format(provider: str, api_key: str) -> None:
    """Validate API key format for known providers."""
    provider_lower = provider.lower()

    # OpenAI keys should start with sk-
    if provider_lower == "openai" and not api_key.startswith("sk-"):
        raise ProviderValidationError(
            "Invalid OpenAI API key format. Keys should start with 'sk-'."
        )

    # Anthropic keys should start with sk-ant-
    if provider_lower == "anthropic" and not api_key.startswith("sk-ant-"):
        raise ProviderValidationError(
            "Invalid Anthropic API key format. Keys should start with 'sk-ant-'."
        )

    # Google/Gemini API keys are typically longer JSON or simple strings
    if provider_lower == "google" and len(api_key) < 10:
        raise ProviderValidationError(
            f"Google API key appears too short (got {len(api_key)} chars). "
            f"Check that you copied the full key."
        )

    # Groq, HuggingFace, and others typically have reasonable length
    if len(api_key.strip()) < 5:
        raise ProviderValidationError(
            f"API key is too short ({len(api_key)} chars). "
            f"Check that you copied the full key without extra whitespace."
        )

    # API keys shouldn't have whitespace
    if api_key != api_key.strip():
        raise ProviderValidationError(
            "API key contains leading/trailing whitespace. "
            "Please remove extra spaces."
        )

    if any(ch.isspace() for ch in api_key):
        raise ProviderValidationError(
            "API key contains whitespace. "
            "API keys should not have spaces, tabs, or line breaks."
        )


def _validate_api_base(api_base: str) -> None:
    """Validate API base URL format."""
    if not api_base:
        return

    try:
        parsed = urlparse(api_base)
    except Exception as e:
        raise ProviderValidationError(
            f"Invalid API base URL: {api_base} ({str(e)})"
        ) from e

    # Must have a scheme (http/https)
    if not parsed.scheme:
        raise ProviderValidationError(
            f"API base URL missing scheme (http:// or https://):\n  {api_base}"
        )

    # Should use https for cloud providers
    if parsed.scheme not in ("http", "https"):
        raise ProviderValidationError(
            f"API base URL must use http or https:\n  {api_base}"
        )

    if parsed.scheme == "http" and not parsed.hostname == "localhost":
        logger.warning(
            f"API base URL uses unencrypted HTTP for non-local host: {api_base}. "
            f"This may expose your API key. Use HTTPS when possible."
        )


def validate_provider_config(
    provider_type: str,
    api_key: str | None = None,
    api_base: str | None = None,
    extra: dict | None = None,
) -> None:
    """Validate provider configuration at save time.

    Args:
        provider_type: Provider type (e.g., 'openai', 'anthropic')
        api_key: API key for cloud providers (None for local providers)
        api_base: Custom API base URL (optional)
        extra: Additional provider-specific config (optional)

    Raises:
        ProviderValidationError: If validation fails
    """
    extra = extra or {}

    # Validate provider type exists
    try:
        ptype = ProviderType(provider_type)
    except ValueError:
        raise ProviderValidationError(
            f"Unknown provider type: '{provider_type}'. "
            f"Supported: {', '.join(pt.value for pt in ProviderType)}"
        ) from None

    info = get_provider_info(ptype)
    if not info:
        raise ProviderValidationError(
            f"Provider '{provider_type}' not found in catalog"
        )

    # Local providers don't need API keys
    if info.is_local:
        if api_key:
            logger.warning(
                f"Local provider '{provider_type}' doesn't need an API key"
            )
        return

    # Cloud providers need API keys
    if not api_key:
        raise ProviderValidationError(
            f"Provider '{provider_type}' requires an API key. "
            f"Get one at: {info.api_key_url or 'the provider website'}"
        )

    # Validate API key format
    try:
        _validate_api_key_format(provider_type, api_key)
    except ProviderValidationError:
        raise

    # Validate custom API base if provided
    if api_base:
        try:
            _validate_api_base(api_base)
        except ProviderValidationError:
            raise

    # Provider-specific validation
    if provider_type == "azure":
        if not api_base:
            raise ProviderValidationError(
                "Azure OpenAI requires an API base (Azure endpoint URL)"
            )
        if not extra.get("api_version"):
            logger.debug("Azure provider: using default api_version 2024-02-01")

    if provider_type == "bedrock":
        if not extra.get("region"):
            logger.debug("AWS Bedrock: using default region us-east-1")


def wrap_provider_call(provider: str, model: str, func, *args, **kwargs):
    """Wrap a provider call with error handling.

    Catches common provider errors and converts them to ProviderCallError
    with helpful messages.

    Args:
        provider: Provider type (e.g., 'openai')
        model: Model name
        func: Async function to call
        *args: Positional arguments for func
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        ProviderCallError: If the provider call fails
    """
    import asyncio

    async def _wrapped():
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            error_message = _parse_provider_error(provider, str(e))
            raise ProviderCallError(
                provider=provider,
                model=model,
                message=error_message,
                original_error=e,
            ) from e

    # If we're already in an async context, return the coroutine
    try:
        asyncio.get_running_loop()
        return _wrapped()
    except RuntimeError:
        # Not in async context, run it
        return asyncio.run(_wrapped())


def _parse_provider_error(provider: str, error_message: str) -> str:
    """Parse provider error and return helpful message."""
    provider = provider.lower()
    error_lower = error_message.lower()

    # API key errors
    if "401" in error_message or "unauthorized" in error_lower or "invalid_api_key" in error_lower:
        return (
            f"Invalid API key for {provider}. "
            f"Check your API key and try again. "
            f"Original error: {error_message[:100]}"
        )

    # Rate limiting
    if "429" in error_message or "rate_limit" in error_lower:
        return (
            f"{provider} rate limit exceeded. "
            f"Please wait and try again. "
            f"Original error: {error_message[:100]}"
        )

    # Network/connection errors
    if any(
        x in error_lower
        for x in ["connection", "timeout", "unreachable", "network", "refused"]
    ):
        return (
            f"Cannot connect to {provider}. "
            f"Check network connectivity and provider status. "
            f"Original error: {error_message[:100]}"
        )

    # Server errors
    if any(x in error_message for x in ["500", "502", "503", "504"]):
        return (
            f"{provider} server error. "
            f"The provider may be experiencing issues. Try again later. "
            f"Original error: {error_message[:100]}"
        )

    # Model not found
    if "not found" in error_lower or "model" in error_lower and "does not exist" in error_lower:
        return (
            f"Model not available on {provider}. "
            f"Check that '{provider}' has the model configured. "
            f"Original error: {error_message[:100]}"
        )

    # Quota exceeded
    if "quota" in error_lower or "limit" in error_lower:
        return (
            f"{provider} quota exceeded or limit reached. "
            f"Check your account and billing. "
            f"Original error: {error_message[:100]}"
        )

    # Generic fallback
    return f"{provider} call failed: {error_message[:200]}"
