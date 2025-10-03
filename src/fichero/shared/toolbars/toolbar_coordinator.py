"""
Toolbar Coordinator for Fichero

Manages coordination between top and bottom toolbars, especially for edit mode.
Handles NavigationController integration and ensures proper HIG compliance.
"""

import toga
import logging
from typing import Optional, Callable, Protocol, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class EditModeState(Enum):
    """Edit mode states following iOS HIG patterns"""
    NORMAL = "normal"
    EDIT = "edit"
    MULTI_SELECT = "multi_select"


class ToolbarProtocol(Protocol):
    """Protocol that toolbars must implement for coordination"""

    def set_edit_mode(self, state: EditModeState, context: Dict[str, Any] = None) -> None:
        """Set the edit mode state with optional context"""
        ...

    def get_edit_mode(self) -> EditModeState:
        """Get current edit mode state"""
        ...


class ToolbarCoordinator:
    """
    Coordinates toolbar behavior across top and bottom toolbars.

    Responsibilities:
    - Edit mode state management
    - NavigationController integration
    - Platform-specific behavior (iOS vs macOS HIG)
    - Communication between toolbars
    """

    def __init__(self, app, is_mobile: bool = None):
        """Initialize toolbar coordinator"""
        self.app = app
        self.is_mobile = is_mobile if is_mobile is not None else app.is_mobile

        # Registered toolbars
        self.top_toolbar: Optional[ToolbarProtocol] = None
        self.bottom_toolbar: Optional[ToolbarProtocol] = None

        # Edit mode state
        self._edit_mode_state = EditModeState.NORMAL
        self._edit_context: Dict[str, Any] = {}

        # Callbacks
        self.on_edit_mode_change: Optional[Callable[[EditModeState, Dict[str, Any]], None]] = None
        self.on_navigation_back: Optional[Callable] = None

        # Collection management callbacks
        self.get_selected_collections: Optional[Callable[[], List[str]]] = None
        self.handle_edit_collection: Optional[Callable[[List[str]], None]] = None
        self.handle_delete_collection: Optional[Callable[[List[str]], None]] = None
        self.handle_sort: Optional[Callable[[], None]] = None

        logger.info(f"ToolbarCoordinator initialized (mobile: {self.is_mobile})")

    def register_top_toolbar(self, toolbar: ToolbarProtocol) -> None:
        """Register the top toolbar for coordination"""
        self.top_toolbar = toolbar
        logger.debug("Top toolbar registered with coordinator")

    def register_bottom_toolbar(self, toolbar: ToolbarProtocol) -> None:
        """Register the bottom toolbar for coordination"""
        self.bottom_toolbar = toolbar
        logger.debug("Bottom toolbar registered with coordinator")

    def set_edit_mode(self, state: EditModeState, context: Dict[str, Any] = None) -> None:
        """
        Set edit mode across all registered toolbars

        Args:
            state: The new edit mode state
            context: Optional context (selected items, etc.)
        """
        try:
            if context is None:
                context = {}

            # When entering edit mode, populate context with edit actions
            if state == EditModeState.EDIT:
                # Get the platform-specific edit actions
                edit_context = self.create_edit_actions_context()
                logger.debug(f"ToolbarCoordinator: Created edit context: {edit_context}")
                context.update(edit_context)
                logger.debug(f"ToolbarCoordinator: Final context keys: {list(context.keys())}")

            self._edit_mode_state = state
            self._edit_context = context.copy()

            # Update all registered toolbars
            if self.top_toolbar:
                logger.debug(f"ToolbarCoordinator: Calling top_toolbar.set_edit_mode({state.value}) with context keys: {list(context.keys())}")
                self.top_toolbar.set_edit_mode(state, context)

            if self.bottom_toolbar:
                logger.debug(f"ToolbarCoordinator: Calling bottom_toolbar.set_edit_mode({state.value}) with context keys: {list(context.keys())}")
                self.bottom_toolbar.set_edit_mode(state, context)

            # Notify listeners
            if self.on_edit_mode_change:
                self.on_edit_mode_change(state, context)

            logger.info(f"Edit mode changed to: {state.value}")

        except Exception as e:
            logger.error(f"Failed to set edit mode: {e}")

    def get_edit_mode(self) -> EditModeState:
        """Get current edit mode state"""
        return self._edit_mode_state

    def get_edit_context(self) -> Dict[str, Any]:
        """Get current edit context"""
        return self._edit_context.copy()

    def toggle_edit_mode(self) -> None:
        """Toggle between normal and edit mode"""
        if self._edit_mode_state == EditModeState.NORMAL:
            self.set_edit_mode(EditModeState.EDIT)
        else:
            self.set_edit_mode(EditModeState.NORMAL)

    def update_edit_context(self, updates: Dict[str, Any]) -> None:
        """Update edit context and notify toolbars"""
        self._edit_context.update(updates)

        # Notify toolbars of context change
        if self.top_toolbar:
            self.top_toolbar.set_edit_mode(self._edit_mode_state, self._edit_context)

        if self.bottom_toolbar:
            self.bottom_toolbar.set_edit_mode(self._edit_mode_state, self._edit_context)

    def setup_navigation_controller_integration(self) -> None:
        """Set up integration with NavigationController"""
        try:
            from fichero.shared.navigation.navigation_controller import NavigationController

            # Create back handler if none exists
            if not self.on_navigation_back:
                self.on_navigation_back = NavigationController.create_back_handler(self.app)

            logger.debug("NavigationController integration set up")

        except ImportError as e:
            logger.warning(f"NavigationController not available: {e}")
        except Exception as e:
            logger.error(f"Failed to set up NavigationController integration: {e}")

    def get_hig_specs(self) -> Dict[str, Any]:
        """Get Human Interface Guidelines specifications for current platform"""
        if self.is_mobile:
            # iOS HIG specifications
            return {
                "platform": "ios",
                "top_toolbar_height": 44,  # Navigation bar
                "bottom_toolbar_height": 49,  # Tab bar (83 with home indicator)
                "button_min_touch_target": 44,
                "icon_size_regular": 25,
                "icon_size_compact": 18,
                "margin_horizontal": 16,
                "margin_vertical": 8,
                "corner_radius": 8,
                "animation_duration": 0.3
            }
        else:
            # macOS HIG specifications
            return {
                "platform": "macos",
                "top_toolbar_height": 52,  # Standard toolbar
                "bottom_toolbar_height": 0,  # Usually hidden on macOS
                "button_min_touch_target": 32,
                "icon_size_regular": 16,
                "icon_size_compact": 13,
                "margin_horizontal": 12,
                "margin_vertical": 6,
                "corner_radius": 6,
                "animation_duration": 0.25
            }

    def create_edit_actions_context(self, selected_count: int = 0) -> Dict[str, Any]:
        """Create standard edit actions context with library view support"""
        hig = self.get_hig_specs()

        # Try to detect platform features for library view
        platform_features = None
        try:
            from fichero.windows.add.platform_features import detect_platform_features
            platform_features = detect_platform_features(self.app)
            logger.debug(f"ToolbarCoordinator: Detected platform features: {platform_features}")
        except Exception as e:
            logger.warning(f"Failed to detect platform features: {e}")

        # Create library view context automatically (assume library view if no specific context provided)
        library_context = self.create_view_edit_context("library", platform_features.__dict__ if platform_features else None)
        logger.debug(f"ToolbarCoordinator: Created library edit context: {list(library_context.keys())}")

        base_context = {
            "selected_count": selected_count,
            "has_selection": selected_count > 0,
            "platform_specs": hig,
            "actions": {
                "delete": selected_count > 0,
                "select_all": True,
                "deselect_all": selected_count > 0,
                "share": selected_count > 0,
                "copy": selected_count > 0,
                "move": selected_count > 0
            }
        }

        # Merge library context into base context
        base_context.update(library_context)
        return base_context

    def create_view_edit_context(self, view_type: str, platform_features: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create view-specific edit context for add functionality"""
        hig = self.get_hig_specs()

        base_context = {
            "view_type": view_type,
            "platform_specs": hig,
            "edit_type": "add_items"
        }

        if view_type == "library":
            # Library view add options
            add_actions = []
            if platform_features:
                if platform_features.get("has_url_input", True):
                    add_actions.append({"id": "url", "title": "Add URL", "icon": "resources/icons/toolbar/link.png"})
                if platform_features.get("has_web_view", True):
                    add_actions.append({"id": "website", "title": "Add Website", "icon": "resources/icons/toolbar/globe.png"})
                if platform_features.get("has_file_dialog", False):
                    add_actions.append({"id": "file", "title": "Add File", "icon": "resources/icons/toolbar/document.png"})
                if platform_features.get("has_folder_dialog", False):
                    add_actions.append({"id": "folder", "title": "Add Folder", "icon": "resources/icons/toolbar/add_folder.png"})
                if platform_features.get("has_camera", False):
                    add_actions.append({"id": "camera", "title": "Add Picture", "icon": "resources/icons/toolbar/camera.png"})

            base_context["add_actions"] = add_actions

            # Separate top and bottom edit actions for library view
            # Top toolbar actions (sort button)
            top_edit_actions = [
                {"id": "sort", "title": "Sort", "icon": "resources/icons/toolbar/chevron.up@10x.png"}
            ]

            # Bottom toolbar actions (add/create actions + add collection)
            bottom_edit_actions = add_actions + [
                {"id": "add_collection", "title": "Add Collection", "icon": "resources/icons/toolbar/add_collection.png"}
            ]

            base_context["top_edit_actions"] = top_edit_actions
            base_context["bottom_edit_actions"] = bottom_edit_actions

            # Keep old collection_actions for backward compatibility (now empty since we split them)
            base_context["collection_actions"] = []

        elif view_type == "collection":
            # Collection view add options (similar to library)
            base_context["add_actions"] = []

        elif view_type == "preview":
            # Preview view edit options (sharing, annotations, etc.)
            base_context["add_actions"] = []

        return base_context

    def get_navigation_handler(self, action_id: str) -> Optional[Callable]:
        """Get NavigationController handler for add action"""
        try:
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    action_map = {
                        "url": nav_controller.navigate_to_add_url,
                        "website": nav_controller.navigate_to_add_website,
                        "file": nav_controller.navigate_to_add_file,
                        "folder": nav_controller.navigate_to_add_folder,
                        "camera": nav_controller.navigate_to_add_camera,
                        # Collection management actions
                        "add_collection": self._handle_add_collection,
                        "edit_collection": self._handle_edit_collection,
                        "delete_collection": self._handle_delete_collection,
                        "sort": self._handle_sort
                    }
                    return action_map.get(action_id)
        except Exception as e:
            logger.error(f"Failed to get navigation handler for {action_id}: {e}")

        return None

    def _handle_add_collection(self, widget=None):
        """Handle Add Collection button press"""
        try:
            logger.info("Add Collection button pressed")
            # TODO: Navigate to add collection view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    # For now, use a simple input dialog (will implement proper view later)
                    self._show_add_collection_dialog()
        except Exception as e:
            logger.error(f"Failed to handle add collection: {e}")

    def _handle_edit_collection(self, widget=None):
        """Handle Edit Collection button press"""
        try:
            logger.info("Edit Collection button pressed")

            # Get selected collections from library view
            if self.get_selected_collections:
                selected_collections = self.get_selected_collections()
                if selected_collections:
                    logger.info(f"Editing {len(selected_collections)} collections")
                    if self.handle_edit_collection:
                        self.handle_edit_collection(selected_collections)
                    else:
                        logger.warning("No edit collection handler registered")
                else:
                    logger.warning("No collections selected for editing")
            else:
                logger.warning("No selection getter registered")

        except Exception as e:
            logger.error(f"Failed to handle edit collection: {e}")

    def _handle_delete_collection(self, widget=None):
        """Handle Delete Collection button press"""
        try:
            logger.info("Delete Collection button pressed")

            # Get selected collections from library view
            if self.get_selected_collections:
                selected_collections = self.get_selected_collections()
                if selected_collections:
                    logger.info(f"Deleting {len(selected_collections)} collections")
                    if self.handle_delete_collection:
                        self.handle_delete_collection(selected_collections)
                    else:
                        logger.warning("No delete collection handler registered")
                else:
                    logger.warning("No collections selected for deletion")
            else:
                logger.warning("No selection getter registered")

        except Exception as e:
            logger.error(f"Failed to handle delete collection: {e}")

    def _handle_sort(self, widget=None):
        """Handle Sort button press"""
        try:
            logger.info("Sort button pressed")
            if self.handle_sort:
                self.handle_sort()
            else:
                logger.warning("No sort handler registered")

        except Exception as e:
            logger.error(f"Failed to handle sort: {e}")

    def _show_add_collection_dialog(self):
        """Show Add Collection dialog"""
        try:
            import toga

            # Simple input dialog for now
            dialog = toga.InfoDialog(
                title="Add Collection",
                message="Collection creation feature coming soon!"
            )
            self.app.main_window.info_dialog(dialog)
        except Exception as e:
            logger.error(f"Failed to show add collection dialog: {e}")

    def _show_edit_collection_dialog(self, collection):
        """Show Edit Collection dialog"""
        try:
            import toga

            dialog = toga.InfoDialog(
                title="Edit Collection",
                message=f"Edit collection '{collection}' feature coming soon!"
            )
            self.app.main_window.info_dialog(dialog)
        except Exception as e:
            logger.error(f"Failed to show edit collection dialog: {e}")

    def _show_delete_collection_confirmation(self, collection):
        """Show Delete Collection confirmation dialog"""
        try:
            import toga

            dialog = toga.QuestionDialog(
                title="Delete Collection",
                message=f"Are you sure you want to delete the collection '{collection}'?\n\nThis action cannot be undone."
            )

            async def handle_result(dialog, result):
                if result:
                    logger.info(f"User confirmed deletion of collection: {collection}")
                    # TODO: Implement actual deletion
                    success_dialog = toga.InfoDialog(
                        title="Collection Deleted",
                        message=f"Collection '{collection}' has been deleted."
                    )
                    self.app.main_window.info_dialog(success_dialog)
                else:
                    logger.info("User cancelled collection deletion")

            self.app.main_window.question_dialog(dialog, handle_result)
        except Exception as e:
            logger.error(f"Failed to show delete collection confirmation: {e}")