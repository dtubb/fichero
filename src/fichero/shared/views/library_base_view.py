"""
Library Base View

Shared base class for library views that unifies desktop and mobile library loading patterns.
Provides common collection loading, display refresh, and event handling logic.
"""

import logging
import asyncio
import threading
from typing import List, Dict, Any, Optional, Callable
from abc import ABC, abstractmethod

from fichero.shared.views.base_view import BaseView

logger = logging.getLogger(__name__)


class LibraryBaseView(BaseView, ABC):
    """Base class for library views with unified loading patterns"""

    def __init__(self, app, is_mobile: bool):
        """Initialize library base view"""
        super().__init__(app, is_mobile)

        # Common library attributes
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None
        self.is_edit_mode: bool = False

        # Library service access
        self.library_service = getattr(app, 'library_service', None)
        if not self.library_service:
            logger.warning("No library service found in app")

        # Collection selection callback
        self.on_collection_selected: Optional[Callable] = None

        logger.debug(f"LibraryBaseView initialized (mobile={is_mobile})")

    def load_collections_unified(self) -> None:
        """Unified collection loading that works for both desktop and mobile"""
        try:
            logger.debug("Starting unified collection loading...")

            # Try async first (mobile pattern)
            try:
                asyncio.create_task(self._load_collections_async())
                logger.debug("Created async task for collection loading")
            except RuntimeError:
                # No event loop running, use thread-safe approach (desktop pattern)
                logger.debug("Using thread for collection loading...")
                threading.Thread(target=self._load_collections_sync, daemon=True).start()
                logger.debug("Started background thread for collection loading")

        except Exception as e:
            logger.error(f"Failed to start collection loading: {e}")
            self._handle_loading_error(e)

    async def _load_collections_async(self) -> None:
        """Async collection loading (mobile pattern)"""
        try:
            logger.debug("Loading collections async...")

            if not self.library_service:
                logger.warning("No library service available for async loading")
                return

            collections = await self.library_service.get_collections_for_ui()
            logger.debug(f"Loaded {len(collections)} collections (async)")

            # Update collections and trigger refresh
            self._update_collections(collections)

        except Exception as e:
            logger.error(f"Failed to load collections async: {e}")
            self._handle_loading_error(e)

    def _load_collections_sync(self) -> None:
        """Sync collection loading in separate thread (desktop pattern)"""
        try:
            logger.debug("Loading collections sync...")

            if not self.library_service:
                logger.warning("No library service available for sync loading")
                return

            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                collections = loop.run_until_complete(self.library_service.get_collections_for_ui())
                logger.debug(f"Loaded {len(collections)} collections (sync)")

                # Update collections and trigger refresh
                self._update_collections(collections)

            finally:
                loop.close()

        except Exception as e:
            logger.error(f"Failed to load collections sync: {e}")
            self._handle_loading_error(e)

    def _update_collections(self, collections: List[Dict[str, Any]]) -> None:
        """Update collections data and refresh display"""
        try:
            # Update internal collections list
            self.collections = collections or []

            # Sort collections by name for consistent display
            self.collections.sort(key=lambda x: x.get('name', ''))

            logger.debug(f"Updated collections: {len(self.collections)} items")

            # Refresh the display (this should be implemented by subclasses)
            self._refresh_collections_display()

            # Notify observers if available (for ViewModel integration)
            self._notify_collections_updated()

        except Exception as e:
            logger.error(f"Failed to update collections: {e}")

    def _handle_loading_error(self, error: Exception) -> None:
        """Handle collection loading errors"""
        logger.error(f"Collection loading error: {error}")

        # Set empty collections on error
        self.collections = []

        # Try to refresh display to show empty state
        try:
            self._refresh_collections_display()
        except Exception as display_error:
            logger.error(f"Failed to refresh display after error: {display_error}")

    def _notify_collections_updated(self) -> None:
        """Notify any observers that collections have been updated"""
        # Default implementation - can be overridden by subclasses
        logger.debug("Collections updated notification (base implementation)")

    @abstractmethod
    def _refresh_collections_display(self) -> None:
        """Refresh the collections display - must be implemented by subclasses"""
        pass

    # Common collection management methods

    def get_collections(self) -> List[Dict[str, Any]]:
        """Get current collections list"""
        return self.collections.copy()

    def get_selected_collection(self) -> Optional[Dict[str, Any]]:
        """Get currently selected collection"""
        return self.selected_collection

    def select_collection(self, collection_id: str) -> bool:
        """Select a collection by ID"""
        try:
            for collection in self.collections:
                if collection.get('id') == collection_id:
                    self.selected_collection = collection
                    logger.debug(f"Selected collection: {collection.get('name')}")

                    # Trigger callback if available
                    if self.on_collection_selected:
                        self.on_collection_selected(collection)

                    return True

            logger.warning(f"Collection not found: {collection_id}")
            return False

        except Exception as e:
            logger.error(f"Failed to select collection {collection_id}: {e}")
            return False

    def refresh_collections(self, force: bool = False) -> None:
        """Refresh collections from the library"""
        logger.debug(f"Refreshing collections (force={force})")

        if force:
            # Clear current collections before reloading
            self.collections = []
            self._refresh_collections_display()

        # Restart loading process
        self.load_collections_unified()

    def get_collection_count(self) -> int:
        """Get number of collections"""
        return len(self.collections)

    def is_collections_loaded(self) -> bool:
        """Check if collections have been loaded"""
        return len(self.collections) > 0