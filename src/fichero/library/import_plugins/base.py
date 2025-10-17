"""
Base Import Plugin

Abstract base class for import plugins in the Fichero library system.
"""

import logging
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Type alias for progress callback
# Signature: (current: int, total: int, message: str) -> None
ProgressCallback = Callable[[int, int, str], None]


@dataclass
class ImportResult:
    """Result of a import operation"""
    success: bool
    collection_id: Optional[str] = None
    collection_name: Optional[str] = None
    files_imported: int = 0
    files_skipped: int = 0
    errors: int = 0
    error_message: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format"""
        return {
            "success": self.success,
            "collection_id": self.collection_id,
            "collection_name": self.collection_name,
            "files_imported": self.files_imported,
            "files_skipped": self.files_skipped,
            "errors": self.errors,
            "error": self.error_message,
            "metadata": self.metadata or {}
        }


class ImportPlugin(ABC):
    """
    Abstract base class for import plugins

    Plugins must implement:
    - can_handle(url) - Check if this plugin can handle a given URL
    - download_and_import() - Download content and import to library
    - get_plugin_info() - Return plugin metadata

    Plugins can optionally support:
    - Progress tracking via progress_callback parameter
    - Cancellation via cancel_event parameter
    """

    def __init__(self, library_manager):
        """
        Initialize plugin with library manager

        Args:
            library_manager: LibraryManager instance for importing content
        """
        self.library_manager = library_manager
        self._cancel_event = asyncio.Event()
        self._progress_callback: Optional[ProgressCallback] = None

    def cancel(self):
        """Request cancellation of current import operation"""
        self._cancel_event.set()
        logger.info(f"Cancellation requested for {self.name}")

    def reset_cancel(self):
        """Reset cancellation state for reuse"""
        self._cancel_event.clear()

    @property
    def is_cancelled(self) -> bool:
        """Check if cancellation was requested"""
        return self._cancel_event.is_set()

    def set_progress_callback(self, callback: Optional[ProgressCallback]):
        """Set progress callback for download progress reporting"""
        self._progress_callback = callback

    def _report_progress(self, current: int, total: int, message: str):
        """Report progress to callback if set"""
        if self._progress_callback:
            try:
                self._progress_callback(current, total, message)
            except Exception as e:
                logger.warning(f"Progress callback error: {e}")

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """
        Check if this plugin can handle the given URL

        Args:
            url: URL to check

        Returns:
            True if plugin can handle this URL, False otherwise
        """
        pass

    @abstractmethod
    async def download_and_import(
        self,
        url: str,
        collection_name: str,
        collection_description: str = "",
        **kwargs
    ) -> ImportResult:
        """
        Download content from URL and import into library

        Args:
            url: URL to download from
            collection_name: Name for the new collection
            collection_description: Optional description
            **kwargs: Plugin-specific options

        Returns:
            ImportResult with import statistics
        """
        pass

    @abstractmethod
    def get_plugin_info(self) -> Dict[str, Any]:
        """
        Get plugin metadata

        Returns:
            Dict with plugin information:
            - name: Plugin name
            - version: Plugin version
            - description: Plugin description
            - supported_domains: List of supported domains/patterns
            - options: List of available options with descriptions
        """
        pass

    @property
    def name(self) -> str:
        """Get plugin name from plugin info"""
        return self.get_plugin_info().get("name", self.__class__.__name__)

    @property
    def version(self) -> str:
        """Get plugin version from plugin info"""
        return self.get_plugin_info().get("version", "1.0.0")

    @property
    def description(self) -> str:
        """Get plugin description from plugin info"""
        return self.get_plugin_info().get("description", "")

    @property
    def supported_domains(self) -> List[str]:
        """Get list of supported domains from plugin info"""
        return self.get_plugin_info().get("supported_domains", [])

    def __repr__(self) -> str:
        """String representation of plugin"""
        return f"<{self.__class__.__name__} name='{self.name}' version='{self.version}'>"
