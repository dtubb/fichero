"""
Unit tests for manifest enrichment with processing_output_id linkage

Tests the transition from metadata dicts to database tables for Director outputs.
Phase 2 Fix: Verify that _enrich_manifest_entry() adds processing_output_id linkage.
"""

import unittest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from pathlib import Path
from datetime import datetime
import pytest


class TestManifestEnrichment(unittest.TestCase):
    """Test that _enrich_manifest_entry() adds processing_output_id linkage"""

    def setUp(self):
        """Set up mock objects before each test"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage

        # Create a mock enrichment function that we'll test
        from fichero.library.library_manager import LibraryManager
        self.enrich_method = LibraryManager._enrich_manifest_entry

    @pytest.mark.asyncio
    async def test_enrich_adds_processing_output_id(self):
        """Test that _enrich_manifest_entry adds processing_output_id when ProcessingOutput exists"""
        # Arrange: Create mock ProcessingOutput
        mock_output = Mock()
        mock_output.id = "test-output-id-123"
        mock_output.step_name = "transcribe_qwen_max"
        mock_output.output_path = "outputs/test.json"

        self.storage.get_outputs_by_item.return_value = [mock_output]

        # Create manifest entry
        entry = {
            'source': 'test_file.jpg',
            'outputs': ['test.json'],
            'success': True
        }

        # Mock item for source path resolution
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/path/to/test_file.jpg'
        mock_item.metadata = {}

        # Create library manager instance with async support
        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock(return_value='http://iiif.url')

        # Call the actual method
        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output/dir'),
            tool_name='transcribe_qwen_max',
            output_file=Path('test.json'),
            collection_id='collection-123',
            item_id='item-123'
        )

        # Assert: Verify processing_output_id was added
        self.assertEqual(enriched['processing_output_id'], "test-output-id-123")
        self.storage.get_outputs_by_item.assert_called_once_with("item-123")

    @pytest.mark.asyncio
    async def test_enrich_matches_by_step_and_filename(self):
        """Test that enrichment matches ProcessingOutput by step_name and filename"""
        # Arrange: Create multiple outputs with different steps and filenames
        mock_output1 = Mock()
        mock_output1.id = "output-1"
        mock_output1.step_name = "enhance"
        mock_output1.output_path = "outputs/enhanced.jpg"

        mock_output2 = Mock()
        mock_output2.id = "output-2"
        mock_output2.step_name = "transcribe_qwen_max"
        mock_output2.output_path = "outputs/transcription.json"

        mock_output3 = Mock()
        mock_output3.id = "output-3"
        mock_output3.step_name = "transcribe_qwen_max"
        mock_output3.output_path = "outputs/transcription.txt"  # Different extension

        self.storage.get_outputs_by_item.return_value = [mock_output1, mock_output2, mock_output3]

        entry = {'source': 'test.jpg', 'outputs': ['transcription.json']}
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/test.jpg'
        mock_item.metadata = {}

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock()

        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output'),
            tool_name='transcribe_qwen_max',
            output_file=Path('transcription.json'),
            collection_id='coll-1',
            item_id='item-1'
        )

        # Assert: Should match output-2 (correct step_name AND filename)
        self.assertEqual(enriched['processing_output_id'], "output-2")

    @pytest.mark.asyncio
    async def test_enrich_handles_multiple_outputs(self):
        """Test that enrichment uses the first match when multiple ProcessingOutputs exist"""
        # Arrange: Create duplicate outputs (same step, same filename)
        mock_output1 = Mock()
        mock_output1.id = "first-output"
        mock_output1.step_name = "crop"
        mock_output1.output_path = "outputs/cropped.jpg"

        mock_output2 = Mock()
        mock_output2.id = "second-output"
        mock_output2.step_name = "crop"
        mock_output2.output_path = "outputs/cropped.jpg"

        self.storage.get_outputs_by_item.return_value = [mock_output1, mock_output2]

        entry = {'source': 'input.jpg', 'outputs': ['cropped.jpg']}
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/input.jpg'
        mock_item.metadata = {}

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock()

        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output'),
            tool_name='crop',
            output_file=Path('cropped.jpg'),
            collection_id='coll-1',
            item_id='item-1'
        )

        # Assert: Should use the first match
        self.assertEqual(enriched['processing_output_id'], "first-output")

    @pytest.mark.asyncio
    async def test_enrich_handles_no_match(self):
        """Test that enrichment doesn't crash when no ProcessingOutput is found"""
        # Arrange: Return outputs that don't match
        mock_output = Mock()
        mock_output.id = "unrelated-output"
        mock_output.step_name = "different_tool"
        mock_output.output_path = "outputs/different_file.txt"

        self.storage.get_outputs_by_item.return_value = [mock_output]

        entry = {'source': 'test.jpg', 'outputs': ['result.json']}
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/test.jpg'
        mock_item.metadata = {}

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock()

        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output'),
            tool_name='catalogue',
            output_file=Path('result.json'),
            collection_id='coll-1',
            item_id='item-1'
        )

        # Assert: processing_output_id should not be present
        self.assertNotIn('processing_output_id', enriched)
        # But output_path should still be there
        self.assertIn('output_path', enriched)

    @pytest.mark.asyncio
    async def test_enrich_handles_database_error(self):
        """Test that enrichment handles database errors gracefully"""
        # Arrange: Make storage.get_outputs_by_item raise an exception
        self.storage.get_outputs_by_item.side_effect = Exception("Database connection failed")

        entry = {'source': 'test.jpg', 'outputs': ['output.json']}
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/test.jpg'
        mock_item.metadata = {}

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock()

        # Act: Call enrichment - should not raise exception
        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output'),
            tool_name='enhance',
            output_file=Path('output.json'),
            collection_id='coll-1',
            item_id='item-1'
        )

        # Assert: Should still return enriched entry (without processing_output_id)
        self.assertIsNotNone(enriched)
        self.assertNotIn('processing_output_id', enriched)
        self.assertIn('output_path', enriched)

    @pytest.mark.asyncio
    async def test_enrich_handles_empty_outputs_list(self):
        """Test that enrichment handles empty outputs list from database"""
        # Arrange: Return empty list
        self.storage.get_outputs_by_item.return_value = []

        entry = {'source': 'test.jpg', 'outputs': ['result.txt']}
        mock_item = Mock()
        mock_item.storage_type = 'local'
        mock_item.source_path = '/test.jpg'
        mock_item.metadata = {}

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr._construct_iiif_url = Mock()

        enriched = await LibraryManager._enrich_manifest_entry(
            lib_mgr,
            entry=entry,
            item_dir=Path('/output'),
            tool_name='transcribe',
            output_file=Path('result.txt'),
            collection_id='coll-1',
            item_id='item-1'
        )

        # Assert: No processing_output_id added
        self.assertNotIn('processing_output_id', enriched)


if __name__ == '__main__':
    unittest.main()
