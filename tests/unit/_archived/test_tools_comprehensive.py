"""
Comprehensive unit tests for Fichero tools.

Tests the core tool components:
- StandardTool base class and ToolResult
- CropTool implementation
- ProviderFactory and transcription providers
- Tool validation and manifest creation
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from typing import Dict, Any
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestToolResult:
    """Test ToolResult data class"""

    def test_tool_result_success(self, tmp_path):
        """Test successful ToolResult creation"""
        from fichero.tools.base_tool import ToolResult

        result = ToolResult(
            success=True,
            output_path=tmp_path / "output.jpg",
            metadata={"method": "auto"}
        )

        assert result.success is True
        assert result.output_path == tmp_path / "output.jpg"
        assert result.metadata["method"] == "auto"
        assert result.error is None

    def test_tool_result_failure(self):
        """Test failed ToolResult creation"""
        from fichero.tools.base_tool import ToolResult

        result = ToolResult(
            success=False,
            error="Processing failed"
        )

        assert result.success is False
        assert result.error == "Processing failed"
        assert result.output_path is None

    def test_tool_result_warns_on_success_no_path(self, caplog):
        """Test warning when success=True but no output_path"""
        from fichero.tools.base_tool import ToolResult
        import logging

        with caplog.at_level(logging.WARNING):
            result = ToolResult(success=True)

        assert "success but no output_path" in caplog.text

    def test_tool_result_warns_on_failure_no_error(self, caplog):
        """Test warning when success=False but no error message"""
        from fichero.tools.base_tool import ToolResult
        import logging

        with caplog.at_level(logging.WARNING):
            result = ToolResult(success=False)

        assert "failure but no error message" in caplog.text


class TestCropToolValidation:
    """Test CropTool parameter validation"""

    def test_validate_default_parameters(self):
        """Test validation passes with default parameters"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({})

        assert is_valid is True
        assert error is None

    def test_validate_valid_output_format(self):
        """Test validation passes with valid output format"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()

        for fmt in ['jpg', 'jpeg', 'png', 'jxl']:
            is_valid, error = tool.validate_parameters({'output_format': fmt})
            assert is_valid is True, f"Expected {fmt} to be valid"

    def test_validate_invalid_output_format(self):
        """Test validation fails with invalid output format"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({'output_format': 'gif'})

        assert is_valid is False
        assert "output_format must be one of" in error

    def test_validate_valid_crop_box(self):
        """Test validation passes with valid crop box"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({
            'box': {'x1': 0, 'y1': 0, 'x2': 100, 'y2': 100}
        })

        assert is_valid is True
        assert error is None

    def test_validate_invalid_crop_box_missing_keys(self):
        """Test validation fails with missing box keys"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({
            'box': {'x1': 0, 'y1': 0}  # Missing x2, y2
        })

        assert is_valid is False
        assert "must contain all keys" in error

    def test_validate_invalid_crop_box_empty(self):
        """Test validation fails with empty box (x2 <= x1)"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({
            'box': {'x1': 100, 'y1': 0, 'x2': 50, 'y2': 100}
        })

        assert is_valid is False
        assert "x2 > x1" in error

    def test_validate_invalid_crop_box_non_numeric(self):
        """Test validation fails with non-numeric box coordinates"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        is_valid, error = tool.validate_parameters({
            'box': {'x1': 'abc', 'y1': 0, 'x2': 100, 'y2': 100}
        })

        assert is_valid is False
        assert "must be numeric" in error


class TestCropToolMetadata:
    """Test CropTool metadata and manifest creation"""

    def test_get_tool_name(self):
        """Test tool name is 'crop'"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        assert tool.get_tool_name() == "crop"

    def test_get_manifest_folder(self):
        """Test manifest folder is 'cropped'"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        assert tool.get_manifest_folder() == "cropped"

    def test_get_default_parameters(self):
        """Test default parameters include output_format"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        defaults = tool.get_default_parameters()

        assert 'output_format' in defaults
        assert defaults['output_format'] == 'jpg'

    def test_supports_batch_processing(self):
        """Test batch processing is supported"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        assert tool.supports_batch_processing() is True

    def test_get_supported_input_formats(self):
        """Test supported input formats include common image types"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        formats = tool.get_supported_input_formats()

        assert 'jpg' in formats
        assert 'jpeg' in formats
        assert 'png' in formats
        assert 'tiff' in formats

    def test_get_output_format_from_parameters(self):
        """Test output format extracted from parameters"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()

        assert tool.get_output_format({'output_format': 'png'}) == 'png'
        assert tool.get_output_format({}) == 'jpg'  # Default

    def test_create_manifest_entry(self, tmp_path):
        """Test manifest entry creation"""
        from fichero.tools.crop_tool import CropTool
        from fichero.tools.base_tool import ToolResult

        tool = CropTool()
        source = tmp_path / "input.jpg"
        output = tmp_path / "output.jpg"

        result = ToolResult(
            success=True,
            output_path=output,
            metadata={
                'method': 'auto',
                'confidence': 0.95,
                'box': {'x1': 10, 'y1': 10, 'x2': 200, 'y2': 300}
            }
        )

        entry = tool.create_manifest_entry(source, output, {}, result)

        assert entry['path'] == 'output.jpg'
        assert entry['source'] == 'input.jpg'
        assert entry['type'] == 'file'
        assert entry['details']['method'] == 'auto'
        assert 'timestamp' in entry['metadata']


class TestProviderFactory:
    """Test transcription ProviderFactory"""

    def test_create_dashscope_provider(self):
        """Test creating DashScope provider"""
        from fichero.tools.transcribe import ProviderFactory

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            provider = ProviderFactory.create('dashscope', api_key='test-key')

        assert provider is not None
        # Name includes model info
        assert 'DashScope' in provider.name

    def test_create_openai_provider(self):
        """Test creating OpenAI provider"""
        from fichero.tools.transcribe import ProviderFactory

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            provider = ProviderFactory.create('openai', api_key='test-key')

        assert provider is not None
        # Name includes provider type
        assert 'OpenAI' in provider.name

    def test_create_lmstudio_provider(self):
        """Test creating LMStudio provider"""
        from fichero.tools.transcribe import ProviderFactory

        # LMStudio requires model_name
        provider = ProviderFactory.create(
            'lmstudio',
            api_url='http://localhost:1234',
            model_name='test-model'
        )

        assert provider is not None
        assert 'LMStudio' in provider.name

    def test_create_unknown_provider_raises(self):
        """Test creating unknown provider raises ValueError"""
        from fichero.tools.transcribe import ProviderFactory

        with pytest.raises(ValueError, match="Unknown provider"):
            ProviderFactory.create('unknown_provider')

    def test_provider_names_case_insensitive(self):
        """Test provider names are case insensitive"""
        from fichero.tools.transcribe import ProviderFactory

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            provider1 = ProviderFactory.create('DASHSCOPE', api_key='test-key')
            provider2 = ProviderFactory.create('DashScope', api_key='test-key')
            provider3 = ProviderFactory.create('dashscope', api_key='test-key')

        # All should be DashScope providers
        assert 'DashScope' in provider1.name
        assert 'DashScope' in provider2.name
        assert 'DashScope' in provider3.name


class TestTranscriptionProviderBase:
    """Test base transcription provider functionality"""

    def test_dashscope_provider_properties(self):
        """Test DashScope provider properties"""
        from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            provider = DashScopeProvider(api_key='test-key')

        assert 'DashScope' in provider.name
        assert provider.supports_parallel is True

    def test_openai_provider_properties(self):
        """Test OpenAI provider properties"""
        from fichero.tools.transcribe_providers.openai_provider import OpenAIProvider

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            provider = OpenAIProvider(api_key='test-key')

        assert 'OpenAI' in provider.name
        assert provider.supports_parallel is True

    def test_lmstudio_provider_properties(self):
        """Test LMStudio provider properties"""
        from fichero.tools.transcribe_providers.lmstudio_provider import LMStudioProvider

        provider = LMStudioProvider(api_url='http://localhost:1234', model_name='test-model')

        assert 'LMStudio' in provider.name


class TestBatchProcessor:
    """Test BatchProcessor utility"""

    def test_batch_processor_initialization(self, tmp_path):
        """Test BatchProcessor initializes correctly"""
        from fichero.tools.utils.batch import BatchProcessor
        import json

        # Create input manifest
        input_manifest = tmp_path / "input_manifest.jsonl"
        with open(input_manifest, 'w') as f:
            f.write(json.dumps({"path": "test.jpg", "type": "file"}) + "\n")

        output_folder = tmp_path / "output"

        # BatchProcessor takes input_manifest, output_folder, process_name, processor_fn
        processor = BatchProcessor(
            input_manifest=input_manifest,
            output_folder=output_folder,
            process_name="test",
            processor_fn=lambda x, y: {"success": True}
        )

        assert processor.input_manifest == input_manifest
        assert processor.output_folder == output_folder

    def test_batch_processor_creates_output_folder(self, tmp_path):
        """Test BatchProcessor creates output folder"""
        from fichero.tools.utils.batch import BatchProcessor
        import json

        input_manifest = tmp_path / "input_manifest.jsonl"
        with open(input_manifest, 'w') as f:
            f.write(json.dumps({"path": "test.jpg", "type": "file"}) + "\n")

        output_folder = tmp_path / "output" / "nested"

        processor = BatchProcessor(
            input_manifest=input_manifest,
            output_folder=output_folder,
            process_name="test",
            processor_fn=lambda x, y: {"success": True}
        )

        # Output folder should be created
        assert output_folder.exists()


class TestSegmentHandler:
    """Test SegmentHandler utility"""

    def test_segment_exists(self, tmp_path):
        """Test checking if segment exists"""
        from fichero.tools.utils.segment_handler import SegmentHandler

        # Create a test file
        test_file = tmp_path / "test.jpg"
        test_file.write_text("test")

        # Should find existing file
        assert SegmentHandler.exists(test_file) is True

        # Should not find non-existent file
        assert SegmentHandler.exists(tmp_path / "nonexistent.jpg") is False

    def test_segment_exists_with_base_folder(self, tmp_path):
        """Test exists with base folder"""
        from fichero.tools.utils.segment_handler import SegmentHandler

        # Create a test file in subfolder
        subfolder = tmp_path / "subfolder"
        subfolder.mkdir()
        test_file = subfolder / "test.jpg"
        test_file.write_text("test")

        # Should find with base folder
        assert SegmentHandler.exists("subfolder/test.jpg", base_folder=tmp_path) is True

    def test_make_segment_name(self):
        """Test segment name creation"""
        from fichero.tools.utils.segment_handler import SegmentHandler

        # SegmentHandler creates segment names with index
        name = SegmentHandler.make_segment_name("document", 1)

        # Should contain segment pattern and index
        assert "segment" in name
        assert "001" in name or "1" in name


class TestEnhanceTool:
    """Test EnhanceTool implementation"""

    def test_enhance_tool_exists(self):
        """Test EnhanceTool can be imported"""
        from fichero.tools.enhance_tool import EnhanceTool

        tool = EnhanceTool()
        assert tool.get_tool_name() == "enhance"

    def test_enhance_tool_manifest_folder(self):
        """Test enhance manifest folder"""
        from fichero.tools.enhance_tool import EnhanceTool

        tool = EnhanceTool()
        assert tool.get_manifest_folder() == "enhanced"


class TestRotateTool:
    """Test RotateTool implementation"""

    def test_rotate_tool_exists(self):
        """Test RotateTool can be imported"""
        from fichero.tools.rotate_tool import RotateTool

        tool = RotateTool()
        assert tool.get_tool_name() == "rotate"

    def test_rotate_tool_manifest_folder(self):
        """Test rotate manifest folder"""
        from fichero.tools.rotate_tool import RotateTool

        tool = RotateTool()
        assert tool.get_manifest_folder() == "rotated"


class TestToolRegistry:
    """Test tool registry integration"""

    def test_tool_registry_import(self):
        """Test ToolRegistry can be imported"""
        from fichero.library.services.tool_registry import ToolRegistry

        # Should have a _tools dict
        assert hasattr(ToolRegistry, '_tools')

    def test_crop_tool_class_exists(self):
        """Test CropTool class can be imported"""
        from fichero.tools.crop_tool import CropTool

        tool = CropTool()
        assert tool.get_tool_name() == "crop"

    def test_tool_registration_decorator(self):
        """Test that tools use registration decorator"""
        from fichero.library.services.tool_registry import ToolRegistry
        from fichero.tools.crop_tool import CropTool

        # CropTool uses @ToolRegistry.register decorator
        # After importing, it should be in the registry
        # Check by name
        if 'crop' in ToolRegistry._tools:
            assert ToolRegistry._tools['crop'] == CropTool


class TestProcessImageWithProvider:
    """Test process_image_with_provider function"""

    def test_process_creates_output_directory(self, tmp_path):
        """Test that output directory is created"""
        from fichero.tools.transcribe import process_image_with_provider

        input_path = tmp_path / "input.jpg"
        input_path.write_text("fake image")

        output_path = tmp_path / "output" / "nested" / "transcription.txt"

        # Mock provider
        mock_provider = Mock()
        mock_provider.process_image.return_value = {
            "text": "Test transcription",
            "success": True
        }

        result = process_image_with_provider(input_path, output_path, mock_provider)

        # Output directory should be created
        assert output_path.parent.exists()

    def test_process_skips_existing_file(self, tmp_path):
        """Test that existing files are skipped"""
        from fichero.tools.transcribe import process_image_with_provider

        input_path = tmp_path / "input.jpg"
        input_path.write_text("fake image")

        output_path = tmp_path / "transcription.txt"
        output_path.write_text("existing content")

        mock_provider = Mock()

        result = process_image_with_provider(input_path, output_path, mock_provider)

        # Should be marked as skipped
        assert result.get("skipped") is True
        # Provider should not be called
        mock_provider.process_image.assert_not_called()


class TestGlobalRateLimiterIntegration:
    """Test global rate limiter integration with tools"""

    @pytest.mark.asyncio
    async def test_rate_limiter_available(self):
        """Test rate limiter can be imported"""
        from fichero.tools.utils.global_rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()
        assert limiter is not None

    @pytest.mark.asyncio
    async def test_rate_limiter_acquire_release(self):
        """Test acquiring and releasing rate limiter slots"""
        from fichero.tools.utils.global_rate_limiter import get_rate_limiter

        limiter = get_rate_limiter()

        async with limiter.acquire('dashscope'):
            # Should successfully acquire
            pass

        # Should release without error


class TestAsyncBatchProcessor:
    """Test AsyncBatchProcessor for parallel transcription"""

    def test_async_batch_processor_initialization(self):
        """Test AsyncBatchProcessor can be initialized"""
        from fichero.tools.transcribe_providers.async_batch_processor import AsyncBatchProcessor
        from fichero.tools.transcribe_providers.dashscope_provider import DashScopeProvider

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            provider = DashScopeProvider(api_key='test-key')
            processor = AsyncBatchProcessor(provider)

        assert processor.provider == provider


class TestLLMBackends:
    """Test unified LLM backends (platform-agnostic)"""

    def test_openai_compatible_backend_initialization(self):
        """Test OpenAICompatibleBackend can be initialized"""
        from fichero.tools.utils.llm_utils import OpenAICompatibleBackend

        backend = OpenAICompatibleBackend(
            model_name='gpt-4',
            api_key='test-key',
            base_url='https://api.example.com/v1'
        )

        assert backend.model_name == 'gpt-4'
        assert backend.base_url == 'https://api.example.com/v1'
        assert backend.provider_type == 'openai'

    def test_chatgpt_backend_uses_openai_compatible(self):
        """Test ChatGPTBackend is OpenAICompatibleBackend subclass"""
        from fichero.tools.utils.llm_utils import ChatGPTBackend, OpenAICompatibleBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            backend = ChatGPTBackend(model_name='gpt-4')

        assert isinstance(backend, OpenAICompatibleBackend)
        assert backend.provider_type == 'openai'
        assert backend.base_url is None  # Uses default OpenAI

    def test_qwen_backend_uses_dashscope_url(self):
        """Test QwenBackend uses DashScope OpenAI-compatible URL"""
        from fichero.tools.utils.llm_utils import QwenBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'DASHSCOPE_API_KEY': 'test-key'}):
            backend = QwenBackend(model_name='qwen-max')

        assert backend.base_url == PROVIDER_BASE_URLS['dashscope']
        assert backend.provider_type == 'dashscope'

    def test_ollama_backend_uses_local_url(self):
        """Test OllamaBackend uses local OpenAI-compatible URL"""
        from fichero.tools.utils.llm_utils import OllamaBackend

        backend = OllamaBackend(model_name='mistral')

        assert 'localhost:11434' in backend.base_url
        assert backend.provider_type == 'local'

    def test_lmstudio_backend_uses_local_url(self):
        """Test LMStudioBackend uses local OpenAI-compatible URL"""
        from fichero.tools.utils.llm_utils import LMStudioBackend

        backend = LMStudioBackend(model_name='test-model')

        assert 'localhost:1234' in backend.base_url
        assert backend.provider_type == 'local'

    def test_claude_backend_requires_anthropic(self):
        """Test ClaudeBackend uses Anthropic SDK"""
        from fichero.tools.utils.llm_utils import ClaudeBackend, ANTHROPIC_AVAILABLE

        if ANTHROPIC_AVAILABLE:
            with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'test-key'}):
                backend = ClaudeBackend(model_name='claude-3-opus')
            assert backend.provider_type == 'anthropic'

    def test_provider_base_urls_defined(self):
        """Test all provider base URLs are defined"""
        from fichero.tools.utils.llm_utils import PROVIDER_BASE_URLS

        assert 'openai' in PROVIDER_BASE_URLS
        assert 'dashscope' in PROVIDER_BASE_URLS
        assert 'ollama' in PROVIDER_BASE_URLS
        assert 'lmstudio' in PROVIDER_BASE_URLS
        assert 'deepseek' in PROVIDER_BASE_URLS
        assert 'groq' in PROVIDER_BASE_URLS
        assert 'together' in PROVIDER_BASE_URLS

    def test_get_llm_backend_from_config_openai(self):
        """Test creating OpenAI backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, ChatGPTBackend

        with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-key'}):
            backend = get_llm_backend_from_config({
                'llm': {
                    'backend': 'openai',
                    'model': 'gpt-4'
                }
            })

        assert isinstance(backend, ChatGPTBackend)

    def test_get_llm_backend_from_config_ollama(self):
        """Test creating Ollama backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OllamaBackend

        backend = get_llm_backend_from_config({
            'llm': {
                'backend': 'ollama',
                'model': 'mistral'
            }
        })

        assert isinstance(backend, OllamaBackend)

    def test_get_llm_backend_from_config_generic(self):
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

    def test_huggingface_backend_uses_hf_url(self):
        """Test HuggingFaceBackend uses HuggingFace Inference API URL"""
        from fichero.tools.utils.llm_utils import HuggingFaceBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = HuggingFaceBackend(model_name='meta-llama/Llama-2-7b')

        assert backend.base_url == PROVIDER_BASE_URLS['huggingface']
        assert backend.provider_type == 'huggingface'

    def test_deepseek_backend_uses_deepseek_url(self):
        """Test DeepSeekBackend uses DeepSeek API URL"""
        from fichero.tools.utils.llm_utils import DeepSeekBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-key'}):
            backend = DeepSeekBackend(model_name='deepseek-chat')

        assert backend.base_url == PROVIDER_BASE_URLS['deepseek']
        assert backend.provider_type == 'deepseek'

    def test_groq_backend_uses_groq_url(self):
        """Test GroqBackend uses Groq API URL"""
        from fichero.tools.utils.llm_utils import GroqBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk_test'}):
            backend = GroqBackend(model_name='llama-3.1-70b-versatile')

        assert backend.base_url == PROVIDER_BASE_URLS['groq']
        assert backend.provider_type == 'groq'

    def test_together_backend_uses_together_url(self):
        """Test TogetherBackend uses Together AI API URL"""
        from fichero.tools.utils.llm_utils import TogetherBackend, PROVIDER_BASE_URLS

        with patch.dict('os.environ', {'TOGETHER_API_KEY': 'test-key'}):
            backend = TogetherBackend(model_name='meta-llama/Llama-3-70b')

        assert backend.base_url == PROVIDER_BASE_URLS['together']
        assert backend.provider_type == 'together'

    def test_get_llm_backend_from_config_deepseek(self):
        """Test creating DeepSeek backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, DeepSeekBackend

        with patch.dict('os.environ', {'DEEPSEEK_API_KEY': 'test-key'}):
            backend = get_llm_backend_from_config({
                'llm': {
                    'backend': 'deepseek',
                    'model': 'deepseek-coder'
                }
            })

        assert isinstance(backend, DeepSeekBackend)

    def test_get_llm_backend_from_config_groq(self):
        """Test creating Groq backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, GroqBackend

        with patch.dict('os.environ', {'GROQ_API_KEY': 'gsk_test'}):
            backend = get_llm_backend_from_config({
                'llm': {
                    'backend': 'groq',
                    'model': 'mixtral-8x7b'
                }
            })

        assert isinstance(backend, GroqBackend)

    def test_get_llm_backend_from_config_huggingface(self):
        """Test creating HuggingFace backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, HuggingFaceBackend

        with patch.dict('os.environ', {'HUGGINGFACE_TOKEN': 'hf_test'}):
            backend = get_llm_backend_from_config({
                'llm': {
                    'backend': 'huggingface',
                    'model': 'mistralai/Mistral-7B'
                }
            })

        assert isinstance(backend, HuggingFaceBackend)

    def test_get_llm_backend_from_config_vllm_local(self):
        """Test creating vLLM local backend from config"""
        from fichero.tools.utils.llm_utils import get_llm_backend_from_config, OpenAICompatibleBackend

        backend = get_llm_backend_from_config({
            'llm': {
                'backend': 'vllm',
                'model': 'local-model'
            }
        })

        assert isinstance(backend, OpenAICompatibleBackend)
        assert 'localhost:8000' in backend.base_url


class TestChunkText:
    """Test text chunking utilities"""

    def test_chunk_text_intelligently(self):
        """Test intelligent text chunking"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        chunks = chunk_text_intelligently(text, max_tokens=10, overlap=0)

        assert len(chunks) > 0
        # Each chunk should have text
        for chunk in chunks:
            assert 'text' in chunk
            assert len(chunk['text']) > 0

    def test_chunk_text_empty_input(self):
        """Test chunking with empty input"""
        from fichero.tools.utils.llm_utils import chunk_text_intelligently

        chunks = chunk_text_intelligently("")

        assert chunks == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
