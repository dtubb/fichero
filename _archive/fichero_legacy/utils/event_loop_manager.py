"""
Centralized event loop management for UI async operations.

This module provides a singleton EventLoopManager that maintains a single background
event loop for UI async operations. This is more efficient than creating a new
thread/loop for each operation (as LibraryManagerSync does), but requires careful
lifecycle management.

Use EventLoopManager when:
- You need to run many async operations from UI
- You want better performance than thread-per-operation
- You can guarantee proper shutdown

Use LibraryManagerSync when:
- You need simple one-off async operations
- You don't want to manage loop lifecycle
- Slight overhead is acceptable

Example:
    # At app startup
    EventLoopManager.start()

    # During app lifecycle
    result = EventLoopManager.run_async(some_async_function())

    # At app shutdown
    EventLoopManager.shutdown()
"""

import asyncio
import threading
import logging
from typing import Optional, Coroutine, Any

logger = logging.getLogger(__name__)


class EventLoopManager:
    """
    Manages a single background event loop for UI async operations.

    This is a singleton class that creates and manages a dedicated event loop
    running in a background thread. All async operations are submitted to this
    loop via run_async().

    Thread Safety:
        - start() and shutdown() should only be called from main thread
        - run_async() is thread-safe and can be called from any thread
        - The background loop runs in its own dedicated thread

    Lifecycle:
        1. start() - Creates background thread with event loop
        2. run_async() - Submit coroutines to run in background loop
        3. shutdown() - Stops loop and joins thread

    Note: This is more efficient than LibraryManagerSync but requires proper
    lifecycle management. For simple use cases, LibraryManagerSync may be better.
    """

    _loop: Optional[asyncio.AbstractEventLoop] = None
    _thread: Optional[threading.Thread] = None
    _started: bool = False
    _shutdown: bool = False
    _lock = threading.Lock()

    @classmethod
    def start(cls):
        """
        Start the background event loop thread.

        This should be called once at application startup, before any
        async operations are submitted.

        Raises:
            RuntimeError: If already started or shut down

        Example:
            EventLoopManager.start()
        """
        with cls._lock:
            if cls._shutdown:
                raise RuntimeError("EventLoopManager has been shut down and cannot be restarted")

            if cls._started:
                logger.warning("EventLoopManager already started")
                return

            logger.info("Starting EventLoopManager background thread")

            # Create new event loop
            cls._loop = asyncio.new_event_loop()

            # Create and start thread
            cls._thread = threading.Thread(
                target=cls._run_loop,
                name="EventLoopManager",
                daemon=True  # Don't prevent program exit
            )
            cls._thread.start()

            cls._started = True
            logger.info("EventLoopManager started successfully")

    @classmethod
    def _run_loop(cls):
        """Run the event loop in the background thread (internal use only)"""
        asyncio.set_event_loop(cls._loop)
        try:
            cls._loop.run_forever()
        except Exception as e:
            logger.error(f"EventLoopManager loop error: {e}")
        finally:
            logger.info("EventLoopManager loop stopped")

    @classmethod
    def run_async(cls, coro: Coroutine) -> Any:
        """
        Run an async coroutine in the managed event loop.

        This method is thread-safe and will block until the coroutine completes.

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine

        Raises:
            RuntimeError: If EventLoopManager not started
            Any exception raised by the coroutine

        Example:
            result = EventLoopManager.run_async(library.get_collection(id))
        """
        if not cls._started or cls._shutdown:
            raise RuntimeError("EventLoopManager not started or already shut down")

        if cls._loop is None:
            raise RuntimeError("Event loop not initialized")

        # Submit coroutine to background loop and wait for result
        future = asyncio.run_coroutine_threadsafe(coro, cls._loop)

        try:
            # Wait for result (blocks current thread)
            return future.result()
        except Exception as e:
            logger.error(f"Error running async operation: {e}")
            raise

    @classmethod
    def run_async_no_wait(cls, coro: Coroutine) -> asyncio.Future:
        """
        Run an async coroutine without waiting for result.

        This is useful for fire-and-forget operations. The returned Future
        can be used to check status or retrieve result later.

        Args:
            coro: The coroutine to run

        Returns:
            A Future representing the running coroutine

        Raises:
            RuntimeError: If EventLoopManager not started

        Example:
            future = EventLoopManager.run_async_no_wait(background_task())
            # Do other work...
            result = future.result()  # Wait for it later if needed
        """
        if not cls._started or cls._shutdown:
            raise RuntimeError("EventLoopManager not started or already shut down")

        if cls._loop is None:
            raise RuntimeError("Event loop not initialized")

        return asyncio.run_coroutine_threadsafe(coro, cls._loop)

    @classmethod
    def shutdown(cls, timeout: float = 5.0):
        """
        Shut down the background event loop and thread.

        This should be called once at application shutdown. It will:
        1. Stop the event loop
        2. Cancel any pending tasks
        3. Close the loop
        4. Join the background thread (with timeout)

        Args:
            timeout: Maximum seconds to wait for thread to join

        Example:
            EventLoopManager.shutdown()
        """
        with cls._lock:
            if cls._shutdown:
                logger.warning("EventLoopManager already shut down")
                return

            if not cls._started:
                logger.warning("EventLoopManager not started, nothing to shut down")
                return

            logger.info("Shutting down EventLoopManager")

            if cls._loop and not cls._loop.is_closed():
                # Stop the loop (will cause run_forever() to return)
                cls._loop.call_soon_threadsafe(cls._loop.stop)

                # Wait for thread to finish
                if cls._thread and cls._thread.is_alive():
                    cls._thread.join(timeout=timeout)

                    if cls._thread.is_alive():
                        logger.warning(
                            f"EventLoopManager thread did not stop within {timeout}s"
                        )

                # Cancel pending tasks
                try:
                    pending = asyncio.all_tasks(cls._loop)
                    for task in pending:
                        task.cancel()
                except Exception as e:
                    logger.warning(f"Error canceling pending tasks: {e}")

                # Close the loop
                cls._loop.close()

            cls._loop = None
            cls._thread = None
            cls._started = False
            cls._shutdown = True

            logger.info("EventLoopManager shut down successfully")

    @classmethod
    def is_started(cls) -> bool:
        """Check if EventLoopManager is started and ready to use"""
        return cls._started and not cls._shutdown and cls._loop is not None

    @classmethod
    def reset(cls):
        """
        Reset the EventLoopManager state (for testing only).

        This should NOT be used in production code. It's only for test
        cases that need to restart the EventLoopManager.
        """
        if cls._started and not cls._shutdown:
            cls.shutdown()

        cls._loop = None
        cls._thread = None
        cls._started = False
        cls._shutdown = False
