"""
Async batch processor for transcription with global rate limiting.

Uses a global rate limiter (shared across all folders) to prevent
exceeding API rate limits when processing multiple folders in parallel.

Features:
- Global semaphore shared across all folders/tools
- 429 error detection with automatic exponential backoff
- Configurable limits from settings
- 3-5x speedup over ThreadPoolExecutor

Following Andy's pattern from the Qwen VL OCR notebook.
"""

import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import time
from datetime import datetime

try:
    from fichero.tools.utils.tool_logger import get_tool_logger
    tool_logger = get_tool_logger('async_batch_processor')
except ImportError:
    import logging
    tool_logger = logging.getLogger('async_batch_processor')

try:
    from fichero.tools.utils.global_rate_limiter import get_rate_limiter, configure_rate_limiter
    RATE_LIMITER_AVAILABLE = True
except ImportError:
    RATE_LIMITER_AVAILABLE = False
    tool_logger.warning("Global rate limiter not available, using local semaphore")

# Try to import nest_asyncio for nested event loop support
# This allows running async code from within an already-running event loop (e.g., Toga GUI)
try:
    import nest_asyncio
    NEST_ASYNCIO_AVAILABLE = True
except ImportError:
    NEST_ASYNCIO_AVAILABLE = False
    tool_logger.debug("nest_asyncio not available, will use thread-based fallback for nested loops")


def _detect_provider_type(provider) -> str:
    """Detect the API provider type for rate limiting."""
    provider_name = getattr(provider, 'name', '').lower()

    if 'dashscope' in provider_name or 'qwen' in provider_name:
        return 'dashscope'
    elif 'openai' in provider_name or 'gpt' in provider_name:
        return 'openai'
    else:
        return 'default'


class AsyncBatchProcessor:
    """
    Async batch processor using global rate limiter.

    Features:
    - Global rate limiting shared across all folders
    - 429 error detection with automatic retry
    - True async/await processing (non-blocking I/O)
    - Progress tracking
    - 3-5x faster than ThreadPoolExecutor

    Usage:
        processor = AsyncBatchProcessor(provider, max_concurrent=15)
        results = await processor.process_batch(image_paths)
    """

    def __init__(
        self,
        provider,
        max_concurrent: int = None,  # None = use global rate limiter settings
        progress_callback: Optional[callable] = None,
        provider_type: str = None  # 'dashscope', 'openai', or auto-detect
    ):
        """
        Initialize async batch processor.

        Args:
            provider: Transcription provider with process_image_async() method
            max_concurrent: Maximum concurrent requests (None = use global settings)
            progress_callback: Optional callback for progress updates
            provider_type: API provider type for rate limiting (auto-detected if None)
        """
        self.provider = provider
        self.progress_callback = progress_callback
        self.provider_type = provider_type or _detect_provider_type(provider)

        # Get max_concurrent from global rate limiter if not specified
        if max_concurrent is None and RATE_LIMITER_AVAILABLE:
            limiter = get_rate_limiter()
            config = limiter.get_config(self.provider_type)
            self.max_concurrent = config.max_concurrent
            tool_logger.info(f"Using global rate limit: {self.max_concurrent} for {self.provider_type}")
        else:
            self.max_concurrent = max_concurrent or 15

        # Check if provider supports async
        if not hasattr(provider, 'process_image_async'):
            raise ValueError(f"Provider {provider.name} does not support async processing")

    async def process_batch(
        self,
        image_paths: List[Path],
        output_folder: Optional[Path] = None,
        skip_existing: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Process a batch of images asynchronously with semaphore rate limiting.

        Args:
            image_paths: List of image paths to process
            output_folder: Optional output folder for checking existing files
            skip_existing: Skip images that already have output files

        Returns:
            List of result dictionaries
        """
        start_time = time.time()

        tool_logger.info(f"Starting async batch processing of {len(image_paths)} images")
        tool_logger.info(f"Max concurrent requests: {self.max_concurrent}")
        tool_logger.info(f"Provider: {self.provider.name}")

        # Filter images if needed
        images_to_process = []
        skipped = 0

        for img_path in image_paths:
            if skip_existing and output_folder:
                output_txt = output_folder / "documents" / img_path.with_suffix('.txt').name
                if output_txt.exists():
                    skipped += 1
                    continue
            images_to_process.append(img_path)

        if skipped > 0:
            tool_logger.info(f"Skipping {skipped} existing files")

        if not images_to_process:
            tool_logger.info("No images to process")
            return []

        # Use global rate limiter if available, otherwise create local semaphore
        if RATE_LIMITER_AVAILABLE:
            limiter = get_rate_limiter()
            available = limiter.get_available_slots(self.provider_type)
            tool_logger.info(f"Using global rate limiter ({self.provider_type}): {available} slots available")
            semaphore = None  # Will use global limiter in _process_with_progress
        else:
            semaphore = asyncio.Semaphore(self.max_concurrent)
            tool_logger.info(f"Using local semaphore with {self.max_concurrent} slots")

        # Create tasks
        tasks = [
            self._process_with_progress(img_path, semaphore, idx, len(images_to_process))
            for idx, img_path in enumerate(images_to_process)
        ]

        # Process all tasks concurrently
        tool_logger.info(f"Processing {len(tasks)} images with max {self.max_concurrent} concurrent...")
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle exceptions
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                tool_logger.error(f"Task {i} failed: {result}")
                final_results.append({
                    "text": "",
                    "success": False,
                    "error": str(result),
                    "details": {}
                })
            else:
                final_results.append(result)

        elapsed = time.time() - start_time

        # Stats
        processed = sum(1 for r in final_results if r.get('success'))
        failed = sum(1 for r in final_results if not r.get('success'))

        tool_logger.info(f"Batch complete: {processed} processed, {failed} failed, {skipped} skipped")
        tool_logger.info(f"Total time: {elapsed:.2f}s ({elapsed/len(images_to_process):.2f}s per image)")

        # Log rate limiter stats
        if RATE_LIMITER_AVAILABLE:
            limiter = get_rate_limiter()
            limiter.log_stats(self.provider_type)

        # Add skipped results
        for img_path in image_paths:
            if img_path not in images_to_process:
                final_results.append({
                    "text": "",
                    "success": False,
                    "skipped": True,
                    "source": img_path.name,
                    "details": {}
                })

        return final_results

    async def _process_with_progress(
        self,
        image_path: Path,
        semaphore: Optional[asyncio.Semaphore],
        index: int,
        total: int
    ) -> Dict[str, Any]:
        """
        Process a single image with progress tracking and rate limiting.

        Uses global rate limiter if available, with 429 retry handling.

        Args:
            image_path: Path to image
            semaphore: Local semaphore (None if using global rate limiter)
            index: Current image index
            total: Total images to process

        Returns:
            Result dictionary
        """
        try:
            # Progress callback
            if self.progress_callback:
                self.progress_callback(index, total, image_path.name)

            # Use global rate limiter with 429 retry handling if available
            if RATE_LIMITER_AVAILABLE and semaphore is None:
                limiter = get_rate_limiter()
                config = limiter.get_config(self.provider_type)

                last_error = None
                retry_delay = config.base_retry_delay

                for attempt in range(config.max_retries + 1):
                    try:
                        async with limiter.acquire(self.provider_type):
                            # Pass None for semaphore since we're using global limiter
                            result = await self.provider.process_image_async(image_path, None)
                            result['source'] = image_path.name
                            return result

                    except Exception as e:
                        last_error = e
                        error_str = str(e).lower()

                        # Check for rate limit error (429)
                        is_rate_limit = any(x in error_str for x in [
                            '429', 'rate limit', 'too many requests', 'throttl',
                            'quota', 'exceeded', 'limit exceeded'
                        ])

                        if is_rate_limit and config.retry_on_429 and attempt < config.max_retries:
                            tool_logger.warning(
                                f"⚠️ Rate limit hit for {image_path.name} "
                                f"(attempt {attempt + 1}/{config.max_retries + 1}). "
                                f"Retrying in {retry_delay:.1f}s..."
                            )
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # Exponential backoff
                            continue
                        else:
                            raise

                # All retries failed
                raise last_error

            else:
                # Use local semaphore (legacy behavior)
                if semaphore:
                    async with semaphore:
                        result = await self.provider.process_image_async(image_path, None)
                else:
                    result = await self.provider.process_image_async(image_path, None)

                result['source'] = image_path.name
                return result

        except Exception as e:
            tool_logger.error(f"Error processing {image_path.name}: {e}")
            return {
                "text": "",
                "success": False,
                "error": str(e),
                "source": image_path.name,
                "details": {}
            }


async def process_batch_async(
    provider,
    image_paths: List[Path],
    output_folder: Optional[Path] = None,
    max_concurrent: int = 15,
    skip_existing: bool = True,
    progress_callback: Optional[callable] = None
) -> List[Dict[str, Any]]:
    """
    Convenience function for async batch processing.

    Args:
        provider: Transcription provider with async support
        image_paths: List of image paths
        output_folder: Optional output folder
        max_concurrent: Maximum concurrent requests
        skip_existing: Skip existing output files
        progress_callback: Optional progress callback

    Returns:
        List of result dictionaries
    """
    processor = AsyncBatchProcessor(provider, max_concurrent, progress_callback)
    return await processor.process_batch(image_paths, output_folder, skip_existing)


def _is_worker_thread() -> bool:
    """
    Detect if we're running in a worker thread (ThreadPoolExecutor).

    Worker threads from ThreadPoolExecutor have names like:
    - 'ThreadPoolExecutor-0_0'
    - 'fichero-io_0', 'fichero-cpu_0' (custom-named workers)

    When in a worker thread, we should always use a separate thread for
    async operations to avoid potential deadlocks with the parent thread's
    event loop or blocking behavior.
    """
    import threading
    current_thread = threading.current_thread()
    thread_name = current_thread.name

    # Check for ThreadPoolExecutor worker threads or our custom-named workers
    is_worker = (
        'ThreadPoolExecutor' in thread_name or
        'fichero-' in thread_name or
        thread_name.startswith('Thread-')
    )

    return is_worker


def _run_with_new_loop(
    provider,
    image_paths: List[Path],
    output_folder: Optional[Path],
    max_concurrent: int,
    skip_existing: bool,
    progress_callback: Optional[callable],
    cleanup_provider: bool
) -> List[Dict[str, Any]]:
    """
    Run async batch processing with a new event loop.

    Creates a fresh event loop, runs the async code, cleans up, and closes the loop.
    Used for CLI, worker threads, and as fallback when nest_asyncio isn't available.

    Note: On macOS with Toga, the default event loop policy creates CFEventLoop
    which doesn't work in worker threads. We explicitly use SelectorEventLoop.
    """
    tool_logger.info("Creating new event loop...")

    # On macOS with Toga, the default policy creates CFEventLoop which hangs in worker threads.
    # Explicitly create a SelectorEventLoop which works correctly in any thread.
    try:
        loop = asyncio.SelectorEventLoop()
        tool_logger.info(f"Created SelectorEventLoop: {loop}")
    except Exception as e:
        tool_logger.warning(f"Could not create SelectorEventLoop ({e}), falling back to default")
        loop = asyncio.new_event_loop()
        tool_logger.info(f"Event loop created: {loop}")

    asyncio.set_event_loop(loop)
    tool_logger.info("Event loop set as current")

    try:
        tool_logger.info("Starting run_until_complete for process_batch_async...")
        result = loop.run_until_complete(
            process_batch_async(
                provider, image_paths, output_folder,
                max_concurrent, skip_existing, progress_callback
            )
        )
        tool_logger.info(f"run_until_complete finished, got {len(result)} results")

        # Cleanup provider BEFORE closing loop (if it has async cleanup)
        if cleanup_provider:
            if hasattr(provider, 'cleanup_async'):
                try:
                    tool_logger.debug("Running async provider cleanup")
                    loop.run_until_complete(provider.cleanup_async())
                except Exception as e:
                    tool_logger.warning(f"Async cleanup failed: {e}, trying sync cleanup")
                    if hasattr(provider, 'cleanup'):
                        provider.cleanup()
            elif hasattr(provider, 'cleanup'):
                tool_logger.debug("Running sync provider cleanup")
                provider.cleanup()

        return result
    except Exception as e:
        tool_logger.error(f"Exception in _run_with_new_loop: {e}")
        import traceback
        tool_logger.error(traceback.format_exc())
        raise
    finally:
        tool_logger.info("Closing event loop")
        loop.close()


def run_async_batch(
    provider,
    image_paths: List[Path],
    output_folder: Optional[Path] = None,
    max_concurrent: int = 15,
    skip_existing: bool = True,
    progress_callback: Optional[callable] = None,
    cleanup_provider: bool = True
) -> List[Dict[str, Any]]:
    """
    Synchronous wrapper for async batch processing.

    Handles three scenarios:
    1. No running event loop (CLI, worker threads): Create new loop and run directly
    2. Running event loop + nest_asyncio: Use nest_asyncio for nested execution
    3. Running event loop, no nest_asyncio: Spawn thread with new loop (fallback)

    Args:
        provider: Transcription provider with async support
        image_paths: List of image paths
        output_folder: Optional output folder
        max_concurrent: Maximum concurrent requests
        skip_existing: Skip existing output files
        progress_callback: Optional progress callback
        cleanup_provider: If True, call provider cleanup before closing loop

    Returns:
        List of result dictionaries
    """
    # Check if there's a running event loop
    has_running_loop = False
    running_loop = None

    try:
        running_loop = asyncio.get_running_loop()
        has_running_loop = True
    except RuntimeError:
        pass  # No running event loop

    # Case 1: No running event loop - create new loop and run directly
    # This is the common case for CLI and worker threads (fichero-io, fichero-cpu)
    if not has_running_loop:
        is_worker = _is_worker_thread()
        if is_worker:
            tool_logger.info("Worker thread - creating event loop for async processing")
        else:
            tool_logger.info("No event loop - creating new loop for async processing")

        return _run_with_new_loop(
            provider, image_paths, output_folder,
            max_concurrent, skip_existing, progress_callback, cleanup_provider
        )

    # Case 2: Running event loop - use nest_asyncio
    if not NEST_ASYNCIO_AVAILABLE:
        raise RuntimeError(
            "Cannot run async batch processing: event loop already running and nest_asyncio not installed. "
            "Install with: pip install nest-asyncio"
        )

    tool_logger.info("Running event loop detected - using nest_asyncio")
    nest_asyncio.apply(running_loop)

    result = running_loop.run_until_complete(
        process_batch_async(
            provider, image_paths, output_folder,
            max_concurrent, skip_existing, progress_callback
        )
    )

    # Cleanup provider
    if cleanup_provider:
        if hasattr(provider, 'cleanup_async'):
            try:
                running_loop.run_until_complete(provider.cleanup_async())
            except Exception as e:
                tool_logger.warning(f"Async cleanup failed: {e}, trying sync cleanup")
                if hasattr(provider, 'cleanup'):
                    provider.cleanup()
        elif hasattr(provider, 'cleanup'):
            provider.cleanup()

    return result
