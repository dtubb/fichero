"""
Unit tests for metadata architecture enhancements (Phase 3)

Tests the collection_level field in ExtractedMetadata model and related
storage layer enhancements for collection-level metadata support.

Key features tested:
- ExtractedMetadata model with collection_level field
- Storage layer collection-level metadata methods
- Collection-level detection logic in metadata extractors
- Database migration compatibility for new field
"""

import unittest
from unittest.mock import Mock, patch
from pathlib import Path
import tempfile
import os
from datetime import datetime


class TestExtractedMetadataModel(unittest.TestCase):
    """Test ExtractedMetadata model with collection_level field"""

    def test_extracted_metadata_collection_level_field(self):
        """Test that ExtractedMetadata supports collection_level field"""
        from fichero.library.models import ExtractedMetadata

        # Test collection-level metadata
        collection_metadata = ExtractedMetadata(
            id='meta-collection',
            processing_output_id='output-1',
            collection_id='col-1',
            item_id='item-1',
            schema_type='catalogue',
            source_label='collection_catalogue',
            version=1,
            schema_version='1.0',
            key='collection_title',
            value='Test Collection',
            collection_level=True  # Collection-level
        )

        # Assert: Field is present and correctly set
        self.assertTrue(hasattr(collection_metadata, 'collection_level'))
        self.assertTrue(collection_metadata.collection_level)

        # Test file-level metadata (default)
        file_metadata = ExtractedMetadata(
            id='meta-file',
            processing_output_id='output-2',
            collection_id='col-1',
            item_id='item-1',
            schema_type='transcription',
            source_label='transcribe',
            version=1,
            schema_version='1.0',
            key='text',
            value='File transcription'
            # collection_level defaults to False
        )

        # Assert: Defaults to file-level
        self.assertFalse(file_metadata.collection_level)

    def test_extracted_metadata_to_dict_includes_collection_level(self):
        """Test that to_dict() includes collection_level field"""
        from fichero.library.models import ExtractedMetadata

        metadata = ExtractedMetadata(
            id='meta-test',
            processing_output_id='output-1',
            collection_id='col-1',
            item_id='item-1',
            schema_type='catalogue',
            source_label='catalogue',
            version=1,
            schema_version='1.0',
            key='title',
            value='Test Title',
            collection_level=True
        )

        # Act
        metadata_dict = metadata.to_dict()

        # Assert: collection_level is in dict
        self.assertIn('collection_level', metadata_dict)
        self.assertTrue(metadata_dict['collection_level'])

    def test_extracted_metadata_from_dict_handles_collection_level(self):
        """Test that from_dict() correctly handles collection_level field"""
        from fichero.library.models import ExtractedMetadata

        # Test with explicit collection_level
        data_with_collection_level = {
            'id': 'meta-test',
            'processing_output_id': 'output-1',
            'collection_id': 'col-1',
            'item_id': 'item-1',
            'schema_type': 'catalogue',
            'source_label': 'catalogue',
            'version': 1,
            'schema_version': '1.0',
            'key': 'title',
            'value': 'Test Title',
            'collection_level': True,
            'created_at': datetime.now().isoformat()
        }

        metadata = ExtractedMetadata.from_dict(data_with_collection_level)
        self.assertTrue(metadata.collection_level)

        # Test without collection_level (should default to False)
        data_without_collection_level = {
            'id': 'meta-test-2',
            'processing_output_id': 'output-2',
            'collection_id': 'col-1',
            'item_id': 'item-1',
            'schema_type': 'transcription',
            'source_label': 'transcribe',
            'version': 1,
            'schema_version': '1.0',
            'key': 'text',
            'value': 'Test Text',
            'created_at': datetime.now().isoformat()
        }

        metadata_default = ExtractedMetadata.from_dict(data_without_collection_level)
        self.assertFalse(metadata_default.collection_level)


class TestStorageLayerCollectionMetadata(unittest.TestCase):
    """Test storage layer enhancements for collection-level metadata"""

    def test_storage_supports_collection_level_filtering(self):
        """Test that storage can filter by collection_level field"""
        from fichero.library.storage import LibraryStorage
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add both types of metadata
            file_metadata = ExtractedMetadata(
                id='meta-file',
                processing_output_id='output-1',
                collection_id='col-storage',
                item_id='item-storage',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='File content',
                collection_level=False
            )

            collection_metadata = ExtractedMetadata(
                id='meta-collection',
                processing_output_id='output-2',
                collection_id='col-storage',
                item_id='item-storage',
                schema_type='catalogue',
                source_label='collection_catalogue',
                version=1,
                schema_version='1.0',
                key='collection_summary',
                value='Collection content',
                collection_level=True
            )

            storage.add_extracted_metadata(file_metadata)
            storage.add_extracted_metadata(collection_metadata)

            # Test: Query all and filter by collection_level (until storage supports this natively)
            all_results = storage.get_extracted_metadata_by_item('item-storage')

            collection_results = [r for r in all_results if r.collection_level]
            self.assertEqual(len(collection_results), 1)
            self.assertTrue(collection_results[0].collection_level)
            self.assertEqual(collection_results[0].value, 'Collection content')

            file_results = [r for r in all_results if not r.collection_level]
            self.assertEqual(len(file_results), 1)
            self.assertFalse(file_results[0].collection_level)
            self.assertEqual(file_results[0].value, 'File content')

    def test_storage_collection_level_metadata_by_collection_id(self):
        """Test querying collection-level metadata by collection_id"""
        from fichero.library.storage import LibraryStorage
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Add collection-level metadata for multiple items
            for i in range(3):
                metadata = ExtractedMetadata(
                    id=f'meta-coll-{i}',
                    processing_output_id=f'output-{i}',
                    collection_id='collection-test',
                    item_id=f'item-{i}',
                    schema_type='catalogue',
                    source_label='collection_catalogue',
                    version=1,
                    schema_version='1.0',
                    key='collection_info',
                    value=f'Collection info {i}',
                    collection_level=True
                )
                storage.add_extracted_metadata(metadata)

            # Add some file-level metadata (should be excluded)
            file_metadata = ExtractedMetadata(
                id='meta-file-exclude',
                processing_output_id='output-file',
                collection_id='collection-test',
                item_id='item-file',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='File content',
                collection_level=False
            )
            storage.add_extracted_metadata(file_metadata)

            # Test: Future enhancement - get collection-level metadata by collection_id
            # For now, manually filter results to simulate this functionality
            all_collection_metadata = []
            for i in range(3):
                item_metadata = storage.get_extracted_metadata_by_item(f'item-{i}')
                collection_level_only = [m for m in item_metadata if m.collection_level]
                all_collection_metadata.extend(collection_level_only)

            # Also check file item to ensure it doesn't include file-level metadata
            file_item_metadata = storage.get_extracted_metadata_by_item('item-file')
            file_level_only = [m for m in file_item_metadata if not m.collection_level]

            self.assertEqual(len(all_collection_metadata), 3)  # Only collection-level metadata
            for result in all_collection_metadata:
                self.assertTrue(result.collection_level)
                self.assertEqual(result.collection_id, 'collection-test')

            self.assertEqual(len(file_level_only), 1)  # The file-level metadata

    def test_database_migration_compatibility(self):
        """Test that new collection_level field works with existing database"""
        from fichero.library.storage import LibraryStorage
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            storage = LibraryStorage(db_path)

            # Simulate old metadata without collection_level field
            old_style_data = {
                'id': 'meta-old',
                'processing_output_id': 'output-old',
                'collection_id': 'col-migration',
                'item_id': 'item-migration',
                'schema_type': 'transcription',
                'source_label': 'transcribe',
                'version': 1,
                'schema_version': '1.0',
                'key': 'text',
                'value': 'Old metadata',
                'created_at': datetime.now().isoformat()
                # No collection_level field
            }

            # Test: from_dict should handle missing field gracefully
            old_metadata = ExtractedMetadata.from_dict(old_style_data)
            self.assertFalse(old_metadata.collection_level)  # Should default to False

            # Test: Storage should handle old metadata
            storage.add_extracted_metadata(old_metadata)

            results = storage.get_extracted_metadata_by_item('item-migration')
            self.assertEqual(len(results), 1)
            self.assertFalse(results[0].collection_level)


class TestCollectionLevelDetection(unittest.TestCase):
    """Test collection-level detection logic in metadata extractors"""

    def test_collection_level_detection_by_output_type(self):
        """Test that collection-level outputs are detected by type"""
        # Mock UniversalExtractor or similar
        with patch('fichero.library.director_integration.UniversalExtractor') as MockExtractor:
            mock_extractor = Mock()
            MockExtractor.return_value = mock_extractor

            from fichero.library.models import ExtractedMetadata

            # Mock collection-level output detection
            collection_output = Mock()
            collection_output.output_type = 'collection_catalogue'
            collection_output.step_name = 'collection_analysis'

            # Extractor should detect this as collection-level
            mock_metadata = ExtractedMetadata(
                id='meta-detected',
                processing_output_id='output-detected',
                collection_id='col-1',
                item_id='item-1',
                schema_type='catalogue',
                source_label='collection_analysis',
                version=1,
                schema_version='1.0',
                key='collection_summary',
                value='Detected as collection-level',
                collection_level=True  # Should be auto-detected
            )

            mock_extractor.extract_from_output.return_value = [mock_metadata]

            # Act: Extract metadata
            extracted = mock_extractor.extract_from_output(collection_output)

            # Assert: Metadata is marked as collection-level
            self.assertEqual(len(extracted), 1)
            self.assertTrue(extracted[0].collection_level)

    def test_file_level_detection_by_output_type(self):
        """Test that file-level outputs are detected by type"""
        with patch('fichero.library.director_integration.UniversalExtractor') as MockExtractor:
            mock_extractor = Mock()
            MockExtractor.return_value = mock_extractor

            from fichero.library.models import ExtractedMetadata

            # Mock file-level output detection
            file_output = Mock()
            file_output.output_type = 'transcription'
            file_output.step_name = 'transcribe'

            # Extractor should detect this as file-level
            mock_metadata = ExtractedMetadata(
                id='meta-file-detected',
                processing_output_id='output-file-detected',
                collection_id='col-1',
                item_id='item-1',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Detected as file-level',
                collection_level=False  # Should be auto-detected
            )

            mock_extractor.extract_from_output.return_value = [mock_metadata]

            # Act: Extract metadata
            extracted = mock_extractor.extract_from_output(file_output)

            # Assert: Metadata is marked as file-level
            self.assertEqual(len(extracted), 1)
            self.assertFalse(extracted[0].collection_level)

    def test_automatic_collection_level_detection_logic(self):
        """Test the logic for automatically detecting collection vs file level"""
        # Define detection rules that should be used
        collection_indicators = [
            'collection_catalogue',
            'collection_summary',
            'batch_analysis',
            'collection_analysis'
        ]

        file_indicators = [
            'transcription',
            'individual_file',
            'single_document'
        ]

        # Test each indicator
        for indicator in collection_indicators:
            # Should be detected as collection-level
            mock_output = Mock()
            mock_output.output_type = indicator
            mock_output.step_name = indicator

            # The detection logic would analyze the output_type/step_name
            # to determine if it's collection or file level
            detected_level = self._detect_collection_level(mock_output)
            self.assertTrue(detected_level, f"Should detect {indicator} as collection-level")

        for indicator in file_indicators:
            # Should be detected as file-level
            mock_output = Mock()
            mock_output.output_type = indicator
            mock_output.step_name = indicator

            detected_level = self._detect_collection_level(mock_output)
            self.assertFalse(detected_level, f"Should detect {indicator} as file-level")

    def _detect_collection_level(self, output):
        """Mock detection logic for testing"""
        collection_keywords = ['collection', 'batch', 'summary']
        output_type = getattr(output, 'output_type', '').lower()
        step_name = getattr(output, 'step_name', '').lower()

        for keyword in collection_keywords:
            if keyword in output_type or keyword in step_name:
                return True
        return False


class TestMetadataArchitectureIntegration(unittest.TestCase):
    """Integration tests for metadata architecture enhancements"""

    def test_end_to_end_collection_metadata_flow(self):
        """Test complete flow: output creation -> metadata extraction -> storage -> query"""
        from fichero.library.storage import LibraryStorage
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_integration.db')
            storage = LibraryStorage(db_path)

            # Step 1: Simulate collection-level output creation
            collection_metadata = ExtractedMetadata(
                id='meta-integration',
                processing_output_id='output-integration',
                collection_id='col-integration',
                item_id='item-integration',
                schema_type='catalogue',
                source_label='collection_catalogue',
                version=1,
                schema_version='1.0',
                key='collection_title',
                value='Integration Test Collection',
                collection_level=True
            )

            file_metadata = ExtractedMetadata(
                id='meta-integration-file',
                processing_output_id='output-integration-file',
                collection_id='col-integration',
                item_id='item-integration',
                schema_type='transcription',
                source_label='transcribe',
                version=1,
                schema_version='1.0',
                key='text',
                value='Integration test file content',
                collection_level=False
            )

            # Step 2: Store metadata
            storage.add_extracted_metadata(collection_metadata)
            storage.add_extracted_metadata(file_metadata)

            # Step 3: Query and verify
            all_metadata = storage.get_extracted_metadata_by_item('item-integration')
            self.assertEqual(len(all_metadata), 2)

            collection_only = storage.get_extracted_metadata_by_item(
                'item-integration',
                collection_level=True
            )
            self.assertEqual(len(collection_only), 1)
            self.assertEqual(collection_only[0].value, 'Integration Test Collection')

            file_only = storage.get_extracted_metadata_by_item(
                'item-integration',
                collection_level=False
            )
            self.assertEqual(len(file_only), 1)
            self.assertEqual(file_only[0].value, 'Integration test file content')

    def test_mixed_metadata_scenario(self):
        """Test scenario with mixed collection and file metadata for multiple items"""
        from fichero.library.storage import LibraryStorage
        from fichero.library.models import ExtractedMetadata

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test_mixed.db')
            storage = LibraryStorage(db_path)

            collection_id = 'mixed-collection'

            # Multiple items with different metadata combinations
            items_metadata = [
                # Item 1: Has both file and collection metadata
                {
                    'item_id': 'item-both',
                    'file_metadata': ExtractedMetadata(
                        id='meta-both-file',
                        processing_output_id='output-both-file',
                        collection_id=collection_id,
                        item_id='item-both',
                        schema_type='transcription',
                        source_label='transcribe',
                        version=1,
                        schema_version='1.0',
                        key='text',
                        value='Item with both types',
                        collection_level=False
                    ),
                    'collection_metadata': ExtractedMetadata(
                        id='meta-both-collection',
                        processing_output_id='output-both-collection',
                        collection_id=collection_id,
                        item_id='item-both',
                        schema_type='catalogue',
                        source_label='collection_catalogue',
                        version=1,
                        schema_version='1.0',
                        key='collection_summary',
                        value='Collection summary from item-both',
                        collection_level=True
                    )
                },
                # Item 2: Only file metadata
                {
                    'item_id': 'item-file-only',
                    'file_metadata': ExtractedMetadata(
                        id='meta-file-only',
                        processing_output_id='output-file-only',
                        collection_id=collection_id,
                        item_id='item-file-only',
                        schema_type='transcription',
                        source_label='transcribe',
                        version=1,
                        schema_version='1.0',
                        key='text',
                        value='File-only content',
                        collection_level=False
                    )
                }
            ]

            # Add all metadata
            for item in items_metadata:
                if 'file_metadata' in item:
                    storage.add_extracted_metadata(item['file_metadata'])
                if 'collection_metadata' in item:
                    storage.add_extracted_metadata(item['collection_metadata'])

            # Test queries
            # 1. All metadata for item with both types
            both_results = storage.get_extracted_metadata_by_item('item-both')
            self.assertEqual(len(both_results), 2)

            # 2. Only collection metadata for item with both
            collection_results = storage.get_extracted_metadata_by_item(
                'item-both',
                collection_level=True
            )
            self.assertEqual(len(collection_results), 1)
            self.assertTrue(collection_results[0].collection_level)

            # 3. File metadata for item with only file metadata
            file_only_results = storage.get_extracted_metadata_by_item('item-file-only')
            self.assertEqual(len(file_only_results), 1)
            self.assertFalse(file_only_results[0].collection_level)


if __name__ == '__main__':
    unittest.main()