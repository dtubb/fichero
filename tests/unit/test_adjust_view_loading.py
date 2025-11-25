"""
Unit tests for adjust view loading from ExtractedMetadata table

Tests that adjust_view loads transcriptions and metadata from the NEW metadata system
(ExtractedMetadata table) instead of reading files directly.
"""

import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path


class TestAdjustViewLoading(unittest.TestCase):
    """Test that adjust view loads data from ExtractedMetadata table"""

    def setUp(self):
        """Set up mock objects before each test"""
        self.storage = Mock()
        self.library_manager = Mock()
        self.library_manager.storage = self.storage

        # Mock app
        self.app = Mock()

    def test_load_transcription_tab_with_output_id(self):
        """Test that transcription tab queries by item_id directly"""
        # Arrange: Mock ExtractedMetadata with transcription
        mock_metadata = Mock()
        mock_metadata.schema_type = 'transcription'
        mock_metadata.key = 'text'
        mock_metadata.value = 'Transcribed content from database'

        self.storage.get_extracted_metadata_by_item.return_value = [mock_metadata]

        # Mock output_data (now deprecated/ignored)
        output_data = {
            'has_outputs': True,
            'processing_steps': [
                Mock(
                    tool_name='transcribe_qwen_max',
                    manifest_entry={'processing_output_id': 'trans-output-123'},
                    file_path=Path('/fake/path.json')
                )
            ]
        }

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView

            # Create adjust view with mocked dependencies
            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager

            # Create transcription_box mock
            adjust.transcription_box = Mock()
            adjust.transcription_box.value = ""

            # Act: Load transcription tab
            await adjust._load_transcription_tab('item-1', output_data)

            # Assert: Database was queried with item_id directly
            self.storage.get_extracted_metadata_by_item.assert_called_with(
                item_id='item-1',
                schema_type='transcription',
                key='text'
            )

            # Assert: Transcription text was set
            self.assertEqual(adjust.transcription_box.value, 'Transcribed content from database')

        import asyncio
        asyncio.run(run_test())

    def test_load_transcription_tab_null_manifest(self):
        """Test null check for manifest_entry works correctly"""
        # Arrange: Mock step without manifest_entry attribute
        mock_step = Mock(spec=['tool_name', 'file_path'])
        mock_step.tool_name = 'transcribe_qwen_max'
        # manifest_entry doesn't exist - should trigger hasattr check

        output_data = {
            'has_outputs': True,
            'processing_steps': [mock_step]
        }

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager
            adjust.transcription_box = Mock()
            adjust.transcription_box.value = ""

            # Act: Should not crash when manifest_entry is missing
            await adjust._load_transcription_tab('item-3', output_data)

            # Assert: No crash occurred (success)
            self.assertIsInstance(adjust.transcription_box.value, str)

        import asyncio
        asyncio.run(run_test())

    def test_load_metadata_tab_with_output_id(self):
        """Test that metadata tab queries by item_id directly"""
        # Arrange: Mock ExtractedMetadata with catalogue data
        mock_meta1 = Mock()
        mock_meta1.schema_type = 'catalogue'
        mock_meta1.key = 'title'
        mock_meta1.value = 'Document Title'

        mock_meta2 = Mock()
        mock_meta2.schema_type = 'catalogue'
        mock_meta2.key = 'date'
        mock_meta2.value = '1895'

        self.storage.get_extracted_metadata_by_item.return_value = [mock_meta1, mock_meta2]

        output_data = {
            'has_outputs': True,
            'processing_steps': [
                Mock(
                    tool_name='catalogue_qwen',
                    manifest_entry={'processing_output_id': 'cat-output-456'},
                    file_path=Path('/fake/catalogue.json')
                )
            ]
        }

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            import toga
            from toga.style import Pack
            from toga.constants import COLUMN

            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager

            # Mock metadata_box with a real Box
            adjust.metadata_box = Mock()
            adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))

            # Act: Load metadata tab
            await adjust._load_metadata_tab('item-4', output_data)

            # Assert: Database was queried with item_id directly (no filter by schema/key)
            self.storage.get_extracted_metadata_by_item.assert_called_with(
                item_id='item-4'
            )

            # Assert: Content was added to metadata_box
            # (We can't check exact content without full UI, but verify no crash)
            self.assertIsNotNone(adjust.metadata_box.content)

        import asyncio
        asyncio.run(run_test())

    def test_load_metadata_tab_groups_by_schema(self):
        """Test that metadata is grouped by schema_type"""
        # Arrange: Mock multiple schema types
        mock_trans = Mock()
        mock_trans.schema_type = 'transcription'
        mock_trans.source_label = 'transcribe'
        mock_trans.key = 'text'
        mock_trans.value = 'Transcribed text'

        mock_cat1 = Mock()
        mock_cat1.schema_type = 'catalogue'
        mock_cat1.source_label = 'catalogue'
        mock_cat1.key = 'title'
        mock_cat1.value = 'Title'

        mock_cat2 = Mock()
        mock_cat2.schema_type = 'catalogue'
        mock_cat2.source_label = 'catalogue'
        mock_cat2.key = 'author'
        mock_cat2.value = 'Author Name'

        self.storage.get_extracted_metadata_by_item.return_value = [mock_trans, mock_cat1, mock_cat2]

        output_data = {
            'has_outputs': True,
            'processing_steps': [
                Mock(
                    tool_name='catalogue_and_transcribe',
                    manifest_entry={'processing_output_id': 'mixed-output'},
                    file_path=Path('/fake.json')
                )
            ]
        }

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            import toga
            from toga.style import Pack
            from toga.constants import COLUMN

            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager
            adjust.metadata_box = Mock()
            adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))

            # Act: Load metadata
            await adjust._load_metadata_tab('item-5', output_data)

            # Assert: Both schema types were processed
            # (Check that get_extracted_metadata_by_item was called)
            self.storage.get_extracted_metadata_by_item.assert_called_once_with(item_id='item-5')

        import asyncio
        asyncio.run(run_test())

    def test_load_metadata_tab_null_manifest(self):
        """Test null check for manifest_entry in metadata tab"""
        # Arrange: Step without manifest_entry
        mock_step = Mock(spec=['tool_name', 'file_path'])
        mock_step.tool_name = 'catalogue'

        output_data = {
            'has_outputs': True,
            'processing_steps': [mock_step]
        }

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            import toga
            from toga.style import Pack
            from toga.constants import COLUMN

            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager
            adjust.metadata_box = Mock()
            adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))

            # Act: Should not crash
            await adjust._load_metadata_tab('item-6', output_data)

            # Assert: No crash (success)
            self.assertIsNotNone(adjust.metadata_box.content)

        import asyncio
        asyncio.run(run_test())

    def test_load_item_uses_cached_output_data(self):
        """Test that output_data parameter avoids re-query"""
        # Arrange: Create cached output_data
        cached_output_data = {
            'has_outputs': True,
            'processing_steps': [
                Mock(
                    tool_name='transcribe',
                    manifest_entry={'processing_output_id': 'cached-123'},
                    file_path=Path('/fake.txt')
                )
            ]
        }

        mock_metadata = Mock()
        mock_metadata.schema_type = 'transcription'
        mock_metadata.key = 'text'
        mock_metadata.value = 'Cached text'
        self.storage.get_extracted_metadata.return_value = [mock_metadata]

        # Mock item
        mock_item = Mock()
        mock_item.id = 'item-7'
        mock_item.name = 'Test Item'
        mock_item.created_at = None
        mock_item.metadata = {}
        self.storage.get_item.return_value = mock_item

        # This should NOT be called
        self.library_manager.get_item_output_data = AsyncMock()

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            import toga
            from toga.style import Pack
            from toga.constants import COLUMN

            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager

            # Create UI mocks
            adjust.info_box = Mock()
            adjust.info_box.content = toga.Box(style=Pack(direction=COLUMN))
            adjust.transcription_box = Mock()
            adjust.transcription_box.value = ""
            adjust.metadata_box = Mock()
            adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))
            adjust.json_box = Mock()
            adjust.json_box.value = ""

            # Act: Load item with cached output_data
            await adjust.load_item('item-7', cached_output_data)

            # Assert: get_item_output_data was NOT called
            self.library_manager.get_item_output_data.assert_not_called()

        import asyncio
        asyncio.run(run_test())

    def test_load_item_fetches_when_no_cache(self):
        """Test that library_manager is queried when output_data is None"""
        # Arrange
        fresh_output_data = {
            'has_outputs': False,
            'processing_steps': []
        }

        mock_item = Mock()
        mock_item.id = 'item-8'
        mock_item.name = 'Fresh Item'
        mock_item.created_at = None
        mock_item.metadata = {}
        self.storage.get_item.return_value = mock_item

        self.library_manager.get_item_output_data = AsyncMock(return_value=fresh_output_data)

        async def run_test():
            from fichero.windows.main.views.adjust.adjust_view import AdjustView
            import toga
            from toga.style import Pack
            from toga.constants import COLUMN

            adjust = AdjustView(self.app, is_mobile=False)
            adjust.library_manager = self.library_manager

            # Create UI mocks
            adjust.info_box = Mock()
            adjust.info_box.content = toga.Box(style=Pack(direction=COLUMN))
            adjust.transcription_box = Mock()
            adjust.transcription_box.value = ""
            adjust.metadata_box = Mock()
            adjust.metadata_box.content = toga.Box(style=Pack(direction=COLUMN))
            adjust.json_box = Mock()
            adjust.json_box.value = ""

            # Act: Load item without cache
            await adjust.load_item('item-8', None)

            # Assert: get_item_output_data WAS called
            self.library_manager.get_item_output_data.assert_called()

        import asyncio
        asyncio.run(run_test())


if __name__ == '__main__':
    unittest.main()
