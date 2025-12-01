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
from pathlib import Path
from tempfile import TemporaryDirectory

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage
from fichero.windows.main.views.library.sidebar_data_model import SidebarDataModel, SidebarCollection, SidebarFolder

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def library_with_folders():
    """Create a library with a collection and folders"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Create a test collection
        collection_id = await manager.add_collection(
            name="Test Collection",
            collection_type="local",
            source_path=None
        )

        # Add some folders to the collection
        folder1_id = await manager.add_item(
            collection_id=collection_id,
            name="Folder 1",
            item_type="folder",
            parent_id=None  # Root level folder
        )

        folder2_id = await manager.add_item(
            collection_id=collection_id,
            name="Folder 2",
            item_type="folder",
            parent_id=None  # Root level folder
        )

        # Add some items to folder1
        await manager.add_item(
            collection_id=collection_id,
            name="Item 1",
            item_type="file",
            parent_id=folder1_id
        )

        await manager.add_item(
            collection_id=collection_id,
            name="Item 2",
            item_type="file",
            parent_id=folder1_id
        )

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

    # Get collection data from library
    collections = await manager.get_all_collections()
    collections_data = [
        {
            'id': c.id,
            'name': c.name,
            'type': c.type,
            'item_count': c.item_count,
            'metadata': c.metadata,
            'sort_order': 0
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
    test_collection_item = None
    for item in widget_data:
        if item.get('_collection_data', {}).get('id') == collection_id:
            test_collection_item = item
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
        manager = LibraryManager(db_path)

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

        # Get all collections
        collections = await manager.get_all_collections()
        collections_data = [
            {
                'id': c.id,
                'name': c.name,
                'type': c.type,
                'item_count': c.item_count,
                'metadata': c.metadata,
                'sort_order': 0
            }
            for c in collections
        ]

        # Load into sidebar model
        sidebar_model = SidebarDataModel()
        sidebar_model.load_from_library_data(collections_data)

        # Verify section organization
        assert 'favorites' in sidebar_model.collections
        assert 'local' in sidebar_model.collections
        assert 'external' in sidebar_model.collections

        # Inbox should be in favorites
        favorites = sidebar_model.collections['favorites']
        assert len(favorites) == 1
        assert favorites[0].metadata.get('is_inbox') is True

        # Local collection should be in local
        local_collections = sidebar_model.collections['local']
        assert any(c.id == local_id for c in local_collections)

        # External collection should be in external
        external_collections = sidebar_model.collections['external']
        assert any(c.id == external_id for c in external_collections)

        logger.info("✅ Test passed: Collections organized into correct sections")


@pytest.mark.asyncio
async def test_empty_collection_no_children():
    """Test that collections without folders don't have _children key"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Create empty collection
        collection_id = await manager.add_collection(
            name="Empty Collection",
            collection_type="local",
            source_path=None
        )

        sidebar_model = SidebarDataModel()

        # Get collection data
        collections = await manager.get_all_collections()
        collections_data = [
            {
                'id': c.id,
                'name': c.name,
                'type': c.type,
                'item_count': c.item_count,
                'metadata': c.metadata,
                'sort_order': 0
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
        empty_collection_item = None
        for item in widget_data:
            if item.get('_collection_data', {}).get('id') == collection_id:
                empty_collection_item = item
                break

        assert empty_collection_item is not None

        # Should NOT have _children key (or it should be empty)
        children = empty_collection_item.get('_children', [])
        assert len(children) == 0, "Empty collection should have no children"

        logger.info("✅ Test passed: Empty collections have no _children")
