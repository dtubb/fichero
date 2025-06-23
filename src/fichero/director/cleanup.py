import asyncio
import gc
import socket
import threading
import warnings
import logging

def cleanup_all_resources():
    """Comprehensive cleanup of all resources including network connections and event loops."""
    logger = logging.getLogger("fichero.director.cleanup")
    logger.info("Starting comprehensive resource cleanup...")
    
    # Temporarily suppress ResourceWarnings during cleanup
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        
        # Try multiple approaches to get and close event loops
        loops_to_close = []
        # Approach 1: Get running loop
        try:
            loop = asyncio.get_running_loop()
            loops_to_close.append(("running", loop))
            logger.info("Found running event loop")
        except RuntimeError:
            logger.info("No running event loop found")
        # Approach 2: Get current loop
        try:
            loop = asyncio.get_event_loop()
            if loop and not loop.is_closed():
                loops_to_close.append(("current", loop))
                logger.info("Found current event loop")
        except RuntimeError:
            logger.info("No current event loop found")
        # Approach 3: Get from policy
        try:
            policy = asyncio.get_event_loop_policy()
            if hasattr(policy, '_local') and hasattr(policy._local, '_loop'):
                cached_loop = policy._local._loop
                if cached_loop and not cached_loop.is_closed():
                    loops_to_close.append(("cached", cached_loop))
                    logger.info("Found cached event loop")
        except Exception as e:
            logger.warning(f"Error getting policy loop: {e}")
        # Close all found loops
        for loop_type, loop in loops_to_close:
            try:
                logger.info(f"Cleaning up {loop_type} event loop...")
                # Cancel all pending tasks
                pending_tasks = asyncio.all_tasks(loop)
                if pending_tasks:
                    logger.info(f"Cancelling {len(pending_tasks)} pending asyncio tasks...")
                    for task in pending_tasks:
                        if not task.done():
                            task.cancel()
                    try:
                        loop.run_until_complete(asyncio.wait(pending_tasks, timeout=1.0))
                    except Exception as e:
                        logger.warning(f"Error waiting for task cancellation: {e}")
                # Close all transports in the loop
                try:
                    if hasattr(loop, '_selector') and hasattr(loop._selector, '_fd_to_key'):
                        for fd, key in list(loop._selector._fd_to_key.items()):
                            if hasattr(key, 'fileobj') and hasattr(key.fileobj, 'close'):
                                try:
                                    key.fileobj.close()
                                    logger.info(f"Closed transport fd={fd}")
                                except Exception as e:
                                    logger.warning(f"Error closing transport fd={fd}: {e}")
                except Exception as e:
                    logger.warning(f"Error closing transports: {e}")
                # Close the loop
                if not loop.is_closed():
                    logger.info(f"Closing {loop_type} event loop...")
                    loop.close()
                    logger.info(f"Successfully closed {loop_type} event loop")
                else:
                    logger.info(f"{loop_type} event loop was already closed")
            except Exception as e:
                logger.warning(f"Error cleaning up {loop_type} event loop: {e}")
        # Clean up any remaining network connections
        try:
            for thread in threading.enumerate():
                if hasattr(thread, '_local') and hasattr(thread._local, '__dict__'):
                    for attr_name, attr_value in list(thread._local.__dict__.items()):
                        if hasattr(attr_value, 'close') and callable(attr_value.close):
                            try:
                                attr_value.close()
                                logger.info(f"Closed resource in thread {thread.name}: {attr_name}")
                            except Exception:
                                pass
        except Exception as e:
            logger.warning(f"Error during thread cleanup: {e}")
        # Force garbage collection to clean up any remaining resources
        gc.collect()
        logger.info("Comprehensive resource cleanup completed") 