"""
Unit tests for LibraryManagerSync wrapper.

Tests the synchronous wrapper that provides a sync API for async library operations.
"""

import pytest
import asyncio
import threading
import time
from unittest.mock import Mock, AsyncMock
from pathlib import Path


class TestLibraryManagerSyncBasics:
    """Test basic LibraryManagerSync functionality"""

    def test_sync_wrapper_initialization(self):
        """Test that sync wrapper initializes correctly"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        wrapper = LibraryManagerSync(mock_library)

        assert wrapper.library == mock_library

    def test_sync_wrapper_runs_async_method(self):
        """Test that sync wrapper can run async library methods"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        # Create mock library with async method
        mock_library = Mock()
        async_result = {"id": "col-123", "name": "Test Collection"}

        async def mock_get_collection(collection_id):
            return async_result

        mock_library.get_collection = mock_get_collection

        # Create sync wrapper and call method
        wrapper = LibraryManagerSync(mock_library)
        result = wrapper.get_collection("col-123")

        # Assert result matches
        assert result == async_result

    def test_sync_wrapper_with_no_running_loop(self):
        """Test that sync wrapper works when no event loop exists"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        # Ensure no event loop in current thread
        try:
            loop = asyncio.get_running_loop()
            pytest.skip("Cannot test 'no loop' scenario - loop already running")
        except RuntimeError:
            pass  # Good - no running loop

        mock_library = Mock()

        async def mock_async_operation():
            await asyncio.sleep(0.01)
            return "success"

        mock_library.some_operation = mock_async_operation

        wrapper = LibraryManagerSync(mock_library)
        result = wrapper._run_in_thread(mock_library.some_operation())

        assert result == "success"


class TestLibraryManagerSyncThreadIsolation:
    """Test that sync wrapper properly isolates event loops in threads"""

    def test_concurrent_calls_from_multiple_threads(self):
        """Test that multiple threads can call wrapper concurrently"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        call_count = {"count": 0}
        lock = threading.Lock()

        async def mock_operation(item_id):
            # Simulate async I/O
            await asyncio.sleep(0.01)
            with lock:
                call_count["count"] += 1
            return f"result-{item_id}"

        mock_library.get_item = mock_operation

        wrapper = LibraryManagerSync(mock_library)

        # Run 5 operations concurrently from different threads
        results = []

        def thread_worker(item_id):
            result = wrapper._run_in_thread(mock_library.get_item(item_id))
            results.append(result)

        threads = []
        for i in range(5):
            t = threading.Thread(target=thread_worker, args=(f"item-{i}",))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join(timeout=5.0)

        # Assert all operations completed
        assert len(results) == 5
        assert call_count["count"] == 5
        assert "result-item-0" in results

    def test_no_event_loop_conflicts(self):
        """Test that wrapper doesn't conflict with existing event loops"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()

        async def mock_operation():
            # This should not interfere with the outer loop
            return "nested-success"

        mock_library.operation = mock_operation

        async def outer_async_function():
            """Function that runs in an event loop"""
            # Verify we have a running loop
            loop = asyncio.get_running_loop()
            assert loop.is_running()

            # Create wrapper and call it from async context
            wrapper = LibraryManagerSync(mock_library)

            # This should work even though we're in an async context
            # because wrapper uses separate thread
            result = await asyncio.to_thread(
                wrapper._run_in_thread,
                mock_library.operation()
            )

            return result

        # Run the outer function
        result = asyncio.run(outer_async_function())
        assert result == "nested-success"


class TestLibraryManagerSyncExceptionHandling:
    """Test exception propagation through sync wrapper"""

    def test_exception_propagates_correctly(self):
        """Test that exceptions from async methods propagate"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()

        async def mock_failing_operation():
            raise ValueError("Test error")

        mock_library.failing_op = mock_failing_operation

        wrapper = LibraryManagerSync(mock_library)

        with pytest.raises(ValueError, match="Test error"):
            wrapper._run_in_thread(mock_library.failing_op())

    def test_exception_with_cleanup(self):
        """Test that exceptions don't leave resources hanging"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        cleanup_called = {"called": False}

        async def mock_operation_with_cleanup():
            try:
                raise RuntimeError("Simulated error")
            finally:
                cleanup_called["called"] = True

        mock_library.operation = mock_operation_with_cleanup

        wrapper = LibraryManagerSync(mock_library)

        with pytest.raises(RuntimeError):
            wrapper._run_in_thread(mock_library.operation())

        # Cleanup should have been called
        assert cleanup_called["called"] is True


class TestLibraryManagerSyncCollectionMethods:
    """Test specific collection method wrappers"""

    def test_get_collection_sync(self):
        """Test get_collection sync wrapper"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        mock_collection = {"id": "col-456", "name": "Test"}

        async def mock_get_collection(collection_id):
            return mock_collection

        mock_library.get_collection = mock_get_collection

        wrapper = LibraryManagerSync(mock_library)
        result = wrapper.get_collection("col-456")

        assert result == mock_collection

    def test_add_collection_sync(self):
        """Test add_collection sync wrapper"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        new_collection = {"id": "col-new", "name": "New Collection"}

        async def mock_add_collection(name, collection_type, source_path=None):
            return new_collection

        mock_library.add_collection = mock_add_collection

        wrapper = LibraryManagerSync(mock_library)
        result = wrapper.add_collection("New Collection", "local", Path("/test"))

        assert result == new_collection

    def test_get_all_collections_sync(self):
        """Test get_all_collections sync wrapper"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()
        collections = [
            {"id": "col-1", "name": "Collection 1"},
            {"id": "col-2", "name": "Collection 2"}
        ]

        async def mock_get_all_collections():
            return collections

        mock_library.get_all_collections = mock_get_all_collections

        wrapper = LibraryManagerSync(mock_library)
        result = wrapper.get_all_collections()

        assert len(result) == 2
        assert result[0]["id"] == "col-1"


class TestLibraryManagerSyncPerformance:
    """Test performance characteristics of sync wrapper"""

    def test_overhead_acceptable(self):
        """Test that wrapper overhead is acceptable (< 100ms per call)"""
        from fichero.library.sync_wrapper import LibraryManagerSync

        mock_library = Mock()

        async def fast_operation():
            # Very fast operation
            return "quick"

        mock_library.operation = fast_operation

        wrapper = LibraryManagerSync(mock_library)

        # Measure overhead
        start = time.time()
        for _ in range(10):
            wrapper._run_in_thread(mock_library.operation())
        elapsed = time.time() - start

        # 10 calls should take < 1 second (< 100ms per call)
        assert elapsed < 1.0, f"Overhead too high: {elapsed:.2f}s for 10 calls"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
