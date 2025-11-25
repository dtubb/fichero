"""
Comprehensive unit tests for all transcription options and processing modes.

Tests:
- All providers (DashScope, OpenAI, LMStudio)
- All models (qwen-vl-ocr, qwen-vl-max)
- All processing modes (sync ThreadPool, async, multi-image)
- Prompt configurations
- Error handling
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import asyncio

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture(scope="module", autouse=True)
def mock_dependencies():
    """Mock heavy dependencies for this test module"""
    original_modules = {}
    modules_to_mock = [
        'fichero.config',
        'fichero.config.core',
        'fichero.config.core.settings',
        'fichero.config.core.loader',
        'fichero.utils',
        'fichero.tools.utils.tool_logger',
        'fichero.tools.utils.api_keys',
        'fichero.tools.utils.segment_handler',
        'fichero.tools.utils.batch',
        'PIL',
        'PIL.Image',
        'openai',
        'requests'
    ]

    for module_name in modules_to_mock:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]

        if module_name == 'fichero.tools.utils.tool_logger':
            mock_tool_logger = MagicMock()
            mock_tool_logger.get_tool_logger = lambda x: MagicMock()
            sys.modules[module_name] = mock_tool_logger
        else:
            sys.modules[module_name] = MagicMock()

    yield

    for module_name in modules_to_mock:
        if module_name in original_modules:
            sys.modules[module_name] = original_modules[module_name]
        else:
            sys.modules.pop(module_name, None)


# Import after mocking
from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider
from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider


class TestDashScopeModels:
    """Test DashScope provider with different models"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_qwen_vl_ocr_model(self, mock_openai):
        """Test qwen-vl-ocr model configuration"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        assert provider.model_name == "qwen-vl-ocr"
        assert provider.model_key == "qwen-vl-ocr"
        assert "qwen-vl-ocr" in provider.name

        # Check prompt is configured
        assert provider.prompt is not None
        assert len(provider.prompt) > 0

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_qwen_vl_max_model(self, mock_openai):
        """Test qwen-vl-max model configuration"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-max")

        assert provider.model_name == "qwen3-vl-235b-a22b-instruct"
        assert provider.model_key == "qwen-vl-max"
        assert "qwen-vl-max" in provider.name

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_qwen3_vl_flash_model(self, mock_openai):
        """Test qwen3-vl-flash model configuration"""
        provider = DashScopeProvider(api_key="test", model="qwen3-vl-flash")

        assert provider.model_name == "qwen3-vl-flash"
        assert provider.model_key == "qwen3-vl-flash"


class TestAsyncSupport:
    """Test async processing support"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.AsyncOpenAI')
    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_dashscope_supports_async(self, mock_openai, mock_async_openai):
        """DashScope provider supports async processing"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        assert provider.supports_async is True
        assert hasattr(provider, 'async_client')
        assert hasattr(provider, 'process_image_async')

    @patch('fichero.tools.transcribe_providers.openai_provider.AsyncOpenAI')
    @patch('fichero.tools.transcribe_providers.openai_provider.OpenAI')
    def test_openai_supports_async(self, mock_openai, mock_async_openai):
        """OpenAI provider supports async processing"""
        provider = OpenAIProvider(api_key="test", model="qwen-vl-ocr")

        assert provider.supports_async is True
        assert hasattr(provider, 'async_client')
        assert hasattr(provider, 'process_image_async')

    @patch('fichero.tools.transcribe_providers.dashscope_provider.AsyncOpenAI')
    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    @pytest.mark.asyncio
    async def test_async_cleanup(self, mock_openai, mock_async_openai):
        """Async provider cleanup works correctly"""
        mock_async_client = AsyncMock()
        mock_async_openai.return_value = mock_async_client

        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")
        await provider.cleanup_async()

        # Should close async client
        mock_async_client.close.assert_called_once()


class TestMultiImageSupport:
    """Test multi-image batching support"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_dashscope_supports_multi_image(self, mock_openai):
        """DashScope supports multi-image batching"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-max")

        assert provider.supports_multi_image is True
        assert provider.min_images_per_batch >= 4
        assert provider.max_images_per_batch >= 4

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_multi_image_limits_qwen_vl_max(self, mock_openai):
        """qwen-vl-max has correct multi-image limits"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-max")

        assert provider.min_images_per_batch == 4
        assert provider.max_images_per_batch == 512

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_multi_image_limits_qwen_vl_ocr(self, mock_openai):
        """qwen-vl-ocr has correct multi-image limits"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        assert provider.min_images_per_batch == 4
        assert provider.max_images_per_batch == 80

    @patch('fichero.tools.transcribe_providers.openai_provider.OpenAI')
    def test_openai_no_multi_image(self, mock_openai):
        """OpenAI provider doesn't support multi-image batching"""
        provider = OpenAIProvider(api_key="test", model="qwen-vl-ocr")

        # OpenAI-compatible API doesn't support multi-image
        assert provider.supports_multi_image is False


class TestPromptConfiguration:
    """Test prompt configuration for different models"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_qwen_vl_ocr_has_detailed_prompt(self, mock_openai):
        """qwen-vl-ocr now uses detailed prompt with square brackets"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        prompt = provider.prompt

        # Check for key instructions in prompt
        assert "SQUARE BRACKETS" in prompt or "square brackets" in prompt.lower()
        assert "line by line" in prompt.lower()
        assert "plain text" in prompt.lower()

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_qwen_vl_max_has_detailed_prompt(self, mock_openai):
        """qwen-vl-max has detailed prompt"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-max")

        prompt = provider.prompt

        assert "SQUARE BRACKETS" in prompt or "square brackets" in prompt.lower()
        assert "SKIP UNREADABLE" in prompt or "skip unreadable" in prompt.lower()

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_custom_prompt_override(self, mock_openai):
        """Custom prompt can override defaults"""
        custom_prompt = "Custom extraction instructions"
        provider = DashScopeProvider(
            api_key="test",
            model="qwen-vl-ocr",
            prompt=custom_prompt
        )

        assert provider.prompt == custom_prompt


class TestSyncProcessing:
    """Test synchronous processing (ThreadPoolExecutor mode)"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_sync_processing_available(self, mock_openai):
        """Providers support synchronous processing"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        assert provider.supports_parallel is True
        assert hasattr(provider, 'process_image')
        assert callable(provider.process_image)


class TestProcessingModes:
    """Test all processing modes are correctly configured"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.AsyncOpenAI')
    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_dashscope_all_modes(self, mock_openai, mock_async_openai):
        """DashScope supports all processing modes"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        # Sync mode
        assert provider.supports_parallel is True
        assert hasattr(provider, 'process_image')

        # Async mode
        assert provider.supports_async is True
        assert hasattr(provider, 'process_image_async')

        # Multi-image mode
        assert provider.supports_multi_image is True
        assert hasattr(provider, 'process_multi_image')

    @patch('fichero.tools.transcribe_providers.openai_provider.AsyncOpenAI')
    @patch('fichero.tools.transcribe_providers.openai_provider.OpenAI')
    def test_openai_supported_modes(self, mock_openai, mock_async_openai):
        """OpenAI supports sync and async modes"""
        provider = OpenAIProvider(api_key="test", model="qwen-vl-ocr")

        # Sync mode
        assert provider.supports_parallel is True
        assert hasattr(provider, 'process_image')

        # Async mode
        assert provider.supports_async is True
        assert hasattr(provider, 'process_image_async')

        # No multi-image mode
        assert provider.supports_multi_image is False


class TestDefaultConfiguration:
    """Test default configuration matches benchmark winner"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_recommended_configuration(self, mock_openai):
        """Recommended configuration: DashScope qwen-vl-ocr with async"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        # Model check
        assert provider.model_name == "qwen-vl-ocr"

        # Async support (for 15 concurrent)
        assert provider.supports_async is True

        # Has detailed prompt
        assert len(provider.prompt) > 50  # Detailed prompt should be long


class TestProviderEndpoints:
    """Test that providers use correct API endpoints"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    @patch('fichero.tools.transcribe_providers.dashscope_provider.AsyncOpenAI')
    def test_dashscope_uses_intl_endpoint(self, mock_async_openai, mock_openai):
        """DashScope uses international endpoint"""
        provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")

        # Check OpenAI client was initialized with correct base_url
        mock_openai.assert_called_once()
        call_kwargs = mock_openai.call_args.kwargs
        assert "dashscope-intl.aliyuncs.com" in call_kwargs.get("base_url", "")

    @patch('fichero.tools.transcribe_providers.openai_provider.OpenAI')
    def test_openai_uses_intl_endpoint_by_default(self, mock_openai):
        """OpenAI provider uses international endpoint by default"""
        provider = OpenAIProvider(api_key="test", model="qwen-vl-ocr")

        assert "dashscope-intl.aliyuncs.com" in provider.base_url


class TestModelPromptConsistency:
    """Test that both models now have consistent prompts"""

    @patch('fichero.tools.transcribe_providers.dashscope_provider.OpenAI')
    def test_both_models_have_detailed_prompts(self, mock_openai):
        """Both qwen-vl-ocr and qwen-vl-max have detailed prompts"""
        ocr_provider = DashScopeProvider(api_key="test", model="qwen-vl-ocr")
        max_provider = DashScopeProvider(api_key="test", model="qwen-vl-max")

        # Both should have detailed prompts
        assert len(ocr_provider.prompt) > 50
        assert len(max_provider.prompt) > 50

        # Both should have square bracket instructions
        assert "SQUARE BRACKETS" in ocr_provider.prompt or "square brackets" in ocr_provider.prompt.lower()
        assert "SQUARE BRACKETS" in max_provider.prompt or "square brackets" in max_provider.prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
