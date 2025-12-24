"""
Simple app settings - Pydantic model serialized to JSON.

Stores user preferences (not providers/models/tools - those go in DuckDB).

Note: This module is NOT thread-safe. For GUI apps, access settings
from the main thread only, or add external synchronization.

Usage:
    from fichero.settings import settings

    # Read
    path = settings.library_path

    # Write
    settings.library_path = "/new/path"
    settings.save()
"""

from pathlib import Path
from pydantic import BaseModel, Field
import json
import logging

logger = logging.getLogger(__name__)


class Settings(BaseModel):
    """App settings - simple preferences only."""

    # Library
    library_path: str = ""  # Empty = default ~/Library/Application Support/ca.tubb.fichero/library
    processing_output_path: str = ""  # Empty = default ~/Library/Application Support/ca.tubb.fichero/processed

    # Defaults
    default_transcription_provider: str = "dashscope"
    default_llm_provider: str = "dashscope"

    # UI
    theme: str = "system"  # system, light, dark

    # Processing
    max_concurrent_requests: int = 30


class SettingsManager:
    """Load/save settings to JSON file."""

    def __init__(self, path: Path | None = None):
        if path is None:
            from fichero.storage import settings as storage_settings
            path = storage_settings.base_path / "settings.json"
        self._path = path
        self._settings: Settings | None = None

    @property
    def settings(self) -> Settings:
        if self._settings is None:
            self._settings = self._load()
        return self._settings

    def _load(self) -> Settings:
        """Load settings from JSON, or return defaults."""
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                return Settings(**data)
            except Exception as e:
                logger.warning(f"Failed to load settings: {e}")
        return Settings()

    def save(self) -> None:
        """Save settings to JSON."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self.settings.model_dump_json(indent=2))

    def __getattr__(self, name: str):
        """Proxy attribute access to settings."""
        return getattr(self.settings, name)

    def __setattr__(self, name: str, value):
        """Proxy attribute setting to settings."""
        if name.startswith("_"):
            super().__setattr__(name, value)
        elif name in Settings.model_fields:
            setattr(self.settings, name, value)
        else:
            super().__setattr__(name, value)


# Global instance
settings = SettingsManager()
