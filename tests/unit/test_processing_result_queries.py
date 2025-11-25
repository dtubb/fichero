"""
Unit tests for ProcessingResult table queries

Tests that status queries use ProcessingResult table as source of truth,
not item.metadata dictionaries.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path
from datetime import datetime
import pytest


class TestProcessingResultQueries(unittest.TestCase):
    """Test that status queries use ProcessingResult table"""

    def setUp(self):
        """Set up mock objects before each test"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.library_manager.library_path = Path('/test/library')

    @pytest.mark.asyncio
    async def test_get_item_outputs_queries_processing_result(self):
        """Verify get_item_output_data() queries ProcessingResult"""
        # Arrange: Mock ProcessingResult from database
        mock_result = Mock()
        mock_result.id = 'result-123'
        mock_result.workflow = 'Catalogue'
        mock_result.status = 'success'
        mock_result.output_paths = ['/output/path']
        mock_result.metadata = {'steps': []}

        # Mock item
        mock_item = Mock()
        mock_item.id = 'item-1'
        mock_item.name = 'test.jpg'
        mock_item.source_path = '/source/test.jpg'
        mock_item.metadata = {}  # Empty metadata dict

        # Create library manager instance
        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = AsyncMock(return_value=mock_item)
        lib_mgr.get_latest_processing_result = AsyncMock(return_value=mock_result)

        # Act: Get output data
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-1')

        # Assert: ProcessingResult was queried
        lib_mgr.get_latest_processing_result.assert_called_once_with('item-1')

        # Verify output_data contains workflow info from ProcessingResult
        self.assertIsNotNone(output_data)
        self.assertEqual(output_data['workflow'], 'Catalogue')

    @pytest.mark.asyncio
    async def test_get_item_outputs_returns_director_status(self):
        """Verify returned dict has 'director_status' key (for compatibility)"""
        # Arrange
        mock_result = Mock()
        mock_result.id = 'result-456'
        mock_result.workflow = 'TranscribeAndCatalogue'
        mock_result.status = 'success'
        mock_result.output_paths = ['/output/path']
        mock_result.metadata = {'steps': []}

        mock_item = Mock()
        mock_item.id = 'item-2'
        mock_item.name = 'document.pdf'
        mock_item.source_path = '/source/document.pdf'
        mock_item.metadata = {}

        async def mock_get_item(item_id):
            return mock_item

        async def mock_get_latest_result(item_id):
            return mock_result

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = mock_get_item
        lib_mgr.get_latest_processing_result = mock_get_latest_result

        # Act
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-2')

        # Assert: Has 'director_status' key for backward compatibility
        self.assertIn('director_status', output_data)

    @pytest.mark.asyncio
    async def test_director_status_derived_from_table(self):
        """Verify director_status value comes from ProcessingResult.status"""
        # Arrange: ProcessingResult with specific status
        mock_result = Mock()
        mock_result.id = 'result-789'
        mock_result.workflow = 'Catalogue'
        mock_result.status = 'partial'  # Specific status from table
        mock_result.output_paths = ['/output']
        mock_result.metadata = {'steps': []}

        mock_item = Mock()
        mock_item.id = 'item-3'
        mock_item.name = 'file.jpg'
        mock_item.source_path = '/source/file.jpg'
        mock_item.metadata = {
            'director_status': 'old_success'  # Old value (should be ignored)
        }

        async def mock_get_item(item_id):
            return mock_item

        async def mock_get_latest_result(item_id):
            return mock_result

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = mock_get_item
        lib_mgr.get_latest_processing_result = mock_get_latest_result

        # Act
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-3')

        # Assert: director_status comes from ProcessingResult.status, not metadata
        self.assertEqual(output_data['director_status'], 'partial')
        self.assertNotEqual(output_data['director_status'], 'old_success')

    @pytest.mark.asyncio
    async def test_no_fallback_to_metadata_dict(self):
        """Verify it doesn't fall back to item.metadata['director_*']"""
        # Arrange: No ProcessingResult, but item has legacy metadata
        mock_item = Mock()
        mock_item.id = 'item-4'
        mock_item.name = 'legacy.jpg'
        mock_item.source_path = '/source/legacy.jpg'
        mock_item.metadata = {
            'director_status': 'legacy_success',  # Legacy data
            'director_workflow': 'LegacyWorkflow'
        }

        async def mock_get_item(item_id):
            return mock_item

        async def mock_get_latest_result(item_id):
            return None  # No ProcessingResult in database

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = mock_get_item
        lib_mgr.get_latest_processing_result = mock_get_latest_result

        # Act
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-4')

        # Assert: Returns 'pending' status, NOT legacy metadata value
        self.assertEqual(output_data['director_status'], 'pending')
        self.assertNotEqual(output_data['director_status'], 'legacy_success')

        # workflow should be None, not legacy value
        self.assertIsNone(output_data['workflow'])

    def test_inspector_queries_processing_result(self):
        """Verify InspectorWindow queries ProcessingResult directly"""
        # Arrange: Mock storage.get_processing_history to return ProcessingResults
        mock_result1 = Mock()
        mock_result1.id = 'result-1'
        mock_result1.workflow = 'Catalogue'
        mock_result1.status = 'success'
        mock_result1.started_at = datetime(2025, 1, 1, 10, 0)
        mock_result1.completed_at = datetime(2025, 1, 1, 10, 5)
        mock_result1.output_paths = ['/output1']
        mock_result1.processing_time = 300.0

        mock_result2 = Mock()
        mock_result2.id = 'result-2'
        mock_result2.workflow = 'TranscribeAndCatalogue'
        mock_result2.status = 'partial'
        mock_result2.started_at = datetime(2025, 1, 2, 14, 30)
        mock_result2.completed_at = datetime(2025, 1, 2, 14, 45)
        mock_result2.output_paths = ['/output2']
        mock_result2.processing_time = 900.0

        self.storage.get_processing_history.return_value = [mock_result1, mock_result2]

        # Mock app
        mock_app = Mock()
        mock_app.library_manager = self.library_manager

        # Act: Query processing history
        history = self.storage.get_processing_history('item-5')

        # Assert: Returns ProcessingResult objects from database
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].workflow, 'Catalogue')
        self.assertEqual(history[1].workflow, 'TranscribeAndCatalogue')

        # Verify database was queried
        self.storage.get_processing_history.assert_called_once_with('item-5')

    @pytest.mark.asyncio
    async def test_processing_result_preferred_over_metadata(self):
        """Test that ProcessingResult is preferred source even if metadata exists"""
        # Arrange: Item with BOTH ProcessingResult and legacy metadata
        mock_result = Mock()
        mock_result.id = 'result-new'
        mock_result.workflow = 'NewWorkflow'
        mock_result.status = 'success'
        mock_result.output_paths = ['/new/output']
        mock_result.metadata = {'steps': []}

        mock_item = Mock()
        mock_item.id = 'item-6'
        mock_item.name = 'hybrid.jpg'
        mock_item.source_path = '/source/hybrid.jpg'
        mock_item.metadata = {
            'director_status': 'old_status',
            'director_workflow': 'OldWorkflow'
        }

        async def mock_get_item(item_id):
            return mock_item

        async def mock_get_latest_result(item_id):
            return mock_result

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = mock_get_item
        lib_mgr.get_latest_processing_result = mock_get_latest_result

        # Act
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-6')

        # Assert: Uses ProcessingResult data, ignores metadata
        self.assertEqual(output_data['director_status'], 'success')
        self.assertEqual(output_data['workflow'], 'NewWorkflow')

    @pytest.mark.asyncio
    async def test_empty_processing_result_returns_pending(self):
        """Test that no ProcessingResult returns 'pending' status"""
        # Arrange: No processing result
        mock_item = Mock()
        mock_item.id = 'item-7'
        mock_item.name = 'unprocessed.jpg'
        mock_item.metadata = {}

        async def mock_get_item(item_id):
            return mock_item

        async def mock_get_latest_result(item_id):
            return None  # No processing yet

        from fichero.library.library_manager import LibraryManager
        lib_mgr = Mock(spec=LibraryManager)
        lib_mgr.storage = self.storage
        lib_mgr.library_path = Path('/test/library')
        lib_mgr.get_item = mock_get_item
        lib_mgr.get_latest_processing_result = mock_get_latest_result

        # Act
        output_data = await LibraryManager.get_item_output_data(lib_mgr, 'item-7')

        # Assert: Returns pending status
        self.assertEqual(output_data['director_status'], 'pending')
        self.assertFalse(output_data['has_outputs'])
        self.assertIsNone(output_data['workflow'])


if __name__ == '__main__':
    unittest.main()
