"""
Base classes for media loaders.

Provides:
- MediaContent: Normalized output from any loader
- MediaLoader: Abstract base class for all loaders
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict

if TYPE_CHECKING:
    pass


class MediaContent(BaseModel):
    """Normalized output from any media loader.

    All loaders produce this same structure, regardless of input format.
    The rest of the pipeline can work with this uniform interface.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: str
    """Original path or URL."""

    text: str | None = None
    """Extracted text content (if available)."""

    images: list[Any] = Field(default_factory=list)
    """List of PIL Images (pages, frames, etc.). Type is Any to avoid PIL import."""

    audio: bytes | None = None
    """Raw audio bytes (for future multimodal VLM support)."""

    metadata: dict[str, Any] = Field(default_factory=dict)
    """Format-specific metadata (page count, dimensions, etc.)."""

    mime_type: str | None = None
    """Detected MIME type."""

    needs_vlm: bool = True
    """Whether this content needs VLM processing for transcription.
    False if good text was extracted directly (e.g., digital PDF with selectable text)."""

    @property
    def page_count(self) -> int:
        """Number of pages/frames."""
        return len(self.images)

    @property
    def has_text(self) -> bool:
        """Whether text was extracted."""
        return bool(self.text and len(self.text.strip()) > 0)

    @property
    def has_images(self) -> bool:
        """Whether images are available."""
        return len(self.images) > 0


class MediaLoader(ABC):
    """
    Base class for all media loaders.

    Each loader handles specific file types and produces MediaContent.
    """

    @abstractmethod
    async def load(self, source: str | Path) -> MediaContent:
        """
        Load media from source and return normalized MediaContent.

        Args:
            source: File path or URL

        Returns:
            MediaContent with extracted text/images/metadata
        """
        ...

    @abstractmethod
    def can_handle(self, source: str | Path) -> bool:
        """
        Check if this loader can handle the given source.

        Args:
            source: File path or URL

        Returns:
            True if this loader can process the source
        """
        ...

    def load_sync(self, source: str | Path) -> MediaContent:
        """
        Synchronous wrapper for load().

        For use in non-async contexts.
        """

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None:
            # Already in async context - use nest_asyncio or run in thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, self.load(source))
                return future.result()
        else:
            return asyncio.run(self.load(source))
