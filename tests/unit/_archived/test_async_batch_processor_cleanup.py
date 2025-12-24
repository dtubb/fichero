"""
Unit tests for async batch processor cleanup functionality.

Tests that provider cleanup happens before event loop closes, preventing
"Event loop is closed" errors.
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, call
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture(scope="module", autouse=True)
def mock_dependencies():
    """Mock heavy dependencies"""
    from unittest.mock import MagicMock

    original_modules = {}
    modules_to_mock = [
        'fichero.config',
        'fichero.config.core',
        'fichero.config.core.settings',
        'fichero.utils',
        'fichero.tools.utils.tool_logger',
    ]

    for module_name in modules_to_mock:
        if module_name in sys.modules:
            original_modules[module_name] = sys.modules[module_name]

        if module_name == 'fichero.tools.utils.tool_logger':
            mock_tool_logger = MagicMock()
            mock_tool_logger.get_tool_logger = lambda x: MagicMock()
            sys.modules[module_name] = mock_tool_logger
        else:
            sys.modules[module_name] = MagicMock()

    yield

    for module_name in modules_to_mock:
        if module_name in original_modules:
            sys.modules[module_name] = original_modules[module_name]
        else:
            sys.modules.pop(module_name, None)


from fichero.tools.transcribe_providers.async_batch_processor import run_async_batch


class TestProviderCleanupWithAsync:
    """Test cleanup for providers with async cleanup methods"""

    def test_cleanup_async_called_before_loop_closes(self):
        """Test that cleanup_async() is called before loop closes"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        # Track when cleanup is called and if loop was still open
        cleanup_state = {"loop_was_open": None}

        async def mock_cleanup_async():
            # Check if loop is still running when cleanup is called
            try:
                loop = asyncio.get_running_loop()
                cleanup_state["loop_was_open"] = not loop.is_closed()
            except RuntimeError:
                cleanup_state["loop_was_open"] = False

        mock_provider.cleanup_async = mock_cleanup_async

        test_paths = [Path("/test/image.jpg")]

        # Act
        result = run_async_batch(
            mock_provider,
            test_paths,
            max_concurrent=5,
            cleanup_provider=True  # Enable cleanup
        )

        # Assert
        assert len(result) == 1
        # Cleanup should have been called while loop was still open
        assert cleanup_state["loop_was_open"] is True

    def test_cleanup_async_called_even_on_success(self):
        """Test that cleanup is called even when processing succeeds"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "success",
            "success": True,
            "details": {}
        })

        cleanup_called = {"called": False}

        async def mock_cleanup_async():
            cleanup_called["called"] = True

        mock_provider.cleanup_async = mock_cleanup_async

        # Act
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is True
        assert cleanup_called["called"] is True


class TestProviderCleanupWithSync:
    """Test cleanup for providers with only sync cleanup methods"""

    def test_sync_cleanup_called_when_no_async(self):
        """Test that sync cleanup() is called when cleanup_async doesn't exist"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        cleanup_called = {"called": False}

        def mock_cleanup():
            cleanup_called["called"] = True

        mock_provider.cleanup = mock_cleanup
        # No cleanup_async attribute

        # Act
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is True
        assert cleanup_called["called"] is True

    def test_no_cleanup_when_no_methods_exist(self):
        """Test that missing cleanup methods don't cause errors"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })
        # No cleanup or cleanup_async methods

        # Act - should not raise
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is True


class TestProviderCleanupDisabled:
    """Test that cleanup can be disabled"""

    def test_cleanup_not_called_when_disabled(self):
        """Test that cleanup is skipped when cleanup_provider=False"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        cleanup_called = {"called": False}

        async def mock_cleanup_async():
            cleanup_called["called"] = True

        mock_provider.cleanup_async = mock_cleanup_async

        # Act
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=False  # Disable cleanup
        )

        # Assert
        assert result[0]["success"] is True
        assert cleanup_called["called"] is False


class TestProviderCleanupOnException:
    """Test cleanup behavior when exceptions occur"""

    def test_cleanup_on_processing_exception(self):
        """Test that cleanup runs even when processing fails"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"

        # Processing fails but cleanup should still run
        async def mock_process_failing(path, semaphore):
            raise RuntimeError("Processing error")

        mock_provider.process_image_async = mock_process_failing

        cleanup_called = {"called": False}

        async def mock_cleanup_async():
            cleanup_called["called"] = True

        mock_provider.cleanup_async = mock_cleanup_async

        # Act
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is False  # Processing failed
        assert "error" in result[0]  # Error captured
        assert cleanup_called["called"] is True  # But cleanup still ran

    def test_fallback_to_sync_cleanup_on_async_failure(self):
        """Test that sync cleanup is tried if async cleanup fails"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        cleanup_calls = {"async": False, "sync": False}

        async def mock_cleanup_async():
            cleanup_calls["async"] = True
            raise RuntimeError("Async cleanup failed")

        def mock_cleanup():
            cleanup_calls["sync"] = True

        mock_provider.cleanup_async = mock_cleanup_async
        mock_provider.cleanup = mock_cleanup

        # Act
        result = run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is True
        assert cleanup_calls["async"] is True  # Async cleanup was attempted
        assert cleanup_calls["sync"] is True  # Sync cleanup was used as fallback


class TestProviderCleanupInThreadMode:
    """Test cleanup when running in thread-based mode (with existing event loop)"""

    @pytest.mark.asyncio
    async def test_cleanup_in_thread_mode(self):
        """Test that cleanup works when run_async_batch uses thread mode"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "thread mode test",
            "success": True,
            "details": {}
        })

        cleanup_called = {"called": False}

        async def mock_cleanup_async():
            cleanup_called["called"] = True

        mock_provider.cleanup_async = mock_cleanup_async

        # Act - call from async context (triggers thread mode)
        loop = asyncio.get_running_loop()
        assert loop.is_running()  # Verify we have a running loop

        result = await asyncio.to_thread(
            run_async_batch,
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert result[0]["success"] is True
        assert cleanup_called["called"] is True


class TestCleanupResourceLeaks:
    """Test that cleanup prevents resource leaks"""

    def test_http_connections_closed(self):
        """Test that HTTP connections are properly closed"""
        # Arrange
        mock_provider = Mock()
        mock_provider.name = "HTTPProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        # Simulate HTTP client that needs closing
        mock_client = Mock()
        mock_client.closed = False

        async def mock_cleanup_async():
            # Simulate closing HTTP connections
            await asyncio.sleep(0.01)
            mock_client.closed = True

        mock_provider.cleanup_async = mock_cleanup_async
        mock_provider.client = mock_client

        # Act
        run_async_batch(
            mock_provider,
            [Path("/test/image.jpg")],
            cleanup_provider=True
        )

        # Assert
        assert mock_client.closed is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
