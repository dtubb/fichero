"""
Whisper provider for audio transcription.

Supports three modes:
- local: Local Whisper model (openai-whisper package)
- api: OpenAI Whisper API (cloud-based, paid)
- faster: Faster-Whisper (CTranslate2 optimized, faster than local)

Usage:
    from fichero.tools.transcribe_providers.whisper_provider import WhisperProvider

    # Local transcription
    provider = WhisperProvider(mode="local", model="base")
    result = await provider.process_audio(Path("audio.mp3"))

    # API transcription
    provider = WhisperProvider(mode="api")
    result = await provider.process_audio(Path("audio.mp3"))

    # Faster-Whisper (recommended for speed)
    provider = WhisperProvider(mode="faster", model="base")
    result = await provider.process_audio(Path("audio.mp3"))
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fichero.tools.transcribe_providers.base_provider import BaseTranscriptionProvider

logger = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

AUDIO_FORMATS = {
    ".wav",
    ".mp3",
    ".m4a",
    ".aac",
    ".flac",
    ".ogg",
    ".wma",
    ".opus",
    ".webm",  # Audio in WebM container
}

# Model sizes (smaller = faster, larger = more accurate)
WHISPER_MODELS = {
    "tiny": "Fastest, lowest accuracy (~39 MB)",
    "base": "Good balance (~74 MB)",
    "small": "Better accuracy (~244 MB)",
    "medium": "High accuracy (~769 MB)",
    "large": "Highest accuracy (~1.5 GB)",
    "large-v2": "Improved large (~1.5 GB)",
    "large-v3": "Latest large (~1.5 GB)",
}


# =============================================================================
# Whisper Provider
# =============================================================================

class WhisperProvider(BaseTranscriptionProvider):
    """Whisper-based audio transcription provider.

    Three modes available:
    - "local": Uses openai-whisper package (requires ffmpeg)
    - "api": Uses OpenAI Whisper API (requires API key)
    - "faster": Uses faster-whisper with CTranslate2 (4x faster than local)
    """

    def __init__(
        self,
        mode: str = "local",
        model: str = "base",
        language: str | None = None,
        device: str | None = None,  # "cpu", "cuda", "mps" (Apple Silicon)
        compute_type: str = "float16",  # For faster-whisper
    ):
        """Initialize Whisper provider.

        Args:
            mode: "local", "api", or "faster"
            model: Model size ("tiny", "base", "small", "medium", "large", etc.)
            language: Language code (e.g., "en", "es", "zh"). Auto-detect if None.
            device: Device for inference ("cpu", "cuda", "mps"). Auto-select if None.
            compute_type: Compute type for faster-whisper ("float16", "int8", etc.)
        """
        self.mode = mode
        self.model_name = model
        self.language = language
        self.device = device
        self.compute_type = compute_type
        self._model = None

    @property
    def name(self) -> str:
        """Return provider name for logging."""
        return f"whisper-{self.mode}"

    @property
    def model(self) -> str:
        """Return model name being used."""
        return self.model_name

    @property
    def provider_name(self) -> str:
        """Return provider identifier."""
        return f"whisper-{self.mode}"

    @property
    def supported_formats(self) -> set[str]:
        """Return supported audio formats."""
        return AUDIO_FORMATS

    @property
    def max_file_size_mb(self) -> int:
        """Maximum file size in MB."""
        if self.mode == "api":
            return 25  # OpenAI API limit
        return 500  # Local can handle larger files

    # =========================================================================
    # Model Loading
    # =========================================================================

    def _load_model(self) -> None:
        """Lazy-load the Whisper model."""
        if self._model is not None:
            return

        if self.mode == "local":
            self._load_local_model()
        elif self.mode == "faster":
            self._load_faster_model()
        # API mode doesn't need a model

    def _load_local_model(self) -> None:
        """Load openai-whisper model."""
        try:
            import whisper
        except ImportError:
            raise ImportError(
                "openai-whisper not installed. Install with: pip install openai-whisper\n"
                "Also requires ffmpeg: brew install ffmpeg"
            )

        device = self.device
        if device is None:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"

        logger.info(f"Loading Whisper model: {self.model_name} on {device}")
        self._model = whisper.load_model(self.model_name, device=device)

    def _load_faster_model(self) -> None:
        """Load faster-whisper model."""
        try:
            from faster_whisper import WhisperModel
        except ImportError:
            raise ImportError(
                "faster-whisper not installed. Install with: pip install faster-whisper"
            )

        device = self.device
        if device is None:
            # Auto-detect device
            try:
                import torch
                if torch.cuda.is_available():
                    device = "cuda"
                else:
                    device = "cpu"
            except ImportError:
                device = "cpu"

        logger.info(
            f"Loading Faster-Whisper model: {self.model_name} on {device} "
            f"(compute_type={self.compute_type})"
        )
        self._model = WhisperModel(
            self.model_name,
            device=device,
            compute_type=self.compute_type,
        )

    # =========================================================================
    # Interface Methods
    # =========================================================================

    def process_image(self, file_path: Path) -> dict[str, Any]:
        """Process file (interface compatibility - actually processes audio).

        Args:
            file_path: Path to audio file

        Returns:
            Dict with 'text', 'success', and optional 'error' keys
        """
        import asyncio

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If already in async context, create a new loop
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.process_audio(file_path))
                    text = future.result()
            else:
                text = asyncio.run(self.process_audio(file_path))

            return {
                "text": text,
                "success": True,
                "details": {
                    "provider": self.provider_name,
                    "model": self.model_name,
                    "mode": self.mode,
                }
            }
        except Exception as e:
            return {
                "text": "",
                "success": False,
                "error": str(e),
                "details": {"provider": self.provider_name}
            }

    async def process_audio(self, audio_path: Path) -> str:
        """Transcribe audio file.

        Args:
            audio_path: Path to audio file

        Returns:
            Transcription text
        """
        audio_path = Path(audio_path)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        suffix = audio_path.suffix.lower()
        if suffix not in AUDIO_FORMATS:
            logger.warning(f"Unusual audio format: {suffix}")

        if self.mode == "api":
            return await self._transcribe_api(audio_path)
        else:
            return await self._transcribe_local(audio_path)

    # =========================================================================
    # Local Transcription
    # =========================================================================

    async def _transcribe_local(self, audio_path: Path) -> str:
        """Local Whisper transcription (openai-whisper or faster-whisper)."""
        # Run in thread pool (Whisper is CPU/GPU intensive)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._transcribe_local_sync,
            audio_path
        )

    def _transcribe_local_sync(self, audio_path: Path) -> str:
        """Synchronous local transcription."""
        self._load_model()

        if self.mode == "faster":
            return self._transcribe_faster_sync(audio_path)
        else:
            return self._transcribe_whisper_sync(audio_path)

    def _transcribe_whisper_sync(self, audio_path: Path) -> str:
        """Transcribe with openai-whisper."""
        options: dict[str, Any] = {}
        if self.language:
            options["language"] = self.language

        result = self._model.transcribe(str(audio_path), **options)
        return result["text"].strip()

    def _transcribe_faster_sync(self, audio_path: Path) -> str:
        """Transcribe with faster-whisper."""
        options: dict[str, Any] = {}
        if self.language:
            options["language"] = self.language

        segments, info = self._model.transcribe(str(audio_path), **options)

        # Collect all segment text
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)

        logger.debug(
            f"Transcribed {audio_path.name}: "
            f"detected language={info.language} ({info.language_probability:.0%})"
        )

        return " ".join(text_parts).strip()

    # =========================================================================
    # API Transcription
    # =========================================================================

    async def _transcribe_api(self, audio_path: Path) -> str:
        """Transcribe using OpenAI Whisper API."""
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "openai package not installed. Install with: pip install openai"
            )

        from fichero.tools.utils.api_keys import get_api_key

        api_key = get_api_key("openai")
        if not api_key:
            raise ValueError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable."
            )

        client = AsyncOpenAI(api_key=api_key)

        with open(audio_path, "rb") as audio_file:
            kwargs: dict[str, Any] = {
                "model": "whisper-1",
                "file": audio_file,
            }
            if self.language:
                kwargs["language"] = self.language

            response = await client.audio.transcriptions.create(**kwargs)

        return response.text.strip()

    # =========================================================================
    # Batch Processing
    # =========================================================================

    async def process_image_async(self, file_path: Path) -> str:
        """Async interface for batch processor compatibility."""
        return await self.process_audio(file_path)

    # =========================================================================
    # Utilities
    # =========================================================================

    @staticmethod
    def is_available(mode: str = "local") -> bool:
        """Check if the specified mode is available.

        Args:
            mode: "local", "api", or "faster"

        Returns:
            True if the mode is available
        """
        if mode == "local":
            try:
                import whisper
                return True
            except ImportError:
                return False
        elif mode == "faster":
            try:
                from faster_whisper import WhisperModel
                return True
            except ImportError:
                return False
        elif mode == "api":
            try:
                from openai import AsyncOpenAI
                from fichero.tools.utils.api_keys import get_api_key
                return bool(get_api_key("openai"))
            except ImportError:
                return False
        return False

    @staticmethod
    def get_available_modes() -> list[str]:
        """Get list of available transcription modes."""
        modes = []
        if WhisperProvider.is_available("local"):
            modes.append("local")
        if WhisperProvider.is_available("faster"):
            modes.append("faster")
        if WhisperProvider.is_available("api"):
            modes.append("api")
        return modes


# =============================================================================
# Convenience Functions
# =============================================================================

async def transcribe_audio(
    audio_path: Path,
    mode: str = "local",
    model: str = "base",
    language: str | None = None,
) -> str:
    """Convenience function to transcribe audio.

    Args:
        audio_path: Path to audio file
        mode: "local", "api", or "faster"
        model: Model size for local/faster modes
        language: Language code (auto-detect if None)

    Returns:
        Transcription text
    """
    provider = WhisperProvider(mode=mode, model=model, language=language)
    return await provider.process_audio(audio_path)


def transcribe_audio_sync(
    audio_path: Path,
    mode: str = "local",
    model: str = "base",
    language: str | None = None,
) -> str:
    """Synchronous convenience function.

    Args:
        audio_path: Path to audio file
        mode: "local", "api", or "faster"
        model: Model size for local/faster modes
        language: Language code (auto-detect if None)

    Returns:
        Transcription text
    """
    return asyncio.run(transcribe_audio(audio_path, mode, model, language))


__all__ = [
    "WhisperProvider",
    "AUDIO_FORMATS",
    "WHISPER_MODELS",
    "transcribe_audio",
    "transcribe_audio_sync",
]
