"""
Unit Tests for URLDownloader

Tests the URL download and caching functionality.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import asyncio
from pathlib import Path
import tempfile
import shutil


class TestURLDownloader(unittest.TestCase):
    """Unit tests for URLDownloader class"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for cache
        self.temp_dir = Path(tempfile.mkdtemp())

        # Import URLDownloader
        from fichero.library.url_downloader import URLDownloader
        self.downloader = URLDownloader(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures"""
        # Remove temporary directory
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_url_downloader_initialization(self):
        """Test URLDownloader initializes correctly"""
        self.assertIsNotNone(self.downloader)
        self.assertEqual(self.downloader.cache_root, self.temp_dir)
        self.assertTrue(self.temp_dir.exists())

    def test_extract_filename_with_extension(self):
        """Test filename extraction from URL with extension"""
        url = "https://example.com/path/to/image.jpg"
        filename = self.downloader._extract_filename(url)
        self.assertEqual(filename, "image.jpg")

    def test_extract_filename_with_special_chars(self):
        """Test filename extraction with URL encoding"""
        url = "https://example.com/path/to/my%20image.jpg"
        filename = self.downloader._extract_filename(url)
        self.assertEqual(filename, "my image.jpg")

    def test_extract_filename_without_extension(self):
        """Test filename extraction when URL has no extension"""
        url = "https://example.com/path/to/resource"
        filename = self.downloader._extract_filename(url)
        # Should create a hashed filename when no extension is found
        self.assertTrue(filename.startswith("download_"))

    def test_guess_content_type_jpg(self):
        """Test content type guessing for JPEG files"""
        path = Path("test.jpg")
        content_type = self.downloader._guess_content_type(path)
        self.assertEqual(content_type, "image/jpeg")

    def test_guess_content_type_png(self):
        """Test content type guessing for PNG files"""
        path = Path("test.png")
        content_type = self.downloader._guess_content_type(path)
        self.assertEqual(content_type, "image/png")

    def test_guess_content_type_unknown(self):
        """Test content type guessing for unknown files"""
        path = Path("test.unknownextension123")
        content_type = self.downloader._guess_content_type(path)
        self.assertEqual(content_type, "application/octet-stream")

    def test_get_cache_size_empty(self):
        """Test cache size calculation when cache is empty"""
        size = self.downloader.get_cache_size()
        self.assertEqual(size, 0)

    def test_get_cache_size_with_collection(self):
        """Test cache size calculation for specific collection"""
        # Create test collection directory with a file
        collection_id = "test_collection"
        collection_dir = self.temp_dir / collection_id
        collection_dir.mkdir()

        test_file = collection_dir / "test.txt"
        test_file.write_text("Hello, World!")

        size = self.downloader.get_cache_size(collection_id)
        self.assertEqual(size, 13)  # "Hello, World!" is 13 bytes

    def test_clear_cache_empty(self):
        """Test clearing empty cache"""
        deleted = self.downloader.clear_cache()
        self.assertEqual(deleted, 0)

    def test_clear_cache_with_files(self):
        """Test clearing cache with files"""
        # Create test collection directory with files
        collection_id = "test_collection"
        collection_dir = self.temp_dir / collection_id
        collection_dir.mkdir()

        # Create test files
        for i in range(3):
            test_file = collection_dir / f"test{i}.txt"
            test_file.write_text(f"Content {i}")

        deleted = self.downloader.clear_cache(collection_id)
        self.assertEqual(deleted, 3)
        self.assertFalse(collection_dir.exists())  # Directory should be removed

    # Note: Full download_url() testing is done via integration tests
    # and CLI testing since async mocking is complex. The method has been
    # validated to work with real URLs in manual testing.


if __name__ == '__main__':
    unittest.main()
