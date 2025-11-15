"""
Navigation Controller for Fichero

Centralized navigation logic that's independent of UI widgets.
Uses event bus for UI communication to prevent loops.

Enhanced in Phase 3.1 with UniversalLayoutManager for dynamic view layout.
"""

import logging
from typing import Optional, Dict, Any, List, Callable
from pathlib import Path

from .navigation_state import NavigationState, NavigationContext, NavigationHistory
from .navigation_commands import NavigationCommand
from .navigation_event_bus import emit_navigation_event, NavigationEvents
from .layout_manager import UniversalLayoutManager

logger = logging.getLogger(__name__)


class NavigationController:
    """Centralized navigation controller for all navigation logic"""

    def __init__(self, library_service, app=None, is_mobile: bool = False):
        """Initialize navigation controller"""
        self.library_service = library_service
        self.app = app
        self.is_mobile = is_mobile

        # Navigation state
        self.history = NavigationHistory()
        self.current_state = NavigationState(context=NavigationContext.LIBRARY)

        # Toolbar coordinator for edit mode state capture
        self._toolbar_coordinator = None

        # Modal navigation stack for handling modal view hierarchies
        self.modal_history: List[NavigationState] = []

        # Modal overlay management for mobile platform
        self._modal_previous_content = None
        self._current_modal_view = None

        # State deduplication to prevent multiple identical events
        self._last_emitted_state = None

        # PHASE 3.1: Universal Layout Manager for dynamic view layout
        # Replaces hardcoded 3-pane desktop system with flexible, resizable panes
        self.layout_manager: Optional[UniversalLayoutManager] = None
        self._initialize_layout_manager()

        # ✅ RELIABILITY FIX: Don't push initial state to history yet
        # The library state will be added to history when we first navigate away from it
        # This ensures can_navigate_back() works correctly after navigation

        logger.info(f"Navigation controller initialized (mobile: {is_mobile})")

    # ===== STATE MANAGEMENT =====

    def get_current_state(self) -> NavigationState:
        """Get the current navigation state"""
        return self.current_state.copy()

    def can_navigate_back(self) -> bool:
        """Check if back navigation is possible"""
        return self.history.can_go_back()

    def can_navigate_forward(self) -> bool:
        """Check if forward navigation is possible"""
        return self.history.can_go_forward()

    # ===== CORE NAVIGATION METHODS =====

    def navigate_to_library(self) -> bool:
        """Navigate to the library (root) view"""
        try:
            new_state = NavigationState(context=NavigationContext.LIBRARY)
            self._transition_to_state(new_state)
            logger.info("Navigated to library")
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to library: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to library: {str(e)}")
            return False

    def navigate_to_collection(self, collection_id: str, collection_name: Optional[str] = None) -> bool:
        """Navigate to a specific collection"""
        try:
            if not collection_id:
                logger.error("Cannot navigate to collection: no collection ID provided")
                return False

            # Create new state for collection
            new_state = NavigationState(
                context=NavigationContext.COLLECTION,
                collection_id=collection_id,
                collection_name=collection_name or collection_id,
                current_path=""  # Start at root of collection
            )

            self._transition_to_state(new_state)

            # Emit collection loaded event
            emit_navigation_event(NavigationEvents.SHOW_COLLECTION, {
                'collection_id': collection_id,
                'collection_name': collection_name,
                'navigation_state': new_state.to_dict()
            })

            logger.info(f"Navigated to collection: {collection_name or collection_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to collection {collection_id}: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to collection: {str(e)}")
            return False

    def navigate_to_path(self, path: str) -> bool:
        """Navigate to a specific path within current collection"""
        try:
            if self.current_state.context != NavigationContext.COLLECTION:
                logger.error("Cannot navigate to path: not in collection context")
                return False

            if not self.current_state.collection_id:
                logger.error("Cannot navigate to path: no current collection")
                return False

            # Update path directly without adding to history
            # Hierarchical navigation uses _get_parent_path() for back navigation
            self.current_state.current_path = path

            self._emit_state_changed()
            logger.info(f"Navigated to path: {path} in collection {self.current_state.collection_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to path {path}: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to path: {str(e)}")
            return False

    def navigate_to_folder(self, folder_name: str) -> bool:
        """Navigate into a folder within current collection"""
        try:
            if self.current_state.context != NavigationContext.COLLECTION:
                logger.error("Cannot navigate to folder: not in collection context")
                return False

            # Build new path
            current_path = self.current_state.current_path
            if current_path:
                new_path = f"{current_path.rstrip('/')}/{folder_name}"
            else:
                new_path = folder_name

            return self.navigate_to_path(new_path)

        except Exception as e:
            logger.error(f"Failed to navigate to folder {folder_name}: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to folder: {str(e)}")
            return False

    def navigate_to_preview(self, file_path: str, file_metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Navigate to file preview"""
        try:
            if not file_path:
                logger.error("Cannot navigate to preview: no file path provided")
                return False

            # Extract item_id from file_metadata if available
            metadata_dict = file_metadata or {}
            item_id = metadata_dict.get('id') or metadata_dict.get('item_id')

            # Create new state for preview
            new_state = NavigationState(
                context=NavigationContext.PREVIEW,
                collection_id=self.current_state.collection_id,
                collection_name=self.current_state.collection_name,
                current_path=self.current_state.current_path,
                file_path=file_path,
                metadata=metadata_dict
            )

            self._transition_to_state(new_state)

            # Emit preview requested event with item_id extracted
            event_data = {
                'file_path': file_path,
                'file_metadata': metadata_dict,
                'navigation_state': new_state.to_dict()
            }

            # Add item_id directly to event data so handlers don't have to extract it
            if item_id:
                event_data['item_id'] = item_id

            emit_navigation_event(NavigationEvents.SHOW_PREVIEW, event_data)

            logger.info(f"Navigated to preview: {file_path} (item_id: {item_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to preview {file_path}: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to preview: {str(e)}")
            return False

    def navigate_back(self) -> bool:
        """Navigate back in history with intelligent hierarchical support"""
        try:
            # Prevent recursive navigation calls during state transitions
            if hasattr(self, '_navigating_back') and self._navigating_back:
                logger.debug("🔒 Blocking recursive navigate_back() call")
                return False

            self._navigating_back = True

            # DEBUG: Log current state before back navigation
            logger.info(f"🔍 NAVIGATE_BACK DEBUG: context={self.current_state.context.value}, path='{self.current_state.current_path}', collection_id={self.current_state.collection_id}")

            # Check if we're in a modal view and have modal history
            if self.modal_history:
                # Close current modal and restore previous state
                if self.is_mobile and self._current_modal_view:
                    self._close_modal_overlay()

                # Restore previous state from modal history
                previous_state = self.modal_history.pop()
                self.current_state = previous_state

                # Restore edit mode state if available
                edit_mode_data = {
                    'edit_mode_state': previous_state.edit_mode_state,
                    'edit_context': previous_state.edit_context
                }
                if edit_mode_data['edit_mode_state']:
                    logger.debug(f"Restoring edit mode: {edit_mode_data['edit_mode_state']}")
                    # Restore edit mode immediately after state change
                    self._restore_edit_mode(edit_mode_data)

                self._emit_state_changed()
                logger.info(f"Modal back navigation to: {previous_state.context.value}")
                self._navigating_back = False
                return True

            # Special handling for hierarchical navigation within collections
            if self.current_state.context == NavigationContext.COLLECTION:
                if self.current_state.current_path:
                    # We're inside a subfolder - go up one level
                    parent_path = self._get_parent_path(self.current_state.current_path)
                    if parent_path is not None:  # None means we're at root
                        logger.info(f"Hierarchical back navigation: '{self.current_state.current_path}' → '{parent_path}'")

                        # Update path without adding to history (we're going backwards)
                        self.current_state.current_path = parent_path
                        self._emit_state_changed()
                        self._navigating_back = False
                        return True
                else:
                    # We're at collection root - go back to library
                    logger.info(f"At collection root - navigating back to library")
                    library_state = NavigationState(
                        context=NavigationContext.LIBRARY
                    )
                    self.current_state = library_state
                    self._emit_state_changed()
                    logger.info(f"✅ Navigated back to library from collection root")
                    self._navigating_back = False
                    return True

            # Special handling for preview back navigation - preserve folder context
            logger.info(f"🔍 PREVIEW CHECK: context={self.current_state.context}, collection_id={self.current_state.collection_id}, current_path='{self.current_state.current_path}'")
            if (self.current_state.context == NavigationContext.PREVIEW and
                self.current_state.collection_id and
                self.current_state.current_path is not None):

                logger.info(f"🎯 PREVIEW BACK NAVIGATION TRIGGERED!")
                # Navigate back to the collection folder we came from (preserve path)
                collection_state = NavigationState(
                    context=NavigationContext.COLLECTION,
                    collection_id=self.current_state.collection_id,
                    collection_name=self.current_state.collection_name,
                    current_path=self.current_state.current_path  # ✅ Preserve folder path
                )

                self.current_state = collection_state
                self._emit_state_changed()
                logger.info(f"✅ Preview back navigation to collection folder: '{self.current_state.current_path}'")
                self._navigating_back = False
                return True
            else:
                logger.info(f"🚫 PREVIEW BACK NAVIGATION CONDITION NOT MET")

                # Standard history navigation for cross-context or when at collection root
                logger.debug(f"History state: current_index={self.history.current_index}, history_size={len(self.history.history)}, can_go_back={self.history.can_go_back()}")

                # FIXED: Check if we're in COLLECTION context with empty history
                # This happens on first navigation to collection - library state should be available to go back to
                if (self.current_state.context == NavigationContext.COLLECTION and
                    len(self.history.history) > 0 and not self.history.can_go_back()):

                    # SPECIAL CASE: First navigation to collection
                    # The library state is in history but current_index points to it
                    # We need to go back to the library state (which is the last state in history)
                    logger.info(f"🎯 SPECIAL CASE: First collection navigation back to library")
                    library_state = self.history.history[-1]  # Get the last (most recent) state in history
                    if library_state.context == NavigationContext.LIBRARY:
                        self.current_state = library_state
                        self._emit_state_changed()
                        logger.info(f"✅ Navigated back to library from first collection visit")
                        self._navigating_back = False
                        return True

                previous_state = self.history.go_back()
                if previous_state:
                    # Don't add to history when going back - we're already moving through it
                    self.current_state = previous_state
                    self._emit_state_changed()
                    logger.info(f"Navigated back to: {previous_state.context.value}")
                    self._navigating_back = False
                    return True
                else:
                    logger.debug("No previous state to navigate back to")
                    self._navigating_back = False
                    return False

        except Exception as e:
            logger.error(f"Failed to navigate back: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate back: {str(e)}")
            self._navigating_back = False
            return False

    def _get_parent_path(self, path: str) -> Optional[str]:
        """Get parent path for hierarchical navigation, or None if at root"""
        if not path or path == "":
            return None  # Already at root

        # Remove the last path segment
        parts = path.rstrip('/').split('/')
        if len(parts) <= 1:
            return ""  # Go to collection root
        else:
            return '/'.join(parts[:-1])  # Go to parent folder

    def navigate_forward(self) -> bool:
        """Navigate forward in history"""
        try:
            next_state = self.history.go_forward()
            if next_state:
                self.current_state = next_state
                self._emit_state_changed()
                logger.info(f"Navigated forward to: {next_state.context.value}")
                return True
            else:
                logger.debug("No next state to navigate forward to")
                return False

        except Exception as e:
            logger.error(f"Failed to navigate forward: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate forward: {str(e)}")
            return False

    # ===== MODAL VIEW NAVIGATION =====

    def navigate_to_settings(self) -> bool:
        """Navigate to settings modal view"""
        return self._navigate_to_modal(NavigationContext.SETTINGS, "settings")

    def navigate_to_activity_monitor(self) -> bool:
        """Navigate to activity monitor modal view"""
        return self._navigate_to_modal(NavigationContext.ACTIVITY_MONITOR, "activity_monitor")

    def navigate_to_processing(self) -> bool:
        """Navigate to processing modal view"""
        return self._navigate_to_modal(NavigationContext.PROCESSING, "processing")

    def navigate_to_plans(self) -> bool:
        """Navigate to plans modal view"""
        return self._navigate_to_modal(NavigationContext.PLANS, "plans")

    def navigate_to_prompts(self) -> bool:
        """Navigate to prompts modal view"""
        return self._navigate_to_modal(NavigationContext.PROMPTS, "prompts")

    def navigate_to_about(self) -> bool:
        """Navigate to about modal view"""
        return self._navigate_to_modal(NavigationContext.ABOUT, "about")

    def navigate_to_output(self) -> bool:
        """Navigate to output modal view"""
        return self._navigate_to_modal(NavigationContext.PREVIEW, "output")

    def navigate_to_inspector(self, item_id: str = None, item_data: dict = None, selection_type: str = 'ITEM') -> bool:
        """Navigate to inspector modal view with item information

        Args:
            item_id: ID of the item/collection to inspect
            item_data: Dictionary of metadata to display
            selection_type: Type of selection ('ITEM', 'COLLECTION', 'FOLDER')
        """
        params = {}
        if item_id:
            params['item_id'] = item_id
        if item_data:
            params['item_data'] = item_data
        params['selection_type'] = selection_type
        return self._navigate_to_modal(NavigationContext.INSPECTOR, "inspector", params)

    def navigate_to_add_url(self) -> bool:
        """Navigate to add URL modal view"""
        return self._navigate_to_modal(NavigationContext.ADD, "url")

    def navigate_to_add_file(self) -> bool:
        """Navigate to add file modal view"""
        # For desktop platforms with native dialogs, call directly
        if not self.is_mobile and hasattr(self.app, 'main_window'):
            try:
                import asyncio
                asyncio.create_task(self._handle_desktop_file_dialog())
                return True
            except Exception as e:
                logger.error(f"Failed to open desktop file dialog: {e}")

        # Fallback to modal view for mobile or if direct dialog fails
        return self._navigate_to_modal(NavigationContext.ADD, "file")

    def navigate_to_add_folder(self) -> bool:
        """Navigate to add folder modal view"""
        # For desktop platforms with native dialogs, call directly
        if not self.is_mobile and hasattr(self.app, 'main_window'):
            try:
                import asyncio
                asyncio.create_task(self._handle_desktop_folder_dialog())
                return True
            except Exception as e:
                logger.error(f"Failed to open desktop folder dialog: {e}")

        # Fallback to modal view for mobile or if direct dialog fails
        return self._navigate_to_modal(NavigationContext.ADD, "folder")

    def navigate_to_add_camera(self) -> bool:
        """Navigate to add camera modal view"""
        return self._navigate_to_modal(NavigationContext.ADD, "camera")

    def navigate_to_add(self, add_type: str = "url") -> bool:
        """Navigate to add modal view - legacy method"""
        return self._navigate_to_modal(NavigationContext.ADD, add_type)

    def navigate_to_rename_collection(self, collection_id: str, collection_name: str) -> bool:
        """Navigate to rename collection modal view"""
        return self._navigate_to_modal(NavigationContext.RENAME, "collection", {
            "collection_id": collection_id,
            "collection_name": collection_name
        })

    def _navigate_to_modal(self, context: NavigationContext, modal_type: str, params: dict = None) -> bool:
        """Generic modal navigation handler"""
        try:
            # Create the modal view using factory methods
            view = None
            if modal_type == "settings":
                view = self._create_settings_view()
            elif modal_type == "about":
                view = self._create_about_view()
            elif modal_type == "activity_monitor":
                view = self._create_activity_monitor_view()
            elif modal_type == "plans":
                view = self._create_plans_view()
            elif modal_type == "prompts":
                view = self._create_prompts_view()
            elif modal_type == "processing":
                view = self._create_processing_view()
            elif modal_type == "url":
                view = self._create_add_url_view()
            elif modal_type == "file":
                view = self._create_add_file_view()
            elif modal_type == "folder":
                view = self._create_add_folder_view()
            elif modal_type == "camera":
                view = self._create_add_camera_view()
            elif modal_type == "collection" and context == NavigationContext.RENAME:
                if params:
                    view = self._create_rename_collection_view(
                        params.get("collection_id"),
                        params.get("collection_name")
                    )
            elif modal_type == "inspector":
                view = self._create_inspector_view(params)
            elif modal_type == "output":
                view = self._create_output_view()

            if not view:
                logger.error(f"Failed to create view for modal type: {modal_type}")
                return False

            # Handle platform-specific display and navigation
            if self.is_mobile:
                # Mobile: Modal overlay with history tracking
                success = self._show_modal_overlay(view)
                if not success:
                    logger.error(f"Failed to show modal overlay for {modal_type}")
                    return False

                # Capture current edit mode state before modal transition
                edit_mode_data = self._capture_current_edit_mode()

                # Create new state for modal view
                new_state = NavigationState(
                    context=context,
                    collection_id=self.current_state.collection_id,  # Preserve context
                    collection_name=self.current_state.collection_name,
                    current_path=self.current_state.current_path,
                    metadata={'modal_type': modal_type}
                )

                # Preserve current state WITH edit mode data in modal history
                saved_state = self.current_state.copy()
                saved_state.edit_mode_state = edit_mode_data.get('edit_mode_state')
                saved_state.edit_context = edit_mode_data.get('edit_context')
                self.modal_history.append(saved_state)

                logger.debug(f"Saved edit mode state for modal navigation: {edit_mode_data.get('edit_mode_state')}")
                self._transition_to_state(new_state, add_to_history=False)

            else:
                # Desktop: Modal windows with history tracking for proper closure
                # Capture current edit mode state before modal transition
                edit_mode_data = self._capture_current_edit_mode()

                # Create new state for modal view
                new_state = NavigationState(
                    context=context,
                    collection_id=self.current_state.collection_id,  # Preserve context
                    collection_name=self.current_state.collection_name,
                    current_path=self.current_state.current_path,
                    metadata={'modal_type': modal_type}
                )

                # Preserve current state WITH edit mode data in modal history
                saved_state = self.current_state.copy()
                saved_state.edit_mode_state = edit_mode_data.get('edit_mode_state')
                saved_state.edit_context = edit_mode_data.get('edit_context')
                self.modal_history.append(saved_state)

                logger.debug(f"Desktop modal: Saved edit mode state for modal navigation: {edit_mode_data.get('edit_mode_state')}")

                # Emit modal event for UI display
                emit_navigation_event(NavigationEvents.SHOW_MODAL, {
                    'modal_type': modal_type,
                    'context': context.value,
                    'view': view,
                    'navigation_state': self.current_state.to_dict()
                })

                # Update navigation state for proper back navigation
                self._transition_to_state(new_state, add_to_history=False)

            logger.info(f"Navigated to {modal_type} modal view")
            return True

        except Exception as e:
            logger.error(f"Failed to navigate to {modal_type} modal: {e}")
            self._emit_error("Navigation Error", f"Failed to navigate to {modal_type}: {str(e)}")
            return False

    # ===== COMMAND EXECUTION =====

    def execute_command(self, command: NavigationCommand) -> bool:
        """Execute a navigation command"""
        try:
            if not command.can_execute(self):
                logger.warning(f"Command cannot be executed: {command.get_description()}")
                return False

            success = command.execute(self)
            if success:
                logger.info(f"Executed command: {command.get_description()}")
            else:
                logger.error(f"Command execution failed: {command.get_description()}")

            return success

        except Exception as e:
            logger.error(f"Failed to execute command {command.get_description()}: {e}")
            self._emit_error("Command Error", f"Failed to execute command: {str(e)}")
            return False


    # ===== HELPER METHODS =====

    def _initialize_layout_manager(self):
        """
        Initialize the Universal Layout Manager (Phase 3.1).

        Creates a layout manager that handles dynamic view splitting
        and resizing. Replaces the hardcoded 3-pane desktop system.
        """
        try:
            self.layout_manager = UniversalLayoutManager(is_mobile=self.is_mobile)

            # Set up layout event handlers
            self.layout_manager.on_view_focused = self._on_layout_view_focused
            self.layout_manager.on_view_added = self._on_layout_view_added
            self.layout_manager.on_view_removed = self._on_layout_view_removed

            logger.info("Universal Layout Manager initialized")

        except Exception as e:
            logger.error(f"Failed to initialize layout manager: {e}")
            # Layout manager is optional, so we can continue without it
            self.layout_manager = None

    def _on_layout_view_focused(self, slot_id: str):
        """
        Handle view focus event from layout manager.

        Args:
            slot_id: ID of the focused view slot
        """
        logger.debug(f"Layout view focused: {slot_id}")
        # Emit event for UI updates
        emit_navigation_event(NavigationEvents.VIEW_FOCUSED, {
            'slot_id': slot_id
        })

    def _on_layout_view_added(self, slot_id: str):
        """
        Handle view added event from layout manager.

        Args:
            slot_id: ID of the added view slot
        """
        logger.debug(f"Layout view added: {slot_id}")

    def _on_layout_view_removed(self, slot_id: str):
        """
        Handle view removed event from layout manager.

        Args:
            slot_id: ID of the removed view slot
        """
        logger.debug(f"Layout view removed: {slot_id}")

    def get_layout_container(self) -> Optional[Any]:
        """
        Get the root layout container for placing in the window.

        Returns:
            toga.Box container with the dynamic layout, or None if not initialized
        """
        if self.layout_manager:
            return self.layout_manager.container
        return None

    def get_breadcrumbs(self) -> List[Dict[str, str]]:
        """Get breadcrumb trail for current state"""
        breadcrumbs = []

        # Always start with library
        breadcrumbs.append({
            'name': 'Library',
            'path': '',
            'context': 'library'
        })

        # Add collection if we're in one
        if self.current_state.collection_id:
            breadcrumbs.append({
                'name': self.current_state.collection_name or self.current_state.collection_id,
                'path': '',
                'context': 'collection'
            })

            # Add path segments if we're in a subfolder
            if self.current_state.current_path:
                path_parts = self.current_state.current_path.split('/')
                current_path = ''
                for part in path_parts:
                    if part:  # Skip empty parts
                        current_path = f"{current_path}/{part}" if current_path else part
                        breadcrumbs.append({
                            'name': part,
                            'path': current_path,
                            'context': 'folder'
                        })

        return breadcrumbs

    def get_navigation_info(self) -> Dict[str, Any]:
        """Get comprehensive navigation information for debugging"""
        return {
            'current_state': self.current_state.to_dict(),
            'can_go_back': self.can_navigate_back(),
            'can_go_forward': self.can_navigate_forward(),
            'breadcrumbs': self.get_breadcrumbs(),
            'history_size': len(self.history.history),
            'is_mobile': self.is_mobile
        }

    # ===== EDIT MODE STATE MANAGEMENT =====

    def register_toolbar_coordinator(self, coordinator):
        """Register toolbar coordinator for edit mode state capture"""
        self._toolbar_coordinator = coordinator
        logger.debug("Toolbar coordinator registered for edit mode preservation")

    def _capture_current_edit_mode(self) -> Dict[str, Any]:
        """Capture current edit mode state from toolbar coordinator"""
        try:
            if self._toolbar_coordinator:
                return {
                    'edit_mode_state': self._toolbar_coordinator._edit_mode_state.value,
                    'edit_context': self._toolbar_coordinator._edit_context.copy()
                }
            return {'edit_mode_state': 'normal', 'edit_context': {}}
        except Exception as e:
            logger.error(f"Failed to capture edit mode state: {e}")
            return {'edit_mode_state': 'normal', 'edit_context': {}}

    def _restore_edit_mode(self, edit_mode_data: Dict[str, Any]) -> None:
        """Restore edit mode state to toolbar coordinator"""
        try:
            if self._toolbar_coordinator and edit_mode_data:
                from fichero.shared.toolbars.toolbar_coordinator import EditModeState

                mode_str = edit_mode_data.get('edit_mode_state', 'normal')
                context = edit_mode_data.get('edit_context', {})

                # Convert string back to enum
                mode = EditModeState.NORMAL
                if mode_str == 'edit':
                    mode = EditModeState.EDIT
                elif mode_str == 'multi_select':
                    mode = EditModeState.MULTI_SELECT

                # Restore edit mode
                self._toolbar_coordinator.set_edit_mode(mode, context)
                logger.debug(f"Restored edit mode: {mode.value}")
            else:
                logger.debug("No toolbar coordinator or edit mode data to restore")

        except Exception as e:
            logger.error(f"Failed to restore edit mode state: {e}")

    def get_current_title(self) -> str:
        """Get context-appropriate title for current navigation state"""
        try:
            context = self.current_state.context.value

            if context == 'library':
                return "Library"
            elif context == 'collection':
                return self.current_state.collection_name or "Collection"
            elif context == 'preview':
                # For preview, show the filename or "Preview"
                if self.current_state.file_path:
                    from pathlib import Path
                    return Path(self.current_state.file_path).name
                return "Preview"
            elif context == 'add':
                return "Add"
            elif context == 'settings':
                return "Settings"
            elif context == 'about':
                return "About"
            elif context == 'processing':
                return "Processing"
            elif context == 'plans':
                return "Plans"
            elif context == 'prompts':
                return "Prompts"
            elif context == 'activity_monitor':
                return "Activity Monitor"
            else:
                return "Fichero"  # Default fallback

        except Exception as e:
            logger.error(f"Failed to get current title: {e}")
            return "Fichero"

    def should_show_title(self, view_type: str = None) -> bool:
        """Determine if title should be shown for current context"""
        try:
            context = self.current_state.context.value

            # Collections can optionally disable titles (as user requested)
            if context == 'collection' and view_type == 'collection':
                return False  # User specifically requested no titles for collections

            # All other contexts show titles for user orientation
            return True

        except Exception as e:
            logger.error(f"Failed to determine title visibility: {e}")
            return True  # Safe default

    # ===== PRIVATE METHODS =====

    def _transition_to_state(self, new_state: NavigationState, add_to_history: bool = True):
        """Transition to a new navigation state"""
        # Save current state to history (unless we're navigating back)
        if add_to_history:
            self.history.push(self.current_state)

        # Update current state
        self.current_state = new_state

        # Emit state change event
        self._emit_state_changed()

    def _emit_state_changed(self):
        """Emit navigation state change event with deduplication"""
        # Create state signature for deduplication (context + key identifying fields)
        current_state_dict = self.current_state.to_dict()
        state_signature = {
            'context': current_state_dict['context'],
            'collection_id': current_state_dict.get('collection_id'),
            'current_path': current_state_dict.get('current_path'),
            'file_path': current_state_dict.get('file_path')
        }

        # Check if this state was already emitted recently to prevent event storms
        if self._last_emitted_state == state_signature:
            logger.debug(f"🔕 Skipping duplicate state change emission for {self.current_state.context.value}")
            return

        # Update last emitted state
        self._last_emitted_state = state_signature
        logger.debug(f"📡 Emitting state change: {self.current_state.context.value}")

        context = self.current_state.context
        if context == NavigationContext.LIBRARY:
            emit_navigation_event(NavigationEvents.SHOW_LIBRARY, {
                'navigation_state': current_state_dict
            })
        elif context == NavigationContext.COLLECTION:
            emit_navigation_event(NavigationEvents.SHOW_COLLECTION, {
                'collection_id': self.current_state.collection_id,
                'collection_name': self.current_state.collection_name,
                'navigation_state': current_state_dict
            })
        elif context == NavigationContext.PREVIEW:
            emit_navigation_event(NavigationEvents.SHOW_PREVIEW, {
                'file_path': self.current_state.file_path,
                'file_metadata': self.current_state.metadata,
                'navigation_state': current_state_dict
            })

        # Always emit general state change event
        emit_navigation_event(NavigationEvents.STATE_CHANGED, {
            'navigation_state': current_state_dict,
            'can_navigate_back': self.can_navigate_back(),
            'breadcrumbs': self.get_breadcrumbs()
        })

    def _emit_error(self, title: str, message: str):
        """Emit navigation error event"""
        emit_navigation_event(NavigationEvents.NAVIGATION_ERROR, {
            'title': title,
            'message': message
        })

    # ===== VIEW FACTORY METHODS =====

    def _create_settings_view(self):
        """Create settings modal view"""
        try:
            from fichero.windows.settings.mobile_view import SettingsMobileView
            return SettingsMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create settings view: {e}")
            return None

    def _create_about_view(self):
        """Create about modal view"""
        try:
            from fichero.windows.about.mobile_view import AboutMobileView
            return AboutMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create about view: {e}")
            return None

    def _create_activity_monitor_view(self):
        """Create activity monitor modal view"""
        try:
            from fichero.windows.activity_monitor.mobile_view import ActivityMonitorMobileView
            return ActivityMonitorMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create activity monitor view: {e}")
            return None

    def _create_plans_view(self):
        """Create plans modal view"""
        try:
            from fichero.windows.plans.mobile_view import PlansMobileView
            return PlansMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create plans view: {e}")
            return None

    def _create_prompts_view(self):
        """Create prompts modal view"""
        try:
            from fichero.windows.prompts.mobile_view import PromptsMobileView
            return PromptsMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create prompts view: {e}")
            return None

    def _create_processing_view(self):
        """Create processing modal view"""
        try:
            from fichero.windows.processing.mobile_view import ProcessingMobileView
            return ProcessingMobileView(self.app)
        except Exception as e:
            logger.error(f"Failed to create processing view: {e}")
            return None

    def _create_add_file_view(self):
        """Create add file modal view"""
        try:
            from fichero.windows.add.views.file_view import FileAddView
            return FileAddView(self.app)
        except Exception as e:
            logger.error(f"Failed to create add file view: {e}")
            return None

    def _create_add_folder_view(self):
        """Create add folder modal view"""
        try:
            from fichero.windows.add.views.folder_view import FolderAddView
            return FolderAddView(self.app)
        except Exception as e:
            logger.error(f"Failed to create add folder view: {e}")
            return None

    def _create_add_camera_view(self):
        """Create add camera modal view"""
        try:
            from fichero.windows.add.views.camera_view import CameraAddView

            # Create callback to handle camera photo additions
            def on_content_added(content_info):
                logger.info(f"Camera photo added callback: {content_info}")
                # Create async task to handle camera photo addition
                import asyncio
                asyncio.create_task(self._handle_camera_content_added(content_info))

            return CameraAddView(self.app, on_content_added=on_content_added)
        except Exception as e:
            logger.error(f"Failed to create add camera view: {e}")
            return None

    def _create_add_url_view(self):
        """Create add URL modal view"""
        try:
            from fichero.windows.add.views.url_view import URLAddView

            # Create callback to handle URL additions - returns the async task
            def on_content_added(content_info):
                logger.info(f"URL content added callback: {content_info}")
                # Return the async task so the view can await it
                import asyncio
                return asyncio.create_task(self._handle_url_content_added(content_info))

            return URLAddView(self.app, on_content_added=on_content_added)
        except Exception as e:
            logger.error(f"Failed to create add URL view: {e}")
            return None

    def _create_rename_collection_view(self, collection_id: str, collection_name: str):
        """Create rename collection modal view"""
        try:
            from fichero.windows.library.rename_view import RenameCollectionView

            # Create callback to refresh library view after rename
            def on_renamed(coll_id, new_name):
                logger.info(f"Collection renamed callback: {coll_id} -> {new_name}")
                # Refresh the library view to show the new name
                try:
                    if hasattr(self.app, 'main_window') and self.app.main_window:
                        # Get the current library view and refresh it
                        main_window = self.app.main_window
                        if hasattr(main_window, 'library_view'):
                            library_view = main_window.library_view
                            if hasattr(library_view, 'refresh_collections'):
                                library_view.refresh_collections()  # Call directly, not async
                                logger.info("Library refreshed after rename via callback")
                except Exception as e:
                    logger.error(f"Failed to refresh library after rename: {e}")

            return RenameCollectionView(
                self.app,
                collection_id,
                collection_name,
                on_renamed=on_renamed
            )
        except Exception as e:
            logger.error(f"Failed to create rename collection view: {e}")
            return None

    def _create_output_view(self):
        """Create output modal view"""
        try:
            from fichero.windows.main.views.preview import PreviewView
            # Pass library_manager for file-specific filtering
            library_manager = getattr(self.app, 'library_manager', None)
            return PreviewView(self.app, self.is_mobile, library_manager=library_manager)
        except Exception as e:
            logger.error(f"Failed to create output view: {e}")
            return None

    def _create_inspector_view(self, params: dict = None):
        """Create inspector modal view - uses InspectorMobileView on mobile"""
        try:
            if not self.is_mobile:
                # Desktop: Use existing inspector window
                inspector_window = getattr(self.app, 'inspector_window', None)
                if not inspector_window:
                    from fichero.windows.inspector.inspector_window import InspectorWindow
                    inspector_window = InspectorWindow(self.app)
                    self.app.inspector_window = inspector_window

                # Update inspector with item data if provided
                if params:
                    item_data = params.get('item_data', {})
                    selection_type = params.get('selection_type', 'ITEM')
                    if item_data:
                        inspector_window.update_metadata(item_data, selection_type)

                # Show window directly on desktop
                inspector_window.show()
                return None  # Desktop doesn't need modal view, uses window directly
            else:
                # Mobile: Create InspectorMobileView (follows pattern of activity monitor, etc.)
                from fichero.windows.inspector.mobile_view import InspectorMobileView

                item_data = params.get('item_data', {}) if params else {}
                selection_type = params.get('selection_type', 'ITEM') if params else 'ITEM'

                return InspectorMobileView(self.app, item_data=item_data, selection_type=selection_type)

        except Exception as e:
            logger.error(f"Failed to create inspector view: {e}")
            import traceback
            traceback.print_exc()
            return None

    # ===== MODAL OVERLAY MANAGEMENT =====

    def _show_modal_overlay(self, view) -> bool:
        """Show modal overlay on mobile (moved from WindowViewManager)"""
        try:
            if not self.app or not self.is_mobile:
                return False

            main_window = getattr(self.app, 'main_window_wrapper', None)
            if not main_window or not hasattr(main_window, 'main_container'):
                logger.error("No main container found for modal overlay")
                return False

            container = main_window.main_container

            # Store current content
            self._modal_previous_content = list(container.children)

            # Clear container and add modal view
            container.clear()
            container.add(view.get_container() if hasattr(view, 'get_container') else view)

            self._current_modal_view = view
            logger.debug("Modal overlay shown successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to show modal overlay: {e}")
            return False

    def _close_modal_overlay(self) -> bool:
        """Close modal overlay and restore previous content"""
        try:
            if not self.app or not self.is_mobile:
                return False

            main_window = getattr(self.app, 'main_window_wrapper', None)
            if not main_window or not hasattr(main_window, 'main_container'):
                return False

            container = main_window.main_container

            # Restore previous content if we have it
            if self._modal_previous_content:
                container.clear()
                for child in self._modal_previous_content:
                    container.add(child)

                # Clear stored content
                self._modal_previous_content = None
                self._current_modal_view = None

            logger.debug("Modal overlay closed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to close modal overlay: {e}")
            return False

    # ===== DESKTOP DIALOG HANDLERS =====

    async def _handle_desktop_file_dialog(self):
        """Handle desktop file dialog directly - bypasses intermediate views"""
        try:
            import toga
            from pathlib import Path

            logger.info("Opening desktop file dialog directly")

            # Supported file types (include case variations for JPG/JPEG/TIF/TIFF)
            file_types = ['pdf', 'doc', 'docx', 'txt', 'rtf',
                         'jpg', 'JPG', 'jpeg', 'JPEG', 'JPGS',
                         'png', 'PNG', 'gif', 'GIF', 'bmp', 'BMP',
                         'tif', 'TIF', 'tiff', 'TIFF',
                         'mp4', 'mov', 'avi', 'mkv', 'mp3', 'wav', 'aac', 'm4a',
                         'zip', 'rar', '7z']

            # Open file dialog
            dialog = toga.OpenFileDialog(
                title="Select Files to Add to Library",
                file_types=file_types,
                multiple_select=True
            )

            selected_files = await self.app.main_window.dialog(dialog)

            if selected_files:
                files = selected_files if isinstance(selected_files, list) else [selected_files]
                logger.info(f"Desktop file dialog selected {len(files)} files")

                # Process directly using existing library backend logic
                await self._handle_desktop_content_added({
                    'option_id': 'file',
                    'files': files,
                    'action': 'added'
                })
            else:
                logger.info("Desktop file dialog: No files selected")

        except Exception as e:
            logger.error(f"Failed to handle desktop file dialog: {e}")

    async def _handle_desktop_folder_dialog(self):
        """Handle desktop folder dialog directly - bypasses intermediate views"""
        try:
            import toga
            from pathlib import Path

            logger.info("Opening desktop folder dialog directly")

            # Open folder dialog
            dialog = toga.SelectFolderDialog(
                title="Select Folders to Add to Library",
                multiple_select=True
            )

            selected_folders = await self.app.main_window.dialog(dialog)

            if selected_folders:
                folders = selected_folders if isinstance(selected_folders, list) else [selected_folders]
                logger.info(f"Desktop folder dialog selected {len(folders)} folders")

                # Process directly using existing library backend logic
                await self._handle_desktop_content_added({
                    'option_id': 'folder',
                    'folders': folders,
                    'action': 'added'
                })
            else:
                logger.info("Desktop folder dialog: No folders selected")

        except Exception as e:
            logger.error(f"Failed to handle desktop folder dialog: {e}")

    async def _handle_desktop_content_added(self, content_info):
        """Handle content added via desktop dialogs - delegates to library service"""
        try:
            logger.info(f"Desktop dialog content added: {content_info}")

            if not hasattr(self.app, 'library_service') or not self.app.library_service:
                logger.error("Library service not available")
                return

            option_id = content_info.get('option_id')

            if option_id == 'file' and 'files' in content_info:
                # Delegate file import to library service (shared code path with CLI)
                files = content_info['files']
                if files:
                    try:
                        # Check if there's a pending operation (from Link File command)
                        operation = "copy"  # Default
                        if hasattr(self.app, 'library_view') and hasattr(self.app.library_view, '_pending_operation'):
                            operation = self.app.library_view._pending_operation
                            delattr(self.app.library_view, '_pending_operation')
                            logger.info(f"Using pending operation: {operation}")

                        result = await self.app.library_service.import_files_for_ui(
                            files=files,
                            collection_name=None,  # Auto-generate name
                            operation=operation
                        )

                        if result['success']:
                            logger.info(f"Successfully imported {result['files_imported']} files to collection: {result['collection_name']}")
                        else:
                            logger.error(f"File import failed: {result['error_message']}")
                    except Exception as e:
                        logger.error(f"Failed to import files: {e}")
                        import traceback
                        traceback.print_exc()

            elif option_id == 'folder' and 'folders' in content_info:
                # Delegate folder import to library service (shared code path with CLI)
                folders = content_info['folders']

                # Check if there's a pending operation (from Link Folder command)
                operation = "copy"  # Default
                if hasattr(self.app, 'library_view') and hasattr(self.app.library_view, '_pending_operation'):
                    operation = self.app.library_view._pending_operation
                    delattr(self.app.library_view, '_pending_operation')
                    logger.info(f"Using pending operation: {operation}")

                for folder_path in folders:
                    try:
                        result = await self.app.library_service.import_folder_for_ui(
                            folder_path=folder_path,
                            collection_name=None,  # Auto-generate name
                            operation=operation  # Use specified operation (copy or link)
                        )

                        if result['success']:
                            logger.info(f"Successfully imported folder: {result['collection_name']}")
                        else:
                            logger.error(f"Folder import failed: {result['error_message']}")
                    except Exception as e:
                        logger.error(f"Failed to import folder {folder_path}: {e}")
                        import traceback
                        traceback.print_exc()

            # Refresh library view to show the new collections
            if hasattr(self.app, 'library_service'):
                await self.app.library_service.refresh_collections()
                logger.info("Refreshed library view after imports")

            # Navigate back to library to show the new collections
            self.navigate_to_library()

        except Exception as e:
            logger.error(f"Failed to handle desktop content added: {e}")
            import traceback
            traceback.print_exc()

    async def _handle_camera_content_added(self, content_info):
        """Handle camera photos added via camera view - delegates to library service"""
        try:
            logger.info(f"Camera photo added: {content_info}")

            # Extract photo path from content_info
            photo_path = content_info.get('photo_path')
            if not photo_path:
                logger.warning("No photo path provided in content_info")
                return

            if not hasattr(self.app, 'library_service') or not self.app.library_service:
                logger.error("Library service not available")
                return

            # Get current collection if we're in one (optional - camera creates its own collection)
            collection_id = None
            if self.current_state.context == NavigationContext.COLLECTION:
                collection_id = self.current_state.collection_id

            try:
                # Delegate to library service
                result = await self.app.library_service.add_camera_photo_for_ui(
                    photo_path=photo_path,
                    collection_id=collection_id  # None = create/use "Camera Photos" collection
                )

                if result['success']:
                    logger.info(f"Successfully added camera photo to collection: {result['collection_name']}")
                else:
                    logger.error(f"Camera photo import failed: {result['error_message']}")
            except Exception as e:
                logger.error(f"Failed to import camera photo: {e}")
                import traceback
                traceback.print_exc()

            # Refresh library view to show the new photo
            if hasattr(self.app, 'library_service'):
                await self.app.library_service.refresh_collections()
                logger.info("Refreshed library view after camera photo import")

            # Navigate back to library to show the updated collection
            self.navigate_to_library()

        except Exception as e:
            logger.error(f"Failed to handle camera content added: {e}")
            import traceback
            traceback.print_exc()

    async def _handle_url_content_added(self, content_info):
        """Handle URLs added via URL add view - delegates to library service"""
        try:
            logger.info(f"URL content added: {content_info}")

            # Extract URLs from content_info
            urls = content_info.get('urls', [])
            if not urls:
                logger.warning("No URLs provided in content_info")
                return

            if not hasattr(self.app, 'library_service') or not self.app.library_service:
                logger.error("Library service not available")
                return

            # Determine which collection to add to:
            # - If we're viewing a collection, add to that collection
            # - If we're in library view with no selection, create new collection
            collection_id = None
            if hasattr(self.app, 'main_window') and self.app.main_window:
                main_window = self.app.main_window
                # Check if collection_view exists and has a collection selected
                if hasattr(main_window, 'collection_view') and main_window.collection_view:
                    collection_view = main_window.collection_view
                    if hasattr(collection_view, 'collection_id') and collection_view.collection_id:
                        collection_id = collection_view.collection_id
                        logger.info(f"Adding URL to current collection: {collection_id}")
                # Check if library_view exists and has a collection selected
                elif hasattr(main_window, 'library_view') and main_window.library_view:
                    library_view = main_window.library_view
                    if hasattr(library_view, 'get_selected_collection'):
                        selected = library_view.get_selected_collection()
                        if selected:
                            collection_id = selected.get('id')
                            logger.info(f"Adding URL to selected collection from library: {collection_id}")

            if not collection_id:
                logger.info("No collection selected - will create new collection for URL")

            # Process each URL via library service
            for url in urls:
                try:
                    # Delegate to library service (shared code path with CLI)
                    result = await self.app.library_service.import_url_for_ui(
                        url=url,
                        collection_id=collection_id,  # Use current collection or None to create new
                        collection_name=None,  # Auto-generate name if creating new
                        description=None,  # Auto-generate description
                        timeout=600,
                        max_items=1000,
                        download_mode="link"  # Default to link mode for EAP
                    )

                    if result['success']:
                        logger.info(f"Successfully imported {result['files_imported']} items from {url}")
                    else:
                        logger.error(f"Import failed: {result['error_message']}")

                except Exception as e:
                    logger.error(f"Failed to import URL {url}: {e}")
                    import traceback
                    traceback.print_exc()

            # Refresh library view to show the new collections
            if hasattr(self.app, 'library_service'):
                await self.app.library_service.refresh_collections()
                logger.info("Refreshed library view after URL imports")

            # Navigate back to library to show the new collections
            self.navigate_to_library()

        except Exception as e:
            logger.error(f"Failed to handle URL content added: {e}")
            import traceback
            traceback.print_exc()

    # ===== SIMPLE NAVIGATION HELPERS =====

    @staticmethod
    def create_back_handler(app) -> Callable:
        """Create a smart back handler for toolbar buttons with add view fallback"""
        def back_handler(widget=None):
            if hasattr(app, 'view_integration') and app.view_integration:
                navigation_controller = app.view_integration.get_navigation_controller()
                if navigation_controller:
                    # Try NavigationController back navigation first
                    success = navigation_controller.navigate_back()

                    # If NavigationController has no history, check if we're in an ADD context
                    if not success:
                        current_state = navigation_controller.get_current_state()
                        if current_state.context == NavigationContext.ADD:
                            # We're in an add view with no navigation history
                            # Check if we're in a specific add view or the main add dialog
                            modal_type = current_state.metadata.get('modal_type', '')

                            if modal_type in ['url', 'file', 'folder', 'camera']:
                                # We're in a specific add view - navigate back to library directly
                                logger.info(f"ADD {modal_type} back navigation - returning to library")
                                navigation_controller.navigate_to_library()
                            else:
                                # Unknown add context - fall back to closing modal
                                logger.info("No navigation history in unknown ADD context - falling back to modal close")
                                navigation_controller.navigate_back()
                        else:
                            logger.debug("NavigationController back failed, but not in ADD context")
        return back_handler

    # ===== BACKWARD COMPATIBILITY =====

    def add_callback(self, event_name: str, callback):
        """Backward compatibility method - routes callbacks to event bus"""
        try:
            from .navigation_event_bus import subscribe_to_navigation, NavigationEvents

            if event_name == 'state_changed':
                # Convert state_changed callback to event bus subscription
                def wrapper(event):
                    try:
                        # Call the callback with the navigation state
                        callback(self.current_state)
                    except Exception as e:
                        logger.error(f"Error in callback wrapper: {e}")

                subscribe_to_navigation(NavigationEvents.STATE_CHANGED, wrapper)
                logger.debug(f"Added backward compatibility callback for '{event_name}'")
            else:
                logger.warning(f"Unknown callback event: {event_name}")

        except Exception as e:
            logger.error(f"Failed to add callback: {e}")

    def remove_callback(self, event_name: str, callback):
        """Backward compatibility method - no-op since we can't easily unsubscribe"""
        logger.debug(f"remove_callback called for '{event_name}' (no-op in event bus version)")