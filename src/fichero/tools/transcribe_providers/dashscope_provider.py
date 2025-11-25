"""
DashScope SDK provider for Qwen VL models.

Supports:
- qwen-vl-max (high quality, slower)
- qwen-vl-ocr (OCR optimized, streaming)
- qwen3-vl-235b-a22b-instruct (latest flagship model)

Uses the official DashScope SDK with advanced features like automatic
image rotation and built-in OCR tasks.
"""

import base64
import time
import asyncio
from pathlib import Path
from PIL import Image
from io import BytesIO
from typing import Dict, Any, Optional
from datetime import datetime
from openai import OpenAI, AsyncOpenAI

from .base_provider import BaseTranscriptionProvider

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
    tool_logger = get_tool_logger('dashscope_provider')
except ImportError:
    import logging
    tool_logger = logging.getLogger('dashscope_provider')


class DashScopeProvider(BaseTranscriptionProvider):
    """
    DashScope provider using OpenAI-compatible SDK.

    Features:
    - Multiple model support (qwen-vl-max, qwen-vl-ocr, etc.)
    - Progressive image resizing on timeout
    - Parallel processing support
    - Automatic retry with exponential backoff
    """

    DEFAULT_MODELS = {
        "qwen-vl-max": "qwen3-vl-235b-a22b-instruct",
        "qwen-vl-ocr": "qwen-vl-ocr",
        "qwen3-vl-flash": "qwen3-vl-flash"
    }

    DEFAULT_PROMPTS = {
        "qwen-vl-max": (
            "Extract all text line by line. Do not number lines. "
            "SKIP UNREADABLE TEXT. PUT IN SQUARE BRACKETS [GUESSES AND UNCERTAIN] TEXT. "
            "RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. "
            "DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, OR GIBBERISH. "
            "RETURN EMPTY IF NO TEXT. SAY NOTHING ELSE."
        ),
        "qwen-vl-ocr": (
            "Extract all text line by line. Do not number lines. "
            "SKIP UNREADABLE TEXT. PUT IN SQUARE BRACKETS [GUESSES AND UNCERTAIN] TEXT. "
            "RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. "
            "DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, OR GIBBERISH. "
            "RETURN EMPTY IF NO TEXT. SAY NOTHING ELSE."
        )
    }

    # Multi-image batch limits by model
    MULTI_IMAGE_LIMITS = {
        "qwen3-vl-235b-a22b-instruct": (4, 512),  # min, max
        "qwen3-vl-flash": (4, 512),
        "qwen-vl-ocr": (4, 80),
        "default": (4, 80)
    }

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-vl-max",
        prompt: Optional[str] = None,
        max_size: int = 1024,
        streaming: bool = False,
        timeout: float = 180.0,
        **config
    ):
        """
        Initialize DashScope provider.

        Args:
            api_key: DashScope API key
            model: Model to use ("qwen-vl-max", "qwen-vl-ocr", or full model name)
            prompt: Custom prompt (uses default if not provided)
            max_size: Maximum image dimension in pixels
            streaming: Enable streaming responses (qwen-vl-ocr only)
            timeout: API request timeout in seconds
            **config: Additional configuration
        """
        super().__init__(api_key, **config)

        # Resolve model name
        self.model_name = self.DEFAULT_MODELS.get(model, model)
        self.model_key = model  # Keep original key for prompt lookup

        # Set prompt
        if prompt:
            self.prompt = prompt
        else:
            self.prompt = self.DEFAULT_PROMPTS.get(model, self.DEFAULT_PROMPTS["qwen-vl-max"])

        self.max_size = max_size
        self.streaming = streaming
        self.timeout = timeout

        # Initialize OpenAI clients (sync and async)
        self.client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=timeout
        )

        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
            timeout=timeout
        )

    @property
    def name(self) -> str:
        return f"DashScope ({self.model_key})"

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def supports_parallel(self) -> bool:
        # DashScope supports parallel requests
        return True

    @property
    def supports_async(self) -> bool:
        """DashScope supports async processing with AsyncOpenAI"""
        return True

    @property
    def max_file_size_mb(self) -> int:
        # DashScope can handle larger files
        return 20

    @property
    def supports_multi_image(self) -> bool:
        """DashScope Qwen-VL supports multi-image batching"""
        return True

    @property
    def max_images_per_batch(self) -> int:
        """Maximum images per batch based on model"""
        limits = self.MULTI_IMAGE_LIMITS.get(self.model_name, self.MULTI_IMAGE_LIMITS["default"])
        return limits[1]

    @property
    def min_images_per_batch(self) -> int:
        """Minimum images per batch (4 for Qwen-VL)"""
        limits = self.MULTI_IMAGE_LIMITS.get(self.model_name, self.MULTI_IMAGE_LIMITS["default"])
        return limits[0]

    def _encode_image(self, image: Image.Image, max_size: int) -> str:
        """
        Encode image to base64 with resizing.

        Args:
            image: PIL Image object
            max_size: Maximum dimension in pixels

        Returns:
            Base64 encoded JPEG string, or empty string for invalid images
        """
        width, height = image.size
        aspect_ratio = max(width, height) / float(min(width, height))

        # Skip extremely wide/tall images
        if aspect_ratio > 200:
            tool_logger.warning(f"Skipping image with extreme aspect ratio: {aspect_ratio:.1f}")
            return ""

        # Resize if needed
        if width > max_size or height > max_size:
            if width > height:
                new_width = max_size
                new_height = int((max_size / width) * height)
            else:
                new_height = max_size
                new_width = int((max_size / height) * width)
            image = image.resize((new_width, new_height), Image.LANCZOS)
            tool_logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height} (max_size={max_size})")

        # Encode with compression
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=80)
        encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
        size_kb = len(encoded) / 1024
        tool_logger.info(f"Encoded image size: {size_kb:.1f} KB (max_size={max_size})")
        return encoded

    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """
        Process a single image using DashScope API.

        Args:
            image_path: Path to image file

        Returns:
            Result dictionary with text, success status, and details
        """
        try:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Processing: {image_path.name}")

            # Load image
            try:
                image = Image.open(image_path).convert("RGB")
                orig_width, orig_height = image.size
                tool_logger.info(f"Original image size: {orig_width}x{orig_height}")
            except Exception as e:
                tool_logger.error(f"Failed to open image {image_path}: {e}")
                return {
                    "text": "",
                    "success": False,
                    "error": f"Failed to open image: {e}",
                    "details": {}
                }

            # Progressive size reduction for timeouts
            size_attempts = [self.max_size, 768, 512, 256]
            completion = None

            for size_index, max_size in enumerate(size_attempts):
                # Encode image at current size
                base64_image = self._encode_image(image, max_size=max_size)

                if not base64_image:
                    tool_logger.warning(f"Failed to encode image at size {max_size}, trying next size")
                    continue

                # Retry logic at this size
                max_retries = 2
                retry_delay = 1.0

                for attempt in range(max_retries):
                    try:
                        size_msg = f" (size={max_size}px)" if size_index > 0 else ""
                        tool_logger.info(f"🌐 Calling {self.model_key} API{size_msg} (attempt {attempt + 1}/{max_retries})")

                        # API call
                        completion = self.client.chat.completions.create(
                            model=self.model_name,
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                    {"type": "text", "text": self.prompt}
                                ]
                            }],
                            timeout=self.timeout
                        )
                        tool_logger.info(f"✅ API call succeeded for: {image_path.name}")
                        break  # Success - exit retry loop

                    except Exception as api_error:
                        error_str = str(api_error).lower()

                        # Check for fatal errors
                        is_auth_error = "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str
                        if is_auth_error:
                            tool_logger.error(f"🔑 FATAL: Invalid API key error: {api_error}")
                            raise ValueError(f"Invalid API key - processing stopped: {api_error}")

                        # Check for timeout - try smaller size
                        is_timeout = "timeout" in error_str or "timed out" in error_str
                        if is_timeout and size_index < len(size_attempts) - 1:
                            next_size = size_attempts[size_index + 1]
                            tool_logger.warning(f"⏱️ Timeout at size {max_size}px, will try {next_size}px")
                            break  # Break retry loop, continue to next size

                        # Standard retry
                        if attempt < max_retries - 1:
                            tool_logger.warning(f"API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                            tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            # Last attempt at this size
                            if size_index >= len(size_attempts) - 1:
                                # No more sizes to try
                                error_msg = f"API call failed after trying all sizes: {api_error}"
                                tool_logger.error(f"❌ {error_msg}")
                                return {
                                    "text": "",
                                    "success": False,
                                    "error": error_msg,
                                    "details": {}
                                }
                            else:
                                # Try next smaller size
                                tool_logger.warning(f"⚠️ Failed at size {max_size}px, trying smaller size")
                                break

                # Check if we got completion at this size
                if completion:
                    break

            # Check if we got a completion
            if not completion:
                error_msg = "Failed to get response after trying all image sizes"
                tool_logger.error(f"❌ {error_msg}")
                return {
                    "text": "",
                    "success": False,
                    "error": error_msg,
                    "details": {}
                }

            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Received response for: {image_path.name}")

            # Extract transcription
            transcription = completion.choices[0].message.content

            return {
                "text": transcription,
                "success": True,
                "details": {
                    "has_content": bool(transcription.strip()),
                    "text_length": len(transcription.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": self.model_name,
                    "num_lines": len(transcription.strip().split('\n')),
                    "original_size": f"{orig_width}x{orig_height}"
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
        Process a single image using DashScope API with async/await.

        This method uses AsyncOpenAI for true non-blocking I/O, enabling
        high concurrency (15+ concurrent requests) without thread overhead.

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
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Processing async: {image_path.name}")

            # Load image (sync I/O - PIL doesn't have async)
            try:
                image = Image.open(image_path).convert("RGB")
                orig_width, orig_height = image.size
                tool_logger.info(f"Original image size: {orig_width}x{orig_height}")
            except Exception as e:
                tool_logger.error(f"Failed to open image {image_path}: {e}")
                return {
                    "text": "",
                    "success": False,
                    "error": f"Failed to open image: {e}",
                    "details": {}
                }

            # Progressive size reduction for timeouts
            size_attempts = [self.max_size, 768, 512, 256]
            completion = None

            for size_index, max_size in enumerate(size_attempts):
                # Encode image at current size
                base64_image = self._encode_image(image, max_size=max_size)

                if not base64_image:
                    tool_logger.warning(f"Failed to encode image at size {max_size}, trying next size")
                    continue

                # Retry logic at this size
                max_retries = 2
                retry_delay = 1.0

                for attempt in range(max_retries):
                    try:
                        size_msg = f" (size={max_size}px)" if size_index > 0 else ""
                        tool_logger.info(f"🌐 Calling {self.model_key} API async{size_msg} (attempt {attempt + 1}/{max_retries})")

                        # Async API call with timeout
                        completion = await asyncio.wait_for(
                            self.async_client.chat.completions.create(
                                model=self.model_name,
                                messages=[{
                                    "role": "user",
                                    "content": [
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                                        {"type": "text", "text": self.prompt}
                                    ]
                                }]
                            ),
                            timeout=self.timeout
                        )
                        tool_logger.info(f"✅ Async API call succeeded for: {image_path.name}")
                        break  # Success - exit retry loop

                    except asyncio.TimeoutError:
                        tool_logger.warning(f"⏱️ Timeout at size {max_size}px")
                        if size_index < len(size_attempts) - 1:
                            next_size = size_attempts[size_index + 1]
                            tool_logger.warning(f"Will try {next_size}px")
                            break  # Break retry loop, continue to next size
                        else:
                            raise

                    except Exception as api_error:
                        error_str = str(api_error).lower()

                        # Check for fatal errors
                        is_auth_error = "401" in error_str or "unauthorized" in error_str or "invalid_api_key" in error_str
                        if is_auth_error:
                            tool_logger.error(f"🔑 FATAL: Invalid API key error: {api_error}")
                            raise ValueError(f"Invalid API key - processing stopped: {api_error}")

                        # Standard retry
                        if attempt < max_retries - 1:
                            tool_logger.warning(f"Async API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                            tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2
                        else:
                            # Last attempt at this size
                            if size_index >= len(size_attempts) - 1:
                                # No more sizes to try
                                error_msg = f"Async API call failed after trying all sizes: {api_error}"
                                tool_logger.error(f"❌ {error_msg}")
                                return {
                                    "text": "",
                                    "success": False,
                                    "error": error_msg,
                                    "details": {}
                                }
                            else:
                                # Try next smaller size
                                tool_logger.warning(f"⚠️ Failed at size {max_size}px, trying smaller size")
                                break

                # Check if we got completion at this size
                if completion:
                    break

            # Check if we got a completion
            if not completion:
                error_msg = "Failed to get response after trying all image sizes"
                tool_logger.error(f"❌ {error_msg}")
                return {
                    "text": "",
                    "success": False,
                    "error": error_msg,
                    "details": {}
                }

            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Received async response for: {image_path.name}")

            # Extract transcription
            transcription = completion.choices[0].message.content

            return {
                "text": transcription,
                "success": True,
                "details": {
                    "has_content": bool(transcription.strip()),
                    "text_length": len(transcription.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": self.model_name,
                    "num_lines": len(transcription.strip().split('\n')),
                    "original_size": f"{orig_width}x{orig_height}",
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
        """Validate DashScope configuration"""
        if not self.api_key:
            tool_logger.error("DashScope API key required")
            return False

        # Test API key
        try:
            tool_logger.info("🔑 Testing API key validity...")
            test_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{
                    "role": "user",
                    "content": [{"type": "text", "text": "test"}]
                }],
                timeout=30
            )
            tool_logger.info("✅ API key validated successfully")
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "401" in error_str or "unauthorized" in error_str:
                tool_logger.error(f"🔑 Invalid API key: {e}")
                return False
            else:
                tool_logger.warning(f"⚠️ API key test failed (but may be transient): {e}")
                return True  # Allow processing to continue

    def process_multi_image(self, image_paths: list[Path]) -> list[Dict[str, Any]]:
        """
        Process multiple images in a single API request.

        This leverages Qwen-VL's multi-image capability to process 4-512 images
        in one request, reducing API calls and costs.

        Args:
            image_paths: List of 4-512 image file paths

        Returns:
            List of result dictionaries, one per image

        Raises:
            ValueError: If image count is outside valid range
        """
        num_images = len(image_paths)

        # Validate image count
        if num_images < self.min_images_per_batch:
            raise ValueError(
                f"Multi-image batch requires at least {self.min_images_per_batch} images, "
                f"got {num_images}. Use process_image() for fewer images."
            )

        if num_images > self.max_images_per_batch:
            raise ValueError(
                f"Multi-image batch cannot exceed {self.max_images_per_batch} images, "
                f"got {num_images}. Split into smaller batches."
            )

        tool_logger.info(f"Processing {num_images} images in multi-image batch")

        try:
            # Build content with all images
            content = []

            # Add all images
            for idx, img_path in enumerate(image_paths):
                try:
                    image = Image.open(img_path).convert("RGB")
                    base64_image = self._encode_image(image, max_size=self.max_size)

                    if not base64_image:
                        tool_logger.warning(f"Failed to encode image {idx + 1}/{num_images}: {img_path.name}")
                        continue

                    content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    })

                except Exception as e:
                    tool_logger.error(f"Error loading image {idx + 1}/{num_images} ({img_path.name}): {e}")
                    continue

            # Add prompt with numbering instruction
            multi_image_prompt = (
                f"{self.prompt}\n\n"
                f"You are processing {len(content)} images. "
                f"For each image, return the transcription preceded by '=== IMAGE N ===' "
                f"where N is the image number (1-{len(content)}). "
                f"Separate each image's transcription with a blank line."
            )

            content.append({
                "type": "text",
                "text": multi_image_prompt
            })

            # Make API call with retry
            max_retries = 2
            retry_delay = 1.0
            completion = None

            for attempt in range(max_retries):
                try:
                    tool_logger.info(f"🌐 Calling {self.model_key} API with {len(content) - 1} images (attempt {attempt + 1}/{max_retries})")

                    completion = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{
                            "role": "user",
                            "content": content
                        }],
                        timeout=self.timeout * 2  # Double timeout for multi-image
                    )

                    tool_logger.info(f"✅ Multi-image API call succeeded")
                    break

                except Exception as api_error:
                    if attempt < max_retries - 1:
                        tool_logger.warning(f"Multi-image API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        raise

            if not completion:
                raise ValueError("Failed to get API response after retries")

            # Parse combined transcription
            combined_text = completion.choices[0].message.content
            results = self._parse_multi_image_response(combined_text, image_paths)

            return results

        except Exception as e:
            error_msg = f"Multi-image batch processing failed: {e}"
            tool_logger.error(error_msg)

            # Return error result for each image
            return [{
                "text": "",
                "success": False,
                "error": error_msg,
                "details": {}
            } for _ in image_paths]

    def _parse_multi_image_response(self, combined_text: str, image_paths: list[Path]) -> list[Dict[str, Any]]:
        """
        Parse combined multi-image response into individual results.

        Args:
            combined_text: Combined transcription from API
            image_paths: Original image paths (for result ordering)

        Returns:
            List of result dictionaries
        """
        results = []
        num_images = len(image_paths)

        # Split by image markers
        import re
        sections = re.split(r'===\s*IMAGE\s+(\d+)\s*===', combined_text)

        # Process sections (format: [preamble, "1", text1, "2", text2, ...])
        parsed_texts = {}
        for i in range(1, len(sections), 2):
            if i + 1 < len(sections):
                img_num = int(sections[i])
                img_text = sections[i + 1].strip()
                parsed_texts[img_num] = img_text

        # Create results in original order
        for idx, img_path in enumerate(image_paths):
            img_num = idx + 1
            text = parsed_texts.get(img_num, "")

            # If no marker found, try to split by blank lines as fallback
            if not parsed_texts:
                parts = combined_text.split('\n\n')
                text = parts[idx].strip() if idx < len(parts) else ""

            results.append({
                "text": text,
                "success": True,
                "details": {
                    "has_content": bool(text.strip()),
                    "text_length": len(text.strip()),
                    "processed_at": datetime.now().isoformat(),
                    "model": self.model_name,
                    "num_lines": len(text.strip().split('\n')),
                    "multi_image_batch": True,
                    "batch_position": idx + 1,
                    "batch_size": num_images
                }
            })

        return results

    def cleanup(self):
        """Clean up DashScope resources"""
        if hasattr(self, 'client'):
            try:
                self.client.close()
            except:
                pass

        if hasattr(self, 'async_client'):
            try:
                # AsyncOpenAI cleanup needs to be done in async context
                # The caller should use await async_client.close() if possible
                pass
            except:
                pass

    async def cleanup_async(self):
        """Async cleanup for DashScope resources"""
        if hasattr(self, 'async_client'):
            try:
                await self.async_client.close()
            except:
                pass
