"""
Unit tests for inbox duplication race condition fix (Phase 6)

Tests verify that the asyncio lock prevents multiple concurrent calls to
get_all_collections() from creating duplicate inbox collections.
"""

import pytest
import pytest_asyncio
import asyncio
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from fichero.library.library_manager import LibraryManager
from fichero.library.storage import LibraryStorage

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def temp_library():
    """Create a temporary library for testing"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        storage = LibraryStorage(db_path)
        manager = LibraryManager(db_path)
        yield manager, storage
        # Cleanup is automatic with TemporaryDirectory


@pytest.mark.asyncio
async def test_inbox_created_only_once(temp_library):
    """
    Test that inbox is created only once even with concurrent calls.

    This is the critical race condition fix: multiple concurrent calls to
    get_all_collections() should result in only ONE inbox being created.
    """
    manager, storage = temp_library

    # Verify no inbox exists initially
    all_collections = storage.get_all_collections()
    inbox_count = sum(1 for c in all_collections if c.metadata.get('is_inbox'))
    assert inbox_count == 0, "Should start with no inbox"

    # Simulate race condition: 5 concurrent calls to get_all_collections()
    # Only ONE inbox should be created
    tasks = [manager.get_all_collections() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    # Verify all results are consistent
    for result in results:
        assert isinstance(result, list)

    # Check database: should have exactly ONE inbox
    all_collections = storage.get_all_collections()
    inbox_collections = [c for c in all_collections if c.metadata.get('is_inbox')]

    assert len(inbox_collections) == 1, f"Expected exactly 1 inbox, found {len(inbox_collections)}"

    # Verify the inbox has correct properties
    inbox = inbox_collections[0]
    assert inbox.name == "Inbox"
    assert inbox.type == "local"
    assert inbox.metadata.get('system_collection') is True

    logger.info(f"✅ Test passed: Only 1 inbox created from {len(tasks)} concurrent calls")


@pytest.mark.asyncio
async def test_inbox_setup_lock_initialization():
    """Test that the inbox setup lock is properly initialized"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Lock should be None initially
        assert manager._inbox_setup_lock is None

        # After first async call, lock should be created
        await manager.get_all_collections()

        assert manager._inbox_setup_lock is not None
        assert isinstance(manager._inbox_setup_lock, asyncio.Lock)

        logger.info("✅ Test passed: Inbox setup lock initialized correctly")


@pytest.mark.asyncio
async def test_inbox_setup_flag_cleared():
    """Test that inbox setup flag is cleared after first creation"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Flag should be True initially
        assert manager._inbox_setup_pending is True

        # After first call, flag should be False
        await manager.get_all_collections()
        assert manager._inbox_setup_pending is False

        # Subsequent calls should not re-create inbox
        await manager.get_all_collections()
        await manager.get_all_collections()

        # Verify only one inbox exists
        all_collections = manager.storage.get_all_collections()
        inbox_count = sum(1 for c in all_collections if c.metadata.get('is_inbox'))
        assert inbox_count == 1

        logger.info("✅ Test passed: Inbox setup flag cleared after first creation")


@pytest.mark.asyncio
async def test_get_or_create_inbox_no_recursion():
    """Test that get_or_create_inbox doesn't recursively call get_all_collections"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Direct call to get_or_create_inbox should work without recursion
        inbox_id = await manager.get_or_create_inbox()

        assert inbox_id is not None
        assert isinstance(inbox_id, str)

        # Verify inbox was created
        all_collections = manager.storage.get_all_collections()
        inbox = next((c for c in all_collections if c.id == inbox_id), None)

        assert inbox is not None
        assert inbox.metadata.get('is_inbox') is True

        logger.info("✅ Test passed: get_or_create_inbox works without recursion")


@pytest.mark.asyncio
async def test_concurrent_inbox_creation_stress():
    """Stress test: 20 concurrent calls should still create only one inbox"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # 20 concurrent calls
        tasks = [manager.get_all_collections() for _ in range(20)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(isinstance(r, list) for r in results)

        # Only one inbox
        all_collections = manager.storage.get_all_collections()
        inbox_count = sum(1 for c in all_collections if c.metadata.get('is_inbox'))

        assert inbox_count == 1, f"Expected 1 inbox, found {inbox_count} from 20 concurrent calls"

        logger.info("✅ Test passed: Stress test with 20 concurrent calls created only 1 inbox")


@pytest.mark.asyncio
async def test_existing_inbox_not_duplicated():
    """Test that existing inbox is not duplicated on subsequent calls"""
    with TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_library.db"
        manager = LibraryManager(db_path)

        # Create inbox manually first
        inbox_id = await manager.get_or_create_inbox()

        # Now make concurrent calls - should not create another inbox
        tasks = [manager.get_all_collections() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Verify still only one inbox
        all_collections = manager.storage.get_all_collections()
        inbox_collections = [c for c in all_collections if c.metadata.get('is_inbox')]

        assert len(inbox_collections) == 1
        assert inbox_collections[0].id == inbox_id

        logger.info("✅ Test passed: Existing inbox not duplicated")
