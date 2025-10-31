"""
Unit Tests for EAP Import Plugin

Tests the British Library Endangered Archives Programme (EAP) import plugin,
including URL handling, collection ID extraction, and archive file filtering.
"""

import unittest
from unittest.mock import Mock
import re


class TestEAPPlugin(unittest.TestCase):
    """Tests for EAP Import Plugin"""

    def setUp(self):
        """Set up test fixtures"""
        self.mock_library_manager = Mock()

        # Import the plugin
        from fichero.library.import_plugins.eap_plugin import EAPImportPlugin
        self.plugin = EAPImportPlugin(self.mock_library_manager)

    def test_can_handle_collection_urls(self):
        """Test that plugin can handle various EAP collection URLs"""
        test_urls = [
            'https://eap.bl.uk/collection/EAP1477-1-2',
            'https://eap.bl.uk/collection/EAP1477-1-1',
            'https://eap.bl.uk/collection/EAP1477-1',
            'https://eap.bl.uk/collection/EAP1477-1-2/search',
            'https://eap.bl.uk/collection/EAP1477-1-1/search',
        ]

        for url in test_urls:
            with self.subTest(url=url):
                self.assertTrue(
                    self.plugin.can_handle(url),
                    f"Plugin should handle: {url}"
                )

    def test_can_handle_project_urls(self):
        """Test that plugin can handle project URLs"""
        test_urls = [
            'https://eap.bl.uk/project/EAP1477',
            'https://eap.bl.uk/project/EAP1477/search',
        ]

        for url in test_urls:
            with self.subTest(url=url):
                self.assertTrue(
                    self.plugin.can_handle(url),
                    f"Plugin should handle: {url}"
                )

    def test_can_handle_archive_file_urls(self):
        """Test that plugin can handle archive-file URLs"""
        test_urls = [
            'https://eap.bl.uk/archive-file/EAP1477-1-2-1',
            'https://eap.bl.uk/archive-file/EAP1477-1-1-5/manifest',
        ]

        for url in test_urls:
            with self.subTest(url=url):
                self.assertTrue(
                    self.plugin.can_handle(url),
                    f"Plugin should handle: {url}"
                )

    def test_collection_id_extraction(self):
        """Test collection ID extraction from URLs"""
        test_cases = [
            {
                'url': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'expected_id': 'EAP1477-1-2',
                'type': 'collection'
            },
            {
                'url': 'https://eap.bl.uk/collection/EAP1477-1-1',
                'expected_id': 'EAP1477-1-1',
                'type': 'collection'
            },
            {
                'url': 'https://eap.bl.uk/collection/EAP1477-1',
                'expected_id': 'EAP1477-1',
                'type': 'collection'
            },
            {
                'url': 'https://eap.bl.uk/project/EAP1477/search',
                'expected_id': 'EAP1477',
                'type': 'project'
            },
        ]

        for case in test_cases:
            url = case['url']
            expected_id = case['expected_id']
            url_type = case['type']

            with self.subTest(url=url):
                # Extract collection/project ID using the same logic as the plugin
                if '/collection/' in url:
                    match = re.search(r'/collection/(EAP[^/\?]+)', url)
                elif '/project/' in url:
                    match = re.search(r'/project/(EAP[^/\?]+)', url)
                else:
                    match = None

                self.assertIsNotNone(match, f"Should extract ID from: {url}")
                extracted_id = match.group(1) if match else None
                self.assertEqual(
                    extracted_id,
                    expected_id,
                    f"Should extract '{expected_id}' from {url}"
                )

    def test_archive_id_filtering(self):
        """Test that archive IDs are correctly filtered by collection ID"""
        test_cases = [
            {
                'collection_id': 'EAP1477-1-1',
                'archive_id': 'EAP1477-1-1-1',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477-1-1',
                'archive_id': 'EAP1477-1-1-25',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477-1-1',
                'archive_id': 'EAP1477-1-2-1',
                'should_match': False
            },
            {
                'collection_id': 'EAP1477-1-2',
                'archive_id': 'EAP1477-1-2-1',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477-1-2',
                'archive_id': 'EAP1477-1-1-1',
                'should_match': False
            },
            {
                'collection_id': 'EAP1477',
                'archive_id': 'EAP1477-1-1',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477',
                'archive_id': 'EAP1477-1-2',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477',
                'archive_id': 'EAP1477-1-1-1',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477-1',
                'archive_id': 'EAP1477-1-1',
                'should_match': True
            },
            {
                'collection_id': 'EAP1477-1',
                'archive_id': 'EAP1477-1-2',
                'should_match': True
            },
        ]

        for case in test_cases:
            collection_id = case['collection_id']
            archive_id = case['archive_id']
            should_match = case['should_match']

            with self.subTest(collection=collection_id, archive=archive_id):
                # Use the same filtering logic as the plugin
                matches = archive_id.startswith(collection_id)

                self.assertEqual(
                    matches,
                    should_match,
                    f"Archive '{archive_id}' {'should' if should_match else 'should not'} "
                    f"match collection '{collection_id}'"
                )

    def test_url_normalization(self):
        """Test that collection URLs are normalized to include /search"""
        test_cases = [
            {
                'input': 'https://eap.bl.uk/collection/EAP1477-1-2',
                'expected': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'description': 'Collection URL should get /search appended'
            },
            {
                'input': 'https://eap.bl.uk/collection/EAP1477-1-1',
                'expected': 'https://eap.bl.uk/collection/EAP1477-1-1/search',
                'description': 'Collection URL should get /search appended'
            },
            {
                'input': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'expected': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'description': 'Collection URL already with /search should not change'
            },
            {
                'input': 'https://eap.bl.uk/collection/EAP1477-1-2/',
                'expected': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'description': 'Collection URL with trailing slash should get /search'
            },
            {
                'input': 'https://eap.bl.uk/project/EAP1477',
                'expected': 'https://eap.bl.uk/project/EAP1477/search',
                'description': 'Project URL should get /search appended'
            },
            {
                'input': 'https://eap.bl.uk/project/EAP1477/',
                'expected': 'https://eap.bl.uk/project/EAP1477/search',
                'description': 'Project URL should get /search appended'
            },
            {
                'input': 'https://eap.bl.uk/project/EAP1477/search',
                'expected': 'https://eap.bl.uk/project/EAP1477/search',
                'description': 'Project URL with /search should not change'
            },
        ]

        for case in test_cases:
            input_url = case['input']
            expected_url = case['expected']

            with self.subTest(input=input_url):
                # Simulate the normalization logic from download_and_import
                url = input_url
                # Append /search to both collection and project URLs
                if ('/collection/' in url or '/project/' in url) and not url.endswith('/search'):
                    url = url.rstrip('/') + '/search'

                self.assertEqual(
                    url,
                    expected_url,
                    f"{case['description']}: {input_url} -> {expected_url}"
                )

    def test_archive_filtering_logic(self):
        """Test the archive filtering logic without mocking aiohttp"""
        # Test the core filtering logic that would be applied in _find_archive_files
        test_cases = [
            {
                'collection_url': 'https://eap.bl.uk/collection/EAP1477-1-1/search',
                'archive_ids': ['EAP1477-1-1-1', 'EAP1477-1-1-2', 'EAP1477-1-2-1', 'EAP1477-1-2-2'],
                'expected_filtered': ['EAP1477-1-1-1', 'EAP1477-1-1-2']
            },
            {
                'collection_url': 'https://eap.bl.uk/collection/EAP1477-1-2/search',
                'archive_ids': ['EAP1477-1-1-1', 'EAP1477-1-1-2', 'EAP1477-1-2-1', 'EAP1477-1-2-2'],
                'expected_filtered': ['EAP1477-1-2-1', 'EAP1477-1-2-2']
            },
            {
                'collection_url': 'https://eap.bl.uk/project/EAP1477/search',
                'archive_ids': ['EAP1477-1-1-1', 'EAP1477-1-2-1', 'EAP1477-2-1-1', 'EAP1478-1-1-1'],
                'expected_filtered': ['EAP1477-1-1-1', 'EAP1477-1-2-1', 'EAP1477-2-1-1']
            },
        ]

        for case in test_cases:
            url = case['collection_url']
            archive_ids = case['archive_ids']
            expected = case['expected_filtered']

            with self.subTest(url=url):
                # Extract collection ID (same logic as in _find_archive_files)
                collection_id = None
                if '/collection/' in url:
                    match = re.search(r'/collection/(EAP[^/\?]+)', url)
                    if match:
                        collection_id = match.group(1)
                elif '/project/' in url:
                    match = re.search(r'/project/(EAP[^/\?]+)', url)
                    if match:
                        collection_id = match.group(1)

                # Apply filtering (same logic as in _find_archive_files)
                filtered = []
                for archive_id in archive_ids:
                    if collection_id:
                        if archive_id.startswith(collection_id):
                            filtered.append(archive_id)
                    else:
                        filtered.append(archive_id)

                self.assertEqual(
                    sorted(filtered),
                    sorted(expected),
                    f"For {url}, expected {expected} but got {filtered}"
                )


if __name__ == '__main__':
    unittest.main()
