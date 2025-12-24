"""
Library ViewModel for Fichero

Manages library data state independent of UI widgets.
Handles collection loading, creation, deletion, and state management.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from .base_viewmodel import BaseViewModel
from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.shared.navigation.navigation_commands import NavigateToCollection

logger = logging.getLogger(__name__)


class LibraryViewModel(BaseViewModel):
    """ViewModel for library operations and data management"""

    def __init__(self, library_service, navigation_controller: NavigationController):
        super().__init__()
        self.library_service = library_service
        self.navigation_controller = navigation_controller

        # Data state
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None
        self.edit_mode = False

        # Cache and refresh state
        self.last_refresh = None
        self.auto_refresh_enabled = True

        logger.info("LibraryViewModel initialized")

    # ===== COLLECTION MANAGEMENT =====

    def load_collections(self, force_refresh: bool = False):
        """Load collections from library service"""
        try:
            if not force_refresh and self.collections and self._is_cache_valid():
                logger.debug("Using cached collections data")
                return

            self.notify_loading_changed(True)

            # Use sync method from library service (already returns Toga-compatible format)
            print(f"🔧 LibraryViewModel: About to call get_collections_sync()...")
            collections = self.library_service.get_collections_sync()
            print(f"🔧 LibraryViewModel: get_collections_sync() returned {len(collections) if collections else 0} collections")

            # Update data
            self.collections = collections
            self.last_refresh = datetime.now()

            # Notify observers
            print(f"🔧 LibraryViewModel: About to notify observers with {len(self.collections)} collections")
            self.notify_data_changed('collections', self.collections)
            print(f"🔧 LibraryViewModel: Observers notified")
            self.notify_loading_changed(False)

            logger.info(f"Loaded {len(self.collections)} collections")

        except Exception as e:
            logger.error(f"Failed to load collections: {e}")
            self.notify_error_occurred('load_error', f"Failed to load collections: {str(e)}")
            self.notify_loading_changed(False)

    def add_collection(self, name: str, collection_type: str = "local",
                      source_path: Optional[str] = None, description: str = "") -> bool:
        """Add a new collection"""
        try:
            if not name.strip():
                self.notify_error_occurred('validation_error', "Collection name is required")
                return False

            self.notify_loading_changed(True)

            # Use sync wrapper for library service
            collection_id = self._add_collection_sync(name, collection_type, source_path, description)

            if collection_id:
                # Refresh collections to show the new one
                self.load_collections(force_refresh=True)
                logger.info(f"Added collection: {name}")
                return True
            else:
                self.notify_error_occurred('add_error', f"Failed to add collection: {name}")
                return False

        except Exception as e:
            logger.error(f"Failed to add collection {name}: {e}")
            self.notify_error_occurred('add_error', f"Failed to add collection: {str(e)}")
            return False
        finally:
            self.notify_loading_changed(False)

    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection"""
        try:
            if not collection_id:
                self.notify_error_occurred('validation_error', "Collection ID is required")
                return False

            # Find collection name for logging
            collection = next((c for c in self.collections if c.get('id') == collection_id), None)
            collection_name = collection.get('name', collection_id) if collection else collection_id

            self.notify_loading_changed(True)

            # Use sync wrapper for library service
            success = self._delete_collection_sync(collection_id)

            if success:
                # Remove from local collections list
                self.collections = [c for c in self.collections if c.get('id') != collection_id]

                # Clear selection if it was the deleted collection
                if self.selected_collection and self.selected_collection.get('id') == collection_id:
                    self.selected_collection = None
                    self.notify_data_changed('selection', None)

                # Notify observers
                self.notify_data_changed('collections', self.collections)
                logger.info(f"Deleted collection: {collection_name}")
                return True
            else:
                self.notify_error_occurred('delete_error', f"Failed to delete collection: {collection_name}")
                return False

        except Exception as e:
            logger.error(f"Failed to delete collection {collection_id}: {e}")
            self.notify_error_occurred('delete_error', f"Failed to delete collection: {str(e)}")
            return False
        finally:
            self.notify_loading_changed(False)

    def select_collection(self, collection_id: str) -> bool:
        """Select a collection and prepare for navigation"""
        try:
            # Find the collection
            collection = next((c for c in self.collections if c.get('id') == collection_id), None)
            if not collection:
                logger.error(f"Collection not found: {collection_id}")
                self.notify_error_occurred('selection_error', "Collection not found")
                return False

            # Update selection
            self.selected_collection = collection
            self.notify_data_changed('selection', collection)

            logger.info(f"Selected collection: {collection.get('name', collection_id)}")
            return True

        except Exception as e:
            logger.error(f"Failed to select collection {collection_id}: {e}")
            self.notify_error_occurred('selection_error', f"Failed to select collection: {str(e)}")
            return False

    def navigate_to_collection(self, collection_id: str) -> bool:
        """Navigate to a collection using the navigation controller"""
        try:
            # Find the collection
            collection = next((c for c in self.collections if c.get('id') == collection_id), None)
            if not collection:
                logger.error(f"Collection not found for navigation: {collection_id}")
                self.notify_error_occurred('navigation_error', "Collection not found")
                return False

            # Select the collection first
            self.select_collection(collection_id)

            # Use navigation controller to navigate
            command = NavigateToCollection(
                collection_id=collection_id,
                collection_name=collection.get('name', collection_id)
            )

            success = self.navigation_controller.execute_command(command)
            if success:
                logger.info(f"Navigated to collection: {collection.get('name', collection_id)}")
            else:
                self.notify_error_occurred('navigation_error', "Failed to navigate to collection")

            return success

        except Exception as e:
            logger.error(f"Failed to navigate to collection {collection_id}: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate to collection: {str(e)}")
            return False

    # ===== EDIT MODE MANAGEMENT =====

    def toggle_edit_mode(self) -> bool:
        """Toggle edit mode state"""
        try:
            self.edit_mode = not self.edit_mode
            self.notify_data_changed('edit_mode', self.edit_mode)
            logger.debug(f"Edit mode: {'enabled' if self.edit_mode else 'disabled'}")
            return self.edit_mode
        except Exception as e:
            logger.error(f"Failed to toggle edit mode: {e}")
            return self.edit_mode

    def set_edit_mode(self, enabled: bool):
        """Set edit mode state"""
        try:
            if self.edit_mode != enabled:
                self.edit_mode = enabled
                self.notify_data_changed('edit_mode', self.edit_mode)
                logger.debug(f"Edit mode set to: {enabled}")
        except Exception as e:
            logger.error(f"Failed to set edit mode: {e}")

    # ===== DATA ACCESS =====

    def get_collections(self) -> List[Dict[str, Any]]:
        """Get current collections list"""
        return self.collections.copy()

    def get_selected_collection(self) -> Optional[Dict[str, Any]]:
        """Get currently selected collection"""
        return self.selected_collection.copy() if self.selected_collection else None

    def get_collection_by_id(self, collection_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific collection by ID"""
        return next((c.copy() for c in self.collections if c.get('id') == collection_id), None)

    def is_edit_mode(self) -> bool:
        """Check if edit mode is enabled"""
        return self.edit_mode

    def get_collection_count(self) -> int:
        """Get total number of collections"""
        return len(self.collections)

    # ===== BASEVIEWMODEL IMPLEMENTATION =====

    def refresh(self):
        """Refresh the ViewModel data"""
        self.load_collections(force_refresh=True)

    def get_state_dict(self) -> Dict[str, Any]:
        """Get ViewModel state as dictionary for debugging"""
        base_state = super().get_state_dict()
        base_state.update({
            'collection_count': len(self.collections),
            'selected_collection_id': self.selected_collection.get('id') if self.selected_collection else None,
            'edit_mode': self.edit_mode,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'auto_refresh_enabled': self.auto_refresh_enabled
        })
        return base_state

    # ===== PRIVATE METHODS =====

    def _is_cache_valid(self, max_age_seconds: int = 300) -> bool:
        """Check if cached data is still valid"""
        if not self.last_refresh:
            return False

        age = (datetime.now() - self.last_refresh).total_seconds()
        return age < max_age_seconds

    def _add_collection_sync(self, name: str, collection_type: str,
                           source_path: Optional[str], description: str) -> Optional[str]:
        """Synchronous wrapper for adding collection"""
        try:
            # Since library_service has sync methods, use them directly
            # If we need to use async methods, we'd need to run in event loop
            if hasattr(self.library_service, 'add_collection_sync'):
                return self.library_service.add_collection_sync(name, collection_type, source_path, description)
            else:
                # Fallback to direct library manager access
                from fichero.library.models import Collection
                new_collection = Collection(
                    name=name,
                    type=collection_type,
                    source_path=source_path,
                    metadata={"description": description}
                )
                success = self.library_service.library_manager.storage.add_collection(new_collection)
                return new_collection.id if success else None
        except Exception as e:
            logger.error(f"Sync add collection failed: {e}")
            return None

    def _delete_collection_sync(self, collection_id: str) -> bool:
        """Synchronous wrapper for deleting collection"""
        try:
            if hasattr(self.library_service, 'delete_collection_sync'):
                return self.library_service.delete_collection_sync(collection_id)
            else:
                # Fallback to direct library manager access
                return self.library_service.library_manager.storage.delete_collection(collection_id)
        except Exception as e:
            logger.error(f"Sync delete collection failed: {e}")
            return False