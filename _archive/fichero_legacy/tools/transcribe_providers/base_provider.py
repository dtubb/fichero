"""
Base provider interface for transcription services.

All transcription providers must implement this interface.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Optional, Any
from datetime import datetime


class BaseTranscriptionProvider(ABC):
    """
    Base class for transcription providers.

    Providers handle the specific API calls and image encoding for different
    transcription services (DashScope, OpenAI, LMStudio, etc.)

    The provider is responsible for:
    - Encoding images appropriately for their API
    - Making API calls with retry logic
    - Returning transcribed text or error messages
    - Cleaning up resources
    """

    def __init__(self, api_key: Optional[str] = None, **config):
        """
        Initialize the provider.

        Args:
            api_key: API key (if required by provider)
            **config: Provider-specific configuration
        """
        self.api_key = api_key
        self.config = config

    @abstractmethod
    def process_image(self, image_path: Path) -> Dict[str, Any]:
        """
        Process a single image and return transcription.

        Args:
            image_path: Path to the image file

        Returns:
            Dictionary with:
            {
                "text": str,              # Transcribed text
                "success": bool,          # True if successful
                "error": str (optional),  # Error message if failed
                "details": dict           # Provider-specific metadata
            }
        """
        pass

    def process_multi_image(self, image_paths: list[Path]) -> list[Dict[str, Any]]:
        """
        Process multiple images in a single API request.

        This method is optional and only implemented by providers that support
        multi-image batching (e.g., Qwen-VL with 4-512 images per request).

        Args:
            image_paths: List of image file paths to process together

        Returns:
            List of result dictionaries, one per image, in the same order as input.
            Each dictionary has the same format as process_image() return value.

        Raises:
            NotImplementedError: If provider doesn't support multi-image batching
        """
        raise NotImplementedError(
            f"{self.name} does not support multi-image batching. "
            "Use process_image() for single-image processing or parallel workers."
        )

    def validate_config(self) -> bool:
        """
        Validate provider configuration.

        Returns:
            True if configuration is valid, False otherwise
        """
        return True

    def cleanup(self):
        """Clean up provider resources (connections, sessions, etc.)"""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return provider name for logging"""
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """Return model name being used"""
        pass

    @property
    def supports_parallel(self) -> bool:
        """
        Whether this provider supports parallel processing.

        Returns:
            True if provider can handle parallel requests safely
        """
        return False

    @property
    def max_file_size_mb(self) -> int:
        """
        Maximum file size in MB that provider can handle.

        Returns:
            Maximum file size in megabytes
        """
        return 10

    @property
    def supported_formats(self) -> list:
        """
        Supported image formats.

        Returns:
            List of supported file extensions (e.g., ['.jpg', '.png'])
        """
        return ['.jpg', '.jpeg', '.png', '.tiff', '.tif']

    @property
    def supports_multi_image(self) -> bool:
        """
        Whether this provider supports multi-image batching.

        Returns:
            True if provider can process multiple images in one API request
        """
        return False

    @property
    def max_images_per_batch(self) -> int:
        """
        Maximum number of images that can be processed in a single API request.

        Returns:
            Maximum image count per batch (0 if multi-image not supported)
        """
        return 0

    @property
    def min_images_per_batch(self) -> int:
        """
        Minimum number of images required for multi-image batching.

        Returns:
            Minimum image count per batch (0 if multi-image not supported)
        """
        return 0

    @property
    def provider_name(self) -> str:
        """Return provider service name (e.g., 'dashscope', 'openai', 'lmstudio')"""
        return "unknown"

    @property
    def model_version(self) -> Optional[str]:
        """Return model version if known"""
        return None

    @property
    def api_endpoint(self) -> Optional[str]:
        """Return API endpoint URL if applicable"""
        return None

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get comprehensive model/provider information for tracking.

        Returns:
            Dictionary with model details:
            {
                'model': str,              # Model name (e.g., 'qwen-vl-ocr')
                'provider': str,           # Provider name (e.g., 'dashscope')
                'model_version': str,      # Model version (optional)
                'api_endpoint': str,       # API endpoint (optional)
                'api_parameters': dict,    # Parameters used (temperature, etc.)
                'usage': dict              # Token usage if tracked
            }
        """
        return {
            'model': self.model,
            'provider': self.provider_name,
            'model_version': self.model_version,
            'api_endpoint': self.api_endpoint,
            'api_parameters': self.get_api_parameters(),
            'usage': self.get_usage_stats()
        }

    def get_api_parameters(self) -> Dict[str, Any]:
        """
        Get API parameters used for this provider.

        Override in subclasses to include provider-specific parameters.

        Returns:
            Dictionary of parameters (temperature, max_tokens, etc.)
        """
        return {}

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get token usage statistics from processing.

        Override in subclasses to track and return usage.

        Returns:
            Dictionary with usage stats (prompt_tokens, completion_tokens, etc.)
        """
        return {}
