"""
Collection ViewModel for Fichero

Manages collection data state independent of UI widgets.
Handles collection item loading, navigation, and hierarchical folder structure.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path

from .base_viewmodel import BaseViewModel
from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.shared.navigation.navigation_commands import NavigateToPath, NavigateToFolder, NavigateToPreview, NavigateBack

logger = logging.getLogger(__name__)


class CollectionViewModel(BaseViewModel):
    """ViewModel for collection operations and hierarchical navigation"""

    def __init__(self, library_service, navigation_controller: NavigationController):
        super().__init__()
        self.library_service = library_service
        self.navigation_controller = navigation_controller

        # Collection context
        self.collection_id: Optional[str] = None
        self.collection_name: Optional[str] = None
        self.current_path: str = ""  # Current path within collection

        # Data state
        self.items: List[Dict[str, Any]] = []
        self.selected_item: Optional[Dict[str, Any]] = None
        self.edit_mode = False

        # Cache and refresh state
        self.last_refresh = None
        self.auto_refresh_enabled = True

        # Listen to navigation controller for state changes
        self.navigation_controller.add_callback('state_changed', self._on_navigation_state_changed)

        logger.info("CollectionViewModel initialized")

    # ===== COLLECTION CONTEXT MANAGEMENT =====

    def set_collection(self, collection_id: str, collection_name: Optional[str] = None):
        """Set the current collection context"""
        try:
            self.collection_id = collection_id
            self.collection_name = collection_name or collection_id
            self.current_path = ""  # Reset to root
            self.items = []
            self.selected_item = None

            # Notify observers of context change
            self.notify_data_changed('collection_context', {
                'collection_id': self.collection_id,
                'collection_name': self.collection_name,
                'current_path': self.current_path
            })

            # Load items for this collection
            self.load_items()

            logger.info(f"Set collection context: {self.collection_name}")

        except Exception as e:
            logger.error(f"Failed to set collection context: {e}")
            self.notify_error_occurred('context_error', f"Failed to set collection: {str(e)}")

    def set_current_path(self, path: str):
        """Set the current path within the collection"""
        try:
            if self.current_path != path:
                self.current_path = path
                self.selected_item = None

                # Notify observers of path change
                self.notify_data_changed('current_path', self.current_path)

                # Load items for this path
                self.load_items()

                logger.info(f"Set current path: {path}")

        except Exception as e:
            logger.error(f"Failed to set current path: {e}")
            self.notify_error_occurred('path_error', f"Failed to set path: {str(e)}")

    # ===== ITEM MANAGEMENT =====

    def load_items(self, force_refresh: bool = False):
        """Load items for current collection and path"""
        try:
            if not self.collection_id:
                logger.warning("Cannot load items: no collection set")
                return

            if not force_refresh and self.items and self._is_cache_valid():
                logger.debug("Using cached items data")
                return

            self.notify_loading_changed(True)

            # Use hierarchical structure method from library service
            items = self.library_service.get_collection_structure_sync(
                self.collection_id,
                self.current_path
            )

            # Update data
            self.items = items
            self.last_refresh = datetime.now()

            # Notify observers
            self.notify_data_changed('items', self.items)
            self.notify_loading_changed(False)

            logger.info(f"Loaded {len(self.items)} items for collection {self.collection_id} at path '{self.current_path}'")

        except Exception as e:
            logger.error(f"Failed to load items: {e}")
            self.notify_error_occurred('load_error', f"Failed to load items: {str(e)}")
            self.notify_loading_changed(False)

    def select_item(self, item_id: str) -> bool:
        """Select an item"""
        try:
            # Find the item
            item = next((i for i in self.items if i.get('id') == item_id), None)
            if not item:
                logger.error(f"Item not found: {item_id}")
                self.notify_error_occurred('selection_error', "Item not found")
                return False

            # Update selection
            self.selected_item = item
            self.notify_data_changed('selection', item)

            logger.info(f"Selected item: {item.get('title', item_id)}")
            return True

        except Exception as e:
            logger.error(f"Failed to select item {item_id}: {e}")
            self.notify_error_occurred('selection_error', f"Failed to select item: {str(e)}")
            return False

    def navigate_to_item(self, item_data: Dict[str, Any]) -> bool:
        """Navigate to an item (folder or file)"""
        try:
            item_name = item_data.get('title', item_data.get('name', 'Unknown'))
            is_folder = item_data.get('is_folder', False)
            item_type = item_data.get('type', 'unknown')

            if is_folder or item_type == 'folder':
                # Navigate to folder
                folder_name = item_data.get('path', item_data.get('name', ''))
                return self.navigate_to_folder(folder_name)
            else:
                # Navigate to file preview
                file_path = item_data.get('file_path')
                if file_path:
                    return self.navigate_to_preview(file_path, item_data)
                else:
                    logger.warning(f"No file path for item: {item_name}")
                    self.notify_error_occurred('navigation_error', "No file path available for preview")
                    return False

        except Exception as e:
            logger.error(f"Failed to navigate to item: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate to item: {str(e)}")
            return False

    def navigate_to_folder(self, folder_name: str) -> bool:
        """Navigate into a folder using navigation controller"""
        try:
            command = NavigateToFolder(folder_name=folder_name)
            success = self.navigation_controller.execute_command(command)

            if success:
                logger.info(f"Navigated to folder: {folder_name}")
            else:
                self.notify_error_occurred('navigation_error', "Failed to navigate to folder")

            return success

        except Exception as e:
            logger.error(f"Failed to navigate to folder {folder_name}: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate to folder: {str(e)}")
            return False

    def navigate_to_path(self, path: str) -> bool:
        """Navigate to a specific path using navigation controller"""
        try:
            command = NavigateToPath(path=path)
            success = self.navigation_controller.execute_command(command)

            if success:
                logger.info(f"Navigated to path: {path}")
            else:
                self.notify_error_occurred('navigation_error', "Failed to navigate to path")

            return success

        except Exception as e:
            logger.error(f"Failed to navigate to path {path}: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate to path: {str(e)}")
            return False

    def navigate_to_preview(self, file_path: str, file_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Navigate to file preview using navigation controller"""
        try:
            command = NavigateToPreview(file_path=file_path, file_metadata=file_metadata)
            success = self.navigation_controller.execute_command(command)

            if success:
                logger.info(f"Navigated to preview: {file_path}")
            else:
                self.notify_error_occurred('navigation_error', "Failed to navigate to preview")

            return success

        except Exception as e:
            logger.error(f"Failed to navigate to preview {file_path}: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate to preview: {str(e)}")
            return False

    def navigate_back(self) -> bool:
        """Navigate back using navigation controller"""
        try:
            command = NavigateBack()
            success = self.navigation_controller.execute_command(command)

            if success:
                logger.info("Navigated back")
            else:
                logger.debug("No back navigation available")

            return success

        except Exception as e:
            logger.error(f"Failed to navigate back: {e}")
            self.notify_error_occurred('navigation_error', f"Failed to navigate back: {str(e)}")
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

    # ===== BREADCRUMB MANAGEMENT =====

    def get_breadcrumbs(self) -> List[Dict[str, str]]:
        """Get breadcrumb trail using navigation controller"""
        try:
            return self.navigation_controller.get_breadcrumbs()
        except Exception as e:
            logger.error(f"Failed to get breadcrumbs: {e}")
            return []

    def navigate_to_breadcrumb(self, breadcrumb_index: int) -> bool:
        """Navigate to a specific breadcrumb level"""
        try:
            breadcrumbs = self.get_breadcrumbs()
            if 0 <= breadcrumb_index < len(breadcrumbs):
                breadcrumb = breadcrumbs[breadcrumb_index]
                if breadcrumb['context'] == 'library':
                    # Navigate to library
                    from fichero.shared.navigation.navigation_commands import NavigateToLibrary
                    command = NavigateToLibrary()
                    return self.navigation_controller.execute_command(command)
                elif breadcrumb['context'] == 'collection':
                    # Navigate to collection root
                    return self.navigate_to_path("")
                elif breadcrumb['context'] == 'folder':
                    # Navigate to specific folder
                    return self.navigate_to_path(breadcrumb['path'])
            return False
        except Exception as e:
            logger.error(f"Failed to navigate to breadcrumb {breadcrumb_index}: {e}")
            return False

    # ===== DATA ACCESS =====

    def get_items(self) -> List[Dict[str, Any]]:
        """Get current items list"""
        return self.items.copy()

    def get_selected_item(self) -> Optional[Dict[str, Any]]:
        """Get currently selected item"""
        return self.selected_item.copy() if self.selected_item else None

    def get_item_by_id(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific item by ID"""
        return next((i.copy() for i in self.items if i.get('id') == item_id), None)

    def is_edit_mode(self) -> bool:
        """Check if edit mode is enabled"""
        return self.edit_mode

    def get_item_count(self) -> int:
        """Get total number of items"""
        return len(self.items)

    def get_collection_context(self) -> Dict[str, Any]:
        """Get current collection context"""
        return {
            'collection_id': self.collection_id,
            'collection_name': self.collection_name,
            'current_path': self.current_path
        }

    def can_navigate_back(self) -> bool:
        """Check if back navigation is possible"""
        return self.navigation_controller.can_navigate_back()

    # ===== BASEVIEWMODEL IMPLEMENTATION =====

    def refresh(self):
        """Refresh the ViewModel data"""
        self.load_items(force_refresh=True)

    def get_state_dict(self) -> Dict[str, Any]:
        """Get ViewModel state as dictionary for debugging"""
        base_state = super().get_state_dict()
        base_state.update({
            'collection_id': self.collection_id,
            'collection_name': self.collection_name,
            'current_path': self.current_path,
            'item_count': len(self.items),
            'selected_item_id': self.selected_item.get('id') if self.selected_item else None,
            'edit_mode': self.edit_mode,
            'last_refresh': self.last_refresh.isoformat() if self.last_refresh else None,
            'auto_refresh_enabled': self.auto_refresh_enabled,
            'can_navigate_back': self.can_navigate_back()
        })
        return base_state

    # ===== PRIVATE METHODS =====

    def _is_cache_valid(self, max_age_seconds: int = 60) -> bool:
        """Check if cached data is still valid (shorter cache for collection items)"""
        if not self.last_refresh:
            return False

        age = (datetime.now() - self.last_refresh).total_seconds()
        return age < max_age_seconds

    def _on_navigation_state_changed(self, navigation_state):
        """Handle navigation state changes from navigation controller"""
        try:
            # Update our state to match navigation controller
            if navigation_state.context.value == "collection":
                # Update collection context if it changed
                if (navigation_state.collection_id != self.collection_id or
                    navigation_state.current_path != self.current_path):

                    self.collection_id = navigation_state.collection_id
                    self.collection_name = navigation_state.collection_name
                    self.current_path = navigation_state.current_path

                    # Notify observers of context change
                    self.notify_data_changed('collection_context', {
                        'collection_id': self.collection_id,
                        'collection_name': self.collection_name,
                        'current_path': self.current_path
                    })

                    # Load items for new context
                    self.load_items(force_refresh=True)

        except Exception as e:
            logger.error(f"Failed to handle navigation state change: {e}")