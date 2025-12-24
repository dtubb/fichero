"""
Unit tests for sidebar hierarchy node_type and has_children flags

Tests that all sidebar items (sections, collections, folders) have the required
metadata flags for NSOutlineView hierarchy support.
"""

import pytest
from fichero.windows.main.views.library.sidebar_data_model import (
    SidebarDataModel,
    SidebarSection,
    SidebarCollection,
    SidebarFolder
)


class TestSidebarHierarchyFlags:
    """Test that sidebar items have proper NSOutlineView hierarchy flags"""

    def test_section_has_hierarchy_flags(self):
        """Section items should have _node_type and _has_children flags"""
        section = SidebarSection(
            id="test_section",
            title="Test Section"
        )

        item = section.to_widget_item()

        # Verify required flags exist
        assert '_node_type' in item, "Section missing _node_type flag"
        assert '_has_children' in item, "Section missing _has_children flag"

        # Verify correct values
        assert item['_node_type'] == 'section', "Section should have node_type='section'"
        assert item['_has_children'] is True, "Sections should always have children (their collections)"

    def test_collection_has_hierarchy_flags(self):
        """Collection items should have _node_type and _has_children flags"""
        collection = SidebarCollection(
            id="test_col",
            name="Test Collection",
            type="local",
            section_id="local"
        )

        item = collection.to_widget_item()

        # Verify required flags exist
        assert '_node_type' in item, "Collection missing _node_type flag"
        assert '_has_children' in item, "Collection missing _has_children flag"

        # Verify correct values
        assert item['_node_type'] == 'collection', "Collection should have node_type='collection'"
        assert item['_has_children'] is False, "Collection without folders should have _has_children=False"

    def test_folder_has_hierarchy_flags(self):
        """Folder items should have _node_type and _has_children flags"""
        folder = SidebarFolder(
            id="test_folder",
            name="Test Folder",
            collection_id="test_col",
            parent_collection_name="Test Collection"
        )

        item = folder.to_widget_item()

        # Verify required flags exist
        assert '_node_type' in item, "Folder missing _node_type flag"
        assert '_has_children' in item, "Folder missing _has_children flag"

        # Verify correct values
        assert item['_node_type'] == 'folder', "Folder should have node_type='folder'"
        assert item['_has_children'] is False, "Folders should have _has_children=False (subfolders not yet supported)"

    def test_collection_with_folders_has_children_true(self):
        """Collection with folders should have _has_children=True after to_widget_data()"""
        model = SidebarDataModel()

        # Create a collection
        collection = SidebarCollection(
            id="col_with_folders",
            name="Collection with Folders",
            type="local",
            section_id="local"
        )
        model.add_collection(collection)

        # Add folders to the collection
        folder1 = SidebarFolder(
            id="folder1",
            name="Folder 1",
            collection_id="col_with_folders",
            parent_collection_name="Collection with Folders"
        )
        folder2 = SidebarFolder(
            id="folder2",
            name="Folder 2",
            collection_id="col_with_folders",
            parent_collection_name="Collection with Folders"
        )
        model.add_folder("col_with_folders", folder1)
        model.add_folder("col_with_folders", folder2)

        # Convert to widget data
        widget_data = model.to_widget_data()

        # Find the collection item in widget_data
        collection_item = None
        for item in widget_data:
            if item.get('_item_id') == "col_with_folders":
                collection_item = item
                break

        assert collection_item is not None, "Collection not found in widget_data"

        # Verify _has_children was set to True
        assert collection_item['_has_children'] is True, "Collection with folders should have _has_children=True"

        # Verify _children array exists
        assert '_children' in collection_item, "Collection with folders should have _children array"
        assert len(collection_item['_children']) == 2, "Should have 2 child folders"

    def test_collection_without_folders_has_children_false(self):
        """Collection without folders should have _has_children=False"""
        model = SidebarDataModel()

        # Create a collection without folders
        collection = SidebarCollection(
            id="col_no_folders",
            name="Collection without Folders",
            type="local",
            section_id="local"
        )
        model.add_collection(collection)

        # Convert to widget data (no folders added)
        widget_data = model.to_widget_data()

        # Find the collection item in widget_data
        collection_item = None
        for item in widget_data:
            if item.get('_item_id') == "col_no_folders":
                collection_item = item
                break

        assert collection_item is not None, "Collection not found in widget_data"

        # Verify _has_children is False
        assert collection_item['_has_children'] is False, "Collection without folders should have _has_children=False"

        # Verify no _children array
        assert '_children' not in collection_item or collection_item['_children'] is None or len(collection_item['_children']) == 0, \
            "Collection without folders should not have _children array"

    def test_folders_in_children_array_have_flags(self):
        """Folders in _children array should have proper flags"""
        model = SidebarDataModel()

        # Create collection with folder
        collection = SidebarCollection(
            id="test_col",
            name="Test Collection",
            type="local",
            section_id="local"
        )
        model.add_collection(collection)

        folder = SidebarFolder(
            id="test_folder",
            name="Test Folder",
            collection_id="test_col",
            parent_collection_name="Test Collection"
        )
        model.add_folder("test_col", folder)

        # Convert to widget data
        widget_data = model.to_widget_data()

        # Find collection item
        collection_item = next((item for item in widget_data if item.get('_item_id') == "test_col"), None)
        assert collection_item is not None

        # Verify children array
        assert '_children' in collection_item
        assert len(collection_item['_children']) == 1

        # Verify child folder has flags
        folder_item = collection_item['_children'][0]
        assert '_node_type' in folder_item
        assert '_has_children' in folder_item
        assert folder_item['_node_type'] == 'folder'
        assert folder_item['_has_children'] is False

    def test_all_sections_have_flags(self):
        """All default sections should have proper flags"""
        model = SidebarDataModel()

        # Check all default sections
        for section in model.sections:
            item = section.to_widget_item()

            assert '_node_type' in item, f"Section {section.id} missing _node_type"
            assert '_has_children' in item, f"Section {section.id} missing _has_children"
            assert item['_node_type'] == 'section', f"Section {section.id} has wrong node_type"
            assert item['_has_children'] is True, f"Section {section.id} should have _has_children=True"

    def test_inbox_collection_has_flags(self):
        """Inbox collection should have proper hierarchy flags"""
        collection = SidebarCollection(
            id="inbox",
            name="Inbox",
            type="local",
            section_id="favorites",
            metadata={"is_inbox": True, "system_collection": True},
            font_weight="semibold"
        )

        item = collection.to_widget_item()

        # Verify flags exist
        assert '_node_type' in item
        assert '_has_children' in item

        # Verify values
        assert item['_node_type'] == 'collection'
        assert item['_has_children'] is False  # No folders by default

        # Verify inbox-specific styling is preserved
        assert item['font_weight'] == 'semibold'

    def test_external_collection_has_flags(self):
        """External collection should have proper hierarchy flags"""
        collection = SidebarCollection(
            id="external_col",
            name="External Collection",
            type="external",
            section_id="external",
            font_style="italic"
        )

        item = collection.to_widget_item()

        # Verify flags exist
        assert '_node_type' in item
        assert '_has_children' in item

        # Verify values
        assert item['_node_type'] == 'collection'
        assert item['_has_children'] is False

        # Verify external-specific styling is preserved
        assert item['font_style'] == 'italic'
