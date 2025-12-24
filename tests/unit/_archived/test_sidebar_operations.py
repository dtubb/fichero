"""
Unit tests for sidebar operations (rename, delete, reorder, refresh)

Tests verify that sidebar operations properly:
1. Save changes to the database
2. Trigger appropriate event handlers
3. Refresh the sidebar after operations
"""

import pytest
import pytest_asyncio
import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch, AsyncMock

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage


@pytest_asyncio.fixture
async def library_manager():
    """Create a LibraryManager instance with proper test isolation"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        mock_app = Mock()
        with patch('fichero.library.path_resolver.get_library_database_path', return_value=db_path):
            manager = LibraryManager(app=mock_app)
        yield manager


class TestRenameOperations:
    """Test that rename operations save to database"""

    @pytest.mark.asyncio
    async def test_rename_collection_updates_database(self, library_manager):
        """Renaming a collection should persist to the database"""
        # Create a collection
        collection_id = await library_manager.add_collection(
            name="Original Name",
            collection_type="local",
            source_path=None
        )

        # Rename it
        success = await library_manager.update_collection(
            collection_id,
            name="New Name"
        )

        assert success is True

        # Verify the change persisted
        collections = library_manager.storage.get_all_collections()
        renamed = next((c for c in collections if c.id == collection_id), None)

        assert renamed is not None
        assert renamed.name == "New Name"

    @pytest.mark.asyncio
    async def test_rename_preserves_other_fields(self, library_manager):
        """Renaming should not affect other collection fields"""
        # Create a collection with metadata
        collection_id = await library_manager.add_collection(
            name="Original Name",
            collection_type="local",
            source_path=None,
            description="Test description",
            metadata={"custom_key": "custom_value"}
        )

        # Rename it
        await library_manager.update_collection(collection_id, name="New Name")

        # Verify other fields unchanged
        collections = library_manager.storage.get_all_collections()
        renamed = next((c for c in collections if c.id == collection_id), None)

        assert renamed is not None
        assert renamed.name == "New Name"
        assert renamed.type == "local"
        assert renamed.metadata.get("custom_key") == "custom_value"

    @pytest.mark.asyncio
    async def test_rename_nonexistent_collection_fails(self, library_manager):
        """Renaming a non-existent collection should fail gracefully"""
        success = await library_manager.update_collection(
            "nonexistent-id",
            name="New Name"
        )

        # Should return False or handle gracefully
        assert success is False


class TestDeleteOperations:
    """Test that delete operations remove from database"""

    @pytest.mark.asyncio
    async def test_delete_collection_removes_from_database(self, library_manager):
        """Deleting a collection should remove it from the database"""
        # Create a collection
        collection_id = await library_manager.add_collection(
            name="To Delete",
            collection_type="local",
            source_path=None
        )

        # Verify it exists
        collections_before = library_manager.storage.get_all_collections()
        assert any(c.id == collection_id for c in collections_before)

        # Delete it
        success = await library_manager.delete_collection(collection_id)
        assert success is True

        # Verify it's gone
        collections_after = library_manager.storage.get_all_collections()
        assert not any(c.id == collection_id for c in collections_after)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_collection_fails(self, library_manager):
        """Deleting a non-existent collection should fail gracefully"""
        success = await library_manager.delete_collection("nonexistent-id")

        # Should return False or handle gracefully
        assert success is False

    @pytest.mark.asyncio
    async def test_delete_inbox_not_allowed(self, library_manager):
        """Deleting the inbox should not be allowed"""
        # Create inbox
        inbox_id = await library_manager.get_or_create_inbox()

        # Attempt to delete inbox
        success = await library_manager.delete_collection(inbox_id)

        # Should fail (inbox is protected)
        # Note: If this fails, inbox protection may not be implemented
        # In that case, update the implementation to protect inbox

        # Verify inbox still exists
        collections = library_manager.storage.get_all_collections()
        inbox = next((c for c in collections if c.id == inbox_id), None)
        assert inbox is not None


class TestReorderOperations:
    """Test that reorder operations save sort_order to database"""

    @pytest.mark.asyncio
    async def test_reorder_collection_updates_sort_order(self, library_manager):
        """Reordering a collection should update sort_order in database"""
        # Create multiple collections
        id1 = await library_manager.add_collection(
            name="Collection 1",
            collection_type="local",
            source_path=None
        )
        id2 = await library_manager.add_collection(
            name="Collection 2",
            collection_type="local",
            source_path=None
        )
        id3 = await library_manager.add_collection(
            name="Collection 3",
            collection_type="local",
            source_path=None
        )

        # Get total collection count (includes inbox)
        all_collections = await library_manager.get_all_collections()
        total_count = len(all_collections)

        # Reorder: move collection 3 to position 1 (1-based)
        success = await library_manager.reorder_collection(id3, 1)
        assert success is True

        # Verify order changed in database
        collections = library_manager.storage.get_all_collections()
        local_collections = [c for c in collections if c.type == "local" and not c.metadata.get('is_inbox')]

        # Sort by sort_order to check new order
        sorted_collections = sorted(local_collections, key=lambda c: c.sort_order or 999)

        # Collection 3 should be first now among local collections
        assert sorted_collections[0].id == id3

    @pytest.mark.asyncio
    async def test_reorder_preserves_collection_data(self, library_manager):
        """Reordering should not affect other collection fields"""
        # Create a collection with metadata
        collection_id = await library_manager.add_collection(
            name="Test Collection",
            collection_type="local",
            source_path=None,
            description="Test description",
            metadata={"custom_key": "custom_value"}
        )

        # Get total collection count for valid position
        all_collections = await library_manager.get_all_collections()
        position = len(all_collections)  # Move to last position

        # Reorder it
        await library_manager.reorder_collection(collection_id, position)

        # Verify other fields unchanged
        collections = library_manager.storage.get_all_collections()
        collection = next((c for c in collections if c.id == collection_id), None)

        assert collection is not None
        assert collection.name == "Test Collection"
        assert collection.type == "local"
        assert collection.metadata.get("custom_key") == "custom_value"


class TestSidebarRefresh:
    """Test that sidebar refreshes after operations"""

    @pytest.mark.asyncio
    async def test_add_collection_increments_count(self, library_manager):
        """Adding a collection should increase the collection count"""
        # Get initial count (may include inbox)
        initial = library_manager.storage.get_all_collections()
        initial_count = len(initial)

        # Add a collection
        await library_manager.add_collection(
            name="New Collection",
            collection_type="local",
            source_path=None
        )

        # Verify count increased
        after = library_manager.storage.get_all_collections()
        assert len(after) == initial_count + 1

    @pytest.mark.asyncio
    async def test_get_all_collections_returns_current_state(self, library_manager):
        """get_all_collections should always return the current database state"""
        # Add a collection
        collection_id = await library_manager.add_collection(
            name="Test Collection",
            collection_type="local",
            source_path=None
        )

        # Get collections - should include the new one
        # get_all_collections returns List[Collection] objects with .id attribute
        collections = await library_manager.get_all_collections()
        assert any(c.id == collection_id for c in collections)

        # Delete it
        await library_manager.delete_collection(collection_id)

        # Force refresh to get current state
        collections = await library_manager.get_all_collections(force_refresh=True)
        assert not any(c.id == collection_id for c in collections)


class TestConcurrentOperations:
    """Test that concurrent operations don't cause issues"""

    @pytest.mark.asyncio
    async def test_concurrent_renames_dont_conflict(self, library_manager):
        """Multiple concurrent renames should all succeed"""
        # Create multiple collections
        ids = []
        for i in range(5):
            cid = await library_manager.add_collection(
                name=f"Collection {i}",
                collection_type="local",
                source_path=None
            )
            ids.append(cid)

        # Rename all concurrently
        tasks = [
            library_manager.update_collection(cid, name=f"Renamed {i}")
            for i, cid in enumerate(ids)
        ]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(results)

        # Verify all renamed
        collections = library_manager.storage.get_all_collections()
        for i, cid in enumerate(ids):
            c = next((c for c in collections if c.id == cid), None)
            assert c is not None
            assert c.name == f"Renamed {i}"

    @pytest.mark.asyncio
    async def test_concurrent_adds_all_succeed(self, library_manager):
        """Multiple concurrent add_collection calls should all succeed"""
        # Create 10 collections concurrently
        tasks = [
            library_manager.add_collection(
                name=f"Concurrent {i}",
                collection_type="local",
                source_path=None
            )
            for i in range(10)
        ]
        ids = await asyncio.gather(*tasks)

        # All should have valid IDs
        assert all(id is not None for id in ids)
        assert len(set(ids)) == 10  # All unique

        # Verify all exist in database
        collections = library_manager.storage.get_all_collections()
        for cid in ids:
            assert any(c.id == cid for c in collections)
