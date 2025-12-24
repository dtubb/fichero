"""
Unit tests for hierarchical sidebar implementation (Phase 6)

Tests verify that:
1. Folders are loaded correctly for collections
2. SidebarDataModel organizes data hierarchically
3. Widget data includes _children key for collections with folders
4. Folder count is calculated correctly
"""

import pytest
import pytest_asyncio
import asyncio
import logging
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.library.models import CollectionItem
from fichero.windows.main.views.library.sidebar_data_model import SidebarDataModel, SidebarCollection, SidebarFolder

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def library_with_folders():
    """Create a library with a collection and folders"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        mock_app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            manager = LibraryManager(app=mock_app)

        # Create a test collection
        collection_id = await manager.add_collection(
            name="Test Collection",
            collection_type="local",
            source_path=None
        )

        # Add folders directly via storage layer
        folder1_id = str(uuid.uuid4())
        folder1 = CollectionItem(
            id=folder1_id,
            collection_id=collection_id,
            type="folder",
            name="Folder 1",
            parent_id=None,  # Root level folder
            storage_type="local"
        )
        manager.storage.add_collection_item(folder1)

        folder2_id = str(uuid.uuid4())
        folder2 = CollectionItem(
            id=folder2_id,
            collection_id=collection_id,
            type="folder",
            name="Folder 2",
            parent_id=None,  # Root level folder
            storage_type="local"
        )
        manager.storage.add_collection_item(folder2)

        # Add some items to folder1
        item1 = CollectionItem(
            id=str(uuid.uuid4()),
            collection_id=collection_id,
            type="file",
            name="Item 1",
            parent_id=folder1_id,
            storage_type="local"
        )
        manager.storage.add_collection_item(item1)

        item2 = CollectionItem(
            id=str(uuid.uuid4()),
            collection_id=collection_id,
            type="file",
            name="Item 2",
            parent_id=folder1_id,
            storage_type="local"
        )
        manager.storage.add_collection_item(item2)

        yield manager, collection_id, folder1_id, folder2_id


@pytest.mark.asyncio
async def test_load_collection_folders(library_with_folders):
    """Test that load_collection_folders loads only root-level folders"""
    manager, collection_id, folder1_id, folder2_id = library_with_folders

    sidebar_model = SidebarDataModel()

    # Load folders for the collection
    folder_count = await sidebar_model.load_collection_folders(
        collection_id=collection_id,
        collection_name="Test Collection",
        library_manager=manager
    )

    # Should have loaded 2 root-level folders
    assert folder_count == 2, f"Expected 2 folders, got {folder_count}"

    # Check that folders were added to the model
    assert collection_id in sidebar_model.folders
    folders = sidebar_model.folders[collection_id]
    assert len(folders) == 2

    # Verify folder names
    folder_names = {f.name for f in folders}
    assert folder_names == {"Folder 1", "Folder 2"}

    logger.info("✅ Test passed: Root-level folders loaded correctly")


@pytest.mark.asyncio
async def test_folder_item_count(library_with_folders):
    """Test that folder item count is calculated correctly"""
    manager, collection_id, folder1_id, folder2_id = library_with_folders

    sidebar_model = SidebarDataModel()

    await sidebar_model.load_collection_folders(
        collection_id=collection_id,
        collection_name="Test Collection",
        library_manager=manager
    )

    # Find Folder 1 (which has 2 items)
    folders = sidebar_model.folders[collection_id]
    folder1 = next((f for f in folders if f.name == "Folder 1"), None)

    assert folder1 is not None
    assert folder1.item_count == 2, f"Expected 2 items in Folder 1, got {folder1.item_count}"

    # Find Folder 2 (which has 0 items)
    folder2 = next((f for f in folders if f.name == "Folder 2"), None)
    assert folder2 is not None
    assert folder2.item_count == 0, f"Expected 0 items in Folder 2, got {folder2.item_count}"

    logger.info("✅ Test passed: Folder item counts calculated correctly")


@pytest.mark.asyncio
async def test_widget_data_includes_children(library_with_folders):
    """Test that to_widget_data includes _children key for collections with folders"""
    manager, collection_id, folder1_id, folder2_id = library_with_folders

    sidebar_model = SidebarDataModel()

    # Get collection data from library (Collection objects don't have item_count)
    collections = await manager.get_all_collections()
    collections_data = [
        {
            'id': c.id,
            'name': c.name,
            'type': c.type,
            'metadata': c.metadata,
            'sort_order': c.sort_order or 0
        }
        for c in collections
    ]

    # Load collections into sidebar model
    sidebar_model.load_from_library_data(collections_data)

    # Load folders for the test collection
    await sidebar_model.load_collection_folders(
        collection_id=collection_id,
        collection_name="Test Collection",
        library_manager=manager
    )

    # Convert to widget data
    widget_data = sidebar_model.to_widget_data(include_section_headers=True)

    # Find the test collection in widget data
    # With include_section_headers=True, collections are nested inside section items as _children
    test_collection_item = None
    for section_item in widget_data:
        children = section_item.get('_children', [])
        for item in children:
            collection_data = item.get('_collection_data')
            if collection_data and collection_data.get('id') == collection_id:
                test_collection_item = item
                break
        if test_collection_item:
            break

    assert test_collection_item is not None, "Test collection not found in widget data"

    # Verify it has _children key
    assert '_children' in test_collection_item, "Collection should have _children key"

    children = test_collection_item['_children']
    assert len(children) == 2, f"Expected 2 children, got {len(children)}"

    # Verify children are folder items
    for child in children:
        assert '_folder_data' in child, "Child should have _folder_data key"
        folder_data = child['_folder_data']
        assert folder_data.get('is_folder') is True

    logger.info("✅ Test passed: Widget data includes _children for collections with folders")


@pytest.mark.asyncio
async def test_sidebar_sections_organization():
    """Test that sidebar model organizes collections into correct sections"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        mock_app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            manager = LibraryManager(app=mock_app)

        # Create inbox (should go to favorites)
        inbox_id = await manager.get_or_create_inbox()

        # Create local collection (should go to local)
        local_id = await manager.add_collection(
            name="Local Collection",
            collection_type="local",
            source_path=None
        )

        # Create external collection (should go to external)
        external_id = await manager.add_collection(
            name="External Collection",
            collection_type="external",
            source_path="/some/path"
        )

        # Get all collections (Collection objects don't have item_count)
        collections = await manager.get_all_collections()
        collections_data = [
            {
                'id': c.id,
                'name': c.name,
                'type': c.type,
                'metadata': c.metadata,
                'sort_order': c.sort_order or 0
            }
            for c in collections
        ]

        # Load into sidebar model
        sidebar_model = SidebarDataModel()
        sidebar_model.load_from_library_data(collections_data)

        # Verify section organization (favorites and collections sections)
        assert 'favorites' in sidebar_model.collections
        assert 'collections' in sidebar_model.collections

        # Inbox should be in favorites
        favorites = sidebar_model.collections['favorites']
        assert len(favorites) == 1
        assert favorites[0].metadata.get('is_inbox') is True

        # Local and external collections should be in 'collections' section
        collections_section = sidebar_model.collections['collections']
        assert any(c.id == local_id for c in collections_section)
        assert any(c.id == external_id for c in collections_section)

        logger.info("✅ Test passed: Collections organized into correct sections")


@pytest.mark.asyncio
async def test_empty_collection_no_children():
    """Test that collections without folders don't have _children key"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        mock_app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            manager = LibraryManager(app=mock_app)

        # Create empty collection
        collection_id = await manager.add_collection(
            name="Empty Collection",
            collection_type="local",
            source_path=None
        )

        sidebar_model = SidebarDataModel()

        # Get collection data (Collection objects don't have item_count)
        collections = await manager.get_all_collections()
        collections_data = [
            {
                'id': c.id,
                'name': c.name,
                'type': c.type,
                'metadata': c.metadata,
                'sort_order': c.sort_order or 0
            }
            for c in collections
        ]

        sidebar_model.load_from_library_data(collections_data)

        # Try to load folders (should be 0)
        folder_count = await sidebar_model.load_collection_folders(
            collection_id=collection_id,
            collection_name="Empty Collection",
            library_manager=manager
        )

        assert folder_count == 0

        # Convert to widget data
        widget_data = sidebar_model.to_widget_data(include_section_headers=True)

        # Find the empty collection
        # With include_section_headers=True, collections are nested inside section items as _children
        empty_collection_item = None
        for section_item in widget_data:
            children = section_item.get('_children', [])
            for item in children:
                collection_data = item.get('_collection_data')
                if collection_data and collection_data.get('id') == collection_id:
                    empty_collection_item = item
                    break
            if empty_collection_item:
                break

        assert empty_collection_item is not None

        # Should NOT have _children key (or it should be empty)
        children = empty_collection_item.get('_children', [])
        assert len(children) == 0, "Empty collection should have no children"

        logger.info("✅ Test passed: Empty collections have no _children")


@pytest.mark.asyncio
async def test_to_source_list_items_conversion():
    """Test that to_source_list_items converts model to SourceListItem format"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        mock_app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            manager = LibraryManager(app=mock_app)

        # Create inbox
        inbox_id = await manager.get_or_create_inbox()

        # Create local collection
        local_id = await manager.add_collection(
            name="Local Collection",
            collection_type="local",
            source_path=None
        )

        # Get collection data
        collections = await manager.get_all_collections()
        collections_data = [
            {
                'id': c.id,
                'name': c.name,
                'type': c.type,
                'metadata': c.metadata,
                'item_count': 0,
                'sort_order': c.sort_order or 0
            }
            for c in collections
        ]

        # Load into sidebar model
        sidebar_model = SidebarDataModel()
        sidebar_model.load_from_library_data(collections_data)

        # Convert to SourceListItem format
        items = sidebar_model.to_source_list_items()

        # Should have section headers
        assert len(items) >= 1, "Should have at least one section"

        # Check that items are SourceListItem-like (have expected attributes)
        for section in items:
            assert hasattr(section, 'id'), "Section should have id"
            assert hasattr(section, 'text'), "Section should have text"
            assert hasattr(section, 'is_header'), "Section should have is_header"
            assert hasattr(section, 'children'), "Section should have children"
            assert section.is_header is True, "Section should be a header"

            # Check children are collections
            for child in section.children:
                assert hasattr(child, 'id'), "Child should have id"
                assert hasattr(child, 'text'), "Child should have text"
                assert hasattr(child, 'data'), "Child should have data"
                assert child.is_header is False, "Collection should not be a header"

                # Data should contain collection info
                data = child.data
                assert data is not None, "Data should not be None"
                assert data.get('type') == 'collection', f"Type should be 'collection', got {data.get('type')}"
                assert 'id' in data, "Data should contain id"
                assert 'name' in data, "Data should contain name"

        logger.info("Test passed: to_source_list_items converts correctly")
