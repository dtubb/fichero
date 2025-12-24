"""
Unit tests for Inbox Collection System

Tests the inbox collection creation, protection, and sidebar integration.
"""

import unittest
import tempfile
import shutil
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.windows.main.views.library.sidebar_data_model import SidebarDataModel


class AsyncTestCase(unittest.TestCase):
    """Base class for async test cases"""

    def run_async(self, coro):
        """Helper to run async functions in tests"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)


class TestInboxCreation(AsyncTestCase):
    """Test inbox collection creation and initialization"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        # Create storage
        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        # Create library manager with mock app
        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(self.app)
            # Disable automatic inbox creation for tests
            self.library_manager._inbox_setup_pending = False

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_get_or_create_inbox_creates_new(self):
        """Test that get_or_create_inbox creates inbox if it doesn't exist"""
        # Get or create inbox
        inbox_id = self.run_async(self.library_manager.get_or_create_inbox())

        self.assertIsNotNone(inbox_id)

        # Verify inbox was created
        inbox = self.run_async(self.library_manager.get_collection(inbox_id))
        self.assertIsNotNone(inbox)
        self.assertEqual(inbox.name, "Inbox")
        self.assertEqual(inbox.type, "local")
        self.assertTrue(inbox.metadata.get('is_inbox'))
        self.assertTrue(inbox.metadata.get('system_collection'))

    def test_get_or_create_inbox_returns_existing(self):
        """Test that get_or_create_inbox returns existing inbox"""
        # Create inbox first time
        inbox_id_1 = self.run_async(self.library_manager.get_or_create_inbox())

        # Call again - should return same inbox
        inbox_id_2 = self.run_async(self.library_manager.get_or_create_inbox())

        self.assertEqual(inbox_id_1, inbox_id_2)

        # Verify only one inbox exists
        collections = self.run_async(self.library_manager.get_all_collections())
        inbox_collections = [c for c in collections if c.metadata.get('is_inbox')]
        self.assertEqual(len(inbox_collections), 1)

    def test_inbox_created_on_get_all_collections(self):
        """Test that inbox is automatically created when getting all collections"""
        # Enable automatic inbox creation for this test
        self.library_manager._inbox_setup_pending = True

        # Get all collections - should create inbox automatically
        collections = self.run_async(self.library_manager.get_all_collections())

        # Find inbox
        inbox_collections = [c for c in collections if c.metadata.get('is_inbox')]
        self.assertEqual(len(inbox_collections), 1)
        self.assertEqual(inbox_collections[0].name, "Inbox")


class TestInboxProtection(AsyncTestCase):
    """Test inbox protection from deletion and renaming"""

    def setUp(self):
        """Set up test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.library_dir = self.test_dir / "library"
        self.library_dir.mkdir()

        self.db_path = self.library_dir / "test.db"
        self.storage = LibraryStorage(str(self.db_path))

        self.app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=self.db_path):
            self.library_manager = LibraryManager(self.app)
            # Disable automatic inbox creation for tests
            self.library_manager._inbox_setup_pending = False

        # Create inbox
        self.inbox_id = self.run_async(self.library_manager.get_or_create_inbox())

    def tearDown(self):
        """Clean up test environment"""
        shutil.rmtree(self.test_dir)

    def test_cannot_delete_inbox(self):
        """Test that inbox cannot be deleted"""
        # Attempt to delete inbox
        result = self.run_async(self.library_manager.delete_collection(self.inbox_id))

        # Should return False (deletion blocked)
        self.assertFalse(result)

        # Verify inbox still exists
        inbox = self.run_async(self.library_manager.get_collection(self.inbox_id))
        self.assertIsNotNone(inbox)

    def test_cannot_rename_inbox(self):
        """Test that inbox cannot be renamed"""
        # Attempt to rename inbox
        result = self.run_async(self.library_manager.rename_collection(
            self.inbox_id,
            "New Name"
        ))

        # Should return False (rename blocked)
        self.assertFalse(result)

        # Verify inbox still has original name
        inbox = self.run_async(self.library_manager.get_collection(self.inbox_id))
        self.assertEqual(inbox.name, "Inbox")

    def test_can_delete_regular_collection(self):
        """Test that regular collections can still be deleted"""
        # Create regular collection
        regular_id = self.run_async(self.library_manager.add_collection(
            name="Regular Collection",
            collection_type="local",
            source_path=None
        ))

        # Delete should succeed
        result = self.run_async(self.library_manager.delete_collection(regular_id))
        self.assertTrue(result)

        # Verify collection was deleted
        collection = self.run_async(self.library_manager.get_collection(regular_id))
        self.assertIsNone(collection)

    def test_can_rename_regular_collection(self):
        """Test that regular collections can still be renamed"""
        # Create regular collection
        regular_id = self.run_async(self.library_manager.add_collection(
            name="Regular Collection",
            collection_type="local",
            source_path=None
        ))

        # Rename should succeed
        result = self.run_async(self.library_manager.rename_collection(
            regular_id,
            "New Name"
        ))
        self.assertTrue(result)

        # Verify collection was renamed
        collection = self.run_async(self.library_manager.get_collection(regular_id))
        self.assertEqual(collection.name, "New Name")


class TestSidebarInboxSection(unittest.TestCase):
    """Test inbox section in sidebar data model"""

    def test_inbox_section_exists(self):
        """Test that inbox section is defined"""
        model = SidebarDataModel()

        # Find inbox section
        inbox_section = next((s for s in model.sections if s.id == "inbox"), None)
        self.assertIsNotNone(inbox_section)
        self.assertEqual(inbox_section.title, "Inbox")
        self.assertEqual(inbox_section.sort_order, 0)
        self.assertEqual(inbox_section.icon, "archivebox@10x.png")

    def test_section_order(self):
        """Test that sections are in correct order"""
        model = SidebarDataModel()

        section_ids = [s.id for s in model.sections]
        self.assertEqual(section_ids[0], "inbox")  # Inbox first
        self.assertEqual(section_ids[1], "local")  # Library second
        self.assertEqual(section_ids[2], "external")  # External third

    def test_section_titles(self):
        """Test that section titles are correct"""
        model = SidebarDataModel()

        titles = {s.id: s.title for s in model.sections}
        self.assertEqual(titles["inbox"], "Inbox")
        self.assertEqual(titles["local"], "Library")
        self.assertEqual(titles["external"], "External Folders")

    def test_inbox_collection_maps_to_inbox_section(self):
        """Test that collections with is_inbox metadata map to inbox section"""
        model = SidebarDataModel()

        # Simulate inbox collection data
        collections_data = [
            {
                'id': 'inbox-123',
                'name': 'Inbox',
                'type': 'local',
                'item_count': 5,
                'sort_order': 0,
                'metadata': {
                    'is_inbox': True,
                    'system_collection': True
                }
            },
            {
                'id': 'regular-456',
                'name': 'Regular Collection',
                'type': 'local',
                'item_count': 3,
                'sort_order': 1,
                'metadata': {}
            }
        ]

        model.load_from_library_data(collections_data)

        # Verify inbox collection is in inbox section
        self.assertEqual(len(model.collections['inbox']), 1)
        self.assertEqual(model.collections['inbox'][0].id, 'inbox-123')

        # Verify regular collection is in local section
        self.assertEqual(len(model.collections['local']), 1)
        self.assertEqual(model.collections['local'][0].id, 'regular-456')

    def test_widget_data_includes_inbox(self):
        """Test that to_widget_data includes inbox section"""
        model = SidebarDataModel()

        # Add inbox collection
        collections_data = [
            {
                'id': 'inbox-123',
                'name': 'Inbox',
                'type': 'local',
                'item_count': 5,
                'sort_order': 0,
                'metadata': {
                    'is_inbox': True,
                    'system_collection': True
                }
            }
        ]

        model.load_from_library_data(collections_data)

        # Get widget data with section headers
        widget_data = model.to_widget_data(
            folder_icon_cache={},
            include_section_headers=True
        )

        # Find inbox section header
        inbox_header = next((item for item in widget_data if
                           item.get('_is_section_header') and
                           item.get('_section_id') == 'inbox'), None)
        self.assertIsNotNone(inbox_header)
        self.assertEqual(inbox_header['text'], 'Inbox')

        # Find inbox collection
        inbox_collection = next((item for item in widget_data if
                               (item.get('_collection_data') or {}).get('id') == 'inbox-123'), None)
        self.assertIsNotNone(inbox_collection)


if __name__ == "__main__":
    unittest.main()
