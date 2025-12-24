"""
Comprehensive unit tests for LLM provider backends.

Tests all AI provider integrations including:
- Cloud providers: OpenAI, Claude, DashScope/Qwen, HuggingFace, DeepSeek, Groq, Together
- Local providers: Ollama, LM Studio, vLLM, llama.cpp, LocalAI
- On-device: Apple Vision (macOS/iOS OCR)
- API key resolution and fallback hierarchy
- Configuration-based backend creation
- Retry utilities and rate limiting
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import os
import asyncio
import platform


class TestProviderBaseURLs:
    """Test PROVIDER_BASE_URLS configuration"""

    def test_all_cloud_providers_have_urls(self):
        """Verify all cloud providers have base URLs defined"""
        from fichero.tools.utils.llm_utils import PROVIDER_BASE_URLS

        cloud_providers = ['openai', 'dashscope', 'deepseek', 'groq', 'together', 'huggingface']
        for provider in cloud_providers:
            assert provider in PROVIDER_BASE_URLS, f"Missing URL for {provider}"
            assert PROVIDER_BASE_URLS[provider].startswith('https://'), f"{provider} should use HTTPS"

    def test_all_local_providers_have_urls(self):
        """Verify all local providers have base URLs defined"""
        from fichero.tools.utils.llm_utils import PROVIDER_BASE_URLS

        local_providers = ['ollama', 'lmstudio']
        for provider in local_providers:
            assert provider in PROVIDER_BASE_URLS, f"Missing URL for {provider}"
            assert 'localhost' in PROVIDER_BASE_URLS[provider], f"{provider} should use localhost"

    def test_provider_urls_have_correct_format(self):
        """Verify provider URLs have correct format"""
        from fichero.tools.utils.llm_utils import PROVIDER_BASE_URLS

        for provider, url in PROVIDER_BASE_URLS.items():
            # Should not end with trailing slash
            assert not url.endswith('/'), f"{provider} URL should not end with /"
            # Should be a valid URL format
            assert '://' in url, f"{provider} URL should have protocol"


class TestOpenAICompatibleBackend:
    """Test the base OpenAI-compatible backend"""

    def test_initialization_with_defaults(self):
        """Test backend initializes with default values"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(model_name='test-model')

        assert backend.model_name == 'test-model'
        assert backend.temperature == 0.0
        assert backend.max_tokens == 3072
        assert backend.client is not None
        assert backend.async_client is not None

    def test_initialization_with_custom_values(self):
        """Test backend initializes with custom values"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(
            model_name='custom-model',
            api_key='test-key',
            base_url='https://custom.api.com/v1',
            temperature=0.7,
            max_tokens=2048,
            timeout=60.0
        )

        assert backend.model_name == 'custom-model'
        assert backend.api_key == 'test-key'
        assert backend.base_url == 'https://custom.api.com/v1'
        assert backend.temperature == 0.7
        assert backend.max_tokens == 2048
        assert backend.timeout == 60.0

    def test_provider_type_is_openai(self):
        """Test default provider type"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(model_name='test')
        assert backend.provider_type == 'openai'

    def test_cleanup_does_not_raise(self):
        """Test cleanup method doesn't raise exceptions"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(model_name='test')
        # Should not raise
        backend.cleanup()


class TestChatGPTBackend:
    """Test OpenAI/ChatGPT backend"""

    def test_initialization_uses_openai_key(self):
        """Test ChatGPT backend uses OpenAI API key"""
        from fichero.tools.utils.llm_utils import ChatGPTBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-test-key'}):
            backend = ChatGPTBackend(model_name='gpt-4')

        assert backend.provider_type == 'openai'
        assert backend.base_url is None  # Uses default OpenAI URL

    def test_inherits_from_openai_compatible(self):
        """Test ChatGPT backend inherits from OpenAICompatibleBackend"""
        from fichero.tools.utils.llm_utils import ChatGPTBackend, OpenAICompatibleBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            backend = ChatGPTBackend(model_name='gpt-4')

        assert isinstance(backend, OpenAICompatibleBackend)

    def test_accepts_custom_api_key(self):
        """Test ChatGPT backend accepts custom API key"""
        from fichero.tools.utils.llm_utils import ChatGPTBackend

        backend = ChatGPTBackend(model_name='gpt-4', api_key='custom-key')
        assert backend.api_key == 'custom-key'


class TestQwenBackend:
    """Test DashScope/Qwen backend"""

    def test_uses_dashscope_url(self):
        """Test Qwen backend uses DashScope URL"""
        from fichero.tools.utils.llm_utils import QwenBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            backend = QwenBackend(model_name='qwen-max')

        assert backend.base_url == PROVIDER_BASE_URLS['dashscope']
        assert backend.provider_type == 'dashscope'

    def test_uses_dashscope_api_key(self):
        """Test Qwen backend uses DASHSCOPE_API_KEY"""
        from fichero.tools.utils.llm_utils import QwenBackend

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'sk-dash-test'}):
            backend = QwenBackend(model_name='qwen-max')

        assert backend.api_key == 'sk-dash-test'


class TestOllamaBackend:
    """Test Ollama local backend"""

    def test_uses_local_url(self):
        """Test Ollama uses localhost URL"""
        from fichero.tools.utils.llm_utils import OllamaBackend

        backend = OllamaBackend(model_name='mistral')

        assert 'localhost:11434' in backend.base_url
        assert '/v1' in backend.base_url

    def test_provider_type_is_local(self):
        """Test Ollama provider type is local"""
        from fichero.tools.utils.llm_utils import OllamaBackend

        backend = OllamaBackend(model_name='llama2')
        assert backend.provider_type == 'local'

    def test_no_api_key_needed(self):
        """Test Ollama doesn't require API key"""
        from fichero.tools.utils.llm_utils import OllamaBackend

        backend = OllamaBackend(model_name='mistral')
        assert backend.api_key == 'not-needed'

    def test_custom_url(self):
        """Test Ollama with custom URL"""
        from fichero.tools.utils.llm_utils import OllamaBackend

        backend = OllamaBackend(model_name='mistral', api_url='http://192.168.1.100:11434')
        assert '192.168.1.100:11434' in backend.base_url


class TestLMStudioBackend:
    """Test LM Studio local backend"""

    def test_uses_local_url(self):
        """Test LM Studio uses localhost URL"""
        from fichero.tools.utils.llm_utils import LMStudioBackend

        backend = LMStudioBackend(model_name='local-model')

        assert 'localhost:1234' in backend.base_url
        assert '/v1' in backend.base_url

    def test_provider_type_is_local(self):
        """Test LM Studio provider type is local"""
        from fichero.tools.utils.llm_utils import LMStudioBackend

        backend = LMStudioBackend(model_name='test')
        assert backend.provider_type == 'local'

    def test_no_api_key_needed(self):
        """Test LM Studio doesn't require API key"""
        from fichero.tools.utils.llm_utils import LMStudioBackend

        backend = LMStudioBackend(model_name='test')
        assert backend.api_key == 'not-needed'

    def test_custom_url(self):
        """Test LM Studio with custom URL"""
        from fichero.tools.utils.llm_utils import LMStudioBackend

        backend = LMStudioBackend(model_name='test', api_url='http://localhost:5000')
        assert 'localhost:5000' in backend.base_url


class TestHuggingFaceBackend:
    """Test HuggingFace Inference backend"""

    def test_uses_huggingface_url(self):
        """Test HuggingFace uses correct URL"""
        from fichero.tools.utils.llm_utils import HuggingFaceBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = HuggingFaceBackend(model_name='meta-llama/Llama-2-7b')

        assert backend.base_url == PROVIDER_BASE_URLS['huggingface']

    def test_provider_type_is_huggingface(self):
        """Test HuggingFace provider type"""
        from fichero.tools.utils.llm_utils import HuggingFaceBackend

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = HuggingFaceBackend(model_name='test')

        assert backend.provider_type == 'huggingface'

    def test_uses_huggingface_token(self):
        """Test HuggingFace uses HUGGINGFACE_TOKEN"""
        from fichero.tools.utils.llm_utils import HuggingFaceBackend

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_mytoken123'}):
            backend = HuggingFaceBackend(model_name='test')

        assert backend.api_key == 'hf_mytoken123'

    def test_custom_endpoint_url(self):
        """Test HuggingFace with custom inference endpoint"""
        from fichero.tools.utils.llm_utils import HuggingFaceBackend

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = HuggingFaceBackend(
                model_name='custom-model',
                base_url='https://my-endpoint.endpoints.huggingface.cloud/v1'
            )

        assert backend.base_url == 'https://my-endpoint.endpoints.huggingface.cloud/v1'


class TestDeepSeekBackend:
    """Test DeepSeek backend"""

    def test_uses_deepseek_url(self):
        """Test DeepSeek uses correct URL"""
        from fichero.tools.utils.llm_utils import DeepSeekBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-test'}):
            backend = DeepSeekBackend(model_name='deepseek-chat')

        assert backend.base_url == PROVIDER_BASE_URLS['deepseek']

    def test_provider_type_is_deepseek(self):
        """Test DeepSeek provider type"""
        from fichero.tools.utils.llm_utils import DeepSeekBackend

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test'}):
            backend = DeepSeekBackend()

        assert backend.provider_type == 'deepseek'

    def test_default_model(self):
        """Test DeepSeek has default model"""
        from fichero.tools.utils.llm_utils import DeepSeekBackend

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test'}):
            backend = DeepSeekBackend()

        assert backend.model_name == 'deepseek-chat'

    def test_uses_deepseek_api_key(self):
        """Test DeepSeek uses DEEPSEEK_API_KEY"""
        from fichero.tools.utils.llm_utils import DeepSeekBackend

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-deep-123'}):
            backend = DeepSeekBackend()

        assert backend.api_key == 'sk-deep-123'


class TestGroqBackend:
    """Test Groq backend"""

    def test_uses_groq_url(self):
        """Test Groq uses correct URL"""
        from fichero.tools.utils.llm_utils import GroqBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk_test'}):
            backend = GroqBackend(model_name='llama-3.1-70b-versatile')

        assert backend.base_url == PROVIDER_BASE_URLS['groq']

    def test_provider_type_is_groq(self):
        """Test Groq provider type"""
        from fichero.tools.utils.llm_utils import GroqBackend

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test'}):
            backend = GroqBackend()

        assert backend.provider_type == 'groq'

    def test_default_model(self):
        """Test Groq has default model"""
        from fichero.tools.utils.llm_utils import GroqBackend

        with patch.dict('os.environ', {'GROQ_API_KEY': 'test'}):
            backend = GroqBackend()

        assert backend.model_name == 'llama-3.1-70b-versatile'

    def test_uses_groq_api_key(self):
        """Test Groq uses GROQ_API_KEY"""
        from fichero.tools.utils.llm_utils import GroqBackend

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk_mykey123'}):
            backend = GroqBackend()

        assert backend.api_key == 'gsk_mykey123'


class TestTogetherBackend:
    """Test Together AI backend"""

    def test_uses_together_url(self):
        """Test Together uses correct URL"""
        from fichero.tools.utils.llm_utils import TogetherBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'test-key'}):
            backend = TogetherBackend(model_name='meta-llama/Llama-3-70b')

        assert backend.base_url == PROVIDER_BASE_URLS['together']

    def test_provider_type_is_together(self):
        """Test Together provider type"""
        from fichero.tools.utils.llm_utils import TogetherBackend

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'test'}):
            backend = TogetherBackend()

        assert backend.provider_type == 'together'

    def test_default_model(self):
        """Test Together has default model"""
        from fichero.tools.utils.llm_utils import TogetherBackend

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'test'}):
            backend = TogetherBackend()

        assert 'llama' in backend.model_name.lower()

    def test_uses_together_api_key(self):
        """Test Together uses TOGETHER_API_KEY"""
        from fichero.tools.utils.llm_utils import TogetherBackend

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'together_key_123'}):
            backend = TogetherBackend()

        assert backend.api_key == 'together_key_123'


class TestClaudeBackend:
    """Test Anthropic Claude backend"""

    def test_uses_anthropic_sdk(self):
        """Test Claude uses Anthropic SDK, not OpenAI-compatible"""
        from fichero.tools.utils.llm_utils import ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'sk-ant-test'}):
                backend = ClaudeBackend(model_name='claude-3-opus')

            assert backend.provider_type == 'anthropic'
            assert hasattr(backend, 'client')

    def test_provider_type_is_anthropic(self):
        """Test Claude provider type"""
        from fichero.tools.utils.llm_utils import ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
                backend = ClaudeBackend(model_name='claude-3-sonnet')

            assert backend.provider_type == 'anthropic'

    def test_raises_without_anthropic_package(self):
        """Test Claude raises if anthropic package not installed"""
        from fichero.tools.utils.llm_utils import ANTHROPIC_AVAILABLE

        if not ANTHROPIC_AVAILABLE:
            from fichero.tools.utils.llm_utils import ClaudeBackend
            with pytest.raises(ImportError):
                ClaudeBackend(model_name='claude-3-opus')


class TestGetLLMBackendFromConfig:
    """Test configuration-based backend creation"""

    def test_creates_openai_backend(self):
        """Test creating OpenAI backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ChatGPTBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'openai', 'model': 'gpt-4'}
            })

        assert isinstance(backend, ChatGPTBackend)

    def test_creates_chatgpt_backend(self):
        """Test 'chatgpt' alias works"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ChatGPTBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'chatgpt', 'model': 'gpt-4'}
            })

        assert isinstance(backend, ChatGPTBackend)

    def test_creates_qwen_backend(self):
        """Test creating Qwen backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, QwenBackend

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'qwen', 'model': 'qwen-max'}
            })

        assert isinstance(backend, QwenBackend)

    def test_creates_dashscope_backend(self):
        """Test 'dashscope' alias works"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, QwenBackend

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'dashscope', 'model': 'qwen-plus'}
            })

        assert isinstance(backend, QwenBackend)

    def test_creates_ollama_backend(self):
        """Test creating Ollama backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OllamaBackend

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'ollama', 'model': 'mistral'}
        })

        assert isinstance(backend, OllamaBackend)

    def test_creates_lmstudio_backend(self):
        """Test creating LM Studio backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, LMStudioBackend

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'lmstudio', 'model': 'local-model'}
        })

        assert isinstance(backend, LMStudioBackend)

    def test_creates_huggingface_backend(self):
        """Test creating HuggingFace backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, HuggingFaceBackend

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'huggingface', 'model': 'mistralai/Mistral-7B'}
            })

        assert isinstance(backend, HuggingFaceBackend)

    def test_creates_deepseek_backend(self):
        """Test creating DeepSeek backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, DeepSeekBackend

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'deepseek', 'model': 'deepseek-coder'}
            })

        assert isinstance(backend, DeepSeekBackend)

    def test_creates_groq_backend(self):
        """Test creating Groq backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, GroqBackend

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk_test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'groq', 'model': 'mixtral-8x7b'}
            })

        assert isinstance(backend, GroqBackend)

    def test_creates_together_backend(self):
        """Test creating Together backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, TogetherBackend

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'test'}):
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'together', 'model': 'meta-llama/Llama-3-8b'}
            })

        assert isinstance(backend, TogetherBackend)

    def test_creates_claude_backend(self):
        """Test creating Claude backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
                backend = get_llm_backend_from_config({
                    'llm': {'backend': 'claude', 'model': 'claude-3-opus'}
                })

            assert isinstance(backend, ClaudeBackend)

    def test_creates_anthropic_backend(self):
        """Test 'anthropic' alias works"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
                backend = get_llm_backend_from_config({
                    'llm': {'backend': 'anthropic', 'model': 'claude-3-sonnet'}
                })

            assert isinstance(backend, ClaudeBackend)

    def test_creates_vllm_backend(self):
        """Test creating vLLM local backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OpenAICompatibleBackend

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'vllm', 'model': 'local-model'}
        })

        assert isinstance(backend, OpenAICompatibleBackend)
        assert 'localhost:8000' in backend.base_url

    def test_creates_llamacpp_backend(self):
        """Test creating llama.cpp server backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OpenAICompatibleBackend

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'llamacpp', 'model': 'local-model'}
        })

        assert isinstance(backend, OpenAICompatibleBackend)
        assert 'localhost:8080' in backend.base_url

    def test_creates_localai_backend(self):
        """Test creating LocalAI backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OpenAICompatibleBackend

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'localai', 'model': 'gpt4all-j'}
        })

        assert isinstance(backend, OpenAICompatibleBackend)
        assert 'localhost:8080' in backend.base_url

    def test_creates_generic_backend(self):
        """Test creating generic OpenAI-compatible backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OpenAICompatibleBackend

        backend = get_llm_backend_from_config({
            'llm': {
                'backend': 'generic',
                'model': 'custom-model',
                'base_url': 'https://custom-api.example.com/v1',
                'api_key': 'test-key'
            }
        })

        assert isinstance(backend, OpenAICompatibleBackend)
        assert backend.base_url == 'https://custom-api.example.com/v1'

    def test_raises_for_unknown_backend(self):
        """Test raises error for unknown backend type"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config

        with pytest.raises(ValueError, match="Unsupported backend type"):
            get_llm_backend_from_config({
                'llm': {'backend': 'unknown_provider', 'model': 'test'}
            })

    def test_uses_temperature_from_config(self):
        """Test temperature is passed from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'ollama', 'model': 'mistral', 'temperature': 0.8}
        })

        assert backend.temperature == 0.8

    def test_uses_max_tokens_from_config(self):
        """Test max_tokens is passed from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config

        backend = get_llm_backend_from_config({
            'llm': {'backend': 'ollama', 'model': 'mistral', 'max_tokens': 4096}
        })

        assert backend.max_tokens == 4096

    def test_uses_custom_api_url_for_local_backends(self):
        """Test custom api_url is used for local backends"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config

        backend = get_llm_backend_from_config({
            'llm': {
                'backend': 'ollama',
                'model': 'mistral',
                'api_url': 'http://192.168.1.100:11434'
            }
        })

        assert '192.168.1.100:11434' in backend.base_url

    def test_handles_direct_llm_config_without_wrapper(self):
        """Test that direct LLM config (without 'llm' wrapper) is handled correctly.

        This is crucial for step-specific LLM configs where the step['llm'] is
        passed directly to get_llm_backend_from_config, e.g.:
        step = {"llm": {"backend": "openai", "model": "gpt-4"}}
        get_llm_backend_from_config(step['llm'])  # Direct config, no wrapper
        """
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ChatGPTBackend

        # Test direct config (what step['llm'] returns)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            direct_config = {'backend': 'openai', 'model': 'gpt-4.1'}
            backend = get_llm_backend_from_config(direct_config)

        assert isinstance(backend, ChatGPTBackend)
        assert backend.model_name == 'gpt-4.1'

    def test_handles_wrapped_llm_config(self):
        """Test that wrapped LLM config (with 'llm' key) is still handled correctly."""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ChatGPTBackend

        # Test wrapped config (typical top-level config format)
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            wrapped_config = {'llm': {'backend': 'openai', 'model': 'gpt-4'}}
            backend = get_llm_backend_from_config(wrapped_config)

        assert isinstance(backend, ChatGPTBackend)
        assert backend.model_name == 'gpt-4'

    def test_direct_config_uses_correct_model_not_default(self):
        """Test that direct config doesn't fall back to default 'mistral' model.

        This was a bug where step-specific LLM configs would always use 'mistral'
        because the config was not being parsed correctly.
        """
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config

        # This direct config should use 'gpt-4.1', NOT 'mistral'
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test'}):
            direct_config = {'backend': 'openai', 'model': 'gpt-4.1', 'temperature': 0.0}
            backend = get_llm_backend_from_config(direct_config)

        assert backend.model_name == 'gpt-4.1', f"Expected 'gpt-4.1' but got '{backend.model_name}'"
        assert backend.model_name != 'mistral', "Should not fall back to default 'mistral'"


class TestAPIKeyResolution:
    """Test API key resolution and fallback hierarchy"""

    def test_get_api_key_from_environment(self):
        """Test API key resolution from environment variables"""
        from fichero.tools.utils.api_keys import get_api_key

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'env-key'}):
            key = get_api_key('openai')

        assert key == 'env-key'

    def test_get_api_key_cli_override(self):
        """Test CLI argument overrides environment"""
        from fichero.tools.utils.api_keys import get_api_key

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'env-key'}):
            key = get_api_key('openai', cli_arg='cli-key')

        assert key == 'cli-key'

    def test_get_openai_key(self):
        """Test get_openai_key convenience function"""
        from fichero.tools.utils.api_keys import get_openai_key

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'openai-key'}):
            key = get_openai_key()

        assert key == 'openai-key'

    def test_get_qwen_key(self):
        """Test get_qwen_key convenience function"""
        from fichero.tools.utils.api_keys import get_qwen_key

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'qwen-key'}):
            key = get_qwen_key()

        assert key == 'qwen-key'

    def test_get_claude_key(self):
        """Test get_claude_key convenience function"""
        from fichero.tools.utils.api_keys import get_claude_key

        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'claude-key'}):
            key = get_claude_key()

        assert key == 'claude-key'

    def test_get_huggingface_token(self):
        """Test get_huggingface_token convenience function"""
        from fichero.tools.utils.api_keys import get_huggingface_token

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf-token'}):
            key = get_huggingface_token()

        assert key == 'hf-token'

    def test_ensure_api_key_raises_when_missing(self):
        """Test ensure_api_key raises when key not found"""
        from fichero.tools.utils.api_keys import ensure_api_key

        with patch.dict('os.environ', {}, clear=True):
            with pytest.raises(ValueError, match="API key for unknown_provider is required"):
                ensure_api_key('unknown_provider')

    def test_ensure_api_key_returns_key_when_found(self):
        """Test ensure_api_key returns key when found"""
        from fichero.tools.utils.api_keys import ensure_api_key

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'found-key'}):
            key = ensure_api_key('openai')

        assert key == 'found-key'

    def test_env_var_mapping_complete(self):
        """Test all providers have environment variable mappings"""
        from fichero.tools.utils.api_keys import get_api_key

        providers = ['openai', 'qwen', 'claude', 'huggingface', 'deepseek', 'groq', 'together']

        for provider in providers:
            # Should not raise, even if key not found
            with patch.dict('os.environ', {}, clear=True):
                # Just verify it doesn't crash - returns None if not found
                result = get_api_key(provider)
                # Result should be None since env vars not set
                assert result is None or isinstance(result, str)


class TestChunkTextIntelligently:
    """Test intelligent text chunking"""

    def test_chunk_text_basic(self):
        """Test basic text chunking"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text_intelligently(text, max_tokens=10, overlap=0)

        assert len(chunks) > 0
        for chunk in chunks:
            assert 'text' in chunk
            assert 'tokens' in chunk

    def test_chunk_text_empty_input(self):
        """Test chunking with empty input"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        chunks = chunk_text_intelligently("")
        assert chunks == []

    def test_chunk_text_whitespace_only(self):
        """Test chunking with whitespace only"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        chunks = chunk_text_intelligently("   \n\n   ")
        assert chunks == []

    def test_chunk_text_with_overlap(self):
        """Test chunking with overlap"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        text = "Para one here.\n\nPara two here.\n\nPara three here."
        chunks = chunk_text_intelligently(text, max_tokens=5, overlap=2)

        # With overlap, later chunks should contain content from previous
        assert len(chunks) > 0

    def test_chunk_text_preserves_content(self):
        """Test all content is preserved in chunks"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = chunk_text_intelligently(text, max_tokens=100, overlap=0)

        # Combine all chunk text
        combined = '\n\n'.join(c['text'] for c in chunks)
        assert 'First paragraph' in combined
        assert 'Second paragraph' in combined
        assert 'Third paragraph' in combined


class TestReadTextFile:
    """Test text file reading with encoding fallbacks"""

    def test_read_text_file_utf8(self, tmp_path):
        """Test reading UTF-8 file"""
        from fichero.tools.utils.llm_utils import read_text_file

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!", encoding='utf-8')

        content = read_text_file(test_file)
        assert content == "Hello, World!"

    def test_read_text_file_nonexistent(self, tmp_path):
        """Test reading nonexistent file"""
        from fichero.tools.utils.llm_utils import read_text_file

        nonexistent = tmp_path / "nonexistent.txt"
        content = read_text_file(nonexistent)
        assert content == ""

    def test_read_text_file_with_unicode(self, tmp_path):
        """Test reading file with unicode characters"""
        from fichero.tools.utils.llm_utils import read_text_file

        test_file = tmp_path / "unicode.txt"
        test_file.write_text("Caf\u00e9 \u4e2d\u6587 \U0001f600", encoding='utf-8')

        content = read_text_file(test_file)
        assert "Caf\u00e9" in content
        assert "\u4e2d\u6587" in content


class TestDefaultMaxTokens:
    """Test DEFAULT_MAX_TOKENS configuration"""

    def test_default_max_tokens_value(self):
        """Test DEFAULT_MAX_TOKENS is set correctly"""
        from fichero.tools.utils.llm_utils import DEFAULT_MAX_TOKENS

        assert DEFAULT_MAX_TOKENS == 3072

    def test_backends_use_default_max_tokens(self):
        """Test backends use DEFAULT_MAX_TOKENS when not specified"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend, DEFAULT_MAX_TOKENS

        backend = OpenAICompatibleBackend(model_name='test')
        assert backend.max_tokens == DEFAULT_MAX_TOKENS


class TestMaxOutputTokens:
    """Test MAX_OUTPUT_TOKENS constant"""

    def test_max_output_tokens_value(self):
        """Test MAX_OUTPUT_TOKENS is set correctly"""
        from fichero.tools.utils.llm_utils import MAX_OUTPUT_TOKENS

        assert MAX_OUTPUT_TOKENS == 4096

    def test_effective_max_tokens_capped(self):
        """Test effective max tokens is capped at MAX_OUTPUT_TOKENS"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend, MAX_OUTPUT_TOKENS

        # Create backend with max_tokens higher than MAX_OUTPUT_TOKENS
        backend = OpenAICompatibleBackend(model_name='test', max_tokens=10000)

        # Effective max should be capped
        effective = backend._get_effective_max_tokens()
        assert effective == MAX_OUTPUT_TOKENS

    def test_effective_max_tokens_not_capped_when_lower(self):
        """Test effective max tokens not capped when lower than MAX_OUTPUT_TOKENS"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(model_name='test', max_tokens=2048)
        effective = backend._get_effective_max_tokens()
        assert effective == 2048


class TestRetryUtilities:
    """Test retry decorator and async retry helper"""

    def test_with_retry_decorator_exists(self):
        """Test with_retry decorator is available"""
        from fichero.tools.utils.llm_utils import with_retry

        assert callable(with_retry)

    def test_with_retry_default_parameters(self):
        """Test with_retry has correct default parameters"""
        from fichero.tools.utils.llm_utils import DEFAULT_RETRY_COUNT, DEFAULT_RETRY_DELAY

        assert DEFAULT_RETRY_COUNT == 3
        assert DEFAULT_RETRY_DELAY == 1.0

    def test_with_retry_success_on_first_try(self):
        """Test with_retry returns immediately on success"""
        from fichero.tools.utils.llm_utils import with_retry

        call_count = 0

        @with_retry(max_retries=3, base_delay=0.01)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_func()
        assert result == "success"
        assert call_count == 1

    def test_with_retry_retries_on_failure(self):
        """Test with_retry retries on failure"""
        from fichero.tools.utils.llm_utils import with_retry

        call_count = 0

        @with_retry(max_retries=2, base_delay=0.01)
        def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"

        result = failing_then_success()
        assert result == "success"
        assert call_count == 2

    def test_with_retry_returns_empty_on_exhausted(self):
        """Test with_retry returns empty string when retries exhausted"""
        from fichero.tools.utils.llm_utils import with_retry

        @with_retry(max_retries=2, base_delay=0.01)
        def always_fails():
            raise Exception("Always fails")

        result = always_fails()
        assert result == ""

    def test_with_retry_async_exists(self):
        """Test with_retry_async helper is available"""
        from fichero.tools.utils.llm_utils import with_retry_async

        assert callable(with_retry_async)

    @pytest.mark.asyncio
    async def test_with_retry_async_success(self):
        """Test with_retry_async returns on success"""
        from fichero.tools.utils.llm_utils import with_retry_async

        async def successful_async():
            return "async success"

        result = await with_retry_async(successful_async, max_retries=3, base_delay=0.01)
        assert result == "async success"

    @pytest.mark.asyncio
    async def test_with_retry_async_retries(self):
        """Test with_retry_async retries on failure"""
        from fichero.tools.utils.llm_utils import with_retry_async

        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "eventual success"

        result = await with_retry_async(failing_then_success, max_retries=3, base_delay=0.01)
        assert result == "eventual success"
        assert call_count == 2


class TestAppleVisionBackend:
    """Test Apple Vision on-device OCR backend"""

    def test_apple_vision_available_constant_exists(self):
        """Test APPLE_VISION_AVAILABLE constant exists"""
        from fichero.tools.utils.llm_utils import APPLE_VISION_AVAILABLE

        assert isinstance(APPLE_VISION_AVAILABLE, bool)

    def test_apple_vision_available_on_darwin(self):
        """Test Apple Vision is available on macOS (Darwin)"""
        from fichero.tools.utils.llm_utils import APPLE_VISION_AVAILABLE

        if platform.system() == 'Darwin':
            # May still be False if rubicon-objc not installed
            assert isinstance(APPLE_VISION_AVAILABLE, bool)
        else:
            assert APPLE_VISION_AVAILABLE is False

    def test_apple_vision_backend_class_exists(self):
        """Test AppleVisionBackend class exists"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend

        assert AppleVisionBackend is not None

    def test_apple_vision_backend_provider_type(self):
        """Test AppleVisionBackend has correct provider type"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = AppleVisionBackend()
            assert backend.provider_type == 'apple'

    def test_apple_vision_backend_initialization(self):
        """Test AppleVisionBackend initialization"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = AppleVisionBackend(
                model_name='apple-vision',
                recognition_level='accurate'
            )
            assert backend.model_name == 'apple-vision'
            assert backend.recognition_level == 'accurate'

    def test_apple_vision_backend_fast_mode(self):
        """Test AppleVisionBackend fast recognition mode"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = AppleVisionBackend(recognition_level='fast')
            assert backend.recognition_level == 'fast'

    def test_apple_vision_raises_on_non_darwin(self):
        """Test AppleVisionBackend raises on non-Darwin systems"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if not APPLE_VISION_AVAILABLE:
            with pytest.raises(ImportError, match="Apple Vision framework not available"):
                AppleVisionBackend()

    def test_apple_vision_no_api_key_needed(self):
        """Test Apple Vision doesn't require API key"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            # Should not raise any API key errors
            backend = AppleVisionBackend()
            assert backend is not None

    def test_apple_vision_cleanup_does_not_raise(self):
        """Test Apple Vision cleanup doesn't raise"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = AppleVisionBackend()
            # Should not raise
            backend.cleanup()


class TestGetLLMBackendFromConfigApple:
    """Test Apple backend creation via configuration"""

    def test_creates_apple_backend(self):
        """Test creating Apple Vision backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'apple', 'model': 'apple-vision'}
            })
            assert isinstance(backend, AppleVisionBackend)

    def test_apple_backend_with_recognition_level(self):
        """Test Apple backend with recognition_level config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = get_llm_backend_from_config({
                'llm': {'backend': 'apple', 'recognition_level': 'fast'}
            })
            assert backend.recognition_level == 'fast'


class TestNewAPIKeyHelpers:
    """Test new API key helper functions"""

    def test_get_deepseek_key_exists(self):
        """Test get_deepseek_key function exists"""
        from fichero.tools.utils.api_keys import get_deepseek_key

        assert callable(get_deepseek_key)

    def test_get_deepseek_key_from_env(self):
        """Test get_deepseek_key reads from environment"""
        from fichero.tools.utils.api_keys import get_deepseek_key

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'sk-deepseek-123'}):
            key = get_deepseek_key()

        assert key == 'sk-deepseek-123'

    def test_get_deepseek_key_cli_override(self):
        """Test get_deepseek_key CLI override"""
        from fichero.tools.utils.api_keys import get_deepseek_key

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'env-key'}):
            key = get_deepseek_key(cli_arg='cli-key')

        assert key == 'cli-key'

    def test_get_groq_key_exists(self):
        """Test get_groq_key function exists"""
        from fichero.tools.utils.api_keys import get_groq_key

        assert callable(get_groq_key)

    def test_get_groq_key_from_env(self):
        """Test get_groq_key reads from environment"""
        from fichero.tools.utils.api_keys import get_groq_key

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk-groq-123'}):
            key = get_groq_key()

        assert key == 'gsk-groq-123'

    def test_get_groq_key_cli_override(self):
        """Test get_groq_key CLI override"""
        from fichero.tools.utils.api_keys import get_groq_key

        with patch.dict('os.environ', {'GROQ_API_KEY': 'env-key'}):
            key = get_groq_key(cli_arg='cli-key')

        assert key == 'cli-key'

    def test_get_together_key_exists(self):
        """Test get_together_key function exists"""
        from fichero.tools.utils.api_keys import get_together_key

        assert callable(get_together_key)

    def test_get_together_key_from_env(self):
        """Test get_together_key reads from environment"""
        from fichero.tools.utils.api_keys import get_together_key

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'together-key-123'}):
            key = get_together_key()

        assert key == 'together-key-123'

    def test_get_together_key_cli_override(self):
        """Test get_together_key CLI override"""
        from fichero.tools.utils.api_keys import get_together_key

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'env-key'}):
            key = get_together_key(cli_arg='cli-key')

        assert key == 'cli-key'


class TestSettingsConfiguration:
    """Test settings configuration parsing"""

    def test_default_settings_file_exists(self):
        """Test default.settings.yml file exists"""
        from pathlib import Path

        settings_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_defaults/settings/default.settings.yml'
        assert settings_path.exists(), f"Settings file not found at {settings_path}"

    def test_settings_schema_file_exists(self):
        """Test settings_schema.yml file exists"""
        from pathlib import Path

        schema_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_ui_schemas/settings_schema.yml'
        assert schema_path.exists(), f"Schema file not found at {schema_path}"

    def test_settings_has_ai_defaults(self):
        """Test settings file has ai_defaults section"""
        from pathlib import Path
        import yaml

        settings_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_defaults/settings/default.settings.yml'
        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        assert 'ai_defaults' in settings
        assert 'transcription' in settings['ai_defaults']
        assert 'llm' in settings['ai_defaults']
        assert 'describe' in settings['ai_defaults']

    def test_settings_has_global_ai_settings(self):
        """Test settings has global AI settings"""
        from pathlib import Path
        import yaml

        settings_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_defaults/settings/default.settings.yml'
        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        ai_defaults = settings['ai_defaults']
        assert 'temperature' in ai_defaults
        assert 'max_tokens' in ai_defaults
        assert 'timeout' in ai_defaults

    def test_settings_has_all_provider_rate_limits(self):
        """Test settings has rate limits for all providers"""
        from pathlib import Path
        import yaml

        settings_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_defaults/settings/default.settings.yml'
        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        rate_limits = settings['api_rate_limits']
        expected_providers = ['dashscope', 'openai', 'claude', 'deepseek', 'groq', 'together', 'huggingface']

        for provider in expected_providers:
            assert provider in rate_limits, f"Missing rate limits for {provider}"
            assert 'max_concurrent' in rate_limits[provider]
            assert 'retry_on_429' in rate_limits[provider]
            assert 'max_retries' in rate_limits[provider]

    def test_settings_has_all_api_servers(self):
        """Test settings has all API server configurations"""
        from pathlib import Path
        import yaml

        settings_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_defaults/settings/default.settings.yml'
        with open(settings_path) as f:
            settings = yaml.safe_load(f)

        api_servers = settings['api_servers']
        expected_providers = ['openai', 'qwen', 'claude', 'ollama', 'lmstudio', 'huggingface', 'deepseek', 'groq', 'together']

        for provider in expected_providers:
            assert provider in api_servers, f"Missing API server config for {provider}"


class TestTranslationStrings:
    """Test translation strings for AI provider settings"""

    def test_translations_file_exists(self):
        """Test English translations file exists"""
        from pathlib import Path

        po_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale/en/LC_MESSAGES/fichero.po'
        assert po_path.exists(), f"Translations file not found at {po_path}"

    def test_compiled_translations_file_exists(self):
        """Test compiled .mo file exists"""
        from pathlib import Path

        mo_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale/en/LC_MESSAGES/fichero.mo'
        assert mo_path.exists(), f"Compiled translations file not found at {mo_path}"

    def test_provider_option_translations_exist(self):
        """Test all provider options have translations"""
        from pathlib import Path

        po_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale/en/LC_MESSAGES/fichero.po'
        content = po_path.read_text()

        expected_options = [
            'option_dashscope',
            'option_qwen',
            'option_openai',
            'option_claude',
            'option_ollama',
            'option_lmstudio',
            'option_huggingface',
            'option_deepseek',
            'option_groq',
            'option_together',
            'option_apple'
        ]

        for option in expected_options:
            assert f'msgid "{option}"' in content, f"Missing translation for {option}"

    def test_ai_settings_translations_exist(self):
        """Test AI settings have translations"""
        from pathlib import Path

        po_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale/en/LC_MESSAGES/fichero.po'
        content = po_path.read_text()

        expected_msgids = [
            'preferences_temperature',
            'preferences_max_tokens',
            'preferences_timeout',
            'preferences_ai_global_title',
            'preferences_transcription_title',
            'preferences_llm_title',
            'preferences_describe_title'
        ]

        for msgid in expected_msgids:
            assert f'msgid "{msgid}"' in content, f"Missing translation for {msgid}"

    def test_settings_schema_all_translations_exist(self):
        """Test all translation keys in settings schema have translations"""
        from pathlib import Path
        from ruamel.yaml import YAML
        import gettext

        # Load schema
        schema_path = Path(__file__).parent.parent.parent / 'src/fichero/resources/config_ui_schemas/settings_schema.yml'
        yaml = YAML()
        with open(schema_path) as f:
            schema = yaml.load(f)

        # Load translations
        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        # Collect all translation keys from schema
        missing = []

        def check_translations(obj, path=''):
            if isinstance(obj, dict):
                for key in ['title', 'label', 'help', 'description']:
                    if key in obj:
                        val = obj[key]
                        if isinstance(val, str) and (val.startswith('preferences_') or val.startswith('option_')):
                            translated = _(val)
                            if translated == val:
                                missing.append(val)
                for k, v in obj.items():
                    check_translations(v, f'{path}.{k}')
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    check_translations(item, f'{path}[{i}]')

        check_translations(schema)

        assert len(missing) == 0, f"Missing translations: {missing}"

    def test_settings_tab_titles_translated(self):
        """Test all settings tab titles have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        tab_titles = [
            'preferences_defaults_title',
            'preferences_ai_providers_title',
            'preferences_api_keys_title',
            'preferences_ai_advanced_title',
            'preferences_performance_title',
            'preferences_library_title'
        ]

        for title in tab_titles:
            translated = _(title)
            assert translated != title, f"Tab title not translated: {title}"

    def test_api_key_provider_titles_translated(self):
        """Test all API key provider section titles have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        provider_titles = [
            'preferences_qwen_title',
            'preferences_openai_title',
            'preferences_claude_title',
            'preferences_deepseek_title',
            'preferences_groq_title',
            'preferences_together_title',
            'preferences_huggingface_title',
            'preferences_ollama_title',
            'preferences_lmstudio_title'
        ]

        for title in provider_titles:
            translated = _(title)
            assert translated != title, f"Provider title not translated: {title}"

    def test_common_field_labels_translated(self):
        """Test common field labels have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        common_labels = [
            'preferences_api_key',
            'preferences_base_url',
            'preferences_temperature',
            'preferences_max_tokens',
            'preferences_timeout',
            'preferences_max_concurrent',
            'preferences_max_retries'
        ]

        for label in common_labels:
            translated = _(label)
            assert translated != label, f"Common label not translated: {label}"

    def test_transcription_settings_translated(self):
        """Test transcription-related settings have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        transcription_keys = [
            'preferences_transcription_title',
            'preferences_transcription_provider',
            'preferences_transcription_model',
            'preferences_transcription_provider_help',
            'preferences_transcription_model_help'
        ]

        for key in transcription_keys:
            translated = _(key)
            assert translated != key, f"Transcription setting not translated: {key}"

    def test_llm_settings_translated(self):
        """Test LLM-related settings have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        llm_keys = [
            'preferences_llm_title',
            'preferences_llm_provider',
            'preferences_llm_model',
            'preferences_llm_provider_help',
            'preferences_llm_model_help'
        ]

        for key in llm_keys:
            translated = _(key)
            assert translated != key, f"LLM setting not translated: {key}"

    def test_describe_settings_translated(self):
        """Test describe/image description settings have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        describe_keys = [
            'preferences_describe_title',
            'preferences_describe_provider',
            'preferences_describe_model',
            'preferences_describe_provider_help',
            'preferences_describe_model_help'
        ]

        for key in describe_keys:
            translated = _(key)
            assert translated != key, f"Describe setting not translated: {key}"

    def test_performance_settings_translated(self):
        """Test performance-related settings have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        performance_keys = [
            'preferences_performance_title',
            'preferences_backend_title',
            'preferences_workers_title',
            'preferences_api_rate_limits_title',
            'preferences_global_max_concurrent',
            'preferences_cpu_workers'
        ]

        for key in performance_keys:
            translated = _(key)
            assert translated != key, f"Performance setting not translated: {key}"

    def test_library_settings_translated(self):
        """Test library-related settings have translations"""
        from pathlib import Path
        import gettext

        locale_dir = Path(__file__).parent.parent.parent / 'src/fichero/resources/locale'
        try:
            trans = gettext.translation('fichero', str(locale_dir), ['en'])
            _ = trans.gettext
        except:
            pytest.skip("Could not load translations")

        library_keys = [
            'preferences_library_title',
            'preferences_library_storage_title',
            'preferences_library_path',
            'preferences_processing_output_path',
            'preferences_collection_settings_title',
            'preferences_default_collection_type'
        ]

        for key in library_keys:
            translated = _(key)
            assert translated != key, f"Library setting not translated: {key}"


class TestGetLLMBackendAlias:
    """Test get_llm_backend alias function"""

    def test_get_llm_backend_exists(self):
        """Test get_llm_backend function exists"""
        from fichero.tools.utils.llm_utils import get_llm_backend

        assert callable(get_llm_backend)

    def test_get_llm_backend_is_alias(self):
        """Test get_llm_backend is alias for get_llm_backend_from_config"""
        from fichero.tools.utils.llm_utils import get_llm_backend, get_llm_backend_from_config

        assert get_llm_backend is get_llm_backend_from_config

    def test_get_llm_backend_creates_backend(self):
        """Test get_llm_backend creates backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend, OllamaBackend

        backend = get_llm_backend({
            'llm': {'backend': 'ollama', 'model': 'mistral'}
        })

        assert isinstance(backend, OllamaBackend)


class TestLoadPromptConfig:
    """Test load_prompt_config function"""

    def test_load_prompt_config_exists(self):
        """Test load_prompt_config function exists"""
        from fichero.tools.utils.llm_utils import load_prompt_config

        assert callable(load_prompt_config)

    def test_load_prompt_config_json_file(self, tmp_path):
        """Test loading JSON config file"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        import json

        config_file = tmp_path / "test_config.jsonl"
        config_data = {
            "name": "test_config",
            "description": "Test configuration",
            "llm": {"backend": "ollama", "model": "mistral"},
            "steps": [{"name": "step1", "prompt": "Test prompt"}]
        }
        config_file.write_text(json.dumps(config_data))

        loaded = load_prompt_config(config_file)

        assert loaded['name'] == 'test_config'
        assert loaded['llm']['backend'] == 'ollama'
        assert len(loaded['steps']) == 1

    def test_load_prompt_config_nonexistent_file(self, tmp_path):
        """Test loading nonexistent file returns empty dict"""
        from fichero.tools.utils.llm_utils import load_prompt_config

        nonexistent = tmp_path / "nonexistent.jsonl"
        loaded = load_prompt_config(nonexistent)

        assert loaded == {}

    def test_load_prompt_config_empty_file(self, tmp_path):
        """Test loading empty file returns empty dict"""
        from fichero.tools.utils.llm_utils import load_prompt_config

        empty_file = tmp_path / "empty.jsonl"
        empty_file.write_text("")

        loaded = load_prompt_config(empty_file)

        assert loaded == {}

    def test_load_prompt_config_pretty_printed_json(self, tmp_path):
        """Test loading pretty-printed (multi-line) JSON file"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        import json

        config_file = tmp_path / "pretty.jsonl"
        config_data = {
            "name": "pretty_config",
            "description": "Multi-line JSON",
            "llm": {
                "backend": "openai",
                "model": "gpt-4",
                "temperature": 0.1
            },
            "steps": [
                {"name": "step1", "prompt": "First step"},
                {"name": "step2", "prompt": "Second step"}
            ]
        }
        # Write with indentation (pretty-printed)
        config_file.write_text(json.dumps(config_data, indent=2))

        loaded = load_prompt_config(config_file)

        assert loaded['name'] == 'pretty_config'
        assert loaded['llm']['backend'] == 'openai'
        assert loaded['llm']['temperature'] == 0.1
        assert len(loaded['steps']) == 2
        assert loaded['steps'][0]['name'] == 'step1'
        assert loaded['steps'][1]['name'] == 'step2'

    def test_load_prompt_config_true_jsonl_format(self, tmp_path):
        """Test loading true JSONL format (one JSON per line)"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        import json

        config_file = tmp_path / "true_jsonl.jsonl"
        # Write multiple JSON objects, one per line (true JSONL)
        line1 = json.dumps({"name": "config1", "value": 1})
        line2 = json.dumps({"name": "config2", "value": 2})
        config_file.write_text(f"{line1}\n{line2}\n")

        loaded = load_prompt_config(config_file)

        # Should merge both objects, later overrides earlier
        assert loaded['name'] == 'config2'
        assert loaded['value'] == 2

    def test_load_prompt_config_single_line_jsonl(self, tmp_path):
        """Test loading single-line JSONL returns that object"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        import json

        config_file = tmp_path / "single.jsonl"
        config_data = {"name": "single", "steps": []}
        config_file.write_text(json.dumps(config_data))

        loaded = load_prompt_config(config_file)

        assert loaded['name'] == 'single'
        assert loaded['steps'] == []

    def test_load_prompt_config_catalogue_file(self):
        """Test loading actual Catalogue.jsonl file from resources"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        from pathlib import Path

        catalogue_path = Path(__file__).parent.parent.parent / "src" / "fichero" / "resources" / "config_defaults" / "prompts" / "Catalogue.jsonl"

        if catalogue_path.exists():
            loaded = load_prompt_config(catalogue_path)

            assert 'name' in loaded
            assert 'steps' in loaded
            assert 'llm' in loaded
            assert len(loaded['steps']) > 0
            assert loaded['llm'].get('backend') is not None

    def test_load_prompt_config_with_unicode(self, tmp_path):
        """Test loading config with Unicode characters (Spanish, etc.)"""
        from fichero.tools.utils.llm_utils import load_prompt_config
        import json

        config_file = tmp_path / "unicode.jsonl"
        config_data = {
            "name": "configuración_española",
            "description": "Descripción con acentos: áéíóú ñ",
            "steps": [{"name": "paso1", "prompt": "Analizar el documento histórico"}]
        }
        config_file.write_text(json.dumps(config_data, ensure_ascii=False, indent=2))

        loaded = load_prompt_config(config_file)

        assert loaded['name'] == 'configuración_española'
        assert 'áéíóú' in loaded['description']
        assert loaded['steps'][0]['prompt'] == 'Analizar el documento histórico'


class TestLLMProcessor:
    """Test LLMProcessor class"""

    def test_llm_processor_exists(self):
        """Test LLMProcessor class exists"""
        from fichero.tools.utils.llm_utils import LLMProcessor

        assert LLMProcessor is not None

    def test_llm_processor_initialization(self, tmp_path):
        """Test LLMProcessor initialization with valid params"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"
        output_folder.mkdir()

        prompt_config = {
            "name": "test",
            "steps": [{"name": "step1", "prompt": "Test"}]
        }
        llm = OllamaBackend(model_name='mistral')

        processor = LLMProcessor(
            input_folder=input_folder,
            output_folder=output_folder,
            prompt_config=prompt_config,
            llm=llm,
            max_tokens=1000
        )

        assert processor.input_folder == input_folder
        assert processor.output_folder == output_folder
        assert processor.prompt_config == prompt_config
        assert processor.llm == llm
        assert processor.max_tokens == 1000

    def test_llm_processor_creates_output_dirs(self, tmp_path):
        """Test LLMProcessor creates output subdirectories"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"

        prompt_config = {"name": "test", "steps": [{"name": "step1", "prompt": "Test"}]}
        llm = OllamaBackend(model_name='mistral')

        processor = LLMProcessor(
            input_folder=input_folder,
            output_folder=output_folder,
            prompt_config=prompt_config,
            llm=llm
        )

        assert (output_folder / "steps").exists()
        assert (output_folder / "chunks").exists()
        assert (output_folder / "documents").exists()

    def test_llm_processor_validates_input_folder(self, tmp_path):
        """Test LLMProcessor raises for nonexistent input folder"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        nonexistent = tmp_path / "nonexistent"
        output_folder = tmp_path / "output"

        prompt_config = {"name": "test", "steps": []}
        llm = OllamaBackend(model_name='mistral')

        with pytest.raises(ValueError, match="Input folder does not exist"):
            LLMProcessor(
                input_folder=nonexistent,
                output_folder=output_folder,
                prompt_config=prompt_config,
                llm=llm
            )

    def test_llm_processor_validates_prompt_config_dict(self, tmp_path):
        """Test LLMProcessor raises for non-dict prompt_config"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"

        llm = OllamaBackend(model_name='mistral')

        with pytest.raises(ValueError, match="prompt_config must be a dictionary"):
            LLMProcessor(
                input_folder=input_folder,
                output_folder=output_folder,
                prompt_config="not a dict",
                llm=llm
            )

    def test_llm_processor_validates_steps_key(self, tmp_path):
        """Test LLMProcessor raises when prompt_config missing steps"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"

        prompt_config = {"name": "test"}  # Missing 'steps'
        llm = OllamaBackend(model_name='mistral')

        with pytest.raises(ValueError, match="must contain 'steps' key"):
            LLMProcessor(
                input_folder=input_folder,
                output_folder=output_folder,
                prompt_config=prompt_config,
                llm=llm
            )

    def test_llm_processor_cleanup(self, tmp_path):
        """Test LLMProcessor cleanup doesn't raise"""
        from fichero.tools.utils.llm_utils import LLMProcessor, OllamaBackend

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"

        prompt_config = {"name": "test", "steps": []}
        llm = OllamaBackend(model_name='mistral')

        processor = LLMProcessor(
            input_folder=input_folder,
            output_folder=output_folder,
            prompt_config=prompt_config,
            llm=llm
        )

        # Should not raise
        processor.cleanup()


class TestProcessWithIterativeRefinement:
    """Test process_with_iterative_refinement function"""

    def test_function_exists(self):
        """Test process_with_iterative_refinement exists"""
        from fichero.tools.utils.llm_utils import process_with_iterative_refinement

        assert callable(process_with_iterative_refinement)

    def test_single_iteration_no_change(self):
        """Test refinement stops when no changes made"""
        from fichero.tools.utils.llm_utils import process_with_iterative_refinement, OllamaBackend

        mock_backend = Mock()
        mock_backend.process_text = Mock(return_value="same text")

        result = process_with_iterative_refinement(
            text="same text",
            backend=mock_backend,
            prompt_template="{text}",
            max_iterations=3
        )

        # Should stop after 1 iteration since output == input
        assert result == "same text"
        assert mock_backend.process_text.call_count == 1


class TestProcessDocumentWithLLM:
    """Test process_document_with_llm function"""

    def test_function_exists(self):
        """Test process_document_with_llm exists"""
        from fichero.tools.utils.llm_utils import process_document_with_llm

        assert callable(process_document_with_llm)

    def test_process_document_success(self, tmp_path):
        """Test processing a document successfully"""
        from fichero.tools.utils.llm_utils import process_document_with_llm

        doc_path = tmp_path / "test.txt"
        doc_path.write_text("Test content")

        mock_backend = Mock()
        mock_backend.process_text = Mock(return_value="Processed content")

        result = process_document_with_llm(
            document_path=doc_path,
            backend=mock_backend,
            prompt_template="Process this:"
        )

        assert result['success'] is True
        assert result['content'] == "Processed content"
        assert str(doc_path) in result['source']

    def test_process_document_with_output(self, tmp_path):
        """Test processing with output file"""
        from fichero.tools.utils.llm_utils import process_document_with_llm

        doc_path = tmp_path / "input.txt"
        doc_path.write_text("Input content")
        output_path = tmp_path / "output.txt"

        mock_backend = Mock()
        mock_backend.process_text = Mock(return_value="Output content")

        result = process_document_with_llm(
            document_path=doc_path,
            backend=mock_backend,
            prompt_template="Process this:",
            output_path=output_path
        )

        assert result['success'] is True
        assert output_path.exists()
        assert output_path.read_text() == "Output content"


class TestProcessFolderWithLLM:
    """Test process_folder_with_llm function"""

    def test_function_exists(self):
        """Test process_folder_with_llm exists"""
        from fichero.tools.utils.llm_utils import process_folder_with_llm

        assert callable(process_folder_with_llm)

    def test_process_folder_with_steps(self, tmp_path):
        """Test processing folder with multi-step prompt config"""
        from fichero.tools.utils.llm_utils import process_folder_with_llm

        folder = tmp_path / "input"
        folder.mkdir()

        # Create file data (as expected by the function)
        files = [
            {"path": folder / "file1.txt", "content": "Content 1", "page_num": 1},
            {"path": folder / "file2.txt", "content": "Content 2", "page_num": 2}
        ]

        mock_backend = Mock()
        mock_backend.process_text = Mock(return_value='{"result": "processed"}')
        mock_backend.model_name = "test-model"

        prompt_config = {
            "name": "test_config",
            "steps": [
                {"name": "step1", "prompt": "Process this:", "json": True}
            ]
        }

        result = process_folder_with_llm(
            folder_path=folder,
            files=files,
            llm=mock_backend,
            prompt_config=prompt_config,
            max_tokens=1000
        )

        assert result['success'] is True
        assert result['files_processed'] == 2
        assert result['steps_completed'] == 1
        assert 'step1' in result['results']

    def test_process_folder_multiple_steps(self, tmp_path):
        """Test processing folder with multiple steps and use_previous"""
        from fichero.tools.utils.llm_utils import process_folder_with_llm

        folder = tmp_path / "input"
        folder.mkdir()

        files = [
            {"path": folder / "doc.txt", "content": "Test document content", "page_num": 1}
        ]

        mock_backend = Mock()
        mock_backend.process_text = Mock(side_effect=[
            '{"entities": ["entity1"]}',
            '{"summary": "A summary"}'
        ])
        mock_backend.model_name = "test-model"

        prompt_config = {
            "name": "multi_step",
            "steps": [
                {"name": "extract", "prompt": "Extract entities:", "json": True},
                {"name": "summarize", "prompt": "Summarize:", "json": True, "use_previous": True}
            ]
        }

        result = process_folder_with_llm(
            folder_path=folder,
            files=files,
            llm=mock_backend,
            prompt_config=prompt_config
        )

        assert result['success'] is True
        assert result['steps_completed'] == 2
        assert 'extract' in result['results']
        assert 'summarize' in result['results']

    def test_process_folder_saves_output(self, tmp_path):
        """Test that results are saved to output folder"""
        from fichero.tools.utils.llm_utils import process_folder_with_llm

        input_folder = tmp_path / "input"
        input_folder.mkdir()
        output_folder = tmp_path / "output"

        files = [{"path": input_folder / "test.txt", "content": "Test", "page_num": 1}]

        mock_backend = Mock()
        mock_backend.process_text = Mock(return_value='{"data": "test"}')
        mock_backend.model_name = "test-model"

        prompt_config = {
            "name": "test",
            "steps": [{"name": "process", "prompt": "Process:", "json": True}]
        }

        result = process_folder_with_llm(
            folder_path=input_folder,
            files=files,
            llm=mock_backend,
            prompt_config=prompt_config,
            output_folder=output_folder
        )

        assert result['success'] is True
        assert output_folder.exists()
        assert (output_folder / f"{input_folder.name}_results.json").exists()
        assert (output_folder / "steps" / "process.json").exists()

    def test_process_folder_no_steps(self, tmp_path):
        """Test that empty steps returns error"""
        from fichero.tools.utils.llm_utils import process_folder_with_llm

        folder = tmp_path / "input"
        folder.mkdir()

        files = [{"path": folder / "test.txt", "content": "Test", "page_num": 1}]

        mock_backend = Mock()
        mock_backend.model_name = "test-model"

        prompt_config = {"name": "empty", "steps": []}

        result = process_folder_with_llm(
            folder_path=folder,
            files=files,
            llm=mock_backend,
            prompt_config=prompt_config
        )

        assert result['success'] is False
        assert "No steps defined" in result['error']


class TestBackendInheritance:
    """Test backend class inheritance structure"""

    def test_all_backends_inherit_from_llm_backend(self):
        """Test all backend classes inherit from LLMBackend"""
        from fichero.tools.utils.llm_utils import (
            LLMBackend, OpenAICompatibleBackend, ChatGPTBackend, QwenBackend,
            OllamaBackend, LMStudioBackend, HuggingFaceBackend, DeepSeekBackend,
            GroqBackend, TogetherBackend, ClaudeBackend, AppleVisionBackend
        )

        backends = [
            OpenAICompatibleBackend, ChatGPTBackend, QwenBackend,
            OllamaBackend, LMStudioBackend, HuggingFaceBackend, DeepSeekBackend,
            GroqBackend, TogetherBackend, ClaudeBackend, AppleVisionBackend
        ]

        for backend_cls in backends:
            assert issubclass(backend_cls, LLMBackend), f"{backend_cls.__name__} should inherit from LLMBackend"

    def test_openai_compatible_backends_inherit_correctly(self):
        """Test OpenAI-compatible backends inherit from OpenAICompatibleBackend"""
        from fichero.tools.utils.llm_utils import (
            OpenAICompatibleBackend, ChatGPTBackend, QwenBackend,
            OllamaBackend, LMStudioBackend, HuggingFaceBackend,
            DeepSeekBackend, GroqBackend, TogetherBackend
        )

        openai_compatible_backends = [
            ChatGPTBackend, QwenBackend, OllamaBackend, LMStudioBackend,
            HuggingFaceBackend, DeepSeekBackend, GroqBackend, TogetherBackend
        ]

        for backend_cls in openai_compatible_backends:
            assert issubclass(backend_cls, OpenAICompatibleBackend), \
                f"{backend_cls.__name__} should inherit from OpenAICompatibleBackend"

    def test_claude_backend_not_openai_compatible(self):
        """Test Claude backend does NOT inherit from OpenAICompatibleBackend"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend, ClaudeBackend

        assert not issubclass(ClaudeBackend, OpenAICompatibleBackend)

    def test_apple_backend_not_openai_compatible(self):
        """Test Apple backend does NOT inherit from OpenAICompatibleBackend"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend, AppleVisionBackend

        assert not issubclass(AppleVisionBackend, OpenAICompatibleBackend)


class TestAsyncSupport:
    """Test async method support across backends"""

    def test_openai_compatible_has_async_method(self):
        """Test OpenAICompatibleBackend has async method"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(model_name='test')
        assert hasattr(backend, 'process_text_async')
        assert asyncio.iscoroutinefunction(backend.process_text_async)

    def test_claude_backend_has_async_method(self):
        """Test ClaudeBackend has async method"""
        from fichero.tools.utils.llm_utils import ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test'}):
                backend = ClaudeBackend(model_name='claude-3-sonnet')

            assert hasattr(backend, 'process_text_async')
            assert asyncio.iscoroutinefunction(backend.process_text_async)

    def test_apple_backend_has_async_method(self):
        """Test AppleVisionBackend has async method"""
        from fichero.tools.utils.llm_utils import AppleVisionBackend, APPLE_VISION_AVAILABLE

        if APPLE_VISION_AVAILABLE:
            backend = AppleVisionBackend()
            assert hasattr(backend, 'process_text_async')
            assert asyncio.iscoroutinefunction(backend.process_text_async)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
