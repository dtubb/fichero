"""
Unified LLM utilities for Fichero.

Platform-agnostic implementation using primarily the OpenAI SDK, which is
compatible with most LLM providers via their OpenAI-compatible endpoints:
- OpenAI (native)
- DashScope/Qwen (OpenAI-compatible mode)
- Ollama (OpenAI-compatible API)
- LMStudio (OpenAI-compatible API)
- Anthropic Claude (native SDK - OpenAI mode too limited)
- Hugging Face (Inference Endpoints, TGI - OpenAI-compatible)
- DeepSeek, Groq, Together, etc. (all OpenAI-compatible)

This reduces dependencies and makes it easy to add new providers.
"""

from typing import Dict, List, Optional, Any, Callable, TypeVar
from pathlib import Path
from datetime import datetime
from functools import wraps
import os
import asyncio
import time

T = TypeVar('T')

# Primary SDK - used for most providers via OpenAI-compatible APIs
import openai
from openai import OpenAI, AsyncOpenAI

# Anthropic SDK - Claude's OpenAI-compatible mode is too limited
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from fichero.tools.utils.segment_handler import SegmentHandler
from fichero.tools.utils.files import ensure_dirs, get_relative_path
from fichero.tools.utils.manifest import ManifestProcessor
from fichero.tools.utils.api_keys import (
    get_openai_key, get_qwen_key, get_claude_key, get_huggingface_token,
    get_deepseek_key, get_groq_key, get_together_key
)
import srsly

# Support both standalone CLI usage and workflow executor imports
try:
    from fichero.tools.utils.tool_logger import get_tool_logger
except ImportError:
    from tool_logger import get_tool_logger

# Global rate limiter for API calls
try:
    from fichero.tools.utils.global_rate_limiter import get_rate_limiter
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False

tool_logger = get_tool_logger('llm_utils')

# Default configuration values
DEFAULT_MAX_TOKENS = 3072
MAX_OUTPUT_TOKENS = 4096  # Maximum output tokens for most providers
DEFAULT_RETRY_COUNT = 3
DEFAULT_RETRY_DELAY = 1.0  # seconds


def with_retry(
    max_retries: int = DEFAULT_RETRY_COUNT,
    base_delay: float = DEFAULT_RETRY_DELAY,
    retry_on_rate_limit: bool = True
):
    """
    Decorator for sync functions with exponential backoff retry.

    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (doubles each retry)
        retry_on_rate_limit: Whether to retry on rate limit errors
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last_error = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_error = e
                    error_str = str(e).lower()
                    is_rate_limit = any(x in error_str for x in ['429', 'rate limit', 'too many requests'])

                    if attempt < max_retries:
                        if is_rate_limit and retry_on_rate_limit:
                            tool_logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). Retrying in {delay:.1f}s...")
                        else:
                            tool_logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                        time.sleep(delay)
                        delay *= 2
                    else:
                        tool_logger.error(f"API call failed after {max_retries + 1} attempts: {e}")

            return ""  # Return empty string on failure for text processing
        return wrapper
    return decorator


async def with_retry_async(
    coro_func: Callable[..., T],
    *args,
    max_retries: int = DEFAULT_RETRY_COUNT,
    base_delay: float = DEFAULT_RETRY_DELAY,
    retry_on_rate_limit: bool = True,
    **kwargs
) -> T:
    """
    Async retry helper with exponential backoff.

    Args:
        coro_func: Async function to call
        *args: Arguments to pass to the function
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries
        retry_on_rate_limit: Whether to retry on rate limit errors
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result of the coroutine function
    """
    delay = base_delay
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_func(*args, **kwargs)
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_rate_limit = any(x in error_str for x in ['429', 'rate limit', 'too many requests'])

            if attempt < max_retries:
                if is_rate_limit and retry_on_rate_limit:
                    tool_logger.warning(f"Rate limit hit (attempt {attempt + 1}/{max_retries + 1}). Retrying in {delay:.1f}s...")
                else:
                    tool_logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries + 1}): {e}")
                await asyncio.sleep(delay)
                delay *= 2
            else:
                tool_logger.error(f"API call failed after {max_retries + 1} attempts: {e}")

    return ""  # Return empty string on failure for text processing

# Provider base URLs for OpenAI-compatible APIs
PROVIDER_BASE_URLS = {
    'openai': 'https://api.openai.com/v1',
    'dashscope': 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1',
    'ollama': 'http://localhost:11434/v1',
    'lmstudio': 'http://localhost:1234/v1',
    'deepseek': 'https://api.deepseek.com/v1',
    'groq': 'https://api.groq.com/openai/v1',
    'together': 'https://api.together.xyz/v1',
    'huggingface': 'https://api-inference.huggingface.co/v1',  # HF Inference Endpoints (OpenAI-compatible)
}


class LLMBackend:
    """Base class for LLM backends with global rate limiting support."""

    # Provider type for rate limiting (override in subclasses)
    provider_type: str = 'default'

    def __init__(self, model_name: str, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

    def process_text(self, text: str, prompt: str) -> str:
        raise NotImplementedError

    async def process_text_async(self, text: str, prompt: str) -> str:
        """Async version - override in subclasses"""
        raise NotImplementedError

    def cleanup(self):
        """Clean up resources"""
        pass

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get comprehensive model/provider information for tracking.

        Returns:
            Dictionary with model details for workflow_manifest.json
        """
        return {
            'model': self.model_name,
            'provider': self.provider_type,
            'model_version': None,
            'api_endpoint': None,
            'api_parameters': {
                'temperature': self.temperature,
                'max_tokens': self.max_tokens
            },
            'usage': {}
        }


class OpenAICompatibleBackend(LLMBackend):
    """
    Unified backend for all OpenAI-compatible APIs.

    Works with: OpenAI, DashScope/Qwen, Ollama, LMStudio, DeepSeek, Groq, Together, etc.
    Just change the base_url to switch providers.
    """
    provider_type = 'openai'

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = 120.0
    ):
        super().__init__(model_name, temperature, max_tokens)

        # Resolve API key and base URL
        self.api_key = api_key or os.environ.get('OPENAI_API_KEY', 'not-needed')
        self.base_url = base_url  # None = default OpenAI
        self.timeout = timeout

        # Create sync and async clients
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout
        )
        self.async_client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout
        )

    def _build_messages(self, text: str, prompt: str) -> List[Dict[str, str]]:
        """Build message list for chat completion"""
        return [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": f"{prompt}\n\n{text}"}
        ]

    def _get_effective_max_tokens(self) -> int:
        """Get effective max tokens (capped at MAX_OUTPUT_TOKENS)"""
        return min(self.max_tokens, MAX_OUTPUT_TOKENS)

    def _make_completion_sync(self, text: str, prompt: str) -> str:
        """Make a single synchronous completion request"""
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(text, prompt),
            max_tokens=self._get_effective_max_tokens(),
            temperature=self.temperature
        )
        return response.choices[0].message.content.strip()

    async def _make_completion_async(self, text: str, prompt: str) -> str:
        """Make a single async completion request"""
        response = await self.async_client.chat.completions.create(
            model=self.model_name,
            messages=self._build_messages(text, prompt),
            max_tokens=self._get_effective_max_tokens(),
            temperature=self.temperature
        )
        return response.choices[0].message.content.strip()

    @with_retry()
    def process_text(self, text: str, prompt: str) -> str:
        """Process text synchronously with retry"""
        return self._make_completion_sync(text, prompt)

    async def process_text_async(self, text: str, prompt: str) -> str:
        """Async version with global rate limiting and retry"""
        # Get retry config from rate limiter if available
        if RATE_LIMITER_AVAILABLE:
            limiter = get_rate_limiter()
            config = limiter.get_config(self.provider_type)
            max_retries = config.max_retries
            base_delay = config.base_retry_delay
        else:
            max_retries = DEFAULT_RETRY_COUNT
            base_delay = DEFAULT_RETRY_DELAY

        async def make_request():
            if RATE_LIMITER_AVAILABLE:
                async with limiter.acquire(self.provider_type):
                    return await self._make_completion_async(text, prompt)
            else:
                return await self._make_completion_async(text, prompt)

        return await with_retry_async(
            make_request,
            max_retries=max_retries,
            base_delay=base_delay
        )

    async def process_pages_batch(self, pages: List[Dict], prompt: str, batch_size: int = 10) -> List[Dict]:
        """Process multiple pages concurrently using global rate limiter"""
        async def process_page_with_limit(page_info: Dict) -> Dict:
            page_num = page_info.get('page_num', 0)
            text = page_info.get('content', '')
            page_prompt = f"{prompt}\n\nPage Number: {page_num}"
            result = await self.process_text_async(text, page_prompt)

            return {
                'page_num': page_num,
                'result': result,
                'source_file': page_info.get('path', ''),
                'timestamp': datetime.now().isoformat()
            }

        try:
            tasks = [process_page_with_limit(page) for page in pages]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            successful_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    tool_logger.error(f"Error processing page {pages[i].get('page_num', i)}: {result}")
                else:
                    successful_results.append(result)

            return successful_results
        except Exception as e:
            tool_logger.error(f"Error in batch processing: {e}")
            return []

    def cleanup(self):
        """Clean up resources"""
        try:
            if hasattr(self, 'async_client') and self.async_client:
                if hasattr(self.async_client, '_session') and self.async_client._session:
                    try:
                        loop = asyncio.get_event_loop()
                        if not loop.is_closed():
                            loop.run_until_complete(self.async_client._session.close())
                    except Exception:
                        pass
        except Exception:
            pass

    def get_model_info(self) -> Dict[str, Any]:
        """Get model info with OpenAI-specific details"""
        info = super().get_model_info()
        info['api_endpoint'] = self.base_url or 'https://api.openai.com/v1'
        info['api_parameters']['timeout'] = self.timeout
        return info


# Backwards-compatible aliases using OpenAICompatibleBackend
class ChatGPTBackend(OpenAICompatibleBackend):
    """OpenAI ChatGPT backend"""
    provider_type = 'openai'

    def __init__(self, model_name: str, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        api_key = get_openai_key(api_key)
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=None,  # Default OpenAI
            temperature=temperature,
            max_tokens=max_tokens
        )


class QwenBackend(OpenAICompatibleBackend):
    """DashScope/Qwen backend using OpenAI-compatible API"""
    provider_type = 'dashscope'

    def __init__(self, model_name: str, api_key: Optional[str] = None, temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        api_key = get_qwen_key(api_key)
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS['dashscope'],
            temperature=temperature,
            max_tokens=max_tokens
        )


class LMStudioBackend(OpenAICompatibleBackend):
    """LMStudio local backend using OpenAI-compatible API"""
    provider_type = 'local'

    def __init__(self, model_name: str, api_url: str = "http://localhost:1234", temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        # LMStudio doesn't need API key
        super().__init__(
            model_name=model_name,
            api_key='not-needed',
            base_url=f"{api_url}/v1" if not api_url.endswith('/v1') else api_url,
            temperature=temperature,
            max_tokens=max_tokens
        )


class OllamaBackend(OpenAICompatibleBackend):
    """Ollama local backend using OpenAI-compatible API"""
    provider_type = 'local'

    def __init__(self, model_name: str, api_url: str = "http://localhost:11434", temperature: float = 0.0, max_tokens: int = DEFAULT_MAX_TOKENS):
        super().__init__(
            model_name=model_name,
            api_key='not-needed',
            base_url=f"{api_url}/v1" if not api_url.endswith('/v1') else api_url,
            temperature=temperature,
            max_tokens=max_tokens
        )


class HuggingFaceBackend(OpenAICompatibleBackend):
    """
    Hugging Face backend using OpenAI-compatible API.

    Works with:
    - Hugging Face Inference Endpoints (dedicated/serverless)
    - Text Generation Inference (TGI) servers
    - Any HF model deployed with OpenAI-compatible interface

    Default base_url points to HF Inference API. For custom endpoints,
    pass the full endpoint URL (e.g., https://xxx.endpoints.huggingface.cloud/v1)
    """
    provider_type = 'huggingface'

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS
    ):
        api_key = get_huggingface_token(api_key)
        # Use custom endpoint URL or default HF Inference API
        if base_url is None:
            base_url = PROVIDER_BASE_URLS['huggingface']
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=max_tokens
        )


class DeepSeekBackend(OpenAICompatibleBackend):
    """DeepSeek backend using OpenAI-compatible API"""
    provider_type = 'deepseek'

    def __init__(
        self,
        model_name: str = "deepseek-chat",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS
    ):
        api_key = get_deepseek_key(api_key)
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS['deepseek'],
            temperature=temperature,
            max_tokens=max_tokens
        )


class GroqBackend(OpenAICompatibleBackend):
    """Groq backend using OpenAI-compatible API - ultra-fast inference"""
    provider_type = 'groq'

    def __init__(
        self,
        model_name: str = "llama-3.1-70b-versatile",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS
    ):
        api_key = get_groq_key(api_key)
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS['groq'],
            temperature=temperature,
            max_tokens=max_tokens
        )


class TogetherBackend(OpenAICompatibleBackend):
    """Together AI backend using OpenAI-compatible API"""
    provider_type = 'together'

    def __init__(
        self,
        model_name: str = "meta-llama/Llama-3-70b-chat-hf",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS
    ):
        api_key = get_together_key(api_key)
        super().__init__(
            model_name=model_name,
            api_key=api_key,
            base_url=PROVIDER_BASE_URLS['together'],
            temperature=temperature,
            max_tokens=max_tokens
        )


# Apple Vision OCR support (macOS/iOS only)
try:
    import platform
    if platform.system() == 'Darwin':
        from rubicon.objc import ObjCClass, NSObject
        from rubicon.objc.runtime import load_library

        # Load Vision framework
        load_library('Vision')
        VNRecognizeTextRequest = ObjCClass('VNRecognizeTextRequest')
        VNImageRequestHandler = ObjCClass('VNImageRequestHandler')

        APPLE_VISION_AVAILABLE = True
    else:
        APPLE_VISION_AVAILABLE = False
except ImportError:
    APPLE_VISION_AVAILABLE = False
except Exception:
    APPLE_VISION_AVAILABLE = False


class AppleVisionBackend(LLMBackend):
    """
    Apple Vision backend for on-device OCR.

    Uses Apple's Vision framework for text recognition - no API key needed,
    works offline, and is privacy-preserving. Available on macOS and iOS only.

    For transcription/OCR only - not a general LLM.
    """
    provider_type = 'apple'

    def __init__(
        self,
        model_name: str = "apple-vision",  # Not used, but kept for API consistency
        temperature: float = 0.0,  # Not used for OCR
        max_tokens: int = DEFAULT_MAX_TOKENS,  # Not used for OCR
        recognition_level: str = "accurate"  # "accurate" or "fast"
    ):
        super().__init__(model_name, temperature, max_tokens)

        if not APPLE_VISION_AVAILABLE:
            raise ImportError(
                "Apple Vision framework not available. "
                "This backend only works on macOS/iOS with rubicon-objc installed."
            )

        self.recognition_level = recognition_level

    def transcribe_image(self, image_path: str) -> str:
        """
        Transcribe text from an image using Apple Vision OCR.

        Args:
            image_path: Path to the image file

        Returns:
            Recognized text from the image
        """
        from pathlib import Path
        from rubicon.objc import ObjCClass

        # Load required classes
        NSURL = ObjCClass('NSURL')
        NSArray = ObjCClass('NSArray')

        # Create image URL
        image_url = NSURL.fileURLWithPath_(str(Path(image_path).resolve()))

        # Create request handler
        handler = VNImageRequestHandler.alloc().initWithURL_options_(image_url, None)

        # Create text recognition request
        request = VNRecognizeTextRequest.alloc().init()

        # Set recognition level
        if self.recognition_level == "fast":
            request.setRecognitionLevel_(0)  # VNRequestTextRecognitionLevelFast
        else:
            request.setRecognitionLevel_(1)  # VNRequestTextRecognitionLevelAccurate

        # Perform recognition
        error_ptr = None
        success = handler.performRequests_error_(NSArray.arrayWithObject_(request), error_ptr)

        if not success:
            tool_logger.error(f"Apple Vision OCR failed for {image_path}")
            return ""

        # Extract results
        results = request.results()
        if not results:
            return ""

        # Combine all recognized text
        text_lines = []
        for i in range(results.count()):
            observation = results.objectAtIndex_(i)
            # Get the top candidate
            candidates = observation.topCandidates_(1)
            if candidates and candidates.count() > 0:
                top_candidate = candidates.objectAtIndex_(0)
                text_lines.append(str(top_candidate.string()))

        return '\n'.join(text_lines)

    def process_text(self, text: str, prompt: str) -> str:
        """
        For API consistency - Apple Vision is OCR only.

        If text is a file path to an image, perform OCR.
        Otherwise, return the text as-is (no LLM processing available).
        """
        from pathlib import Path

        # Check if text is a file path to an image
        if text and Path(text).exists() and Path(text).suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.tif', '.heic', '.bmp']:
            return self.transcribe_image(text)

        # For non-image input, just return it (no LLM capability)
        tool_logger.warning("Apple Vision backend is OCR-only. Use a different backend for text processing.")
        return text

    async def process_text_async(self, text: str, prompt: str) -> str:
        """Async version - runs sync operation in executor"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.process_text, text, prompt)

    def cleanup(self):
        """No cleanup needed for Apple Vision"""
        pass


class ClaudeBackend(LLMBackend):
    """
    Anthropic Claude backend.

    Uses native Anthropic SDK because Claude's OpenAI-compatible mode is limited.
    Supports both sync and async operations with proper async client.
    """
    provider_type = 'anthropic'

    def __init__(
        self,
        model_name: str,
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = 120.0
    ):
        super().__init__(model_name, temperature, max_tokens)
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("Please install anthropic package: pip install anthropic")

        key = get_claude_key(api_key)
        self.timeout = timeout

        # Create both sync and async clients
        self.client = anthropic.Anthropic(api_key=key, timeout=timeout)
        self.async_client = anthropic.AsyncAnthropic(api_key=key, timeout=timeout)

    def _build_messages(self, text: str, prompt: str) -> List[Dict[str, str]]:
        """Build message list for Claude API"""
        return [{"role": "user", "content": f"{prompt}\n\n{text}"}]

    def _get_effective_max_tokens(self) -> int:
        """Get effective max tokens (capped at MAX_OUTPUT_TOKENS)"""
        return min(self.max_tokens, MAX_OUTPUT_TOKENS)

    def _make_completion_sync(self, text: str, prompt: str) -> str:
        """Make a single synchronous completion request"""
        response = self.client.messages.create(
            model=self.model_name,
            max_tokens=self._get_effective_max_tokens(),
            temperature=self.temperature,
            messages=self._build_messages(text, prompt)
        )
        return response.content[0].text.strip()

    async def _make_completion_async(self, text: str, prompt: str) -> str:
        """Make a single async completion request"""
        response = await self.async_client.messages.create(
            model=self.model_name,
            max_tokens=self._get_effective_max_tokens(),
            temperature=self.temperature,
            messages=self._build_messages(text, prompt)
        )
        return response.content[0].text.strip()

    @with_retry()
    def process_text(self, text: str, prompt: str) -> str:
        """Process text synchronously with retry"""
        return self._make_completion_sync(text, prompt)

    async def process_text_async(self, text: str, prompt: str) -> str:
        """Async version with proper async client and retry"""
        return await with_retry_async(
            self._make_completion_async,
            text, prompt,
            max_retries=DEFAULT_RETRY_COUNT,
            base_delay=DEFAULT_RETRY_DELAY
        )

    def cleanup(self):
        """Clean up resources"""
        # Anthropic clients don't require explicit cleanup
        pass


def get_llm_backend_from_config(config: Dict) -> LLMBackend:
    """
    Create LLM backend from configuration.

    Args:
        config: Configuration dictionary with 'llm' key containing:
            - backend: Provider type (see supported list below)
            - model: Model name
            - temperature: Sampling temperature (default: 0.0)
            - max_tokens: Max output tokens (default: DEFAULT_MAX_TOKENS)
            - api_key: API key (can also use provider-specific keys)
            - api_url/base_url: Custom API endpoint

    Supported backends:
        Cloud Providers:
        - chatgpt/openai: OpenAI GPT models
        - claude/anthropic: Anthropic Claude models
        - qwen/dashscope: Alibaba Qwen models (DashScope API)
        - huggingface: HuggingFace Inference Endpoints
        - deepseek: DeepSeek models
        - groq: Groq (ultra-fast inference)
        - together: Together AI

        Local Providers:
        - ollama: Local Ollama server (default: localhost:11434)
        - lmstudio: Local LM Studio server (default: localhost:1234)
        - vllm: vLLM server (default: localhost:8000)
        - llamacpp: llama.cpp server (default: localhost:8080)
        - localai: LocalAI server (default: localhost:8080)

        On-Device:
        - apple: Apple Vision framework OCR (macOS/iOS only, no API key needed)

        Custom:
        - generic: Any OpenAI-compatible API (specify base_url)

    Returns:
        LLMBackend instance configured for the specified provider

    Raises:
        ValueError: If backend type is not supported
    """
    # Handle both wrapped config {"llm": {...}} and direct config {"backend": ...}
    # If config has "backend" key directly, it's a direct llm config
    # If config has "llm" key, extract the nested config
    if "backend" in config:
        llm_config = config
    else:
        llm_config = config.get("llm", {})
    backend_type = llm_config.get("backend", "ollama")
    model_name = llm_config.get("model", "mistral")
    temperature = llm_config.get("temperature", 0.0)
    api_key = llm_config.get("api_key")
    api_url = llm_config.get("api_url")
    base_url = llm_config.get("base_url")  # For generic OpenAI-compatible
    max_tokens = llm_config.get("max_tokens", DEFAULT_MAX_TOKENS)

    # Handle provider-specific API keys from config
    openai_api_key = llm_config.get("openai_api_key")
    qwen_api_key = llm_config.get("qwen_api_key")
    claude_api_key = llm_config.get("claude_api_key")

    # Handle provider-specific HuggingFace API key
    huggingface_api_key = llm_config.get("huggingface_api_key")

    if backend_type in ("chatgpt", "openai"):
        return ChatGPTBackend(model_name, openai_api_key or api_key, temperature, max_tokens)
    elif backend_type in ("claude", "anthropic"):
        return ClaudeBackend(model_name, claude_api_key or api_key, temperature, max_tokens)
    elif backend_type in ("qwen", "dashscope"):
        return QwenBackend(model_name, qwen_api_key or api_key, temperature, max_tokens)
    elif backend_type == "lmstudio":
        api_url = api_url or "http://localhost:1234"
        return LMStudioBackend(model_name, api_url, temperature, max_tokens)
    elif backend_type == "ollama":
        api_url = api_url or "http://localhost:11434"
        return OllamaBackend(model_name, api_url, temperature, max_tokens)
    elif backend_type == "huggingface":
        return HuggingFaceBackend(
            model_name=model_name,
            api_key=huggingface_api_key or api_key,
            base_url=base_url or api_url,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type == "deepseek":
        return DeepSeekBackend(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type == "groq":
        return GroqBackend(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type == "together":
        return TogetherBackend(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type in ("vllm", "llamacpp", "localai"):
        # Local servers with OpenAI-compatible APIs
        default_ports = {"vllm": 8000, "llamacpp": 8080, "localai": 8080}
        port = default_ports.get(backend_type, 8000)
        default_url = f"http://localhost:{port}"
        return OpenAICompatibleBackend(
            model_name=model_name,
            api_key='not-needed',
            base_url=f"{api_url or default_url}/v1",
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type == "generic":
        # Generic OpenAI-compatible API
        return OpenAICompatibleBackend(
            model_name=model_name,
            api_key=api_key,
            base_url=base_url or api_url,
            temperature=temperature,
            max_tokens=max_tokens
        )
    elif backend_type == "apple":
        # Apple Vision on-device OCR (macOS/iOS only)
        recognition_level = llm_config.get("recognition_level", "accurate")
        return AppleVisionBackend(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            recognition_level=recognition_level
        )
    else:
        raise ValueError(f"Unsupported backend type: {backend_type}")


def chunk_text_intelligently(text: str, max_tokens: int = 1000, overlap: int = 100) -> List[Dict[str, any]]:
    """Split text into intelligent chunks with overlap for context"""
    if not text.strip():
        tool_logger.warning("Empty text provided for chunking")
        return []

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_tokens = 0

    for para in paragraphs:
        if not para.strip():
            continue

        para_tokens = len(para.split())

        if current_tokens + para_tokens > max_tokens and current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            if chunk_text.strip():
                chunks.append({
                    'text': chunk_text,
                    'tokens': current_tokens,
                    'start_idx': len(chunks),
                    'is_complete': False
                })

            if overlap > 0 and len(current_chunk) > 1:
                current_chunk = [current_chunk[-1]]
                current_tokens = len(current_chunk[0].split())
            else:
                current_chunk = []
                current_tokens = 0

        current_chunk.append(para)
        current_tokens += para_tokens

    # Add final chunk
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        if chunk_text.strip():
            chunks.append({
                'text': chunk_text,
                'tokens': current_tokens,
                'start_idx': len(chunks),
                'is_complete': True
            })

    return chunks


def read_text_file(file_path: Path, encodings: List[str] = None) -> str:
    """Read a text file with multiple encoding fallbacks"""
    if encodings is None:
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252', 'iso-8859-1']

    if not file_path.exists():
        tool_logger.warning(f"File not found: {file_path}")
        return ""

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
        except Exception as e:
            tool_logger.warning(f"Error reading {file_path} with {encoding}: {e}")
            continue

    tool_logger.error(f"Failed to read {file_path} with any encoding")
    return ""


# Alias for backward compatibility
get_llm_backend = get_llm_backend_from_config


def load_prompt_config(config_path: Path) -> Dict:
    """
    Load prompt configuration from a JSON or JSONL file.

    Supports both:
    - Pretty-printed JSON files (multi-line, single object)
    - JSONL files (one JSON object per line)

    Args:
        config_path: Path to the prompt config file (.json or .jsonl)

    Returns:
        Configuration dictionary
    """
    import json
    config_path = Path(config_path)

    if not config_path.exists():
        tool_logger.error(f"Prompt config not found: {config_path}")
        return {}

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()

        if not content:
            return {}

        # First, try to parse as a single JSON object (pretty-printed JSON)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # If that fails, try JSONL format (one JSON object per line)
        configs = []
        for line in content.split('\n'):
            line = line.strip()
            if line:
                try:
                    configs.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # Skip invalid lines in JSONL

        if len(configs) == 1:
            return configs[0]
        elif len(configs) > 1:
            # Merge all configs, later ones override earlier
            merged = {}
            for cfg in configs:
                merged.update(cfg)
            return merged
        else:
            return {}
    except Exception as e:
        tool_logger.error(f"Failed to load prompt config {config_path}: {e}")
        return {}


def process_with_iterative_refinement(
    text: str,
    backend: LLMBackend,
    prompt_template: str,
    max_iterations: int = 3,
    **kwargs
) -> str:
    """
    Process text with iterative refinement using an LLM.

    Args:
        text: Input text to process
        backend: LLM backend to use
        prompt_template: Template for the prompt (use {text} placeholder)
        max_iterations: Maximum refinement iterations
        **kwargs: Additional arguments for prompt formatting

    Returns:
        Processed text after refinement
    """
    result = text
    for i in range(max_iterations):
        prompt = prompt_template.format(text=result, **kwargs)
        response = backend.process_text(result, prompt)
        if response == result:
            break  # No more changes
        result = response
    return result


def process_document_with_llm(
    document_path: Path,
    backend: LLMBackend,
    prompt_template: str,
    output_path: Path = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Process a single document with an LLM.

    Args:
        document_path: Path to the input document
        backend: LLM backend to use
        prompt_template: Template for the prompt
        output_path: Optional output path
        **kwargs: Additional arguments

    Returns:
        Result dictionary with processed content
    """
    text = read_text_file(document_path)
    if not text:
        return {"success": False, "error": f"Could not read {document_path}"}

    # Use process_text(text, prompt) - the standard LLM backend method
    response = backend.process_text(text, prompt_template)

    result = {
        "success": True,
        "source": str(document_path),
        "content": response
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response)
        result["output"] = str(output_path)

    return result


def process_folder_with_llm(
    folder_path: Path,
    files: List[Dict[str, Any]],
    llm: LLMBackend,
    prompt_config: Dict[str, Any],
    max_tokens: int = 1000,
    output_folder: Path = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Process all documents in a folder with an LLM using multi-step prompts.

    This function processes a collection of files through a series of LLM steps
    defined in the prompt_config. Each step can use results from previous steps.

    Args:
        folder_path: Path to the input folder
        files: List of file data dicts with 'path', 'content', 'page_num' keys
        llm: LLM backend to use
        prompt_config: Configuration dictionary with 'steps' key defining prompts
        max_tokens: Maximum tokens for processing
        output_folder: Optional output folder for results
        **kwargs: Additional arguments

    Returns:
        Result dictionary with all step outputs
    """
    import json

    folder_path = Path(folder_path)
    steps = prompt_config.get('steps', [])

    if not steps:
        tool_logger.warning("No steps defined in prompt_config")
        return {"success": False, "error": "No steps defined"}

    # Combine all file contents for folder-level processing
    combined_content = []
    for file_data in sorted(files, key=lambda x: x.get('page_num', 0)):
        page_num = file_data.get('page_num', 0)
        content = file_data.get('content', '')
        metadata = file_data.get('metadata', {})
        visual_desc = file_data.get('visual_description', '')

        page_text = f"--- Page {page_num} ---\n{content}"
        if metadata:
            page_text += f"\n[Metadata: {json.dumps(metadata, ensure_ascii=False)}]"
        if visual_desc:
            page_text += f"\n[Visual: {visual_desc}]"

        combined_content.append(page_text)

    full_text = "\n\n".join(combined_content)
    tool_logger.info(f"Combined {len(files)} files into {len(full_text)} characters")

    # Process through each step
    step_results = {}
    previous_results = ""

    for step in steps:
        step_name = step.get('name', 'unnamed_step')
        prompt_template = step.get('prompt', '')
        use_previous = step.get('use_previous', False)
        is_json = step.get('json', False)

        tool_logger.info(f"Processing step: {step_name}")

        # Build the text content to process
        text_content = full_text
        if use_previous and previous_results:
            text_content = f"{full_text}\n\n--- Previous Results ---\n{previous_results}"

        # Check if step has its own LLM config
        step_llm = llm
        if 'llm' in step:
            step_llm_config = step['llm']
            step_llm = get_llm_backend_from_config(step_llm_config)
            tool_logger.info(f"Using step-specific LLM: {step_llm.model_name}")

        try:
            # Use process_text method: process_text(text, prompt)
            # text = document content, prompt = instruction
            response = step_llm.process_text(text_content, prompt_template)

            # Parse JSON if expected
            if is_json:
                try:
                    # Try to extract JSON from response
                    response_text = response.strip()
                    if response_text.startswith('```'):
                        # Remove markdown code blocks
                        lines = response_text.split('\n')
                        response_text = '\n'.join(lines[1:-1] if lines[-1] == '```' else lines[1:])
                    step_results[step_name] = json.loads(response_text)
                except json.JSONDecodeError:
                    tool_logger.warning(f"Could not parse JSON for step {step_name}, storing as text")
                    step_results[step_name] = response
            else:
                step_results[step_name] = response

            # Update previous results for next step
            if isinstance(step_results[step_name], dict):
                previous_results = json.dumps(step_results[step_name], ensure_ascii=False, indent=2)
            else:
                previous_results = str(step_results[step_name])

            tool_logger.info(f"Step {step_name} complete")

        except Exception as e:
            tool_logger.error(f"Error in step {step_name}: {e}")
            step_results[step_name] = {"error": str(e)}

        # Cleanup step-specific LLM if created
        if 'llm' in step and hasattr(step_llm, 'cleanup'):
            step_llm.cleanup()

    # Save results if output folder specified
    if output_folder:
        output_folder = Path(output_folder)
        output_folder.mkdir(parents=True, exist_ok=True)

        # Save combined results
        results_file = output_folder / f"{folder_path.name}_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(step_results, f, ensure_ascii=False, indent=2)
        tool_logger.info(f"Results saved to: {results_file}")

        # Save individual step results
        steps_folder = output_folder / "steps"
        steps_folder.mkdir(parents=True, exist_ok=True)
        for step_name, result in step_results.items():
            step_file = steps_folder / f"{step_name}.json"
            with open(step_file, 'w', encoding='utf-8') as f:
                if isinstance(result, dict):
                    json.dump(result, f, ensure_ascii=False, indent=2)
                else:
                    json.dump({"result": result}, f, ensure_ascii=False, indent=2)

    return {
        "success": True,
        "folder": str(folder_path),
        "files_processed": len(files),
        "steps_completed": len(step_results),
        "results": step_results
    }


def _process_folder_with_llm_simple(
    folder_path: Path,
    backend: LLMBackend,
    prompt_template: str,
    output_folder: Path = None,
    file_pattern: str = "*.txt",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Simple folder processing - processes each file individually.

    Args:
        folder_path: Path to the input folder
        backend: LLM backend to use
        prompt_template: Template for the prompt
        output_folder: Optional output folder
        file_pattern: Glob pattern for files to process
        **kwargs: Additional arguments

    Returns:
        List of result dictionaries
    """
    folder_path = Path(folder_path)
    results = []

    for file_path in folder_path.glob(file_pattern):
        output_path = None
        if output_folder:
            output_path = Path(output_folder) / file_path.name

        result = process_document_with_llm(
            file_path, backend, prompt_template, output_path, **kwargs
        )
        results.append(result)

    return results


class LLMProcessor:
    """
    Handles LLM processing with consistent initialization and logging.

    Used by LLMProcessScript to set up processing environment.
    """

    def __init__(
        self,
        input_folder: Path,
        output_folder: Path,
        prompt_config: Dict,
        llm: LLMBackend,
        max_tokens: int = 1000,
        input_manifest: Optional[Path] = None
    ):
        """
        Initialize LLM processor.

        Args:
            input_folder: Path to input documents
            output_folder: Path for output files
            prompt_config: Configuration dictionary with prompts and steps
            llm: LLM backend instance
            max_tokens: Maximum tokens for processing
            input_manifest: Optional path to input manifest file
        """
        # Validate input parameters
        input_folder = Path(input_folder)
        output_folder = Path(output_folder)

        if not input_folder.exists():
            raise ValueError(f"Input folder does not exist: {input_folder}")

        if not isinstance(prompt_config, dict):
            raise ValueError("prompt_config must be a dictionary")

        if "steps" not in prompt_config:
            raise ValueError("prompt_config must contain 'steps' key")

        if input_manifest and not Path(input_manifest).exists():
            raise ValueError(f"Input manifest does not exist: {input_manifest}")

        # Initialize instance variables
        self.input_folder = input_folder
        self.output_folder = output_folder
        self.prompt_config = prompt_config
        self.llm = llm
        self.max_tokens = max_tokens
        self.input_manifest = input_manifest

        # Create all required output directories
        self.steps_folder = output_folder / "steps"
        self.chunks_folder = output_folder / "chunks"
        self.documents_folder = output_folder / "documents"

        for folder in [self.steps_folder, self.chunks_folder, self.documents_folder]:
            folder.mkdir(parents=True, exist_ok=True)

        # Initialize manifest processor only if manifest provided
        if input_manifest:
            try:
                self.manifest_proc = ManifestProcessor(
                    manifest_path=input_manifest,
                    progress_file=output_folder / "llm_process_progress.jsonl"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to initialize manifest processor: {str(e)}")
        else:
            self.manifest_proc = None

        # Log initialization
        tool_logger.info(f"Initialized LLMProcessor:")
        tool_logger.info(f"  Input folder: {input_folder}")
        tool_logger.info(f"  Output folder: {output_folder}")
        tool_logger.info(f"  Steps folder: {self.steps_folder}")
        tool_logger.info(f"  Chunks folder: {self.chunks_folder}")
        tool_logger.info(f"  Documents folder: {self.documents_folder}")
        tool_logger.info(f"  Max tokens: {max_tokens}")
        tool_logger.info(f"  Model: {llm.model_name}")
        tool_logger.info(f"  Steps configured: {len(prompt_config.get('steps', []))}")

    def cleanup(self):
        """Clean up backend resources."""
        if hasattr(self.llm, 'cleanup'):
            self.llm.cleanup()
