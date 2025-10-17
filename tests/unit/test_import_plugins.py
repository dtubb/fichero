"""
Unit Tests for Import Plugin System

Tests for the plugin architecture including base classes, registry,
and individual plugins (ZIP, Box.com).
"""

import pytest
import asyncio
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from io import BytesIO

from fichero.library.import_plugins.base import ImportPlugin, ImportResult
from fichero.library.import_plugins.registry import PluginRegistry
from fichero.library.import_plugins.zip_plugin import ZipImportPlugin, OneDriveLinkConverter
from fichero.library.import_plugins.box_plugin import BoxImportPlugin


# ==================== Base Plugin Tests ====================

class TestImportResult:
    """Test ImportResult dataclass"""

    def test_download_result_success(self):
        """Test creating a successful download result"""
        result = ImportResult(
            success=True,
            collection_id="col_123",
            collection_name="Test Collection",
            files_imported=10,
            files_skipped=2,
            errors=1
        )

        assert result.success is True
        assert result.collection_id == "col_123"
        assert result.collection_name == "Test Collection"
        assert result.files_imported == 10
        assert result.files_skipped == 2
        assert result.errors == 1
        assert result.error_message is None

    def test_download_result_failure(self):
        """Test creating a failed download result"""
        result = ImportResult(
            success=False,
            error_message="Network error",
            files_imported=0
        )

        assert result.success is False
        assert result.error_message == "Network error"
        assert result.collection_id is None
        assert result.files_imported == 0

    def test_download_result_to_dict(self):
        """Test converting ImportResult to dictionary"""
        result = ImportResult(
            success=True,
            collection_id="col_123",
            files_imported=5
        )

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert result_dict["success"] is True
        assert result_dict["collection_id"] == "col_123"
        assert result_dict["files_imported"] == 5
        assert "metadata" in result_dict


class TestImportPluginBase:
    """Test base ImportPlugin class"""

    def test_plugin_requires_library_manager(self):
        """Test plugin initialization requires library manager"""
        mock_lib = Mock()

        # Create a concrete implementation for testing
        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True

            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)

            def get_plugin_info(self):
                return {"name": "Test", "version": "1.0.0"}

        plugin = TestPlugin(mock_lib)
        assert plugin.library_manager == mock_lib

    def test_plugin_properties(self):
        """Test plugin name, version, and description properties"""
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True

            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)

            def get_plugin_info(self):
                return {
                    "name": "TestPlugin",
                    "version": "2.0.0",
                    "description": "A test plugin",
                    "supported_domains": ["test.com"]
                }

        plugin = TestPlugin(mock_lib)
        assert plugin.name == "TestPlugin"
        assert plugin.version == "2.0.0"
        assert plugin.description == "A test plugin"
        assert plugin.supported_domains == ["test.com"]

    def test_plugin_repr(self):
        """Test plugin string representation"""
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True

            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)

            def get_plugin_info(self):
                return {"name": "TestPlugin", "version": "1.0.0"}

        plugin = TestPlugin(mock_lib)
        repr_str = repr(plugin)
        assert "TestPlugin" in repr_str
        assert "1.0.0" in repr_str


# ==================== Plugin Registry Tests ====================

class TestPluginRegistry:
    """Test PluginRegistry class"""

    def test_registry_initialization(self):
        """Test registry starts empty"""
        registry = PluginRegistry()
        assert len(registry) == 0
        assert registry.list_plugins() == []

    def test_register_plugin(self):
        """Test registering a plugin"""
        registry = PluginRegistry()
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Test", "version": "1.0.0"}

        plugin = TestPlugin(mock_lib)
        registry.register(plugin)

        assert len(registry) == 1
        assert registry.get_plugin("Test") == plugin

    def test_register_duplicate_plugin(self):
        """Test registering the same plugin twice (should skip)"""
        registry = PluginRegistry()
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Test", "version": "1.0.0"}

        plugin1 = TestPlugin(mock_lib)
        plugin2 = TestPlugin(mock_lib)

        registry.register(plugin1)
        registry.register(plugin2)  # Should skip

        assert len(registry) == 1

    def test_register_non_plugin_raises_error(self):
        """Test registering non-plugin object raises TypeError"""
        registry = PluginRegistry()

        with pytest.raises(TypeError):
            registry.register("not a plugin")

    def test_unregister_plugin(self):
        """Test unregistering a plugin"""
        registry = PluginRegistry()
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Test", "version": "1.0.0"}

        plugin = TestPlugin(mock_lib)
        registry.register(plugin)

        assert len(registry) == 1
        assert registry.unregister("Test") is True
        assert len(registry) == 0

    def test_unregister_nonexistent_plugin(self):
        """Test unregistering non-existent plugin returns False"""
        registry = PluginRegistry()
        assert registry.unregister("NonExistent") is False

    def test_find_plugin_for_url(self):
        """Test finding plugin that can handle a URL"""
        registry = PluginRegistry()
        mock_lib = Mock()

        class ZipPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return url.endswith('.zip')
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "ZIP", "version": "1.0.0"}

        class BoxPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return 'box.com' in url
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Box", "version": "1.0.0"}

        zip_plugin = ZipPlugin(mock_lib)
        box_plugin = BoxPlugin(mock_lib)

        registry.register(zip_plugin)
        registry.register(box_plugin)

        # Test finding correct plugins
        assert registry.find_plugin_for_url("http://example.com/file.zip") == zip_plugin
        assert registry.find_plugin_for_url("https://app.box.com/s/abc123") == box_plugin
        assert registry.find_plugin_for_url("http://example.com/page.html") is None

    def test_list_plugins(self):
        """Test listing all registered plugins"""
        registry = PluginRegistry()
        mock_lib = Mock()

        # Create two different plugin classes (not instances of same class)
        class TestPlugin1(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Plugin1", "version": "1.0.0"}

        class TestPlugin2(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Plugin2", "version": "1.0.0"}

        plugin1 = TestPlugin1(mock_lib)
        plugin2 = TestPlugin2(mock_lib)

        registry.register(plugin1)
        registry.register(plugin2)

        plugins_info = registry.list_plugins()
        assert len(plugins_info) == 2
        names = [p["name"] for p in plugins_info]
        assert "Plugin1" in names
        assert "Plugin2" in names

    def test_clear_registry(self):
        """Test clearing all plugins from registry"""
        registry = PluginRegistry()
        mock_lib = Mock()

        class TestPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return True
            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(success=True)
            def get_plugin_info(self):
                return {"name": "Test", "version": "1.0.0"}

        plugin = TestPlugin(mock_lib)
        registry.register(plugin)

        assert len(registry) == 1
        registry.clear()
        assert len(registry) == 0

    def test_registry_repr(self):
        """Test registry string representation"""
        registry = PluginRegistry()
        repr_str = repr(registry)
        assert "PluginRegistry" in repr_str


# ==================== OneDrive Link Converter Tests ====================

class TestOneDriveLinkConverter:
    """Test OneDrive/SharePoint link conversion"""

    def test_is_onedrive_link_sharepoint(self):
        """Test detecting SharePoint links"""
        converter = OneDriveLinkConverter()
        assert converter.is_onedrive_link("https://company.sharepoint.com/:u:/g/abc") is True
        assert converter.is_onedrive_link("https://company-my.sharepoint.com/my?id=file.zip") is True

    def test_is_onedrive_link_onedrive(self):
        """Test detecting OneDrive links"""
        converter = OneDriveLinkConverter()
        assert converter.is_onedrive_link("https://onedrive.live.com/download?id=123") is True

    def test_is_onedrive_link_short_link(self):
        """Test detecting 1drv.ms short links"""
        converter = OneDriveLinkConverter()
        assert converter.is_onedrive_link("https://1drv.ms/u/s!ABC123") is True

    def test_is_not_onedrive_link(self):
        """Test non-OneDrive links return False"""
        converter = OneDriveLinkConverter()
        assert converter.is_onedrive_link("https://example.com/file.zip") is False
        assert converter.is_onedrive_link("https://dropbox.com/s/abc") is False

    def test_convert_sharepoint_view_url(self):
        """Test converting SharePoint /my?id= view URLs"""
        converter = OneDriveLinkConverter()
        url = "https://company-my.sharepoint.com/my?id=%2Fpersonal%2Fuser%2FDocuments%2Ffile.zip"

        result = converter.convert_to_direct_download(url)

        assert "/_layouts/15/download.aspx" in result
        assert "SourceUrl=" in result

    def test_convert_sharepoint_already_direct(self):
        """Test SharePoint URL that's already a direct download"""
        converter = OneDriveLinkConverter()
        url = "https://company.sharepoint.com/_layouts/15/download.aspx?SourceUrl=abc"

        result = converter.convert_to_direct_download(url)

        assert result == url  # Should return unchanged

    def test_convert_sharepoint_preview_to_download(self):
        """Test converting SharePoint preview link (:u:) to download (:d:)"""
        converter = OneDriveLinkConverter()
        url = "https://company.sharepoint.com/:u:/g/personal/user/abc"

        result = converter.convert_to_direct_download(url)

        assert "/:d:/" in result or "/_layouts/15/download.aspx" in result

    def test_convert_onedrive_view_to_download(self):
        """Test converting OneDrive view link to download link"""
        converter = OneDriveLinkConverter()
        url = "https://onedrive.live.com/view.aspx?id=123"

        result = converter.convert_to_direct_download(url)

        assert "/download.aspx" in result

    def test_convert_short_link_passthrough(self):
        """Test short links (1drv.ms) are passed through for redirect handling"""
        converter = OneDriveLinkConverter()
        url = "https://1drv.ms/u/s!ABC123"

        result = converter.convert_to_direct_download(url)

        assert result == url  # Should pass through unchanged

    def test_convert_handles_exceptions(self):
        """Test converter handles malformed URLs gracefully"""
        converter = OneDriveLinkConverter()
        malformed_url = "not a valid url"

        result = converter.convert_to_direct_download(malformed_url)

        # Should return original URL even if conversion fails
        assert result == malformed_url


# ==================== ZIP Plugin Tests ====================

class TestZipImportPlugin:
    """Test ZIP import plugin"""

    def test_zip_plugin_initialization(self):
        """Test ZIP plugin initializes correctly"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        assert plugin.library_manager == mock_lib
        assert plugin.link_converter is not None

    def test_zip_plugin_can_handle_zip_url(self):
        """Test plugin handles .zip URLs"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        assert plugin.can_handle("https://example.com/file.zip") is True
        assert plugin.can_handle("http://cdn.example.com/archive.ZIP") is True

    def test_zip_plugin_can_handle_onedrive(self):
        """Test plugin handles OneDrive links"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        assert plugin.can_handle("https://company.sharepoint.com/:u:/g/abc") is True
        assert plugin.can_handle("https://onedrive.live.com/download?id=123") is True

    def test_zip_plugin_cannot_handle_other_urls(self):
        """Test plugin rejects non-ZIP URLs"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        assert plugin.can_handle("https://example.com/page.html") is False
        assert plugin.can_handle("https://app.box.com/s/abc") is False

    def test_zip_plugin_info(self):
        """Test ZIP plugin returns correct metadata"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        info = plugin.get_plugin_info()

        assert info["name"] == "ZIP Import"
        assert "version" in info
        assert "sharepoint.com" in info["supported_domains"]
        assert "onedrive.live.com" in info["supported_domains"]

    @pytest.mark.asyncio
    async def test_validate_zip_with_valid_file(self):
        """Test ZIP validation with valid ZIP file"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        # Create a valid ZIP file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("test.txt", "Hello World")

        try:
            is_valid = await plugin._validate_zip(tmp_path)
            assert is_valid is True
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_validate_zip_detects_path_traversal(self):
        """Test ZIP validation detects path traversal attacks"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        # Create a malicious ZIP with path traversal
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("../../../etc/passwd", "malicious")

        try:
            is_valid = await plugin._validate_zip(tmp_path)
            assert is_valid is False
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_validate_zip_detects_absolute_paths(self):
        """Test ZIP validation detects absolute paths"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        # Create a malicious ZIP with absolute path
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("/etc/shadow", "malicious")

        try:
            is_valid = await plugin._validate_zip(tmp_path)
            assert is_valid is False
        finally:
            tmp_path.unlink()

    @pytest.mark.asyncio
    async def test_extract_zip(self):
        """Test ZIP extraction"""
        mock_lib = Mock()
        plugin = ZipImportPlugin(mock_lib)

        # Create a ZIP file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)
            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("test.txt", "Hello World")
                zf.writestr("folder/file.txt", "Nested file")

        try:
            extract_dir = await plugin._extract_zip(tmp_path)

            assert extract_dir.exists()
            assert (extract_dir / "test.txt").exists()
            assert (extract_dir / "folder" / "file.txt").exists()

            # Cleanup
            import shutil
            shutil.rmtree(extract_dir)
        finally:
            tmp_path.unlink()


# ==================== Box Plugin Tests ====================

class TestBoxImportPlugin:
    """Test Box.com import plugin"""

    def test_box_plugin_initialization(self):
        """Test Box plugin initializes correctly"""
        mock_lib = Mock()
        plugin = BoxImportPlugin(mock_lib)

        assert plugin.library_manager == mock_lib

    def test_box_plugin_can_handle_box_urls(self):
        """Test plugin handles Box.com sharing URLs"""
        mock_lib = Mock()
        plugin = BoxImportPlugin(mock_lib)

        assert plugin.can_handle("https://app.box.com/s/abc123") is True
        assert plugin.can_handle("https://company.app.box.com/s/xyz789") is True

    def test_box_plugin_cannot_handle_other_urls(self):
        """Test plugin rejects non-Box URLs"""
        mock_lib = Mock()
        plugin = BoxImportPlugin(mock_lib)

        assert plugin.can_handle("https://dropbox.com/s/abc") is False
        assert plugin.can_handle("https://example.com/file.zip") is False

    def test_box_plugin_info(self):
        """Test Box plugin returns correct metadata"""
        mock_lib = Mock()
        plugin = BoxImportPlugin(mock_lib)

        info = plugin.get_plugin_info()

        assert info["name"] == "Box.com Import"
        assert "version" in info
        assert "box.com" in info["supported_domains"]
        assert "app.box.com" in info["supported_domains"]
        assert "notes" in info  # Should have implementation notes


# ==================== Integration Tests ====================

@pytest.mark.asyncio
class TestPluginIntegration:
    """Integration tests for plugin system"""

    async def test_registry_with_multiple_plugins(self):
        """Test registry correctly routes URLs to plugins"""
        registry = PluginRegistry()
        mock_lib = Mock()

        zip_plugin = ZipImportPlugin(mock_lib)
        box_plugin = BoxImportPlugin(mock_lib)

        registry.register(zip_plugin)
        registry.register(box_plugin)

        # Test routing
        assert registry.find_plugin_for_url("https://example.com/file.zip") == zip_plugin
        assert registry.find_plugin_for_url("https://app.box.com/s/abc") == box_plugin
        assert registry.find_plugin_for_url("https://company.sharepoint.com/:u:/g/abc") == zip_plugin

    async def test_plugin_system_extensibility(self):
        """Test adding new custom plugin to system"""
        registry = PluginRegistry()
        mock_lib = Mock()

        # Create a custom plugin
        class CustomPlugin(ImportPlugin):
            def can_handle(self, url: str) -> bool:
                return "custom.com" in url

            async def download_and_import(self, url, collection_name, collection_description="", **kwargs):
                return ImportResult(
                    success=True,
                    collection_id="custom_123",
                    collection_name=collection_name,
                    files_imported=1
                )

            def get_plugin_info(self):
                return {
                    "name": "Custom Downloader",
                    "version": "1.0.0",
                    "description": "Custom plugin for testing",
                    "supported_domains": ["custom.com"]
                }

        custom_plugin = CustomPlugin(mock_lib)
        registry.register(custom_plugin)

        # Test custom plugin is registered and works
        assert registry.find_plugin_for_url("https://custom.com/file") == custom_plugin

        result = await custom_plugin.download_and_import(
            "https://custom.com/file",
            "Test Collection"
        )

        assert result.success is True
        assert result.collection_id == "custom_123"
        assert result.files_imported == 1
