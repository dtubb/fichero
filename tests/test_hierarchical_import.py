"""
Comprehensive tests for hierarchical import functionality

Tests that all import paths (folder, ZIP, plugins) preserve folder structure
using parent_id relationships.
"""

import pytest
import tempfile
import zipfile
import sqlite3
from pathlib import Path


@pytest.fixture
def test_folder_structure():
    """Create a test folder with hierarchical structure"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create root folder
        root = temp_path / "test_collection"
        root.mkdir()

        # Create subfolders
        docs = root / "documents"
        imgs = root / "images"
        docs.mkdir()
        imgs.mkdir()

        # Create nested subfolders
        contracts = docs / "contracts"
        invoices = docs / "invoices"
        photos = imgs / "photos"
        contracts.mkdir()
        invoices.mkdir()
        photos.mkdir()

        # Create files
        (root / "readme.txt").write_text("Root file")
        (docs / "doc1.txt").write_text("Doc 1")
        (contracts / "contract1.pdf").write_text("Contract 1")
        (invoices / "invoice1.pdf").write_text("Invoice 1")
        (imgs / "img1.jpg").write_text("Image 1")
        (photos / "photo1.jpg").write_text("Photo 1")

        yield root


@pytest.fixture
def test_zip_file(test_folder_structure):
    """Create a test ZIP file with hierarchical structure"""
    with tempfile.TemporaryDirectory() as temp_dir:
        zip_path = Path(temp_dir) / "test.zip"

        with zipfile.ZipFile(zip_path, 'w') as zf:
            for file in test_folder_structure.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(test_folder_structure.parent)
                    zf.write(file, arcname)

        yield zip_path


@pytest.mark.asyncio
async def test_folder_import_hierarchy(test_folder_structure, mock_library_manager):
    """Test that folder import preserves hierarchical structure"""
    # Import folder
    collection_id = await mock_library_manager.add_collection(
        name="Test Folder Hierarchy",
        collection_type="local",
        source_path=str(test_folder_structure)
    )

    assert collection_id is not None

    # Import items
    stats = await mock_library_manager.add_folder_items_to_collection(
        collection_id=collection_id,
        folder_path=str(test_folder_structure),
        operation="link",
        recursive=True
    )

    # Verify import stats
    assert stats["added"] >= 9  # 5 folders + 6 files minimum
    assert stats["errors"] == 0

    # Get all items
    items = mock_library_manager.storage.get_collection_items(collection_id)

    # Separate folders and files
    folders = [item for item in items if item.type == "folder"]
    files = [item for item in items if item.type == "file"]

    # Verify folder count
    assert len(folders) >= 5  # documents, images, contracts, invoices, photos

    # Verify file count
    assert len(files) >= 6

    # Verify root folders have no parent
    root_folders = [f for f in folders if f.parent_id is None]
    assert len(root_folders) >= 2  # documents, images

    # Verify nested folders have parents
    nested_folders = [f for f in folders if f.parent_id is not None]
    assert len(nested_folders) >= 3  # contracts, invoices, photos

    # Verify all nested folders have valid parents
    for nested in nested_folders:
        parent = next((f for f in folders if f.id == nested.parent_id), None)
        assert parent is not None, f"Parent not found for {nested.name}"

    # Verify all files have parent folders
    for file_item in files:
        if file_item.name != "readme.txt":  # Root file might not have parent
            assert file_item.parent_id is not None, f"File {file_item.name} has no parent"


@pytest.mark.asyncio
async def test_zip_import_hierarchy(test_zip_file, mock_library_manager):
    """Test that ZIP import preserves hierarchical structure"""
    from fichero.library.import_plugins.registry import PluginRegistry
    from fichero.library.import_plugins.zip_plugin import ZipImportPlugin

    # Create and register plugin
    registry = PluginRegistry()
    zip_plugin = ZipImportPlugin(mock_library_manager)
    registry.register(zip_plugin)

    # Import ZIP
    result = await zip_plugin.download_and_import(
        url=str(test_zip_file),
        collection_name="Test ZIP Hierarchy",
        collection_description="Test ZIP with folder structure"
    )

    # Verify import succeeded
    assert result.success is True
    assert result.collection_id is not None

    # Get all items
    items = mock_library_manager.storage.get_collection_items(result.collection_id)

    # Separate folders and files
    folders = [item for item in items if item.type == "folder"]
    files = [item for item in items if item.type == "file"]

    # Verify structure was preserved
    assert len(folders) >= 5
    assert len(files) >= 6

    # Verify parent-child relationships
    for file_item in files:
        if file_item.parent_id:
            parent = next((f for f in folders if f.id == file_item.parent_id), None)
            assert parent is not None, f"Parent not found for {file_item.name}"


@pytest.mark.asyncio
async def test_parent_id_relationships(test_folder_structure, mock_library_manager):
    """Test that parent_id relationships are correctly maintained"""
    # Import folder
    collection_id = await mock_library_manager.add_collection(
        name="Test Parent IDs",
        collection_type="local",
        source_path=str(test_folder_structure)
    )

    # Import items
    stats = await mock_library_manager.add_folder_items_to_collection(
        collection_id=collection_id,
        folder_path=str(test_folder_structure),
        operation="link",
        recursive=True
    )

    # Get all items
    items = mock_library_manager.storage.get_collection_items(collection_id)

    # Build parent-child map
    item_map = {item.id: item for item in items}

    # Verify no circular references
    for item in items:
        visited = set()
        current = item
        while current.parent_id:
            if current.id in visited:
                pytest.fail(f"Circular reference detected for item {item.name}")
            visited.add(current.id)
            current = item_map.get(current.parent_id)
            if not current:
                break

    # Verify all parent_ids reference valid folder items
    for item in items:
        if item.parent_id:
            parent = item_map.get(item.parent_id)
            assert parent is not None, f"Invalid parent_id for {item.name}"
            assert parent.type == "folder", f"Parent of {item.name} is not a folder"


@pytest.mark.asyncio
async def test_database_parent_id_column(mock_library_manager):
    """Test that database schema has parent_id column with proper constraints"""
    # Get database path
    db_path = mock_library_manager.storage.db_path

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get table schema
    cursor.execute("PRAGMA table_info(collection_items)")
    columns = cursor.fetchall()

    # Verify parent_id column exists
    column_names = [col[1] for col in columns]
    assert "parent_id" in column_names, "parent_id column not found in collection_items table"

    # Get parent_id column info
    parent_id_col = next((col for col in columns if col[1] == "parent_id"), None)
    assert parent_id_col is not None
    assert parent_id_col[2] == "TEXT", "parent_id should be TEXT type"

    conn.close()


@pytest.mark.asyncio
async def test_hierarchy_with_empty_folders(mock_library_manager):
    """Test that empty folders are handled correctly in hierarchy"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create structure with empty folders
        root = temp_path / "test"
        root.mkdir()

        empty1 = root / "empty1"
        empty2 = root / "empty2"
        with_files = root / "with_files"

        empty1.mkdir()
        empty2.mkdir()
        with_files.mkdir()

        (with_files / "file1.txt").write_text("Content")

        # Import
        collection_id = await mock_library_manager.add_collection(
            name="Test Empty Folders",
            collection_type="local",
            source_path=str(root)
        )

        stats = await mock_library_manager.add_folder_items_to_collection(
            collection_id=collection_id,
            folder_path=str(root),
            operation="link",
            recursive=True
        )

        # Get items
        items = mock_library_manager.storage.get_collection_items(collection_id)
        folders = [item for item in items if item.type == "folder"]

        # Verify all folders were imported
        folder_names = {f.name for f in folders}
        assert "empty1" in folder_names
        assert "empty2" in folder_names
        assert "with_files" in folder_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
