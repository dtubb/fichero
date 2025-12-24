"""Tests for settings module."""

import json
from pathlib import Path

import pytest

from fichero.settings import Settings, SettingsManager


class TestSettings:
    """Test Settings Pydantic model."""

    def test_default_values(self):
        """Settings has sensible defaults."""
        settings = Settings()

        assert settings.library_path == ""
        assert settings.default_transcription_provider == "dashscope"
        assert settings.default_llm_provider == "dashscope"
        assert settings.theme == "system"
        assert settings.max_concurrent_requests == 30

    def test_serialize_to_json(self):
        """Settings can be serialized to JSON."""
        settings = Settings(library_path="/custom/path")

        json_str = settings.model_dump_json()
        data = json.loads(json_str)

        assert data["library_path"] == "/custom/path"
        assert "theme" in data

    def test_deserialize_from_dict(self):
        """Settings can be created from dict."""
        data = {
            "library_path": "/my/library",
            "theme": "dark",
        }
        settings = Settings(**data)

        assert settings.library_path == "/my/library"
        assert settings.theme == "dark"


class TestSettingsManager:
    """Test SettingsManager."""

    def test_load_missing_file_returns_defaults(self, tmp_path):
        """Loading missing file returns defaults."""
        manager = SettingsManager(tmp_path / "missing.json")

        assert manager.settings.library_path == ""
        assert manager.settings.theme == "system"

    def test_save_creates_file(self, tmp_path):
        """Save creates settings file."""
        path = tmp_path / "settings.json"
        manager = SettingsManager(path)

        manager.settings.library_path = "/test/path"
        manager.save()

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["library_path"] == "/test/path"

    def test_load_existing_file(self, tmp_path):
        """Load reads existing settings."""
        path = tmp_path / "settings.json"
        path.write_text(json.dumps({
            "library_path": "/existing/path",
            "theme": "light",
        }))

        manager = SettingsManager(path)

        assert manager.settings.library_path == "/existing/path"
        assert manager.settings.theme == "light"

    def test_proxy_getattr(self, tmp_path):
        """Manager proxies attribute access."""
        manager = SettingsManager(tmp_path / "settings.json")

        # Access through proxy
        assert manager.theme == "system"
        assert manager.max_concurrent_requests == 30

    def test_proxy_setattr(self, tmp_path):
        """Manager proxies attribute setting."""
        manager = SettingsManager(tmp_path / "settings.json")

        manager.theme = "dark"
        assert manager.settings.theme == "dark"

    def test_roundtrip(self, tmp_path):
        """Full save/load roundtrip."""
        path = tmp_path / "settings.json"

        # Create and save
        manager1 = SettingsManager(path)
        manager1.library_path = "/my/library"
        manager1.theme = "dark"
        manager1.max_concurrent_requests = 10
        manager1.save()

        # Load in new manager
        manager2 = SettingsManager(path)

        assert manager2.library_path == "/my/library"
        assert manager2.theme == "dark"
        assert manager2.max_concurrent_requests == 10

    def test_creates_parent_directory(self, tmp_path):
        """Save creates parent directories."""
        path = tmp_path / "subdir" / "deep" / "settings.json"
        manager = SettingsManager(path)

        manager.save()

        assert path.exists()

    def test_handles_corrupt_file(self, tmp_path):
        """Loading corrupt file returns defaults."""
        path = tmp_path / "settings.json"
        path.write_text("not valid json {{{")

        manager = SettingsManager(path)

        # Should get defaults, not crash
        assert manager.settings.theme == "system"
