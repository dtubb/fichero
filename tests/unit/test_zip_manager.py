"""
Unit Tests for ZIP Manager

Tests ZIP download, extraction, and import functionality including:
- OneDrive/SharePoint link conversion
- ZIP download with size limits
- ZIP validation and security checks
- Extraction and import into library
- Error handling and edge cases

Note: SharePoint/OneDrive links that require authentication are not currently supported.
The system generates correct direct download URLs, but these require login cookies/tokens.
For testing with real SharePoint files, use anonymous sharing links or publicly accessible files.
"""

import asyncio
import pytest
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from io import BytesIO

from fichero.library.zip_manager import OneDriveLinkConverter, ZipManager


class TestOneDriveLinkConverter:
    """Tests for OneDrive/SharePoint link conversion"""

    def test_is_onedrive_link_sharepoint(self):
        """Test detection of SharePoint links"""
        converter = OneDriveLinkConverter()

        # SharePoint tenant links
        assert converter.is_onedrive_link("https://company-my.sharepoint.com/:u:/g/personal/user/file.zip")
        assert converter.is_onedrive_link("https://company.sharepoint.com/sites/team/file.zip")

        # OneDrive personal links
        assert converter.is_onedrive_link("https://onedrive.live.com/download?id=123")

        # Short links
        assert converter.is_onedrive_link("https://1drv.ms/u/s!ABC123")

        # Non-OneDrive links
        assert not converter.is_onedrive_link("https://google.com/file.zip")
        assert not converter.is_onedrive_link("https://dropbox.com/file.zip")

    def test_convert_sharepoint_view_url_with_id_parameter(self):
        """Test conversion of SharePoint /my?id= view URLs to direct download"""
        converter = OneDriveLinkConverter()

        url = "https://company-my.sharepoint.com/my?id=%2Fpersonal%2Fuser%2FDocuments%2Ffile.zip&parent=%2Fpersonal%2Fuser%2FDocuments"
        result = converter.convert_to_direct_download(url)

        # Should convert to _layouts/15/download.aspx format
        assert "/_layouts/15/download.aspx" in result
        assert "SourceUrl=" in result
        assert "company-my.sharepoint.com" in result

    def test_convert_sharepoint_preview_url_to_download(self):
        """Test conversion of SharePoint :u: (preview) URLs to :d: (download)"""
        converter = OneDriveLinkConverter()

        url = "https://company-my.sharepoint.com/:u:/g/personal/user/EcNM1t941xRLuzsrTcVHKlIB?e=abc123"
        result = converter.convert_to_direct_download(url)

        # Should replace :u: with :d:
        assert "/:d:/" in result or "/_layouts/15/download.aspx" in result
        assert "/:u:/" not in result

    def test_convert_already_direct_download_url(self):
        """Test that already-direct download URLs are not modified"""
        converter = OneDriveLinkConverter()

        url = "https://company.sharepoint.com/_layouts/15/download.aspx?SourceUrl=/file.zip"
        result = converter.convert_to_direct_download(url)

        # Should return the same URL
        assert result == url

    def test_convert_onedrive_personal_view_to_download(self):
        """Test conversion of OneDrive personal view URLs"""
        converter = OneDriveLinkConverter()

        url = "https://onedrive.live.com/view.aspx?id=123"
        result = converter.convert_to_direct_download(url)

        # Should convert view.aspx to download.aspx
        assert "download.aspx" in result
        assert "view.aspx" not in result

    def test_convert_short_link(self):
        """Test handling of 1drv.ms short links"""
        converter = OneDriveLinkConverter()

        url = "https://1drv.ms/u/s!ABC123"
        result = converter.convert_to_direct_download(url)

        # Short links should be returned as-is (will follow redirects)
        assert result == url

    def test_convert_unknown_format_returns_original(self):
        """Test that unknown URL formats are returned unchanged"""
        converter = OneDriveLinkConverter()

        url = "https://unknown-cloud.com/file.zip"
        result = converter.convert_to_direct_download(url)

        assert result == url

    def test_convert_handles_url_encoding(self):
        """Test proper handling of URL encoding in file paths"""
        converter = OneDriveLinkConverter()

        # URL with spaces encoded as %20
        url = "https://company.sharepoint.com/my?id=%2Fpath%2Fto%2Ffile%20with%20spaces.zip"
        result = converter.convert_to_direct_download(url)

        # Should properly encode for SourceUrl parameter
        assert "SourceUrl=" in result
        assert "%2F" in result  # Forward slashes should be encoded


class TestZipManager:
    """Tests for ZipManager download and import functionality"""

    @pytest.fixture
    def mock_library_manager(self):
        """Create a mock LibraryManager for testing"""
        manager = Mock()
        manager.add_collection = AsyncMock(return_value="test-collection-id")
        manager.add_folder_items_to_collection = AsyncMock(return_value={
            "added": 5,
            "skipped": 0,
            "errors": 0,
            "item_ids": ["item1", "item2", "item3", "item4", "item5"]
        })
        return manager

    @pytest.fixture
    def zip_manager(self, mock_library_manager):
        """Create a ZipManager instance with mocked dependencies"""
        return ZipManager(mock_library_manager)

    def test_zip_manager_initialization(self, mock_library_manager):
        """Test ZipManager initializes correctly"""
        manager = ZipManager(mock_library_manager)

        assert manager.library_manager == mock_library_manager
        assert isinstance(manager.link_converter, OneDriveLinkConverter)

    @pytest.mark.asyncio
    async def test_validate_zip_success(self, zip_manager):
        """Test ZIP validation with a valid ZIP file"""
        # Create a valid ZIP file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)

            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("file1.txt", "Hello World")
                zf.writestr("folder/file2.txt", "Test content")

            # Validate
            is_valid = await zip_manager._validate_zip(tmp_path)

            # Cleanup
            tmp_path.unlink()

            assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_zip_detects_path_traversal(self, zip_manager):
        """Test ZIP validation detects path traversal attacks"""
        # Create a malicious ZIP file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)

            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("safe_file.txt", "Safe content")
                zf.writestr("../../../etc/passwd", "Malicious content")  # Path traversal

            # Validate
            is_valid = await zip_manager._validate_zip(tmp_path)

            # Cleanup
            tmp_path.unlink()

            assert is_valid is False

    @pytest.mark.asyncio
    async def test_validate_zip_detects_absolute_paths(self, zip_manager):
        """Test ZIP validation detects absolute paths"""
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)

            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("safe_file.txt", "Safe content")
                zf.writestr("/etc/hosts", "Malicious content")  # Absolute path

            is_valid = await zip_manager._validate_zip(tmp_path)
            tmp_path.unlink()

            assert is_valid is False

    @pytest.mark.asyncio
    async def test_validate_zip_corrupted_file(self, zip_manager):
        """Test ZIP validation detects corrupted files"""
        # Create a file that's not a valid ZIP
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(b"This is not a ZIP file")

        is_valid = await zip_manager._validate_zip(tmp_path)
        tmp_path.unlink()

        assert is_valid is False

    @pytest.mark.asyncio
    async def test_extract_zip_success(self, zip_manager):
        """Test successful ZIP extraction"""
        # Create a ZIP file with content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp:
            tmp_path = Path(tmp.name)

            with zipfile.ZipFile(tmp_path, 'w') as zf:
                zf.writestr("file1.txt", "Content 1")
                zf.writestr("folder/file2.txt", "Content 2")

            # Extract
            extract_dir = await zip_manager._extract_zip(tmp_path)

            # Verify extraction
            assert extract_dir.exists()
            assert (extract_dir / "file1.txt").exists()
            assert (extract_dir / "folder" / "file2.txt").exists()
            assert (extract_dir / "file1.txt").read_text() == "Content 1"

            # Cleanup
            import shutil
            tmp_path.unlink()
            shutil.rmtree(extract_dir)

    @pytest.mark.asyncio
    async def test_import_extracted_files_single_root_folder(self, zip_manager, mock_library_manager):
        """Test import with single root folder (common ZIP structure)"""
        # Create temp directory with single root folder
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            root_folder = temp_path / "MyFiles"
            root_folder.mkdir()
            (root_folder / "file1.txt").write_text("Test")
            (root_folder / "file2.txt").write_text("Test")

            # Import
            result = await zip_manager._import_extracted_files(
                temp_path,
                "Test Collection",
                "Test Description"
            )

            # Verify collection was created with root folder path
            mock_library_manager.add_collection.assert_called_once()
            call_args = mock_library_manager.add_collection.call_args
            assert call_args[1]["name"] == "Test Collection"
            assert str(root_folder) in call_args[1]["source_path"]

            # Verify import stats
            assert result["success"] is True
            assert result["collection_id"] == "test-collection-id"
            assert result["files_imported"] == 5

    @pytest.mark.asyncio
    async def test_import_extracted_files_multiple_root_folders(self, zip_manager, mock_library_manager):
        """Test import with multiple root folders"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "folder1").mkdir()
            (temp_path / "folder2").mkdir()
            (temp_path / "folder1" / "file.txt").write_text("Test")

            result = await zip_manager._import_extracted_files(
                temp_path,
                "Test Collection",
                "Test Description"
            )

            # Should use temp_path directly (not a subfolder)
            call_args = mock_library_manager.add_collection.call_args
            assert str(temp_path) in call_args[1]["source_path"]

            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_import_extracted_files_skips_macosx_folder(self, zip_manager, mock_library_manager):
        """Test that __MACOSX and hidden folders are ignored"""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            (temp_path / "__MACOSX").mkdir()
            (temp_path / ".DS_Store").write_text("")
            root_folder = temp_path / "RealContent"
            root_folder.mkdir()
            (root_folder / "file.txt").write_text("Real file")

            result = await zip_manager._import_extracted_files(
                temp_path,
                "Test Collection",
                ""
            )

            # Should use RealContent folder (not __MACOSX)
            call_args = mock_library_manager.add_collection.call_args
            assert "RealContent" in call_args[1]["source_path"]
            assert "__MACOSX" not in call_args[1]["source_path"]

    @pytest.mark.asyncio
    async def test_download_zip_size_limit_check(self, zip_manager):
        """Test that download respects size limits"""
        url = "https://example.com/large_file.zip"

        # Mock aiohttp response with large Content-Length
        mock_response = AsyncMock()
        mock_response.headers = {"Content-Length": "600000000"}  # 600 MB
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("fichero.library.zip_manager.aiohttp.ClientSession", return_value=mock_session):
            with pytest.raises(ValueError, match="ZIP file too large"):
                await zip_manager._download_zip(url, timeout=30, max_size_mb=500)

    @pytest.mark.asyncio
    async def test_download_zip_chunk_size_limit(self, zip_manager):
        """Test that download enforces size limit during streaming"""
        url = "https://example.com/file.zip"

        # Mock response without Content-Length (unknown size)
        async def mock_iter_chunked(size):
            # Yield chunks that exceed the limit
            for i in range(100):
                yield b"X" * (10 * 1024 * 1024)  # 10 MB chunks

        mock_response = AsyncMock()
        mock_response.headers = {}  # No Content-Length
        mock_response.content = AsyncMock()
        mock_response.content.iter_chunked = mock_iter_chunked
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.get = Mock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=None)

        with patch("fichero.library.zip_manager.aiohttp.ClientSession", return_value=mock_session):
            with patch("fichero.library.zip_manager.aiofiles.open", create=True):
                with pytest.raises(ValueError, match="Download exceeded maximum size"):
                    await zip_manager._download_zip(url, timeout=30, max_size_mb=50)

    @pytest.mark.asyncio
    async def test_import_from_url_converts_onedrive_links(self, zip_manager, mock_library_manager):
        """Test that OneDrive links are converted before download"""
        sharepoint_url = "https://company.sharepoint.com/:u:/g/personal/user/file.zip"

        with patch.object(zip_manager, '_download_zip', new_callable=AsyncMock) as mock_download:
            with patch.object(zip_manager, '_validate_zip', new_callable=AsyncMock, return_value=True):
                with patch.object(zip_manager, '_extract_zip', new_callable=AsyncMock):
                    with patch.object(zip_manager, '_import_extracted_files', new_callable=AsyncMock):
                        # Mock successful download
                        temp_file = Path(tempfile.mktemp(suffix='.zip'))
                        temp_file.touch()
                        mock_download.return_value = temp_file

                        try:
                            await zip_manager.import_from_url(
                                sharepoint_url,
                                "Test Collection",
                                "",
                                timeout=30,
                                max_zip_size_mb=500
                            )

                            # Verify URL was converted (should not be the original SharePoint URL)
                            called_url = mock_download.call_args[0][0]
                            assert called_url != sharepoint_url
                            assert "/:d:/" in called_url or "/_layouts/15/download.aspx" in called_url
                        finally:
                            if temp_file.exists():
                                temp_file.unlink()

    @pytest.mark.asyncio
    async def test_import_from_url_cleanup_on_success(self, zip_manager, mock_library_manager):
        """Test that temporary files are cleaned up after successful import"""
        url = "https://example.com/file.zip"

        # Create real temp files to verify cleanup
        with tempfile.TemporaryDirectory() as temp_extract_dir:
            temp_extract_path = Path(temp_extract_dir)

            with patch.object(zip_manager, '_download_zip', new_callable=AsyncMock) as mock_download:
                with patch.object(zip_manager, '_validate_zip', new_callable=AsyncMock, return_value=True):
                    with patch.object(zip_manager, '_extract_zip', new_callable=AsyncMock, return_value=temp_extract_path):
                        with patch.object(zip_manager, '_import_extracted_files', new_callable=AsyncMock) as mock_import:
                            # Mock successful import
                            temp_zip = Path(tempfile.mktemp(suffix='.zip'))
                            temp_zip.touch()
                            mock_download.return_value = temp_zip
                            mock_import.return_value = {
                                "success": True,
                                "collection_id": "test-id",
                                "collection_name": "Test",
                                "files_imported": 5,
                                "files_skipped": 0,
                                "errors": 0
                            }

                            result = await zip_manager.import_from_url(url, "Test", "")

                            # ZIP should be deleted
                            assert not temp_zip.exists()
                            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_import_from_url_cleanup_on_error(self, zip_manager):
        """Test that temporary files are cleaned up even on error"""
        url = "https://example.com/file.zip"

        with patch.object(zip_manager, '_download_zip', new_callable=AsyncMock) as mock_download:
            with patch.object(zip_manager, '_validate_zip', new_callable=AsyncMock, return_value=False):
                temp_zip = Path(tempfile.mktemp(suffix='.zip'))
                temp_zip.touch()
                mock_download.return_value = temp_zip

                result = await zip_manager.import_from_url(url, "Test", "")

                # ZIP should still be cleaned up
                assert not temp_zip.exists()
                assert result["success"] is False
                assert "Invalid or corrupted ZIP file" in result["error"]


class TestZipManagerExtensibility:
    """Tests for extensibility patterns for future download managers"""

    def test_link_converter_is_separate_class(self):
        """Test that link conversion is a separate, reusable class"""
        # This design allows for easy addition of other link converters
        # (e.g., DropboxLinkConverter, GoogleDriveLinkConverter)
        converter = OneDriveLinkConverter()
        assert hasattr(converter, 'is_onedrive_link')
        assert hasattr(converter, 'convert_to_direct_download')

    def test_zip_manager_accepts_library_manager_dependency(self):
        """Test that ZipManager uses dependency injection"""
        mock_lib = Mock()
        manager = ZipManager(mock_lib)
        assert manager.library_manager == mock_lib

        # This design makes it easy to:
        # - Mock the library manager for testing
        # - Swap library implementations
        # - Add other managers (TarManager, RarManager, etc.)

    def test_download_method_is_separate_and_overridable(self):
        """Test that download logic is separate and could be extended"""
        mock_lib = Mock()
        manager = ZipManager(mock_lib)

        # The _download_zip method is separate and could be:
        # - Overridden in subclasses
        # - Replaced with different download strategies
        # - Extended with resume/retry logic
        assert hasattr(manager, '_download_zip')
        assert callable(manager._download_zip)


# Integration test markers for future real-world testing
@pytest.mark.integration
@pytest.mark.skip(reason="Requires real SharePoint file and authentication")
class TestZipManagerIntegration:
    """Integration tests with real services (skipped by default)"""

    @pytest.mark.asyncio
    async def test_import_from_public_sharepoint_link(self):
        """Test importing from a real public SharePoint link"""
        # This test would require a real, publicly accessible SharePoint link
        # For now, it's skipped and serves as documentation
        pass

    @pytest.mark.asyncio
    async def test_import_from_authenticated_sharepoint_link(self):
        """Test importing from SharePoint link requiring authentication"""
        # NOTE: This is currently not supported without authentication cookies/tokens
        # Future enhancement: Add support for Microsoft Graph API or OAuth authentication
        pass


if __name__ == "__main__":
    # Run tests with: python -m pytest tests/unit/test_zip_manager.py -v
    pytest.main([__file__, "-v"])
