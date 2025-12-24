"""
Unit tests for Sidebar Data Model

Tests hierarchical organization of collections in the sidebar.
"""

import unittest
from fichero.windows.main.views.library.sidebar_data_model import (
    SidebarSection,
    SidebarCollection,
    SidebarDataModel
)


class TestSidebarSection(unittest.TestCase):
    """Test SidebarSection dataclass"""

    def test_section_creation(self):
        """Test creating a sidebar section"""
        section = SidebarSection(
            id="test",
            title="Test Section",
            icon="NSFolder",
            is_header=True,
            is_expanded=True,
            sort_order=1
        )

        self.assertEqual(section.id, "test")
        self.assertEqual(section.title, "Test Section")
        self.assertEqual(section.icon, "NSFolder")
        self.assertTrue(section.is_header)
        self.assertTrue(section.is_expanded)
        self.assertEqual(section.sort_order, 1)

    def test_section_to_widget_item(self):
        """Test converting section to widget item format"""
        section = SidebarSection(
            id="local",
            title="Local Collections",
            icon="NSFolder"
        )

        widget_item = section.to_widget_item()

        self.assertEqual(widget_item['text'], "Local Collections")
        self.assertEqual(widget_item['icon'], "NSFolder")
        self.assertTrue(widget_item['_is_section_header'])
        self.assertEqual(widget_item['_section_id'], "local")
        self.assertIsNone(widget_item['_collection_data'])


class TestSidebarCollection(unittest.TestCase):
    """Test SidebarCollection dataclass"""

    def test_collection_creation(self):
        """Test creating a sidebar collection"""
        collection = SidebarCollection(
            id="col-123",
            name="Test Collection",
            type="local",
            section_id="local",
            item_count=5,
            icon="NSFolder",
            icon_badge="📁",
            sort_order=1
        )

        self.assertEqual(collection.id, "col-123")
        self.assertEqual(collection.name, "Test Collection")
        self.assertEqual(collection.type, "local")
        self.assertEqual(collection.section_id, "local")
        self.assertEqual(collection.item_count, 5)
        self.assertEqual(collection.icon_badge, "📁")

    def test_collection_to_widget_item(self):
        """Test converting collection to widget item format"""
        collection = SidebarCollection(
            id="col-123",
            name="My Collection",
            type="local",
            section_id="local",
            item_count=10,
            icon_badge="📁"
        )

        widget_item = collection.to_widget_item()

        self.assertEqual(widget_item['text'], "My Collection")
        self.assertEqual(widget_item['_item_id'], "col-123")
        self.assertIn("10 items", widget_item['subtitle'])
        self.assertIn("📁", widget_item['subtitle'])

    def test_collection_widget_item_with_status(self):
        """Test widget item with status icon"""
        collection = SidebarCollection(
            id="col-123",
            name="Offline Collection",
            type="external",
            section_id="external",
            item_count=3,
            icon_badge="🔗",
            status_icon="⚠️"
        )

        widget_item = collection.to_widget_item()

        subtitle = widget_item['subtitle']
        self.assertIn("🔗", subtitle)
        self.assertIn("3 items", subtitle)
        self.assertIn("⚠️", subtitle)


class TestSidebarDataModel(unittest.TestCase):
    """Test SidebarDataModel functionality"""

    def test_initialization(self):
        """Test model initializes with default sections"""
        model = SidebarDataModel()

        self.assertEqual(len(model.sections), 3)  # inbox, local, external
        self.assertIn("inbox", model.collections)
        self.assertIn("local", model.collections)
        self.assertIn("external", model.collections)

    def test_add_collection(self):
        """Test adding a collection to a section"""
        model = SidebarDataModel()

        collection = SidebarCollection(
            id="col-1",
            name="Test Collection",
            type="local",
            section_id="local",
            item_count=5
        )

        model.add_collection(collection)

        self.assertEqual(len(model.collections["local"]), 1)
        self.assertEqual(model.collections["local"][0].name, "Test Collection")

    def test_add_collection_to_invalid_section(self):
        """Test adding collection to non-existent section defaults to local"""
        model = SidebarDataModel()

        collection = SidebarCollection(
            id="col-1",
            name="Test Collection",
            type="local",
            section_id="invalid_section",
            item_count=5
        )

        model.add_collection(collection)

        # Should be added to "local" section
        self.assertEqual(len(model.collections["local"]), 1)
        self.assertEqual(collection.section_id, "local")

    def test_remove_collection(self):
        """Test removing a collection"""
        model = SidebarDataModel()

        collection = SidebarCollection(
            id="col-1",
            name="Test Collection",
            type="local",
            section_id="local",
            item_count=5
        )

        model.add_collection(collection)
        self.assertEqual(len(model.collections["local"]), 1)

        result = model.remove_collection("col-1")

        self.assertTrue(result)
        self.assertEqual(len(model.collections["local"]), 0)

    def test_remove_nonexistent_collection(self):
        """Test removing a collection that doesn't exist"""
        model = SidebarDataModel()

        result = model.remove_collection("nonexistent-id")

        self.assertFalse(result)

    def test_get_collection(self):
        """Test getting a collection by ID"""
        model = SidebarDataModel()

        collection = SidebarCollection(
            id="col-1",
            name="Test Collection",
            type="local",
            section_id="local",
            item_count=5
        )

        model.add_collection(collection)

        found = model.get_collection("col-1")

        self.assertIsNotNone(found)
        self.assertEqual(found.name, "Test Collection")

    def test_get_nonexistent_collection(self):
        """Test getting a collection that doesn't exist"""
        model = SidebarDataModel()

        found = model.get_collection("nonexistent-id")

        self.assertIsNone(found)

    def test_update_collection(self):
        """Test updating collection properties"""
        model = SidebarDataModel()

        collection = SidebarCollection(
            id="col-1",
            name="Original Name",
            type="local",
            section_id="local",
            item_count=5
        )

        model.add_collection(collection)

        model.update_collection("col-1", name="Updated Name", item_count=10)

        updated = model.get_collection("col-1")
        self.assertEqual(updated.name, "Updated Name")
        self.assertEqual(updated.item_count, 10)

    def test_reorder_collection_within_section(self):
        """Test reordering collections within a section"""
        model = SidebarDataModel()

        # Add three collections to local section
        for i in range(1, 4):
            collection = SidebarCollection(
                id=f"col-{i}",
                name=f"Collection {i}",
                type="local",
                section_id="local",
                item_count=i
            )
            model.add_collection(collection)

        # Move collection 3 to position 0
        result = model.reorder_collection("col-3", 0, within_section=True)

        self.assertTrue(result)

        # Verify order
        local_collections = model.collections["local"]
        self.assertEqual(local_collections[0].id, "col-3")
        self.assertEqual(local_collections[1].id, "col-1")
        self.assertEqual(local_collections[2].id, "col-2")

        # Verify sort_order updated
        self.assertEqual(local_collections[0].sort_order, 0)
        self.assertEqual(local_collections[1].sort_order, 1)
        self.assertEqual(local_collections[2].sort_order, 2)

    def test_to_widget_data(self):
        """Test converting model to widget data format"""
        model = SidebarDataModel()

        # Add collections to different sections
        model.add_collection(SidebarCollection(
            id="local-1",
            name="Local Collection",
            type="local",
            section_id="local",
            item_count=5,
            icon_badge="📁"
        ))

        model.add_collection(SidebarCollection(
            id="external-1",
            name="External Collection",
            type="external",
            section_id="external",
            item_count=3,
            icon_badge="🔗"
        ))

        widget_data = model.to_widget_data(include_section_headers=True)

        # Should have: local header, local collection, external header, external collection
        self.assertEqual(len(widget_data), 4)

        # Check structure
        self.assertTrue(widget_data[0]['_is_section_header'])  # Local header
        self.assertEqual(widget_data[0]['_section_id'], "local")

        self.assertEqual(widget_data[1]['_item_id'], "local-1")  # Local collection
        self.assertIn("5 items", widget_data[1]['subtitle'])

        self.assertTrue(widget_data[2]['_is_section_header'])  # External header
        self.assertEqual(widget_data[2]['_section_id'], "external")

        self.assertEqual(widget_data[3]['_item_id'], "external-1")  # External collection
        self.assertIn("3 items", widget_data[3]['subtitle'])

    def test_to_widget_data_without_headers(self):
        """Test widget data without section headers"""
        model = SidebarDataModel()

        model.add_collection(SidebarCollection(
            id="local-1",
            name="Collection 1",
            type="local",
            section_id="local",
            item_count=5
        ))

        widget_data = model.to_widget_data(include_section_headers=False)

        # Should have only the collection, no headers
        self.assertEqual(len(widget_data), 1)
        self.assertEqual(widget_data[0]['_item_id'], "local-1")

    def test_load_from_library_data(self):
        """Test loading collections from library manager data"""
        model = SidebarDataModel()

        library_data = [
            {
                'id': 'col-1',
                'name': 'Local Collection',
                'type': 'local',
                'item_count': 10,
                'metadata': {},
                'sort_order': 1
            },
            {
                'id': 'col-2',
                'name': 'External Collection',
                'type': 'external',
                'item_count': 5,
                'metadata': {},
                'sort_order': 2
            },
            {
                'id': 'col-3',
                'name': 'URL Collection',
                'type': 'url',
                'item_count': 3,
                'metadata': {},
                'sort_order': 3
            }
        ]

        model.load_from_library_data(library_data)

        # Check collections were added to correct sections
        self.assertEqual(len(model.collections["local"]), 1)
        self.assertEqual(len(model.collections["external"]), 2)  # Both external and URL go to external

        # Verify data
        local_col = model.collections["local"][0]
        self.assertEqual(local_col.name, "Local Collection")
        self.assertEqual(local_col.icon_badge, "📁")

        external_col = model.collections["external"][0]
        self.assertEqual(external_col.icon_badge, "🔗")

    def test_type_badges(self):
        """Test that correct badges are assigned based on type"""
        model = SidebarDataModel()

        test_cases = [
            ('local', '📁'),
            ('external', '🔗'),
            ('url', '🌐'),
            ('hybrid', '🔄'),
        ]

        for collection_type, expected_badge in test_cases:
            badge = model._get_type_badge(collection_type)
            self.assertEqual(badge, expected_badge, f"Badge for {collection_type} should be {expected_badge}")

    def test_status_icon_for_unavailable(self):
        """Test status icon for unavailable external collections"""
        model = SidebarDataModel()

        col_data = {
            'type': 'external',
            'is_available': False
        }

        status_icon = model._get_status_icon(col_data)

        self.assertEqual(status_icon, '⚠️')

    def test_status_icon_for_available(self):
        """Test no status icon for available collections"""
        model = SidebarDataModel()

        col_data = {
            'type': 'external',
            'is_available': True
        }

        status_icon = model._get_status_icon(col_data)

        self.assertIsNone(status_icon)

    def test_get_section(self):
        """Test getting a section by ID"""
        model = SidebarDataModel()

        section = model.get_section("local")

        self.assertIsNotNone(section)
        self.assertEqual(section.id, "local")
        self.assertEqual(section.title, "Library")  # Updated from "Local Collections"

    def test_get_nonexistent_section(self):
        """Test getting a section that doesn't exist"""
        model = SidebarDataModel()

        section = model.get_section("nonexistent")

        self.assertIsNone(section)


class TestInboxSection(unittest.TestCase):
    """Test Inbox section functionality"""

    def test_inbox_section_exists(self):
        """Test that inbox section is defined"""
        model = SidebarDataModel()

        inbox_section = model.get_section("inbox")
        self.assertIsNotNone(inbox_section)
        self.assertEqual(inbox_section.title, "Inbox")
        self.assertEqual(inbox_section.sort_order, 0)

    def test_inbox_section_has_correct_icon(self):
        """Test that inbox uses archivebox icon"""
        model = SidebarDataModel()

        inbox_section = model.get_section("inbox")
        self.assertEqual(inbox_section.icon, "archivebox@10x.png")

    def test_section_order_with_inbox(self):
        """Test that sections are in correct order with inbox first"""
        model = SidebarDataModel()

        section_ids = [s.id for s in model.sections]
        self.assertEqual(section_ids[0], "inbox")
        self.assertEqual(section_ids[1], "local")
        self.assertEqual(section_ids[2], "external")

    def test_updated_section_titles(self):
        """Test that section titles match requirements"""
        model = SidebarDataModel()

        titles = {s.id: s.title for s in model.sections}
        self.assertEqual(titles["inbox"], "Inbox")
        self.assertEqual(titles["local"], "Library")
        self.assertEqual(titles["external"], "External Folders")

    def test_inbox_collection_maps_to_inbox_section(self):
        """Test that collections with is_inbox metadata map to inbox section"""
        model = SidebarDataModel()

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
        self.assertEqual(model.collections['inbox'][0].section_id, 'inbox')

        # Verify regular collection is in local section
        self.assertEqual(len(model.collections['local']), 1)
        self.assertEqual(model.collections['local'][0].id, 'regular-456')
        self.assertEqual(model.collections['local'][0].section_id, 'local')

    def test_inbox_widget_data_includes_section_header(self):
        """Test that to_widget_data includes inbox section header"""
        model = SidebarDataModel()

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
        self.assertEqual(inbox_collection['text'], 'Inbox')

    def test_inbox_appears_before_other_sections(self):
        """Test that inbox appears first in widget data"""
        model = SidebarDataModel()

        collections_data = [
            {
                'id': 'inbox-123',
                'name': 'Inbox',
                'type': 'local',
                'item_count': 5,
                'sort_order': 0,
                'metadata': {'is_inbox': True}
            },
            {
                'id': 'local-456',
                'name': 'My Collection',
                'type': 'local',
                'item_count': 3,
                'sort_order': 1,
                'metadata': {}
            }
        ]

        model.load_from_library_data(collections_data)

        widget_data = model.to_widget_data(
            folder_icon_cache={},
            include_section_headers=True
        )

        # Find indices
        inbox_header_idx = next(i for i, item in enumerate(widget_data) if
                               item.get('_is_section_header') and
                               item.get('_section_id') == 'inbox')
        local_header_idx = next(i for i, item in enumerate(widget_data) if
                               item.get('_is_section_header') and
                               item.get('_section_id') == 'local')

        # Inbox should come before Library
        self.assertLess(inbox_header_idx, local_header_idx)


if __name__ == "__main__":
    unittest.main()
