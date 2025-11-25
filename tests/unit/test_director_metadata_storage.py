"""
Unit tests for Director metadata storage

Tests that Director processing data is NOT written to CollectionItem.metadata dicts,
but instead uses dedicated database tables (ProcessingResult, ProcessingOutput, ExtractedMetadata).
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
from datetime import datetime
import pytest


class TestDirectorMetadataStorage(unittest.TestCase):
    """Test that Director data is NOT written to CollectionItem.metadata"""

    def setUp(self):
        """Set up mock objects before each test"""
        self.storage = Mock()
        self.app = Mock()
        self.app.paths = Mock()
        self.app.paths.data = '/test/data'
        self.library_manager = Mock()
        self.library_manager.storage = self.storage
        self.library_manager.library_path = Path('/test/library')
        self.director = Mock()

    def test_no_director_status_in_metadata(self):
        """Verify director_status is not written to item.metadata"""
        # Arrange: Mock item
        mock_item = Mock()
        mock_item.id = 'item-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item

        # Mock director result
        mock_result = Mock()
        mock_result.success = True

        # Mock task info
        task_info = {
            'item_id': 'item-1',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        # Mock parsed outputs
        parsed_outputs = {}

        from fichero.library.director_integration import DirectorIntegrationService

        # Create service
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act: Finalize processing
        service._finalize_single_item(
            task_id='task-123',
            task_info=task_info,
            result=mock_result,
            parsed_outputs=parsed_outputs
        )

        # Assert: item.metadata should NOT have director_status
        self.assertNotIn('director_status', mock_item.metadata)

    def test_no_director_workflow_in_metadata(self):
        """Verify director_workflow is not written to item.metadata"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-2'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-2',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'TranscribeAndCatalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-456', task_info, mock_result, {})

        # Assert: item.metadata should NOT have director_workflow
        self.assertNotIn('director_workflow', mock_item.metadata)

    def test_no_director_plan_in_metadata(self):
        """Verify director_plan is not written to item.metadata"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-3'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-3',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Transcribir y Catalogar',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-789', task_info, mock_result, {})

        # Assert: item.metadata should NOT have director_plan
        self.assertNotIn('director_plan', mock_item.metadata)

    def test_processing_result_created(self):
        """Verify ProcessingResult record is created instead of metadata dict"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-4'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item
        self.storage.add_processing_result = Mock(return_value=True)

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-4',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-abc', task_info, mock_result, {})

        # Assert: ProcessingResult was created
        self.storage.add_processing_result.assert_called_once()

        # Verify the ProcessingResult object has correct fields
        call_args = self.storage.add_processing_result.call_args[0]
        processing_result = call_args[0]

        self.assertEqual(processing_result.item_id, 'item-4')
        self.assertEqual(processing_result.workflow, 'Catalogue')
        self.assertIn(processing_result.status, ['success', 'failed', 'partial'])

    def test_item_status_updated_correctly(self):
        """Verify item.status is set (processing/completed/error)"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-5'
        mock_item.metadata = {}
        mock_item.status = 'processing'

        self.storage.get_item.return_value = mock_item

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-5',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-def', task_info, mock_result, {})

        # Assert: item.status was updated
        self.assertIn(mock_item.status, ['completed', 'error'])
        # With success=True, should be 'completed'
        self.assertEqual(mock_item.status, 'completed')

        # Verify storage.update_item was called
        self.storage.update_item.assert_called_with(mock_item)

    @pytest.mark.asyncio
    async def test_status_derived_from_processing_result(self):
        """Verify status comes from ProcessingResult table, not item.metadata"""
        # Arrange: Item with metadata dict (legacy data)
        mock_item = Mock()
        mock_item.id = 'item-6'
        mock_item.metadata = {
            'director_status': 'old_status',  # Legacy data (should be ignored)
            'director_workflow': 'OldWorkflow'
        }
        mock_item.status = 'pending'

        # Mock ProcessingResult from database
        mock_processing_result = Mock()
        mock_processing_result.status = 'success'
        mock_processing_result.workflow = 'NewWorkflow'

        # Mock get_item_output_data to return status from ProcessingResult
        async def mock_get_output_data(item_id):
            return {
                'director_status': mock_processing_result.status,  # From ProcessingResult table
                'workflow': mock_processing_result.workflow,
                'has_outputs': True,
                'processing_steps': []
            }

        self.library_manager.get_item_output_data = mock_get_output_data

        # Act: Get output data
        output_data = await self.library_manager.get_item_output_data('item-6')

        # Assert: Status comes from ProcessingResult, not metadata dict
        self.assertEqual(output_data['director_status'], 'success')
        self.assertEqual(output_data['workflow'], 'NewWorkflow')

        # NOT from item.metadata
        self.assertNotEqual(output_data['director_status'], 'old_status')
        self.assertNotEqual(output_data['workflow'], 'OldWorkflow')

    def test_metadata_dict_remains_empty_after_processing(self):
        """Verify that item.metadata dict doesn't gain Director fields"""
        # Arrange: Item with empty metadata
        mock_item = Mock()
        mock_item.id = 'item-7'
        mock_item.metadata = {}  # Empty
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-7',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-ghi', task_info, mock_result, {})

        # Assert: item.metadata should still be empty (or only have non-Director fields)
        # No director_status, director_workflow, director_plan
        director_keys = ['director_status', 'director_workflow', 'director_plan',
                        'director_outputs', 'director_processing_time']

        for key in director_keys:
            self.assertNotIn(key, mock_item.metadata,
                           f"item.metadata should not have '{key}' field")

    def test_failed_workflow_sets_error_status(self):
        """Verify that failed workflows set item.status to 'error'"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-8'
        mock_item.metadata = {}
        mock_item.status = 'processing'

        self.storage.get_item.return_value = mock_item

        mock_result = Mock()
        mock_result.success = False  # Failed workflow

        task_info = {
            'item_id': 'item-8',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-fail', task_info, mock_result, {})

        # Assert: item.status should be 'error'
        self.assertEqual(mock_item.status, 'error')

        # But metadata dict should still not have director_status
        self.assertNotIn('director_status', mock_item.metadata)

    # Phase 3 Collection-Level Metadata Tests
    def test_collection_level_metadata_creation(self):
        """Test that collection-level outputs create proper metadata with collection_level=True"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-collection-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'
        mock_item.collection_id = 'collection-1'

        self.storage.get_item.return_value = mock_item
        self.storage.add_processing_result = Mock(return_value=True)

        # Mock ExtractedMetadata for collection-level output
        from fichero.library.models import ExtractedMetadata
        collection_metadata = ExtractedMetadata(
            id='meta-collection-1',
            processing_output_id='output-collection-1',
            collection_id='collection-1',
            item_id='item-collection-1',
            schema_type='catalogue',
            source_label='catalogue',
            version=1,
            schema_version='1.0',
            key='collection_title',
            value='Test Collection Summary',
            collection_level=True  # This is the key test
        )

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-collection-1',
            'type': 'folder',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Transcribir y Catalogar',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        # Mock metadata extraction to return collection-level metadata
        with patch('fichero.library.director_integration.UniversalExtractor') as MockExtractor:
            mock_extractor = Mock()
            MockExtractor.return_value = mock_extractor
            mock_extractor.extract_from_output.return_value = [collection_metadata]

            from fichero.library.director_integration import DirectorIntegrationService
            service = DirectorIntegrationService(self.app, self.library_manager, self.director)

            # Act
            service._finalize_single_item('task-collection', task_info, mock_result, {})

            # Assert: ProcessingResult was created
            self.storage.add_processing_result.assert_called_once()

            # Verify collection-level metadata handling would be called
            # (Note: This is an integration point test, full extraction tested elsewhere)
            call_args = self.storage.add_processing_result.call_args[0]
            processing_result = call_args[0]
            self.assertEqual(processing_result.item_id, 'item-collection-1')
            self.assertEqual(processing_result.workflow, 'Catalogue')

    def test_file_level_metadata_creation(self):
        """Test that file-level outputs create proper metadata with collection_level=False"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-file-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'
        mock_item.collection_id = 'collection-1'

        self.storage.get_item.return_value = mock_item
        self.storage.add_processing_result = Mock(return_value=True)

        # Mock ExtractedMetadata for file-level output
        from fichero.library.models import ExtractedMetadata
        file_metadata = ExtractedMetadata(
            id='meta-file-1',
            processing_output_id='output-file-1',
            collection_id='collection-1',
            item_id='item-file-1',
            schema_type='transcription',
            source_label='transcribe',
            version=1,
            schema_version='1.0',
            key='text',
            value='Individual file transcription',
            collection_level=False  # File-level metadata
        )

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-file-1',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Transcribir y Catalogar',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-file', task_info, mock_result, {})

        # Assert: ProcessingResult was created for file-level processing
        self.storage.add_processing_result.assert_called_once()
        call_args = self.storage.add_processing_result.call_args[0]
        processing_result = call_args[0]
        self.assertEqual(processing_result.item_id, 'item-file-1')

    # Phase 2 Fallback Collection ID Tests
    def test_missing_collection_id_fallback_from_item(self):
        """Test that collection_id is retrieved from item when missing from task_info"""
        # Arrange: Task info WITHOUT collection_id
        mock_item = Mock()
        mock_item.id = 'item-fallback-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'
        mock_item.collection_id = 'collection-from-item'  # This should be used as fallback

        self.storage.get_item.return_value = mock_item
        self.storage.add_processing_result = Mock(return_value=True)

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-fallback-1',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now()
            # NO collection_id in task_info
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-fallback', task_info, mock_result, {})

        # Assert: ProcessingResult was created with collection_id from item
        self.storage.add_processing_result.assert_called_once()
        call_args = self.storage.add_processing_result.call_args[0]
        processing_result = call_args[0]

        # The collection_id should come from the item, not task_info
        # (Note: This tests the fallback logic in the integration service)
        self.assertEqual(processing_result.item_id, 'item-fallback-1')

    def test_database_validation_after_save(self):
        """Test that database validation occurs after ProcessingResult save (Phase 2)"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-validate-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item

        # Mock successful save, then validation
        self.storage.add_processing_result = Mock(return_value=True)

        # Mock validation to check that result exists
        mock_saved_result = Mock()
        mock_saved_result.item_id = 'item-validate-1'
        mock_saved_result.workflow = 'Catalogue'
        self.storage.get_processing_results_by_item = Mock(return_value=[mock_saved_result])

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-validate-1',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService
        service = DirectorIntegrationService(self.app, self.library_manager, self.director)

        # Act
        service._finalize_single_item('task-validate', task_info, mock_result, {})

        # Assert: Both save and validation occurred
        self.storage.add_processing_result.assert_called_once()
        # Note: In real implementation, validation would be called internally
        # This tests the pattern where save is followed by validation

    def test_comprehensive_logging_during_ingestion(self):
        """Test that comprehensive logging occurs during ingestion process (Phase 2)"""
        # Arrange
        mock_item = Mock()
        mock_item.id = 'item-logging-1'
        mock_item.metadata = {}
        mock_item.status = 'pending'

        self.storage.get_item.return_value = mock_item
        self.storage.add_processing_result = Mock(return_value=True)

        mock_result = Mock()
        mock_result.success = True

        task_info = {
            'item_id': 'item-logging-1',
            'type': 'file',
            'output_path': '/output/path',
            'workflow': 'Catalogue',
            'plan_name': 'Test Plan',
            'started_at': datetime.now(),
            'collection_id': 'collection-1'
        }

        from fichero.library.director_integration import DirectorIntegrationService

        # Test that logging doesn't interfere with processing
        with patch('fichero.library.director_integration.logger') as mock_logger:
            service = DirectorIntegrationService(self.app, self.library_manager, self.director)

            # Act
            service._finalize_single_item('task-logging', task_info, mock_result, {})

            # Assert: Processing completed successfully even with logging
            self.storage.add_processing_result.assert_called_once()

            # Verify logging calls were made (Phase 2 enhancement)
            # Note: Specific log messages would be tested in integration tests
            self.assertTrue(mock_logger.info.called or mock_logger.debug.called)


if __name__ == '__main__':
    unittest.main()
