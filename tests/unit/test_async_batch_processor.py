"""
Unit tests for async batch processor event loop handling.

Tests all three execution scenarios:
1. CLI usage (no event loop)
2. GUI main thread (running event loop)
3. IO worker thread (no event loop in thread)
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
import sys
import asyncio
import threading

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


@pytest.fixture(scope="module", autouse=True)
def mock_dependencies():
    """Mock heavy dependencies for this test module"""
    original_modules = {}
    modules_to_mock = [
        'fichero.config',
        'fichero.config.core',
        'fichero.config.core.settings',
        'fichero.config.core.loader',
        'fichero.utils',
        'fichero.tools.utils.tool_logger',
        'PIL',
        'PIL.Image',
        'openai',
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


# Import after mocking
from fichero.tools.transcribe_providers.async_batch_processor import (
    AsyncBatchProcessor,
    run_async_batch,
    process_batch_async
)


class TestEventLoopHandling:
    """Test event loop handling in different scenarios"""

    def test_cli_usage_no_event_loop(self):
        """Test normal CLI usage where no event loop exists"""
        # Create mock provider
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        # Test CLI usage (no existing event loop)
        test_paths = [Path("/test/image.jpg")]

        # Use run_async_batch which creates its own event loop
        result = run_async_batch(
            mock_provider,
            test_paths,
            max_concurrent=5
        )

        assert len(result) == 1
        assert result[0]['success'] is True

    def test_worker_thread_no_event_loop(self):
        """Test IO worker thread scenario where thread has no event loop"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "worker test",
            "success": True,
            "details": {}
        })

        test_paths = [Path("/test/worker_image.jpg")]

        # Run in a separate thread (simulating IO worker)
        result_holder = []

        def worker_function():
            # In worker thread, no event loop exists initially
            result = run_async_batch(
                mock_provider,
                test_paths,
                max_concurrent=5
            )
            result_holder.append(result)

        worker_thread = threading.Thread(target=worker_function)
        worker_thread.start()
        worker_thread.join(timeout=5)

        assert len(result_holder) == 1
        assert len(result_holder[0]) == 1
        assert result_holder[0][0]['success'] is True

    @pytest.mark.asyncio
    async def test_running_event_loop_detected(self):
        """Test detection of running event loop (GUI scenario)"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "gui test",
            "success": True,
            "details": {}
        })

        test_paths = [Path("/test/gui_image.jpg")]

        # At this point, we have a running event loop (managed by pytest-asyncio)
        loop = asyncio.get_running_loop()
        assert loop.is_running()

        # run_async_batch should detect this and use thread-based execution
        result = await asyncio.to_thread(
            run_async_batch,
            mock_provider,
            test_paths,
            max_concurrent=5
        )

        assert len(result) == 1
        assert result[0]['success'] is True


class TestAsyncBatchProcessor:
    """Test AsyncBatchProcessor class"""

    @pytest.mark.asyncio
    async def test_processor_initialization(self):
        """Test AsyncBatchProcessor initialization"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock()

        processor = AsyncBatchProcessor(
            provider=mock_provider,
            max_concurrent=10
        )

        assert processor.provider == mock_provider
        assert processor.max_concurrent == 10

    @pytest.mark.asyncio
    async def test_provider_without_async_support(self):
        """Test that provider without async support raises error"""
        mock_provider = Mock(spec=['name'])  # Only has name, no process_image_async
        mock_provider.name = "SyncOnlyProvider"

        with pytest.raises(ValueError, match="does not support async processing"):
            AsyncBatchProcessor(provider=mock_provider)

    @pytest.mark.asyncio
    async def test_process_batch_with_skip_existing(self):
        """Test batch processing with skip_existing"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        processor = AsyncBatchProcessor(mock_provider, max_concurrent=5)

        # Create test paths
        test_paths = [
            Path("/test/image1.jpg"),
            Path("/test/image2.jpg")
        ]

        # Create mock output folder with existing file
        output_folder = Path("/test/output")

        with patch.object(Path, 'exists') as mock_exists:
            # First image exists, second doesn't
            mock_exists.side_effect = lambda: False

            results = await processor.process_batch(
                test_paths,
                output_folder=output_folder,
                skip_existing=True
            )

            # Both should be processed (none exist in our mock)
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_process_batch_handles_exceptions(self):
        """Test that batch processing handles exceptions gracefully"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"

        # First succeeds, second fails
        async def mock_process(path, semaphore):
            if "fail" in str(path):
                raise ValueError("Test error")
            return {
                "text": "success",
                "success": True,
                "details": {}
            }

        mock_provider.process_image_async = mock_process

        processor = AsyncBatchProcessor(mock_provider, max_concurrent=5)

        test_paths = [
            Path("/test/success.jpg"),
            Path("/test/fail.jpg")
        ]

        results = await processor.process_batch(test_paths)

        assert len(results) == 2
        assert results[0]['success'] is True
        assert results[1]['success'] is False
        assert "error" in results[1]


class TestConcurrencyControl:
    """Test semaphore-based concurrency control"""

    @pytest.mark.asyncio
    async def test_max_concurrent_limit(self):
        """Test that max_concurrent limits parallel requests"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"

        # Track concurrent calls with a lock
        concurrent_calls = 0
        max_concurrent_seen = 0
        lock = asyncio.Lock()

        async def mock_process(path, semaphore):
            nonlocal concurrent_calls, max_concurrent_seen

            # Acquire semaphore to enforce concurrency limit
            async with semaphore:
                async with lock:
                    concurrent_calls += 1
                    max_concurrent_seen = max(max_concurrent_seen, concurrent_calls)

                # Do work while holding semaphore
                await asyncio.sleep(0.01)

                async with lock:
                    concurrent_calls -= 1

            return {
                "text": "test",
                "success": True,
                "details": {}
            }

        mock_provider.process_image_async = mock_process

        processor = AsyncBatchProcessor(mock_provider, max_concurrent=3)

        # Create 10 images
        test_paths = [Path(f"/test/image{i}.jpg") for i in range(10)]

        results = await processor.process_batch(test_paths)

        # All processed
        assert len(results) == 10
        # But never more than 3 concurrent (because semaphore limits it)
        assert max_concurrent_seen <= 3, f"Expected max 3 concurrent, but saw {max_concurrent_seen}"


class TestProgressCallback:
    """Test progress callback functionality"""

    @pytest.mark.asyncio
    async def test_progress_callback_called(self):
        """Test that progress callback is called for each image"""
        mock_provider = Mock()
        mock_provider.name = "TestProvider"
        mock_provider.process_image_async = AsyncMock(return_value={
            "text": "test",
            "success": True,
            "details": {}
        })

        callback_calls = []

        def progress_callback(index, total, filename):
            callback_calls.append((index, total, filename))

        processor = AsyncBatchProcessor(
            mock_provider,
            max_concurrent=5,
            progress_callback=progress_callback
        )

        test_paths = [
            Path("/test/image1.jpg"),
            Path("/test/image2.jpg"),
            Path("/test/image3.jpg")
        ]

        await processor.process_batch(test_paths)

        # Callback should be called for each image
        assert len(callback_calls) == 3
        assert callback_calls[0] == (0, 3, "image1.jpg")
        assert callback_calls[1] == (1, 3, "image2.jpg")
        assert callback_calls[2] == (2, 3, "image3.jpg")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
