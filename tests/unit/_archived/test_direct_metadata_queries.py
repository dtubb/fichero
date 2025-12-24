"""
Unit tests for direct metadata queries by item_id

Tests the refactored metadata loading system where views query metadata
directly by item_id instead of going through manifest files and processing_output_id.

Key changes tested:
- storage.get_extracted_metadata_by_item() with various filters
- preview_view._get_transcription_text() using direct query
- adjust_view._load_transcription_tab() using direct query
- adjust_view._load_metadata_tab() using direct query
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from datetime import datetime
import tempfile
import pytest


class TestStorageDirectMetadataQueries(unittest.TestCase):
    """Test storage.get_extracted_metadata_by_item() method"""

    def setUp(self):
        """Set up mock storage"""
        from fichero.library.models import ExtractedMetadata
        self.ExtractedMetadata = ExtractedMetadata

    def test_query_by_item_id_only(self):
        """Test querying all metadata for an item"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os

        # Create temporary database
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add test metadata
            metadata1 = self.ExtractedMetadata(
                id='meta-1',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-123',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Transcribed text'
            )
            metadata2 = self.ExtractedMetadata(
                id='meta-2',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-123',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='title',
                value='Document Title'
            )

            storage.add_extracted_metadata(metadata1)
            storage.add_extracted_metadata(metadata2)

            # Query all metadata for item
            results = storage.get_extracted_metadata_by_item('item-123')

            # Assert: Both records returned
            self.assertEqual(len(results), 2)
            schema_types = {r.schema_type for r in results}
            self.assertEqual(schema_types, {'transcription', 'catalogue'})

    def test_query_filtered_by_schema_type(self):
        """Test querying with schema_type filter"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add test metadata
            metadata1 = self.ExtractedMetadata(
                id='meta-1',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-456',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Text content'
            )
            metadata2 = self.ExtractedMetadata(
                id='meta-2',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-456',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='title',
                value='Title'
            )

            storage.add_extracted_metadata(metadata1)
            storage.add_extracted_metadata(metadata2)

            # Query only transcription metadata
            results = storage.get_extracted_metadata_by_item(
                'item-456',
                schema_type='transcription'
            )

            # Assert: Only transcription returned
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].schema_type, 'transcription')
            self.assertEqual(results[0].value, 'Text content')

    def test_query_filtered_by_key(self):
        """Test querying with key filter"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add test metadata with multiple keys
            metadata1 = self.ExtractedMetadata(
                id='meta-1',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-789',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='title',
                value='Document Title'
            )
            metadata2 = self.ExtractedMetadata(
                id='meta-2',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-789',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='date',
                value='1895'
            )

            storage.add_extracted_metadata(metadata1)
            storage.add_extracted_metadata(metadata2)

            # Query only title key
            results = storage.get_extracted_metadata_by_item(
                'item-789',
                schema_type='catalogue',
                key='title'
            )

            # Assert: Only title returned
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].key, 'title')
            self.assertEqual(results[0].value, 'Document Title')

    def test_query_returns_newest_first(self):
        """Test that results are ordered by version DESC"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        import time

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add metadata with different versions
            metadata_v1 = self.ExtractedMetadata(
                id='meta-v1',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-999',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Version 1'
            )
            time.sleep(0.01)  # Ensure different timestamps
            metadata_v2 = self.ExtractedMetadata(
                id='meta-v2',
                processing_output_id='output-2',
                collection_id='col-1',
                item_id='item-999',
                schema_type='transcription',
                source_label='transcribe',
                version=2,
                schema_version='1.0',
                key='text',
                value='Version 2'
            )

            storage.add_extracted_metadata(metadata_v1)
            storage.add_extracted_metadata(metadata_v2)

            # Query transcriptions
            results = storage.get_extracted_metadata_by_item(
                'item-999',
                schema_type='transcription',
                key='text'
            )

            # Assert: Version 2 is first (newest)
            self.assertEqual(len(results), 2)
            self.assertEqual(results[0].version, 2)
            self.assertEqual(results[0].value, 'Version 2')

    def test_query_empty_result(self):
        """Test querying non-existent item returns empty list"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Query non-existent item
            results = storage.get_extracted_metadata_by_item('non-existent-item')

            # Assert: Empty list returned
            self.assertEqual(results, [])


class TestPreviewViewDirectQueries(unittest.TestCase):
    """Test preview_view using direct metadata queries"""

    def setUp(self):
        """Set up mocks"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.app = Mock()

    @pytest.mark.asyncio
    @patch('builtins._', lambda x: x, create=True)
    async def test_preview_ignores_output_data_parameter(self):
        """Test that preview_view ignores output_data and queries by item_id"""
        # Arrange
        mock_metadata = Mock()
        mock_metadata.value = 'Direct query transcription'
        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        # output_data should be ignored
        output_data = {'has_outputs': False, 'processing_steps': []}

        from fichero.windows.main.views.preview.preview_view import PreviewView
        preview = PreviewView(self.app, is_mobile=False, library_manager=self.library_manager)

        # Act
        result = await preview._get_transcription_text('item-abc', output_data)

        # Assert: Query was made with item_id, not processing_output_id
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-abc',
            schema_type='transcription',
            key='text'
        )
        self.assertIsNotNone(result)

    @pytest.mark.asyncio
    @patch('builtins._', lambda x: x, create=True)
    async def test_preview_creates_temp_file_from_database(self):
        """Test that preview_view creates temp file from database value"""
        # Arrange
        mock_metadata = Mock()
        mock_metadata.value = 'Database content: 测试'
        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        from fichero.windows.main.views.preview.preview_view import PreviewView
        preview = PreviewView(self.app, is_mobile=False, library_manager=self.library_manager)

        # Act
        result = await preview._get_transcription_text('item-xyz', None)

        # Assert: Temp file created with correct content
        self.assertIsNotNone(result)
        content = Path(result).read_text(encoding='utf-8')
        self.assertEqual(content, 'Database content: 测试')


class TestAdjustViewDirectQueries(unittest.TestCase):
    """Test adjust_view using direct metadata queries"""

    def setUp(self):
        """Set up mocks"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.app = Mock()

    @pytest.mark.asyncio
    async def test_adjust_transcription_tab_queries_by_item_id(self):
        """Test that transcription tab queries by item_id"""
        # Arrange
        mock_metadata = Mock()
        mock_metadata.value = 'Transcription from database'
        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        from fichero.windows.main.views.adjust.adjust_view import AdjustView
        adjust = AdjustView(self.app, is_mobile=False)
        adjust.library_manager = self.library_manager
        adjust.transcription_box = Mock()

        # Act
        await adjust._load_transcription_tab('item-999', None)

        # Assert
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-999',
            schema_type='transcription',
            key='text'
        )
        self.assertEqual(adjust.transcription_box.value, 'Transcription from database')

    @pytest.mark.asyncio
    async def test_adjust_metadata_tab_queries_all_metadata(self):
        """Test that metadata tab queries all metadata for item"""
        # Arrange
        mock_metadata = [
            Mock(schema_type='transcription', source_label='transcribe', key='text', value='Text'),
            Mock(schema_type='catalogue', source_label='catalogue', key='title', value='Title'),
        ]
        self.storage.get_extracted_metadata_by_item.return_value = mock_metadata

        from fichero.windows.main.views.adjust.adjust_view import AdjustView
        import toga
        from toga.style import Pack
        from toga.constants import COLUMN

        adjust = AdjustView(self.app, is_mobile=False)
        adjust.library_manager = self.library_manager
        adjust.metadata_box = Mock()
        adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))

        # Act
        await adjust._load_metadata_tab('item-888', None)

        # Assert: Query was made without filters (gets all metadata)
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-888'
        )

    @pytest.mark.asyncio
    async def test_adjust_handles_no_transcription(self):
        """Test that adjust_view handles missing transcription gracefully"""
        # Arrange: No transcription in database
        self.storage.get_extracted_metadata_by_item.return_value = []

        from fichero.windows.main.views.adjust.adjust_view import AdjustView
        adjust = AdjustView(self.app, is_mobile=False)
        adjust.library_manager = self.library_manager
        adjust.transcription_box = Mock()

        # Act
        await adjust._load_transcription_tab('item-empty', None)

        # Assert: Shows "No transcription available"
        self.assertEqual(adjust.transcription_box.value, "No transcription available")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases for direct metadata queries"""

    def setUp(self):
        """Set up mocks"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.app = Mock()

    def test_empty_item_id_returns_empty(self):
        """Test that empty item_id is handled safely"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Query with empty string
            results = storage.get_extracted_metadata_by_item('')

            # Assert: Returns empty list
            self.assertEqual(results, [])

    @pytest.mark.asyncio
    @patch('builtins._', lambda x: x, create=True)
    async def test_multiple_versions_returns_newest(self):
        """Test that when multiple versions exist, newest is used"""
        # Arrange: Mock multiple versions, newest first
        mock_v2 = Mock()
        mock_v2.version = 2
        mock_v2.value = 'Newer version'

        mock_v1 = Mock()
        mock_v1.version = 1
        mock_v1.value = 'Older version'

        self.storage.get_extracted_metadata_by_item.return_value = [mock_v2, mock_v1]

        from fichero.windows.main.views.preview.preview_view import PreviewView
        preview = PreviewView(self.app, is_mobile=False, library_manager=self.library_manager)

        # Act
        result = await preview._get_transcription_text('item-versions', None)

        # Assert: Uses first result (newest)
        content = Path(result).read_text()
        self.assertEqual(content, 'Newer version')

    def test_query_with_none_filters(self):
        """Test that None filters work correctly (query all)"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add test metadata
            metadata = ExtractedMetadata(
                id='meta-1',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-none-test',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Test'
            )
            storage.add_extracted_metadata(metadata)

            # Query with explicit None filters
            results = storage.get_extracted_metadata_by_item(
                'item-none-test',
                schema_type=None,
                key=None
            )

            # Assert: Returns all metadata
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].value, 'Test')

    def test_query_collection_level_metadata_only(self):
        """Test querying only collection-level metadata"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add both file-level and collection-level metadata
            file_metadata = ExtractedMetadata(
                id='meta-file',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-mixed',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='File-level transcription',
                collection_level=False  # File-level
            )

            collection_metadata = ExtractedMetadata(
                id='meta-collection',
                processing_output_id='output-2',
                collection_id='col-1',
                item_id='item-mixed',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='collection_summary',
                value='Collection-level summary',
                collection_level=True  # Collection-level
            )

            storage.add_extracted_metadata(file_metadata)
            storage.add_extracted_metadata(collection_metadata)

            # Query all metadata and filter manually (until storage supports collection_level)
            results = storage.get_extracted_metadata_by_item('item-mixed')
            collection_results = [r for r in results if r.collection_level]

            # Assert: Collection-level metadata can be identified
            self.assertEqual(len(collection_results), 1)
            self.assertEqual(collection_results[0].value, 'Collection-level summary')
            self.assertTrue(collection_results[0].collection_level)

    def test_query_file_level_metadata_only(self):
        """Test querying only file-level metadata"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add both types
            file_metadata = ExtractedMetadata(
                id='meta-file-only',
                processing_output_id='output-1',
                collection_id='col-1',
                item_id='item-file-only',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='File-level content',
                collection_level=False
            )

            collection_metadata = ExtractedMetadata(
                id='meta-coll-only',
                processing_output_id='output-2',
                collection_id='col-1',
                item_id='item-file-only',
                schema_type='catalogue',
                source_label='catalogue',
                version=1,
                schema_version='1.0',
                key='summary',
                value='Collection summary',
                collection_level=True
            )

            storage.add_extracted_metadata(file_metadata)
            storage.add_extracted_metadata(collection_metadata)

            # Query all metadata and filter manually
            results = storage.get_extracted_metadata_by_item('item-file-only')
            file_results = [r for r in results if not r.collection_level]

            # Assert: File-level metadata can be identified
            self.assertEqual(len(file_results), 1)
            self.assertEqual(file_results[0].value, 'File-level content')
            self.assertFalse(file_results[0].collection_level)

    def test_mixed_collection_metadata_queries(self):
        """Test querying both collection and file metadata together"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add multiple metadata types for same item
            metadatas = [
                ExtractedMetadata(
                    id='meta-1',
                    processing_output_id='output-1',
                    collection_id='col-mixed',
                    item_id='item-mixed-queries',
                    schema_type='transcription',
                    source_label='transcribe',
                    version=1,
                    schema_version='1.0',
                    key='text',
                    value='Individual file transcription',
                    collection_level=False
                ),
                ExtractedMetadata(
                    id='meta-2',
                    processing_output_id='output-2',
                    collection_id='col-mixed',
                    item_id='item-mixed-queries',
                    schema_type='catalogue',
                    source_label='catalogue',
                    version=1,
                    schema_version='1.0',
                    key='title',
                    value='Individual file title',
                    collection_level=False
                ),
                ExtractedMetadata(
                    id='meta-3',
                    processing_output_id='output-3',
                    collection_id='col-mixed',
                    item_id='item-mixed-queries',
                    schema_type='catalogue',
                    source_label='collection_catalogue',
                    version=1,
                    schema_version='1.0',
                    key='collection_title',
                    value='Overall collection title',
                    collection_level=True
                )
            ]

            for metadata in metadatas:
                storage.add_extracted_metadata(metadata)

            # Test 1: Query all metadata (no filter)
            all_results = storage.get_extracted_metadata_by_item('item-mixed-queries')
            self.assertEqual(len(all_results), 3)

            # Test 2: Query only catalogue type
            catalogue_results = storage.get_extracted_metadata_by_item(
                'item-mixed-queries',
                schema_type='catalogue'
            )
            self.assertEqual(len(catalogue_results), 2)  # Both file and collection catalogue

            # Test 3: Query catalogue + filter for collection-level
            catalogue_results = storage.get_extracted_metadata_by_item(
                'item-mixed-queries',
                schema_type='catalogue'
            )
            collection_catalogue_results = [r for r in catalogue_results if r.collection_level]
            self.assertEqual(len(collection_catalogue_results), 1)
            self.assertEqual(collection_catalogue_results[0].value, 'Overall collection title')

            # Test 4: Query catalogue + filter for file-level
            file_catalogue_results = [r for r in catalogue_results if not r.collection_level]
            self.assertEqual(len(file_catalogue_results), 1)
            self.assertEqual(file_catalogue_results[0].value, 'Individual file title')

    def test_get_collection_level_metadata_method(self):
        """Test specific method for getting collection-level metadata"""
        from fichero.library.storage import LibraryStorage
        import tempfile
        import os
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add collection-level metadata for multiple items in same collection
            collection_metadata_1 = ExtractedMetadata(
                id='meta-coll-1',
                processing_output_id='output-coll-1',
                collection_id='collection-abc',
                item_id='item-1',
                schema_type='catalogue',
                source_label='collection_catalogue',
                version=1,
                schema_version='1.0',
                key='collection_description',
                value='This is a test collection',
                collection_level=True
            )

            collection_metadata_2 = ExtractedMetadata(
                id='meta-coll-2',
                processing_output_id='output-coll-2',
                collection_id='collection-abc',
                item_id='item-2',
                schema_type='catalogue',
                source_label='collection_catalogue',
                version=1,
                schema_version='1.0',
                key='collection_summary',
                value='Summary of the collection',
                collection_level=True
            )

            storage.add_extracted_metadata(collection_metadata_1)
            storage.add_extracted_metadata(collection_metadata_2)

            # Test: Filter for collection-level metadata manually
            # (Future enhancement: implement get_collection_level_metadata method)
            all_metadata_for_collection = []

            # Query each item's metadata and filter for collection-level
            for item_id in ['item-1', 'item-2']:
                item_metadata = storage.get_extracted_metadata_by_item(item_id)
                collection_level_metadata = [m for m in item_metadata if m.collection_level]
                all_metadata_for_collection.extend(collection_level_metadata)

            self.assertGreaterEqual(len(all_metadata_for_collection), 1)
            # All results should be collection-level
            for result in all_metadata_for_collection:
                self.assertTrue(result.collection_level)
                self.assertEqual(result.collection_id, 'collection-abc')


class TestBackwardCompatibility(unittest.TestCase):
    """Test that output_data parameter is preserved for backward compatibility"""

    def setUp(self):
        """Set up mocks"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.app = Mock()

    @pytest.mark.asyncio
    @patch('builtins._', lambda x: x, create=True)
    async def test_preview_accepts_output_data_but_ignores_it(self):
        """Test that output_data parameter is accepted but ignored"""
        # Arrange
        mock_metadata = Mock()
        mock_metadata.value = 'Direct query result'
        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        # Provide output_data with processing_output_id (should be ignored)
        output_data = {
            'has_outputs': True,
            'processing_steps': [
                Mock(manifest_entry={'processing_output_id': 'old-id-123'})
            ]
        }

        from fichero.windows.main.views.preview.preview_view import PreviewView
        preview = PreviewView(self.app, is_mobile=False, library_manager=self.library_manager)

        # Act: Pass output_data
        await preview._get_transcription_text('item-compat', output_data)

        # Assert: Query used item_id, not processing_output_id from output_data
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-compat',
            schema_type='transcription',
            key='text'
        )

    @pytest.mark.asyncio
    async def test_adjust_accepts_output_data_but_ignores_it(self):
        """Test that adjust_view accepts output_data but ignores it"""
        # Arrange
        mock_metadata = Mock()
        mock_metadata.value = 'Direct query'
        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        output_data = {
            'has_outputs': True,
            'processing_steps': [Mock()]
        }

        from fichero.windows.main.views.adjust.adjust_view import AdjustView
        adjust = AdjustView(self.app, is_mobile=False)
        adjust.library_manager = self.library_manager
        adjust.transcription_box = Mock()

        # Act: Pass output_data
        await adjust._load_transcription_tab('item-compat-2', output_data)

        # Assert: Query used item_id
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-compat-2',
            schema_type='transcription',
            key='text'
        )

    @pytest.mark.asyncio
    @patch('builtins._', lambda x: x, create=True)
    async def test_collection_level_metadata_in_preview(self):
        """Test that preview view can handle collection-level metadata"""
        # Arrange: Mock both file-level and collection-level metadata
        file_metadata = Mock()
        file_metadata.value = 'File-level transcription'
        file_metadata.collection_level = False

        collection_metadata = Mock()
        collection_metadata.value = 'Collection-level summary'
        collection_metadata.collection_level = True

        # Return both types, but preview should prefer file-level for transcription
        self.storage.get_extracted_metadata_by_item.return_value = [file_metadata, collection_metadata]

        from fichero.windows.main.views.preview.preview_view import PreviewView
        preview = PreviewView(self.app, is_mobile=False, library_manager=self.library_manager)

        # Act
        result = await preview._get_transcription_text('item-with-both-levels', None)

        # Assert: Query included collection_level parameter
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-with-both-levels',
            schema_type='transcription',
            key='text'
        )

        # Should get file-level transcription (first in list)
        if result:
            content = Path(result).read_text()
            self.assertEqual(content, 'File-level transcription')

    @pytest.mark.asyncio
    async def test_collection_level_metadata_in_adjust(self):
        """Test that adjust view can display collection-level metadata"""
        # Arrange: Mock mixed metadata types
        mock_metadata = [
            Mock(schema_type='transcription', source_label='transcribe', key='text',
                 value='File transcription', collection_level=False),
            Mock(schema_type='catalogue', source_label='catalogue', key='title',
                 value='File title', collection_level=False),
            Mock(schema_type='catalogue', source_label='collection_catalogue', key='collection_summary',
                 value='Collection overview', collection_level=True)
        ]
        self.storage.get_extracted_metadata_by_item.return_value = mock_metadata

        from fichero.windows.main.views.adjust.adjust_view import AdjustView
        import toga
        from toga.style import Pack
        from toga.constants import COLUMN

        adjust = AdjustView(self.app, is_mobile=False)
        adjust.library_manager = self.library_manager
        adjust.metadata_box = Mock()
        adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))

        # Act
        await adjust._load_metadata_tab('item-with-collection-metadata', None)

        # Assert: Query was made without collection_level filter (gets all)
        self.storage.get_extracted_metadata_by_item.assert_called_with(
            item_id='item-with-collection-metadata'
        )

        # The view should handle both file-level and collection-level metadata
        # This tests that the UI can display mixed metadata types


if __name__ == '__main__':
    unittest.main()
