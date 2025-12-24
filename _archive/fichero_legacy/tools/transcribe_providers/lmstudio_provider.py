"""
LMStudio provider for local transcription.

Connects to a local LMStudio instance for transcription using locally-hosted models.
Good for privacy-sensitive documents or offline processing.
"""

import base64
import time
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO
from typing import Dict, Any, Optional
from datetime import datetime

from .base_provider import BaseTranscriptionProvider

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
    tool_logger = get_tool_logger('lmstudio_provider')
except ImportError:
    import logging
    tool_logger = logging.getLogger('lmstudio_provider')


class LMStudioProvider(BaseTranscriptionProvider):
    """
    LMStudio provider for local transcription.

    Features:
    - Local processing (no cloud API required)
    - Privacy-focused
    - Configurable model selection

    Limitations:
    - Slower than cloud APIs
    - Limited to models available in LMStudio
    - Sequential processing recommended (parallel can overload local machine)
    """

    DEFAULT_API_URL = "http://localhost:1234/v1"
    DEFAULT_MAX_SIZE = 1024  # Smaller for local processing
    DEFAULT_PROMPT = (
        "Extract all text line by line. Do not number lines. "
        "RETURN ONLY PLAIN TEXT. RETURN NOTHING IF NOT TEXT. SAY NOTHING ELSE. "
        "DO NOT PROCESS REVERSED TEXT, MIRRORED TEXT, GIBBERISH, OR TEXT IN LANGUAGE YOU DO NOT RECOGNIZE. "
        "RETURN EMPTY IF NOT TEXT."
    )

    def __init__(
        self,
        api_url: Optional[str] = None,
        model_name: str = None,
        prompt: Optional[str] = None,
        max_size: int = DEFAULT_MAX_SIZE,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        timeout: float = 180.0,
        **config
    ):
        """
        Initialize LMStudio provider.

        Args:
            api_url: LMStudio API URL (default: http://localhost:1234/v1)
            model_name: Model name in LMStudio (required)
            prompt: Custom prompt for extraction
            max_size: Maximum image dimension in pixels
            max_tokens: Maximum response tokens
            temperature: Model temperature
            timeout: Request timeout in seconds
            **config: Additional configuration
        """
        super().__init__(api_key=None, **config)  # LMStudio doesn't need API key

        # Ensure API URL ends with /v1
        self.api_url = api_url or self.DEFAULT_API_URL
        if not self.api_url.endswith('/v1'):
            self.api_url = f"{self.api_url}/v1"

        if not model_name:
            raise ValueError("model_name is required for LMStudio provider")

        self.model_name = model_name
        self.prompt_text = prompt or self.DEFAULT_PROMPT
        self.max_size = max_size
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout

        # Create session for connection pooling
        self.session = requests.Session()

    @property
    def name(self) -> str:
        return f"LMStudio ({self.model_name})"

    @property
    def model(self) -> str:
        return self.model_name

    @property
    def supports_parallel(self) -> bool:
        # LMStudio runs locally - sequential processing recommended
        return False

    @property
    def max_file_size_mb(self) -> int:
        # Smaller files for local processing
        return 5

    @property
    def provider_name(self) -> str:
        """Return provider service name"""
        return "lmstudio"

    @property
    def api_endpoint(self) -> str:
        """Return API endpoint URL"""
        return self.api_url

    def get_api_parameters(self) -> Dict[str, Any]:
        """Get API parameters used"""
        return {
            'max_size': self.max_size,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'timeout': self.timeout
        }

    def _encode_image(self, image: Image.Image) -> str:
        """
        Encode image to base64 with aggressive resizing for local processing.

        Args:
            image: PIL Image object

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
        if width > self.max_size or height > self.max_size:
            if width > height:
                new_width = self.max_size
                new_height = int((self.max_size / width) * height)
            else:
                new_height = self.max_size
                new_width = int((self.max_size / height) * width)
            image = image.resize((new_width, new_height), Image.LANCZOS)
            tool_logger.info(f"Resized image from {width}x{height} to {new_width}x{new_height}")

        # Encode with compression
        buffered = BytesIO()
        image.save(buffered, format="JPEG", quality=80)
        encoded = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return encoded

    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """
        Process a single image using LMStudio API.

        Args:
            image_path: Path to image file

        Returns:
            Result dictionary with text, success status, and details
        """
        try:
            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Processing: {image_path.name}")

            # Load and process image
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

            # Encode image
            base64_image = self._encode_image(image)
            if not base64_image:
                return {
                    "text": "",
                    "success": False,
                    "error": "Failed to encode image",
                    "details": {}
                }

            # Prepare request payload
            payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": self.prompt_text},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature
            }

            # Retry logic
            max_retries = 3
            retry_delay = 1.0

            for attempt in range(max_retries):
                try:
                    tool_logger.info(f"🌐 Calling LMStudio API (attempt {attempt + 1}/{max_retries})")

                    response = self.session.post(
                        f"{self.api_url}/chat/completions",
                        json=payload,
                        headers={"Content-Type": "application/json"},
                        timeout=self.timeout
                    )
                    response.raise_for_status()

                    # Success
                    break

                except Exception as api_error:
                    if attempt < max_retries - 1:
                        tool_logger.warning(f"LMStudio API call failed (attempt {attempt + 1}/{max_retries}): {api_error}")
                        tool_logger.info(f"Retrying in {retry_delay:.1f} seconds...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                    else:
                        error_msg = f"LMStudio API call failed after {max_retries} attempts: {api_error}"
                        tool_logger.error(error_msg)
                        return {
                            "text": "",
                            "success": False,
                            "error": error_msg,
                            "details": {}
                        }

            # Extract transcription
            result = response.json()
            if "choices" not in result:
                error_msg = f"LMStudio API response missing 'choices': {result}"
                tool_logger.error(error_msg)
                return {
                    "text": "",
                    "success": False,
                    "error": error_msg,
                    "details": {}
                }

            transcription = result["choices"][0]["message"]["content"].strip()

            timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
            tool_logger.info(f"[{timestamp}] Received response for: {image_path.name}")

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

    def validate_config(self) -> bool:
        """Validate LMStudio configuration"""
        try:
            # Test connection to LMStudio
            tool_logger.info(f"Testing connection to LMStudio at {self.api_url}...")
            response = self.session.get(f"{self.api_url}/models", timeout=10)
            response.raise_for_status()
            tool_logger.info("✅ LMStudio connection successful")
            return True
        except Exception as e:
            tool_logger.error(f"Failed to connect to LMStudio: {e}")
            tool_logger.error(f"Make sure LMStudio is running at {self.api_url}")
            return False

    def cleanup(self):
        """Clean up LMStudio session"""
        if hasattr(self, 'session'):
            try:
                self.session.close()
            except:
                pass
