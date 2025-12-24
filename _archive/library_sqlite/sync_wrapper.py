"""
Synchronous wrapper for LibraryManager async operations.

This wrapper provides a synchronous facade for UI/CLI code to call async library
operations without event loop conflicts. It runs async operations in an isolated
thread with its own event loop.

Usage:
    library_sync = LibraryManagerSync(library_manager)
    collection = library_sync.get_collection(collection_id)  # Sync call
"""

import asyncio
import concurrent.futures
from typing import Optional, List, Dict, Any
from pathlib import Path


class LibraryManagerSync:
    """
    Synchronous facade for LibraryManager async operations.

    This wrapper runs async library operations in an isolated thread with its own
    event loop, preventing conflicts with the main thread's event loop (if any).

    Use this wrapper when calling library operations from:
    - Toga GUI callbacks (main thread)
    - CLI commands (no event loop)
    - Synchronous code that can't use await

    Example:
        library_sync = LibraryManagerSync(library_manager)
        collection = library_sync.get_collection("col-123")
        items = library_sync.get_collection_items("col-123")
    """

    def __init__(self, library_manager):
        """
        Initialize sync wrapper with a LibraryManager instance.

        Args:
            library_manager: The async LibraryManager instance to wrap
        """
        self.library = library_manager

    def _run_in_thread(self, coro):
        """
        Run an async coroutine in an isolated thread with its own event loop.

        This prevents event loop conflicts by:
        1. Creating a new thread
        2. Creating a new event loop in that thread
        3. Running the coroutine to completion
        4. Closing the loop
        5. Joining the thread

        Args:
            coro: The coroutine to run

        Returns:
            The result of the coroutine

        Raises:
            Any exception raised by the coroutine
        """
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, coro)
            return future.result()

    # Collection operations

    def get_collection(self, collection_id: str):
        """Get collection by ID (sync wrapper)"""
        return self._run_in_thread(self.library.get_collection(collection_id))

    def get_all_collections(self):
        """Get all collections (sync wrapper)"""
        return self._run_in_thread(self.library.get_all_collections())

    def add_collection(self, name: str, collection_type: str, source_path: Optional[Path] = None):
        """Add new collection (sync wrapper)"""
        return self._run_in_thread(
            self.library.add_collection(name, collection_type, source_path)
        )

    def update_collection(self, collection):
        """Update collection (sync wrapper)"""
        return self._run_in_thread(self.library.update_collection(collection))

    def delete_collection(self, collection_id: str):
        """Delete collection (sync wrapper)"""
        return self._run_in_thread(self.library.delete_collection(collection_id))

    # Item operations

    def get_item(self, item_id: str):
        """Get item by ID (sync wrapper)"""
        return self._run_in_thread(self.library.get_item(item_id))

    def get_collection_items(self, collection_id: str):
        """Get all items in a collection (sync wrapper)"""
        return self._run_in_thread(self.library.get_collection_items(collection_id))

    def add_item(self, collection_id: str, item_type: str, source_path: Path, **kwargs):
        """Add item to collection (sync wrapper)"""
        return self._run_in_thread(
            self.library.add_item(collection_id, item_type, source_path, **kwargs)
        )

    def update_item(self, item):
        """Update item (sync wrapper)"""
        return self._run_in_thread(self.library.update_item(item))

    def delete_item(self, item_id: str):
        """Delete item (sync wrapper)"""
        return self._run_in_thread(self.library.delete_item(item_id))

    # Metadata operations

    def get_item_metadata(self, item_id: str):
        """Get metadata for item (sync wrapper)"""
        return self._run_in_thread(self.library.get_item_metadata(item_id))

    def add_extracted_metadata(self, metadata):
        """Add extracted metadata (sync wrapper)"""
        return self._run_in_thread(self.library.add_extracted_metadata(metadata))

    # Processing operations

    def process_items(self, collection_id: str, item_ids: List[str], plan_name: str,
                     workflow_name: str, **kwargs):
        """Process items (sync wrapper)"""
        return self._run_in_thread(
            self.library.process_items(collection_id, item_ids, plan_name,
                                      workflow_name, **kwargs)
        )

    # URL operations (these benefit from async, but wrapper makes them sync)

    def download_url_item(self, item_id: str):
        """Download URL item (sync wrapper)"""
        return self._run_in_thread(self.library.download_url_item(item_id))

    def download_collection_urls(self, collection_id: str, max_concurrent: int = 10):
        """Download all URLs in collection (sync wrapper)"""
        return self._run_in_thread(
            self.library.download_collection_urls(collection_id, max_concurrent)
        )
