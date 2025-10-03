"""
Unit Tests for URL Import Functionality

Tests URL import components including URLAddView, clipboard functionality,
and CLI bulk import commands.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from pathlib import Path


class TestURLAddView(unittest.TestCase):
    """Tests for URL Add View component"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_app = Mock()
        self.mock_app.is_mobile = False
        self.mock_on_back = Mock()
        self.mock_on_content_added = Mock()

    def test_url_validation(self):
        """Test URL validation logic"""
        from fichero.windows.add.views.url_view import URLAddView

        view = URLAddView(
            app=self.mock_app,
            on_back=self.mock_on_back,
            on_content_added=self.mock_on_content_added
        )

        # Test valid URLs
        valid_urls = [
            'https://example.com',
            'http://test.org/path',
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg',
            'https://subdomain.domain.co.uk/path/file.pdf'
        ]

        for url in valid_urls:
            self.assertTrue(view._is_valid_url(url), f"Should be valid: {url}")

        # Test invalid URLs
        invalid_urls = [
            'not-a-url',
            'ftp://example.com',  # Wrong protocol
            'https://',  # Incomplete
            'http://.',  # Invalid domain
            ''  # Empty
        ]

        for url in invalid_urls:
            self.assertFalse(view._is_valid_url(url), f"Should be invalid: {url}")

    def test_extract_urls_from_text(self):
        """Test URL extraction from mixed text"""
        from fichero.windows.add.views.url_view import URLAddView

        view = URLAddView(
            app=self.mock_app,
            on_back=self.mock_on_back,
            on_content_added=self.mock_on_content_added
        )

        # Test mixed content with URLs
        mixed_text = """
        Here are some URLs:
        https://example.com/page1
        Check out this link: http://test.org/resource
        https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg
        Not a URL: some text here
        https://another-example.com/path/file.pdf
        """

        urls = view._extract_urls_from_text(mixed_text)

        expected_urls = [
            'https://example.com/page1',
            'http://test.org/resource',
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg',
            'https://another-example.com/path/file.pdf'
        ]

        self.assertEqual(len(urls), 4)
        for expected_url in expected_urls:
            self.assertIn(expected_url, urls)

    def test_duplicate_url_removal(self):
        """Test that duplicate URLs are removed"""
        from fichero.windows.add.views.url_view import URLAddView

        view = URLAddView(
            app=self.mock_app,
            on_back=self.mock_on_back,
            on_content_added=self.mock_on_content_added
        )

        text_with_duplicates = """
        https://example.com/page1
        https://test.org/resource
        https://example.com/page1
        https://another.com/file
        https://test.org/resource
        """

        urls = view._extract_urls_from_text(text_with_duplicates)

        # Should have 3 unique URLs
        self.assertEqual(len(urls), 3)

        # Check all expected URLs are present
        expected_urls = [
            'https://example.com/page1',
            'https://test.org/resource',
            'https://another.com/file'
        ]

        for expected_url in expected_urls:
            self.assertIn(expected_url, urls)


class TestBulkImportCommands(unittest.TestCase):
    """Tests for CLI bulk import commands"""

    def setUp(self):
        """Set up test fixtures"""
        # Create temporary directory for testing
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

        # Mock library manager
        self.mock_library_manager = Mock()

        # Mock console
        self.mock_console = Mock()

        # Create bulk import commands instance
        from fichero.cli.commands.library.bulk_import_commands import BulkImportCommands
        self.bulk_import = BulkImportCommands()
        self.bulk_import.library_manager = self.mock_library_manager
        self.bulk_import.console = self.mock_console

    def tearDown(self):
        """Clean up test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_url_format_validation(self):
        """Test URL format validation"""
        # Test valid URLs
        valid_urls = [
            'https://example.com',
            'http://test.org/path/file.html',
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg'
        ]

        for url in valid_urls:
            self.assertTrue(
                self.bulk_import._is_valid_url_format(url),
                f"Should be valid: {url}"
            )

        # Test invalid URLs
        invalid_urls = [
            'not-a-url',
            'ftp://example.com',
            'https://',
            'http://.',
            ''
        ]

        for url in invalid_urls:
            self.assertFalse(
                self.bulk_import._is_valid_url_format(url),
                f"Should be invalid: {url}"
            )

    def test_extract_urls_from_text_cli(self):
        """Test URL extraction in CLI context"""
        test_text = """
        # EAP Collection URLs
        https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg
        https://images.eap.bl.uk/EAP1477/EAP1477_1_2_2/1.jp2/full/max/0/default.jpg

        Some other text here
        https://example.com/resource

        // Comment line
        https://test.org/final
        """

        urls = self.bulk_import._extract_urls_from_text(test_text)

        self.assertEqual(len(urls), 4)
        self.assertIn('https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg', urls)
        self.assertIn('https://images.eap.bl.uk/EAP1477/EAP1477_1_2_2/1.jp2/full/max/0/default.jpg', urls)
        self.assertIn('https://example.com/resource', urls)
        self.assertIn('https://test.org/final', urls)

    def test_generate_url_name(self):
        """Test URL name generation"""
        test_cases = [
            {
                'url': 'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg',
                'index': 1,
                'expected_contains': ['Default']  # Should extract "default" and format it
            },
            {
                'url': 'https://example.com/documents/research-paper.pdf',
                'index': 5,
                'expected_contains': ['Research Paper']  # Should extract and format filename
            },
            {
                'url': 'https://simple-domain.com/',
                'index': 10,
                'expected_contains': ['simple-domain.com', '010']  # Should use domain + index
            }
        ]

        for case in test_cases:
            name = self.bulk_import._generate_url_name(case['url'], case['index'])

            for expected in case['expected_contains']:
                self.assertIn(expected, name,
                    f"Generated name '{name}' should contain '{expected}' for URL {case['url']}")

    async def test_import_url_list(self):
        """Test the URL list import process"""
        # Mock collection creation
        mock_collection_id = 'test_collection_123'
        self.mock_library_manager.add_collection = AsyncMock(return_value=mock_collection_id)
        self.mock_library_manager.add_item_to_collection = AsyncMock(return_value='item_123')

        test_urls = [
            'https://example.com/doc1.pdf',
            'https://test.org/doc2.html',
            'https://images.site.com/image.jpg'
        ]

        # Test the import process
        await self.bulk_import._import_url_list(
            urls=test_urls,
            collection_name='Test Collection',
            description='Test description',
            validate_urls=False
        )

        # Verify collection was created
        self.mock_library_manager.add_collection.assert_called_once()

        # Verify all URLs were added
        self.assertEqual(self.mock_library_manager.add_item_to_collection.call_count, 3)

        # Verify proper parameters were used
        calls = self.mock_library_manager.add_item_to_collection.call_args_list
        for i, call in enumerate(calls):
            args, kwargs = call
            self.assertEqual(kwargs['collection_id'], mock_collection_id)
            self.assertEqual(kwargs['item_type'], 'url')
            self.assertEqual(kwargs['source'], test_urls[i])
            self.assertEqual(kwargs['operation'], 'link')  # Reference only


class TestURLImportIntegration(unittest.TestCase):
    """Integration tests for URL import workflow"""

    def setUp(self):
        """Set up integration test fixtures"""
        # Create temporary directory for testing
        import tempfile
        self.temp_dir = Path(tempfile.mkdtemp())

        # Create test URL file
        self.test_urls = [
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_1/1.jp2/full/max/0/default.jpg',
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_2/1.jp2/full/max/0/default.jpg',
            'https://images.eap.bl.uk/EAP1477/EAP1477_1_2_3/1.jp2/full/max/0/default.jpg'
        ]

        self.url_file = self.temp_dir / 'test_urls.txt'
        self.url_file.write_text('\n'.join(self.test_urls))

    def tearDown(self):
        """Clean up test files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    async def test_end_to_end_url_import(self):
        """Test complete URL import workflow"""
        try:
            # Import real components for integration test
            from fichero.library.library_manager import LibraryManager
            from fichero.windows.main.services.library_service import LibraryService

            # Create real library manager
            library_manager = LibraryManager(self.temp_dir)
            library_service = LibraryService(library_manager)

            # Create collection
            from fichero.library.models import Collection
            collection = Collection(
                name='EAP URL Test Collection',
                type='url',
                metadata={'description': 'Test collection for URL references'}
            )

            collection_id = await library_manager.add_collection(collection)
            self.assertIsNotNone(collection_id)

            # Add URLs as references (no downloading)
            for i, url in enumerate(self.test_urls, 1):
                item_id = await library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type='url',
                    source=url,
                    name=f'EAP Document {i:02d}'
                )
                self.assertIsNotNone(item_id)

            # Verify collection contains URL references
            collections = await library_service.get_collections_for_ui()
            self.assertEqual(len(collections), 1)
            self.assertEqual(collections[0]['name'], 'EAP URL Test Collection')
            self.assertEqual(collections[0]['item_count'], 3)

            # Verify items are URL references
            items = await library_service.get_collection_items_for_ui(collection_id)
            self.assertEqual(len(items), 3)

            for item in items:
                self.assertEqual(item['type'], 'url')
                self.assertIn('https://images.eap.bl.uk/', item['source'])

        except ImportError as e:
            self.skipTest(f"Required modules not available: {e}")

    def test_file_based_url_import(self):
        """Test importing URLs from file"""
        # Read URLs from file
        urls_from_file = self.url_file.read_text().strip().split('\n')

        # Verify all URLs are valid
        from fichero.cli.commands.library.bulk_import_commands import BulkImportCommands
        bulk_import = BulkImportCommands()

        for url in urls_from_file:
            self.assertTrue(bulk_import._is_valid_url_format(url))

        # Verify we got the expected URLs
        self.assertEqual(len(urls_from_file), 3)
        for expected_url in self.test_urls:
            self.assertIn(expected_url, urls_from_file)


def run_async_test(test_func):
    """Helper to run async tests"""
    def wrapper(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(test_func(self))
        finally:
            loop.close()
    return wrapper


# Apply async wrapper to async test methods
for name, method in TestBulkImportCommands.__dict__.items():
    if name.startswith('test_') and asyncio.iscoroutinefunction(method):
        setattr(TestBulkImportCommands, name, run_async_test(method))

for name, method in TestURLImportIntegration.__dict__.items():
    if name.startswith('test_') and asyncio.iscoroutinefunction(method):
        setattr(TestURLImportIntegration, name, run_async_test(method))


if __name__ == '__main__':
    unittest.main()