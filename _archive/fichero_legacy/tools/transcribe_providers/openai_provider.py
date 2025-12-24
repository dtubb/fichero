"""
OpenAI-compatible API provider.

Works with any OpenAI-compatible endpoint, including:
- DashScope OpenAI-compatible mode
- OpenAI GPT-4 Vision
- Other compatible services

This provider is useful for quick migration from existing OpenAI integrations,
but has limitations compared to native SDK providers.
"""

import base64
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from .base_provider import BaseTranscriptionProvider

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
    tool_logger = get_tool_logger('openai_provider')
except ImportError:
    import logging
    tool_logger = logging.getLogger('openai_provider')


class OpenAIProvider(BaseTranscriptionProvider):
    """
    OpenAI-compatible API provider.

    Features:
    - Works with any OpenAI-compatible endpoint
    - Configurable model and parameters
    - Parallel processing support
    - Simple integration for existing OpenAI users

    Limitations:
    - No advanced features (auto-rotation, built-in OCR tasks)
    - Must manually handle prompts and parsing
    """

    DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    DEFAULT_MODEL = "qwen-vl-ocr"
    DEFAULT_PROMPT = (
        "Extract all text from this image. Return only the text content, "
        "line by line, without numbering or additional commentary. "
        "If there is no readable text, return an empty response."
    )

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = DEFAULT_MODEL,
        prompt: Optional[str] = None,
        stream: bool = False,
        min_pixels: int = 3136,  # 28*28*4
        max_pixels: int = 6422528,  # 28*28*8192
        timeout: float = 180.0,
        **config
    ):
        """
        Initialize OpenAI-compatible provider.

        Args:
            api_key: API key for the service
            base_url: Base URL for API endpoint
            model: Model name
            prompt: Custom prompt for extraction
            stream: Enable streaming responses
            min_pixels: Minimum pixels for image scaling
            max_pixels: Maximum pixels for image scaling
            timeout: Request timeout in seconds
            **config: Additional configuration
        """
        super().__init__(api_key, **config)

        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI SDK not available. Install with: pip install openai")

        self.base_url = base_url or self.DEFAULT_BASE_URL
        self.model_name = model
        self.prompt_text = prompt or self.DEFAULT_PROMPT
        self.stream = stream
        self.min_pixels = min_pixels
        self.max_pixels = max_pixels
        self.timeout = timeout

        # Initialize sync client
        self.client = OpenAI(
            api_key=api_key,
            base_url=self.base_url,
            timeout=timeout
        )

        # Async client is created lazily to ensure it's in the correct event loop
        # This prevents issues when running in worker threads with new event loops
        self._async_client = None
        self._async_client_loop = None

    def _get_async_client(self) -> AsyncOpenAI:
        """
        Get or create the async client for the current event loop.

        AsyncOpenAI clients are tied to the event loop they're created in.
        When running in worker threads with new event loops, we need to
        create a fresh client for that loop.
        """
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        # Create new client if none exists or if we're in a different loop
        if self._async_client is None or self._async_client_loop != current_loop:
            # Close old client if it exists
            if self._async_client is not None:
                try:
                    self._async_client.close()
                except Exception:
                    pass

            tool_logger.debug(f"Creating new AsyncOpenAI client for event loop {id(current_loop)}")
            self._async_client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout
            )
            self._async_client_loop = current_loop

        return self._async_client

    @property
    def name(self) -> str:
        return f"OpenAI-compatible ({self.model_name})"

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def supports_parallel(self) -> bool:
        # OpenAI-compatible APIs generally support parallel requests
        return True

    @property
    def supports_async(self) -> bool:
        """OpenAI-compatible APIs support async processing"""
        return True

    @property
    def max_file_size_mb(self) -> int:
        return 10

    @property
    def provider_name(self) -> str:
        """Return provider service name"""
        # Determine provider from base_url
        if "dashscope" in self.base_url.lower():
            return "dashscope"
        elif "openai.com" in self.base_url.lower():
            return "openai"
        else:
            return "openai-compatible"

    @property
    def api_endpoint(self) -> str:
        """Return API endpoint URL"""
        return self.base_url

    def get_api_parameters(self) -> Dict[str, Any]:
        """Get API parameters used"""
        return {
            'stream': self.stream,
            'min_pixels': self.min_pixels,
            'max_pixels': self.max_pixels,
            'timeout': self.timeout
        }

    def _encode_image_base64(self, image_path: Path) -> Optional[str]:
        """
        Encode image to base64.

        Args:
            image_path: Path to image file

        Returns:
            Base64 encoded string or None on error
        """
        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()
                return base64.b64encode(image_data).decode('utf-8')
        except Exception as e:
            tool_logger.error(f"Error encoding image {image_path}: {e}")
            return None

    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """
        Process a single image using OpenAI-compatible API.

        Args:
            image_path: Path to image file

        Returns:
            Result dictionary with text, success status, and details
        """
        try:
            # Validate file size
            file_size_mb = image_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.max_file_size_mb:
                error_msg = f"File exceeds {self.max_file_size_mb}MB size limit ({file_size_mb:.1f}MB)"
                tool_logger.warning(error_msg)
                return {
                    "text": "",
                    "success": False,
                    "error": error_msg,
                    "details": {}
                }

            tool_logger.info(f"Processing: {image_path.name}")

            # Encode image
            base64_image = self._encode_image_base64(image_path)
            if not base64_image:
                return {
                    "text": "",
                    "success": False,
                    "error": "Failed to encode image",
                    "details": {}
                }

            # Build message content
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": self.prompt_text
                }
            ]

            # Retry logic
            max_retries = 3
            retry_delay = 1.0
            response_text = ""
            tokens_used = 0

            for attempt in range(max_retries):
                try:
                    if self.stream:
                        # Streaming response
                        stream_response = self.client.chat.completions.create(
                            model=self.model_name,
                            messages=[{
                                "role": "user",
                                "content": content
                            }],
                            stream=True,
                            extra_body={
                                "min_pixels": self.min_pixels,
                                "max_pixels": self.max_pixels
                            }
                        )

                        # Collect streamed chunks
                        for chunk in stream_response:
                            if chunk.choices[0].delta.content:
                                response_text += chunk.choices[0].delta.content

                    else:
                        # Non-streaming response
                        response = self.client.chat.completions.create(
                            model=self.model_name,
                            messages=[{
                                "role": "user",
                                "content": content
                            }],
                            extra_body={
                                "min_pixels": self.min_pixels,
                                "max_pixels": self.max_pixels
                            }
                        )

                        response_text = response.choices[0].message.content

                        # Get token usage if available
                        if hasattr(response, 'usage'):
                            tokens_used = response.usage.total_tokens

                    # Success
                    break

                except Exception as e:
                    if attempt < max_retries - 1:
                        tool_logger.warning(
                            f"API call failed for {image_path.name} "
                            f"(attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        tool_logger.info(f"Retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        error_msg = f"API call failed after {max_retries} attempts: {e}"
                        tool_logger.error(error_msg)
                        return {
                            "text": "",
                            "success": False,
                            "error": error_msg,
                            "details": {}
                        }

            tool_logger.success(f"Completed: {image_path.name}")

            return {
                "text": response_text,
                "success": True,
                "details": {
                    "has_content": bool(response_text.strip()),
                    "text_length": len(response_text.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": self.model_name,
                    "num_lines": len(response_text.strip().split('\n')),
                    "tokens": tokens_used
                }
            }

        except Exception as e:
            error_msg = str(e)
            tool_logger.error(f"Error processing {image_path.name}: {error_msg}")
            return {
                "text": "",
                "success": False,
                "error": error_msg,
                "details": {}
            }

    async def process_image_async(
        self,
        image_path: Path,
        semaphore: Optional[asyncio.Semaphore] = None
    ) -> Dict[str, Any]:
        """
        Process a single image using OpenAI-compatible API with async/await.

        Args:
            image_path: Path to image file
            semaphore: Optional semaphore for rate limiting

        Returns:
            Result dictionary with text, success status, and details
        """
        # Use semaphore if provided
        if semaphore:
            async with semaphore:
                return await self._process_image_async_internal(image_path)
        else:
            return await self._process_image_async_internal(image_path)

    async def _process_image_async_internal(self, image_path: Path) -> Dict[str, Any]:
        """Internal async processing implementation"""
        try:
            # Validate file size
            file_size_mb = image_path.stat().st_size / (1024 * 1024)
            if file_size_mb > self.max_file_size_mb:
                error_msg = f"File exceeds {self.max_file_size_mb}MB size limit ({file_size_mb:.1f}MB)"
                tool_logger.warning(error_msg)
                return {
                    "text": "",
                    "success": False,
                    "error": error_msg,
                    "details": {}
                }

            tool_logger.info(f"Processing async: {image_path.name}")

            # Encode image
            base64_image = self._encode_image_base64(image_path)
            if not base64_image:
                return {
                    "text": "",
                    "success": False,
                    "error": "Failed to encode image",
                    "details": {}
                }

            # Build message content
            content = [
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}"
                    }
                },
                {
                    "type": "text",
                    "text": self.prompt_text
                }
            ]

            # Retry logic
            max_retries = 3
            retry_delay = 1.0
            response_text = ""
            tokens_used = 0

            for attempt in range(max_retries):
                try:
                    # Use lazy async client to ensure correct event loop binding
                    async_client = self._get_async_client()

                    if self.stream:
                        # Streaming response
                        stream_response = await async_client.chat.completions.create(
                            model=self.model_name,
                            messages=[{
                                "role": "user",
                                "content": content
                            }],
                            stream=True,
                            extra_body={
                                "min_pixels": self.min_pixels,
                                "max_pixels": self.max_pixels
                            }
                        )

                        # Collect streamed chunks
                        async for chunk in stream_response:
                            if chunk.choices[0].delta.content:
                                response_text += chunk.choices[0].delta.content

                    else:
                        # Non-streaming response with timeout
                        response = await asyncio.wait_for(
                            async_client.chat.completions.create(
                                model=self.model_name,
                                messages=[{
                                    "role": "user",
                                    "content": content
                                }],
                                extra_body={
                                    "min_pixels": self.min_pixels,
                                    "max_pixels": self.max_pixels
                                }
                            ),
                            timeout=self.timeout
                        )

                        response_text = response.choices[0].message.content

                        # Get token usage if available
                        if hasattr(response, 'usage'):
                            tokens_used = response.usage.total_tokens

                    # Success
                    break

                except asyncio.TimeoutError:
                    if attempt < max_retries - 1:
                        tool_logger.warning(
                            f"Async API call timed out for {image_path.name} "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        tool_logger.info(f"Retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        error_msg = f"API call timed out after {max_retries} attempts"
                        tool_logger.error(error_msg)
                        return {
                            "text": "",
                            "success": False,
                            "error": error_msg,
                            "details": {}
                        }

                except Exception as e:
                    if attempt < max_retries - 1:
                        tool_logger.warning(
                            f"Async API call failed for {image_path.name} "
                            f"(attempt {attempt + 1}/{max_retries}): {e}"
                        )
                        tool_logger.info(f"Retrying in {retry_delay}s...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        error_msg = f"API call failed after {max_retries} attempts: {e}"
                        tool_logger.error(error_msg)
                        return {
                            "text": "",
                            "success": False,
                            "error": error_msg,
                            "details": {}
                        }

            tool_logger.info(f"Completed async: {image_path.name}")

            return {
                "text": response_text,
                "success": True,
                "details": {
                    "has_content": bool(response_text.strip()),
                    "text_length": len(response_text.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": self.model_name,
                    "num_lines": len(response_text.strip().split('\n')),
                    "tokens": tokens_used,
                    "async_processing": True
                }
            }

        except Exception as e:
            error_msg = str(e)
            tool_logger.error(f"Error processing async {image_path.name}: {error_msg}")
            return {
                "text": "",
                "success": False,
                "error": error_msg,
                "details": {}
            }

    def validate_config(self) -> bool:
        """Validate OpenAI provider configuration"""
        if not self.api_key:
            tool_logger.error("API key required")
            return False

        return True

    def cleanup(self):
        """Clean up OpenAI client resources"""
        if hasattr(self, 'client'):
            try:
                self.client.close()
            except:
                pass

        if hasattr(self, '_async_client') and self._async_client is not None:
            try:
                # Try sync close (works in newer openai versions)
                self._async_client.close()
            except:
                pass
            self._async_client = None
            self._async_client_loop = None

    async def cleanup_async(self):
        """Async cleanup for OpenAI client resources"""
        if hasattr(self, '_async_client') and self._async_client is not None:
            try:
                await self._async_client.close()
            except:
                pass
            self._async_client = None
            self._async_client_loop = None
