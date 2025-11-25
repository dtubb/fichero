"""
Async batch processor for transcription with semaphore rate limiting.

Uses asyncio.Semaphore for concurrent request limiting and async/await
for true non-blocking I/O. This achieves 3-5x speedup over ThreadPoolExecutor.

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

# Note: nest_asyncio is not needed with proper event loop lifecycle management
# The run_async_batch function handles event loop creation/cleanup correctly by:
# 1. Detecting existing event loops and using thread-based execution
# 2. Creating new loops in worker threads where no loop exists
# 3. Properly cleaning up resources (including provider cleanup) before closing loops


class AsyncBatchProcessor:
    """
    Async batch processor using semaphores for rate limiting.

    Features:
    - True async/await processing (non-blocking I/O)
    - Semaphore-based rate limiting
    - Progress tracking
    - 3-5x faster than ThreadPoolExecutor

    Usage:
        processor = AsyncBatchProcessor(provider, max_concurrent=15)
        results = await processor.process_batch(image_paths)
    """

    def __init__(
        self,
        provider,
        max_concurrent: int = 15,
        progress_callback: Optional[callable] = None
    ):
        """
        Initialize async batch processor.

        Args:
            provider: Transcription provider with process_image_async() method
            max_concurrent: Maximum concurrent requests (default 15)
            progress_callback: Optional callback for progress updates
        """
        self.provider = provider
        self.max_concurrent = max_concurrent
        self.progress_callback = progress_callback

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

        # Create semaphore for rate limiting
        semaphore = asyncio.Semaphore(self.max_concurrent)

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
        semaphore: asyncio.Semaphore,
        index: int,
        total: int
    ) -> Dict[str, Any]:
        """
        Process a single image with progress tracking.

        Args:
            image_path: Path to image
            semaphore: Semaphore for rate limiting
            index: Current image index
            total: Total images to process

        Returns:
            Result dictionary
        """
        try:
            # Progress callback
            if self.progress_callback:
                self.progress_callback(index, total, image_path.name)

            # Process with semaphore
            result = await self.provider.process_image_async(image_path, semaphore)

            # Add source info
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

    This function handles event loop creation and cleanup, including
    running in a separate thread when called from a GUI with an existing
    event loop.

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
    # In Python 3.10+, get_event_loop() raises RuntimeError if no loop in thread
    loop = None
    has_running_loop = False

    try:
        loop = asyncio.get_running_loop()
        has_running_loop = True
        tool_logger.info("Detected running event loop - using thread-based execution")
    except RuntimeError:
        # No running event loop - this is normal for worker threads and CLI
        tool_logger.info("No running event loop in current thread")
        pass

    # If there's a running loop, we need to use a separate thread
    if has_running_loop:
        import concurrent.futures

        def run_in_thread():
            # Create new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                result = new_loop.run_until_complete(
                    process_batch_async(
                        provider, image_paths, output_folder,
                        max_concurrent, skip_existing, progress_callback
                    )
                )

                # Cleanup provider BEFORE closing loop (if it has async cleanup)
                if cleanup_provider:
                    if hasattr(provider, 'cleanup_async'):
                        try:
                            tool_logger.debug("Running async provider cleanup (in thread)")
                            new_loop.run_until_complete(provider.cleanup_async())
                        except Exception as e:
                            tool_logger.warning(f"Async cleanup failed: {e}, trying sync cleanup")
                            if hasattr(provider, 'cleanup'):
                                provider.cleanup()
                    elif hasattr(provider, 'cleanup'):
                        tool_logger.debug("Running sync provider cleanup (in thread)")
                        provider.cleanup()

                return result
            finally:
                new_loop.close()

        # Execute in thread and wait for result
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()

    # Create new event loop (normal CLI usage or worker thread)
    tool_logger.info("Creating new event loop for this thread")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            process_batch_async(
                provider, image_paths, output_folder,
                max_concurrent, skip_existing, progress_callback
            )
        )

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
    finally:
        loop.close()
