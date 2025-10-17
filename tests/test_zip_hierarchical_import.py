"""
Unit tests for hierarchical ZIP import functionality

Tests that ZIP files are imported with their folder structure preserved,
creating folder items and linking files to parent folders via parent_id.
"""

import pytest
import tempfile
import zipfile
from pathlib import Path


@pytest.fixture
def create_test_zip():
    """Create a test ZIP file with hierarchical structure"""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create test folder structure
        root_folder = temp_path / "test_archive"
        root_folder.mkdir()

        # Create subfolders
        folder1 = root_folder / "folder1"
        folder2 = root_folder / "folder2"
        folder1.mkdir()
        folder2.mkdir()

        # Create test files
        (folder1 / "file1.txt").write_text("Content 1")
        (folder1 / "file2.txt").write_text("Content 2")
        (folder2 / "file3.txt").write_text("Content 3")

        # Create ZIP file
        zip_path = temp_path / "test_archive.zip"
        with zipfile.ZipFile(zip_path, 'w') as zf:
            for file in root_folder.rglob('*'):
                if file.is_file():
                    arcname = file.relative_to(temp_path)
                    zf.write(file, arcname)

        yield zip_path


@pytest.mark.asyncio
async def test_zip_import_preserves_hierarchy(create_test_zip, mock_library_manager):
    """Test that ZIP import creates folder items and links files to parents"""
    zip_path = create_test_zip

    # Import the ZIP file
    from fichero.library.import_plugins.registry import PluginRegistry
    from fichero.library.import_plugins.zip_plugin import ZipImportPlugin

    # Register ZIP plugin
    registry = PluginRegistry()
    zip_plugin = ZipImportPlugin(mock_library_manager)
    registry.register(zip_plugin)

    # Import ZIP
    result = await zip_plugin.download_and_import(
        url=str(zip_path),
        collection_name="Test Hierarchical Import",
        collection_description="Test ZIP with folder structure"
    )

    # Verify import succeeded
    assert result.success is True
    assert result.files_imported == 3  # 3 files
    assert result.collection_id is not None

    # Get all items from the created collection
    items = mock_library_manager.storage.get_collection_items(result.collection_id)

    # Should have folder items + file items
    folder_items = [item for item in items if item.type == "folder"]
    file_items = [item for item in items if item.type == "file"]

    assert len(folder_items) == 2  # folder1, folder2
    assert len(file_items) == 3    # file1.txt, file2.txt, file3.txt

    # Verify folder names
    folder_names = {f.name for f in folder_items}
    assert "folder1" in folder_names
    assert "folder2" in folder_names

    # Verify files are linked to correct parent folders
    for file_item in file_items:
        assert file_item.parent_id is not None, f"File {file_item.name} has no parent_id"

        # Find parent folder
        parent = next((f for f in folder_items if f.id == file_item.parent_id), None)
        assert parent is not None, f"Parent folder not found for {file_item.name}"

        # Verify file is in correct folder
        if file_item.name in ["file1.txt", "file2.txt"]:
            assert parent.name == "folder1"
        elif file_item.name == "file3.txt":
            assert parent.name == "folder2"


@pytest.mark.asyncio
async def test_folder_hierarchy_in_collection(mock_library_manager):
    """Test that add_folder_items_to_collection preserves hierarchy"""
    # Create test folder structure
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create subfolder structure
        subfolder = temp_path / "sub1"
        subfolder.mkdir()

        # Create files
        (temp_path / "root_file.txt").write_text("Root file")
        (subfolder / "sub_file.txt").write_text("Sub file")

        # Create collection
        collection_id = await mock_library_manager.add_collection(
            name="Hierarchy Test",
            collection_type="local",
            source_path=str(temp_path)
        )

        # Add folder items
        stats = await mock_library_manager.add_folder_items_to_collection(
            collection_id=collection_id,
            folder_path=str(temp_path),
            operation="link",
            recursive=True
        )

        # Verify stats
        assert stats["added"] >= 3  # 1 folder + 2 files minimum
        assert stats["errors"] == 0

        # Get items
        items = mock_library_manager.storage.get_collection_items(collection_id)

        # Find folder and files
        folder_items = [item for item in items if item.type == "folder"]
        file_items = [item for item in items if item.type == "file"]

        assert len(folder_items) >= 1
        assert len(file_items) >= 2

        # Verify root file has no parent
        root_file = next((f for f in file_items if f.name == "root_file.txt"), None)
        assert root_file is not None
        assert root_file.parent_id is None  # Root level file

        # Verify sub file has parent folder
        sub_file = next((f for f in file_items if f.name == "sub_file.txt"), None)
        assert sub_file is not None
        assert sub_file.parent_id is not None  # Has parent

        # Verify parent is the subfolder
        parent_folder = next((f for f in folder_items if f.id == sub_file.parent_id), None)
        assert parent_folder is not None
        assert parent_folder.name == "sub1"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
