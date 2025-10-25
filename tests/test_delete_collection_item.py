"""
Unit tests for delete_collection_item functionality

Tests the complete deletion flow across all three layers:
- Storage layer (database deletion)
- Library manager layer (file cleanup + database)
- Library service layer (UI wrapper)
"""

import sys
from pathlib import Path

# Add src directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pytest
import asyncio
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock

from fichero.library.storage import LibraryStorage
from fichero.library.library_manager import LibraryManager
from fichero.library.models import Collection, CollectionItem
from fichero.windows.main.services.library_service import LibraryService


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        storage = LibraryStorage(db_path)
        yield storage


@pytest.fixture
def temp_library_dir():
    """Create a temporary library directory for testing file operations"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_app(temp_library_dir):
    """Create a mock app with proper paths"""
    app = Mock()
    app.paths = Mock()
    app.paths.app = temp_library_dir / "app"
    app.paths.data = temp_library_dir / "data"
    return app


@pytest.fixture
def library_manager(mock_app, temp_db, temp_library_dir):
    """Create a library manager for testing"""
    manager = LibraryManager(mock_app)
    # Override storage with test database
    manager.storage = temp_db
    manager.library_path = temp_library_dir
    return manager


@pytest.fixture
def library_service(library_manager):
    """Create a library service for testing"""
    return LibraryService(library_manager)


# ===== STORAGE LAYER TESTS =====

def test_delete_collection_item_storage_success(temp_db):
    """Test successful deletion at storage layer"""
    # Create test collection
    collection = Collection(name="Test Collection", type="local")
    assert temp_db.add_collection(collection)

    # Create test item
    item = CollectionItem(
        collection_id=collection.id,
        type="file",
        name="test.jpg",
        storage_type="local"
    )
    assert temp_db.add_collection_item(item)

    # Verify item exists
    assert temp_db.get_item(item.id) is not None

    # Delete item
    assert temp_db.delete_collection_item(item.id)

    # Verify item is gone
    assert temp_db.get_item(item.id) is None


def test_delete_collection_item_storage_nonexistent(temp_db):
    """Test deletion of non-existent item returns False"""
    result = temp_db.delete_collection_item("nonexistent-id")
    assert result is False


def test_delete_collection_item_storage_with_processing_history(temp_db):
    """Test deletion removes related processing history"""
    # Create test collection
    collection = Collection(name="Test Collection", type="local")
    assert temp_db.add_collection(collection)

    # Create test item
    item = CollectionItem(
        collection_id=collection.id,
        type="file",
        name="test.jpg",
        storage_type="local"
    )
    assert temp_db.add_collection_item(item)

    # Add processing history
    from fichero.library.models import ProcessingResult
    from datetime import datetime
    result = ProcessingResult(
        item_id=item.id,
        workflow="test_workflow",
        status="success",
        output_paths=["/test/output"],
        started_at=datetime.now(),
        completed_at=datetime.now()
    )
    assert temp_db.add_processing_result(result)

    # Verify processing history exists
    history = temp_db.get_processing_history(item.id)
    assert len(history) == 1

    # Delete item
    assert temp_db.delete_collection_item(item.id)

    # Verify item and processing history are both gone
    assert temp_db.get_item(item.id) is None
    assert len(temp_db.get_processing_history(item.id)) == 0


# ===== LIBRARY MANAGER LAYER TESTS =====

@pytest.mark.asyncio
async def test_delete_collection_item_manager_not_found(library_manager):
    """Test deletion of non-existent item at manager layer"""
    result = await library_manager.delete_collection_item("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_delete_collection_item_manager_external_item(library_manager):
    """Test deletion of external (linked) item - should not delete files"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="external",
        source_path="/external/path"
    )
    assert collection_id is not None

    # Create external item
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source="/external/test.jpg",
        name="test.jpg",
        operation="link"
    )
    assert item_id is not None

    # Delete item
    result = await library_manager.delete_collection_item(item_id)
    assert result is True

    # Verify item is gone from database
    item = await library_manager.get_item(item_id)
    assert item is None


@pytest.mark.asyncio
async def test_delete_collection_item_manager_local_file(library_manager, temp_library_dir):
    """Test deletion of local (copied) file - should delete file from disk"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create a temporary source file
    source_file = temp_library_dir / "source_test.jpg"
    source_file.write_text("test content")

    # Add item to collection (copy operation)
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source=str(source_file),
        name="test.jpg",
        operation="copy"
    )
    assert item_id is not None

    # Get item to verify local_path
    item = await library_manager.get_item(item_id)
    assert item is not None
    assert item.local_path is not None

    local_file_path = Path(item.local_path)
    assert local_file_path.exists()

    # Delete item
    result = await library_manager.delete_collection_item(item_id)
    assert result is True

    # Verify item is gone from database
    item = await library_manager.get_item(item_id)
    assert item is None

    # Verify local file is deleted
    assert not local_file_path.exists()


@pytest.mark.asyncio
async def test_delete_collection_item_manager_local_directory(library_manager, temp_library_dir):
    """Test deletion of folder item - folders don't get copied, they just add hierarchical structure"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create a temporary source directory with files
    source_dir = temp_library_dir / "source_folder"
    source_dir.mkdir()
    (source_dir / "file1.txt").write_text("content 1")
    (source_dir / "file2.txt").write_text("content 2")

    # Add folder to collection - this creates hierarchical items
    # Folders themselves are not "copied", they create folder items and import files
    result = await library_manager.add_folder_items_to_collection(
        collection_id=collection_id,
        folder_path=str(source_dir),
        operation="copy",
        recursive=True
    )
    assert result['added'] > 0

    # Get the root folder item (first item added)
    folder_item_id = result['item_ids'][0]
    folder_item = await library_manager.get_item(folder_item_id)
    assert folder_item is not None
    assert folder_item.type == "folder"

    # Delete folder item (this should remove the folder from the database)
    delete_result = await library_manager.delete_collection_item(folder_item_id)
    assert delete_result is True

    # Verify folder item is gone from database
    deleted_item = await library_manager.get_item(folder_item_id)
    assert deleted_item is None


@pytest.mark.asyncio
async def test_delete_collection_item_manager_file_deletion_failure(library_manager, temp_library_dir):
    """Test that database deletion succeeds even if file deletion fails"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create item with invalid local_path (simulate file already deleted)
    item = CollectionItem(
        collection_id=collection_id,
        type="file",
        name="missing.jpg",
        storage_type="local",
        local_path="/nonexistent/path/missing.jpg"
    )
    library_manager.storage.add_collection_item(item)

    # Delete item - should succeed despite missing file
    result = await library_manager.delete_collection_item(item.id)
    assert result is True

    # Verify item is gone from database
    deleted_item = await library_manager.get_item(item.id)
    assert deleted_item is None


@pytest.mark.asyncio
@patch('fichero.library.library_manager.emit_navigation_event')
async def test_delete_collection_item_manager_emits_event(mock_emit, library_manager):
    """Test that deletion emits collection_items_changed event"""
    # Reset mock to clear any calls from setup
    mock_emit.reset_mock()

    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Reset mock again after collection creation
    mock_emit.reset_mock()

    # Create test item
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source="/test/file.jpg",
        name="file.jpg",
        operation="link"
    )
    assert item_id is not None

    # Reset mock again before deletion
    mock_emit.reset_mock()

    # Delete item
    result = await library_manager.delete_collection_item(item_id)
    assert result is True

    # Verify event was emitted (should be called exactly once during deletion)
    mock_emit.assert_called_once()
    call_args = mock_emit.call_args
    assert call_args[0][0] == "collection_items_changed"
    assert call_args[0][1]["collection_id"] == collection_id
    assert call_args[0][1]["deleted_item_id"] == item_id


# ===== LIBRARY SERVICE LAYER TESTS =====

@pytest.mark.asyncio
async def test_delete_collection_item_service_success(library_service, library_manager):
    """Test successful deletion through service layer"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create test item
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source="/test/file.jpg",
        name="file.jpg",
        operation="link"
    )
    assert item_id is not None

    # Delete through service
    result = await library_service.delete_collection_item(item_id)
    assert result is True

    # Verify item is gone
    item = await library_manager.get_item(item_id)
    assert item is None


@pytest.mark.asyncio
async def test_delete_collection_item_service_not_found(library_service):
    """Test deletion of non-existent item through service layer"""
    result = await library_service.delete_collection_item("nonexistent-id")
    assert result is False


@pytest.mark.asyncio
async def test_delete_collection_item_service_exception_handling(library_service, library_manager):
    """Test that service layer handles exceptions gracefully"""
    # Create test item
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source="/test/file.jpg",
        name="file.jpg",
        operation="link"
    )

    # Mock library_manager.delete_collection_item to raise exception
    with patch.object(library_manager, 'delete_collection_item', side_effect=Exception("Test error")):
        result = await library_service.delete_collection_item(item_id)
        assert result is False


# ===== INTEGRATION TESTS =====

@pytest.mark.asyncio
async def test_delete_collection_item_full_stack(library_service, library_manager, temp_library_dir):
    """Test complete deletion flow from service -> manager -> storage"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create a temporary source file
    source_file = temp_library_dir / "integration_test.jpg"
    source_file.write_text("integration test content")

    # Add item to collection
    item_id = await library_manager.add_item_to_collection(
        collection_id=collection_id,
        item_type="file",
        source=str(source_file),
        name="integration_test.jpg",
        operation="copy"
    )
    assert item_id is not None

    # Get item details
    item = await library_manager.get_item(item_id)
    assert item is not None
    local_file_path = Path(item.local_path)
    assert local_file_path.exists()

    # Add processing history
    from fichero.library.models import ProcessingResult
    from datetime import datetime
    result = ProcessingResult(
        item_id=item_id,
        workflow="test_workflow",
        status="success",
        output_paths=["/test/output"],
        started_at=datetime.now(),
        completed_at=datetime.now()
    )
    library_manager.storage.add_processing_result(result)

    # Verify processing history exists
    history = library_manager.storage.get_processing_history(item_id)
    assert len(history) == 1

    # Delete through service layer
    delete_result = await library_service.delete_collection_item(item_id)
    assert delete_result is True

    # Verify complete cleanup:
    # 1. Item gone from database
    assert await library_manager.get_item(item_id) is None

    # 2. Processing history gone
    assert len(library_manager.storage.get_processing_history(item_id)) == 0

    # 3. Local file deleted
    assert not local_file_path.exists()


@pytest.mark.asyncio
async def test_delete_multiple_items_sequentially(library_service, library_manager):
    """Test deleting multiple items from same collection"""
    # Create test collection
    collection_id = await library_manager.add_collection(
        name="Test Collection",
        collection_type="local"
    )
    assert collection_id is not None

    # Create multiple items
    item_ids = []
    for i in range(5):
        item_id = await library_manager.add_item_to_collection(
            collection_id=collection_id,
            item_type="file",
            source=f"/test/file{i}.jpg",
            name=f"file{i}.jpg",
            operation="link"
        )
        assert item_id is not None
        item_ids.append(item_id)

    # Verify all items exist
    items = await library_manager.get_collection_items(collection_id)
    assert len(items) == 5

    # Delete all items sequentially
    for item_id in item_ids:
        result = await library_service.delete_collection_item(item_id)
        assert result is True

    # Verify all items are gone
    items = await library_manager.get_collection_items(collection_id)
    assert len(items) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
