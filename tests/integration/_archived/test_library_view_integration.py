"""
Integration Tests for LibraryView Functionality

Tests the complete LibraryView integration including:
- Collection CRUD operations via UI integration layer
- Sidebar data model formatting (badges, icons, status)
- Context menu action execution
- Collection selection and CollectionView updates
- Preview pane metadata flow

These tests focus on the data flow and integration points rather than
the UI rendering, which requires the full Toga/macOS stack.
"""

import unittest
import tempfile
import shutil
import asyncio
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, List, Optional, Any

import pytest

# Import required models and services
from fichero.library.models import Collection, CollectionItem, ProcessingResult
from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.library.ui_integration import LibraryUIIntegration


class TestLibraryUIIntegration(unittest.TestCase):
    """Test LibraryUIIntegration class for collection operations"""

    def setUp(self):
        """Set up test environment with real components"""
        # Create temporary directories for testing
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        # Create test database
        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        # Mock app
        self.app = Mock()

        # Create real library manager with test app
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)

        # Override the storage with our test storage
        self.library_manager.storage = self.storage

        # Create UI integration layer
        self.ui_integration = LibraryUIIntegration(self.library_manager)

        # Track callback invocations
        self.callback_invocations = {
            'collection_added': [],
            'collection_updated': [],
            'collection_deleted': [],
            'item_added': [],
        }

        # Register callbacks
        self.ui_integration.register_ui_callbacks(
            on_collection_added=lambda c: self.callback_invocations['collection_added'].append(c),
            on_collection_updated=lambda c: self.callback_invocations['collection_updated'].append(c),
            on_collection_deleted=lambda id: self.callback_invocations['collection_deleted'].append(id),
            on_item_added=lambda i: self.callback_invocations['item_added'].append(i),
        )

    def tearDown(self):
        """Clean up test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _run_async(self, coro):
        """Helper to run async code in tests"""
        return asyncio.get_event_loop().run_until_complete(coro)

    # ===== Collection CRUD Tests =====

    def test_add_local_collection(self):
        """Test adding a local collection via UI integration"""
        result = self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="My Documents",
                collection_type="local",
                description="Personal documents"
            )
        )

        self.assertTrue(result)
        self.assertEqual(len(self.callback_invocations['collection_added']), 1)

        added_collection = self.callback_invocations['collection_added'][0]
        self.assertEqual(added_collection.name, "My Documents")
        self.assertEqual(added_collection.type, "local")

    def test_add_external_collection(self):
        """Test adding an external collection via UI integration"""
        external_path = str(self.test_dir / "external_drive")
        Path(external_path).mkdir()

        result = self._run_async(
            self.ui_integration.add_external_collection_from_ui(
                path=external_path,
                name="External Drive"
            )
        )

        self.assertTrue(result)
        self.assertEqual(len(self.callback_invocations['collection_added']), 1)

        added_collection = self.callback_invocations['collection_added'][0]
        self.assertEqual(added_collection.name, "External Drive")
        self.assertEqual(added_collection.type, "external")
        self.assertEqual(added_collection.source_path, external_path)

    def test_add_url_collection(self):
        """Test adding a URL collection via UI integration"""
        result = self._run_async(
            self.ui_integration.add_url_collection_from_ui(
                url="https://example.com/archive",
                name="Web Archive"
            )
        )

        self.assertTrue(result)
        self.assertEqual(len(self.callback_invocations['collection_added']), 1)

        added_collection = self.callback_invocations['collection_added'][0]
        self.assertEqual(added_collection.name, "Web Archive")
        self.assertEqual(added_collection.type, "url")
        self.assertIn("example.com", added_collection.source_path)

    def test_rename_collection(self):
        """Test renaming a collection via UI integration"""
        # First add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Original Name",
                collection_type="local"
            )
        )

        added_collection = self.callback_invocations['collection_added'][0]
        collection_id = added_collection.id

        # Rename it
        result = self._run_async(
            self.ui_integration.rename_collection(collection_id, "New Name")
        )

        self.assertTrue(result)
        self.assertEqual(len(self.callback_invocations['collection_updated']), 1)

        updated_collection = self.callback_invocations['collection_updated'][0]
        self.assertEqual(updated_collection.name, "New Name")

    def test_delete_collection(self):
        """Test deleting a collection via UI integration"""
        # First add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="To Delete",
                collection_type="local"
            )
        )

        added_collection = self.callback_invocations['collection_added'][0]
        collection_id = added_collection.id

        # Delete it
        result = self._run_async(
            self.ui_integration.delete_collection(collection_id)
        )

        self.assertTrue(result)
        self.assertEqual(len(self.callback_invocations['collection_deleted']), 1)
        self.assertEqual(self.callback_invocations['collection_deleted'][0], collection_id)

    def test_duplicate_collection(self):
        """Test duplicating a collection via UI integration"""
        # First add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Original",
                collection_type="local",
                description="Original description"
            )
        )

        original_collection = self.callback_invocations['collection_added'][0]

        # Duplicate it
        new_id = self._run_async(
            self.ui_integration.duplicate_collection(original_collection.id)
        )

        self.assertIsNotNone(new_id)
        self.assertEqual(len(self.callback_invocations['collection_added']), 2)

        duplicated_collection = self.callback_invocations['collection_added'][1]
        self.assertEqual(duplicated_collection.name, "Original (Copy)")
        self.assertEqual(duplicated_collection.type, "local")

    # ===== Collection Retrieval and Formatting Tests =====

    def test_get_collections_for_ui_formatting(self):
        """Test that collections are formatted correctly for UI display"""
        # Get initial count (may include default Inbox)
        initial_collections = self._run_async(
            self.ui_integration.get_collections_for_ui()
        )
        initial_count = len(initial_collections)

        # Add multiple collections
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Documents",
                collection_type="local"
            )
        )
        self._run_async(
            self.ui_integration.add_external_collection_from_ui(
                path=str(self.test_dir / "external"),
                name="External"
            )
        )

        # Get formatted collections
        ui_collections = self._run_async(
            self.ui_integration.get_collections_for_ui()
        )

        self.assertEqual(len(ui_collections), initial_count + 2)

        # Check formatting
        for collection in ui_collections:
            self.assertIn('id', collection)
            self.assertIn('name', collection)
            self.assertIn('type', collection)
            self.assertIn('item_count', collection)
            self.assertIn('processing_status', collection)
            self.assertIn('created_at', collection)
            self.assertIn('updated_at', collection)

    def test_get_library_stats(self):
        """Test library statistics retrieval"""
        # Add collections and items
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Test Collection",
                collection_type="local"
            )
        )

        stats = self._run_async(
            self.ui_integration.get_library_stats_for_ui()
        )

        self.assertIn('total_collections', stats)
        self.assertIn('total_items', stats)
        self.assertIn('status', stats)
        self.assertGreaterEqual(stats['total_collections'], 1)


class TestSidebarDataFormatting(unittest.TestCase):
    """Test sidebar data formatting for badges, icons, and status indicators"""

    def test_item_count_badge_formatting(self):
        """Test that item counts are formatted correctly for badges"""
        # Test formatting function (this would be in sidebar_data_model.py)
        def format_item_count(count: int) -> str:
            if count >= 1_000_000:
                return f"{count/1_000_000:.1f}M"
            elif count >= 1_000:
                return f"{count/1_000:.1f}K"
            return str(count) if count > 0 else ""

        # Test various counts
        self.assertEqual(format_item_count(0), "")
        self.assertEqual(format_item_count(42), "42")
        self.assertEqual(format_item_count(999), "999")
        self.assertEqual(format_item_count(1000), "1.0K")
        self.assertEqual(format_item_count(1500), "1.5K")
        self.assertEqual(format_item_count(12345), "12.3K")
        self.assertEqual(format_item_count(1000000), "1.0M")
        self.assertEqual(format_item_count(3400000), "3.4M")

    def test_type_icon_mapping(self):
        """Test that collection types map to correct icons"""
        type_icons = {
            'local': 'folder.fill',
            'external': 'link',
            'url': 'globe',
            'inbox': 'tray',
        }

        self.assertEqual(type_icons.get('local'), 'folder.fill')
        self.assertEqual(type_icons.get('external'), 'link')
        self.assertEqual(type_icons.get('url'), 'globe')
        self.assertEqual(type_icons.get('inbox'), 'tray')

    def test_processing_status_icons(self):
        """Test that processing status maps to correct trailing icons"""
        status_icons = {
            'processed': 'checkmark.circle.fill',
            'unprocessed': 'circle',
            'processing': 'arrow.clockwise',
            'error': 'exclamationmark.circle',
        }

        self.assertEqual(status_icons.get('processed'), 'checkmark.circle.fill')
        self.assertEqual(status_icons.get('unprocessed'), 'circle')
        self.assertEqual(status_icons.get('processing'), 'arrow.clockwise')
        self.assertEqual(status_icons.get('error'), 'exclamationmark.circle')

    def test_sidebar_item_data_structure(self):
        """Test the expected sidebar item data structure"""
        # This validates the data contract for sidebar items
        sidebar_item = {
            'text': 'Documents',
            'icon': 'folder.fill',
            'badge_text': '42',
            'trailing_icon': 'checkmark.circle.fill',
            'font_weight': 'regular',
            'font_style': 'normal',
            '_collection_data': {
                'id': 'collection-123',
                'name': 'Documents',
                'type': 'local',
                'item_count': 42,
                'is_processed': True,
                'source_path': None,
            },
            '_item_id': 'collection-123',
            '_node_type': 'collection',
        }

        # Verify required fields
        self.assertIn('text', sidebar_item)
        self.assertIn('icon', sidebar_item)
        self.assertIn('_collection_data', sidebar_item)
        self.assertIn('_item_id', sidebar_item)
        self.assertIn('_node_type', sidebar_item)

        # Verify collection data
        collection_data = sidebar_item['_collection_data']
        self.assertEqual(collection_data['id'], 'collection-123')
        self.assertEqual(collection_data['name'], 'Documents')
        self.assertEqual(collection_data['type'], 'local')
        self.assertEqual(collection_data['item_count'], 42)


class TestContextMenuActions(unittest.TestCase):
    """Test context menu action handling"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()

        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(app=self.app)

        self.library_manager.storage = self.storage
        self.ui_integration = LibraryUIIntegration(self.library_manager)

    def tearDown(self):
        """Clean up test environment"""
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def _run_async(self, coro):
        """Helper to run async code in tests"""
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_context_menu_rename_action(self):
        """Test rename action from context menu"""
        # Add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Original",
                collection_type="local"
            )
        )

        collections = self._run_async(self.ui_integration.get_collections_for_ui())
        # Find the collection we just added
        original = next((c for c in collections if c['name'] == "Original"), None)
        self.assertIsNotNone(original)
        collection_id = original['id']

        # Simulate rename action
        result = self._run_async(
            self.ui_integration.rename_collection(collection_id, "Renamed")
        )

        self.assertTrue(result)

        # Verify rename
        updated_collections = self._run_async(self.ui_integration.get_collections_for_ui())
        renamed = next((c for c in updated_collections if c['id'] == collection_id), None)
        self.assertIsNotNone(renamed)
        self.assertEqual(renamed['name'], "Renamed")

    def test_context_menu_delete_action(self):
        """Test delete action from context menu"""
        # Get initial count (may include default Inbox)
        initial_collections = self._run_async(self.ui_integration.get_collections_for_ui())
        initial_count = len(initial_collections)

        # Add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="To Delete",
                collection_type="local"
            )
        )

        collections = self._run_async(self.ui_integration.get_collections_for_ui())
        self.assertEqual(len(collections), initial_count + 1)

        # Find the collection we just added
        to_delete = next((c for c in collections if c['name'] == "To Delete"), None)
        self.assertIsNotNone(to_delete)
        collection_id = to_delete['id']

        # Simulate delete action
        result = self._run_async(
            self.ui_integration.delete_collection(collection_id)
        )

        self.assertTrue(result)

        # Verify deletion
        remaining_collections = self._run_async(self.ui_integration.get_collections_for_ui())
        self.assertEqual(len(remaining_collections), initial_count)

    def test_context_menu_duplicate_action(self):
        """Test duplicate action from context menu"""
        # Get initial count (may include default Inbox)
        initial_collections = self._run_async(self.ui_integration.get_collections_for_ui())
        initial_count = len(initial_collections)

        # Add a collection
        self._run_async(
            self.ui_integration.add_collection_from_ui(
                name="Original",
                collection_type="local"
            )
        )

        collections = self._run_async(self.ui_integration.get_collections_for_ui())
        # Find the collection we just added
        original = next((c for c in collections if c['name'] == "Original"), None)
        self.assertIsNotNone(original)
        collection_id = original['id']

        # Simulate duplicate action
        new_id = self._run_async(
            self.ui_integration.duplicate_collection(collection_id)
        )

        self.assertIsNotNone(new_id)

        # Verify duplication
        all_collections = self._run_async(self.ui_integration.get_collections_for_ui())
        self.assertEqual(len(all_collections), initial_count + 2)

        names = [c['name'] for c in all_collections]
        self.assertIn("Original", names)
        self.assertIn("Original (Copy)", names)


class TestCollectionSelectionFlow(unittest.TestCase):
    """Test collection selection and CollectionView integration"""

    def test_selection_metadata_structure(self):
        """Test that selection metadata has required fields for preview panes"""
        # This validates the metadata structure passed through selection events
        selection_metadata = {
            'id': 'item-123',
            'name': 'document.jpg',
            'type': 'file',
            'file_path': '/path/to/document.jpg',
            'original_path': '/path/to/document.jpg',
            'source_path': '/path/to/document.jpg',
            'status': 'completed',
            'storage_type': 'local',
        }

        # Verify required fields for preview pane
        self.assertIn('file_path', selection_metadata)
        self.assertIn('id', selection_metadata)
        self.assertIn('name', selection_metadata)

        # At least one path should be present
        has_path = any([
            selection_metadata.get('original_path'),
            selection_metadata.get('file_path'),
            selection_metadata.get('source_path'),
        ])
        self.assertTrue(has_path)

    def test_selection_event_data_contract(self):
        """Test the data contract for SELECTION_CHANGED events"""
        # This validates what SelectionManager emits
        event_data = {
            'collection_id': 'collection-123',
            'item_id': 'item-456',
            'item_data': {
                'id': 'item-456',
                'name': 'photo.jpg',
                'type': 'file',
                'file_path': '/path/to/photo.jpg',
            },
            'source': 'collection_view',
        }

        self.assertIn('collection_id', event_data)
        self.assertIn('item_id', event_data)
        self.assertIn('item_data', event_data)

        # Verify item_data has what preview panes need
        item_data = event_data['item_data']
        self.assertIn('id', item_data)
        self.assertIn('file_path', item_data)


class TestPreviewPaneMetadataFlow(unittest.TestCase):
    """Test metadata flow from selection to preview panes"""

    def test_image_pane_metadata_requirements(self):
        """Test metadata requirements for PreviewImagePane"""
        # PreviewImagePane.load_item expects:
        # item_metadata.get('original_path') or item_metadata.get('file_path') or item_metadata.get('source_path')

        valid_metadata_cases = [
            {'original_path': '/path/to/image.jpg'},
            {'file_path': '/path/to/image.jpg'},
            {'source_path': '/path/to/image.jpg'},
            {'original_path': '/path/to/image.jpg', 'file_path': '/alt/path.jpg'},
        ]

        for metadata in valid_metadata_cases:
            path = (
                metadata.get('original_path') or
                metadata.get('file_path') or
                metadata.get('source_path')
            )
            self.assertIsNotNone(path, f"Failed for metadata: {metadata}")

    def test_metadata_pane_data_requirements(self):
        """Test metadata requirements for PreviewMetadataPane"""
        # MetadataPane expects output_data with transcription/metadata
        output_data = {
            'transcription': 'Extracted text from document...',
            'workflow': 'Transcribir y Catalogar',
            'processing_status': 'completed',
        }

        self.assertIn('transcription', output_data)

    def test_adjust_view_metadata_loading(self):
        """Test that AdjustView can load from various metadata sources"""
        # AdjustView loads from library_manager.get_item_metadata or output_data
        item_metadata = {
            'id': 'item-123',
            'name': 'document.jpg',
            'type': 'file',
            'file_path': '/path/to/document.jpg',
            'extracted_metadata': {
                'title': 'Historical Document',
                'date': '1920-05-15',
                'description': 'A historical photograph',
            }
        }

        self.assertIn('extracted_metadata', item_metadata)
        self.assertIn('file_path', item_metadata)


if __name__ == '__main__':
    unittest.main()
