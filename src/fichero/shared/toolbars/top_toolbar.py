"""
Top Toolbar for Fichero - HIG Compliant

Provides HIG-compliant top toolbar with:
- NavigationController integration
- Edit mode support with bottom toolbar coordination
- Platform-specific behavior (iOS/macOS)
- Clean composition-based button management
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, Dict, Any

from fichero.shared.toolbars.base_toolbar import BaseToolbar
from fichero.shared.toolbars.toolbar_coordinator import ToolbarCoordinator, EditModeState

logger = logging.getLogger(__name__)


class TopToolbar(BaseToolbar):
    """HIG-compliant top toolbar with edit mode and NavigationController support"""

    def __init__(self,
                 app,
                 title: str = "",
                 auto_mobile_nav: bool = True,
                 is_mobile: bool = None,
                 coordinator: Optional[ToolbarCoordinator] = None):
        """
        Initialize top toolbar

        Args:
            app: The Toga application
            title: Title to show (used for mobile back navigation)
            auto_mobile_nav: Whether to automatically add mobile back button + title
            is_mobile: Override mobile detection
            coordinator: ToolbarCoordinator for edit mode management
        """
        self.title = title
        self.auto_mobile_nav = auto_mobile_nav

        # Initialize base toolbar
        super().__init__(app, is_mobile, coordinator)

        # Navigation callbacks
        self.on_back: Optional[Callable] = None
        self.on_title_click: Optional[Callable] = None

        # Edit mode widgets
        self.edit_button: Optional[toga.Button] = None
        self.done_button: Optional[toga.Button] = None

        # Navigation widgets
        self.back_button: Optional[toga.Button] = None
        self.title_label: Optional[toga.Label] = None

        # Setup NavigationController integration
        self.setup_navigation_controller_integration()

        # Register with coordinator if provided
        if self.coordinator:
            self.coordinator.register_top_toolbar(self)

        # Create toolbar content
        self._create_toolbar()

        logger.debug(f"TopToolbar initialized (title: {title}, auto_nav: {auto_mobile_nav})")

    def setup_navigation_controller_integration(self) -> None:
        """Set up NavigationController integration"""
        try:
            from fichero.shared.navigation.navigation_controller import NavigationController
            from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation, unsubscribe_from_navigation, NavigationEvents

            if not self.on_back:
                self.on_back = NavigationController.create_back_handler(self.app)

            # Subscribe to navigation state changes to update title dynamically
            def on_state_changed(event_data):
                try:
                    self._update_contextual_title()
                except Exception as e:
                    logger.error(f"Failed to update title on state change: {e}")

            # Store callback reference for cleanup
            self._nav_state_callback = on_state_changed
            subscribe_to_navigation(NavigationEvents.STATE_CHANGED, self._nav_state_callback)
            logger.debug("NavigationController integration and title updates set up for TopToolbar")

        except ImportError:
            logger.warning("NavigationController not available")

    def cleanup_callbacks(self):
        """Clean up navigation event subscriptions"""
        try:
            if hasattr(self, '_nav_state_callback'):
                from fichero.shared.navigation.navigation_event_bus import unsubscribe_from_navigation, NavigationEvents
                unsubscribe_from_navigation(NavigationEvents.STATE_CHANGED, self._nav_state_callback)
                delattr(self, '_nav_state_callback')
                logger.debug("TopToolbar navigation callbacks cleaned up")
        except Exception as e:
            logger.error(f"Failed to cleanup TopToolbar callbacks: {e}")

    def _create_toolbar(self) -> None:
        """Create the top toolbar content"""
        try:
            # Clear existing content
            self.clear_content()

            # Add navigation based on configuration
            if self.auto_mobile_nav:
                self._add_navigation_elements()

            # Add edit mode support only if coordinator is provided
            if self.coordinator:
                self._add_edit_mode_support()

            # Add custom content hook for subclasses
            self._add_custom_content()

            logger.debug("TopToolbar content created")

        except Exception as e:
            logger.error(f"Failed to create TopToolbar: {e}")

    def _add_navigation_elements(self) -> None:
        """Add navigation elements based on platform and context"""
        try:
            if self.is_mobile:
                # iOS navigation pattern
                if self.auto_mobile_nav:  # Child views get back button
                    self._add_back_button()
                # Add context-aware title if NavigationController says we should
                self._add_contextual_title()
            else:
                # macOS navigation pattern
                if self.auto_mobile_nav:  # Child views
                    self._add_back_button()
                # Add context-aware title if NavigationController says we should
                self._add_contextual_title()

        except Exception as e:
            logger.error(f"Failed to add navigation elements: {e}")

    def _add_back_button(self) -> None:
        """Add HIG-compliant back button with dynamic parent context"""
        try:
            # Get dynamic back button text based on navigation context
            back_text = self._get_dynamic_back_text()

            self.back_button = self.add_button_left(
                text=back_text,
                on_press=self._on_back_pressed,
                button_id="back"
            )

        except Exception as e:
            logger.error(f"Failed to add back button: {e}")

    def _get_dynamic_back_text(self) -> str:
        """Get simple back button - just chevron without text"""
        return "‹"

    def _add_contextual_title(self) -> None:
        """Add context-aware title from NavigationController (mobile only)"""
        try:
            # On desktop, title is shown in window title bar, not toolbar
            # On mobile, we need the title in the toolbar for navigation context
            logger.info(f"🔍 _add_contextual_title called: is_mobile={self.is_mobile}")
            if not self.is_mobile:
                logger.info("✅ Desktop mode: skipping toolbar title (shown in window title bar)")
                return

            # Mobile: Get title and visibility from NavigationController
            if hasattr(self.app, 'view_integration') and hasattr(self.app.view_integration, 'navigation_controller'):
                nav_controller = self.app.view_integration.navigation_controller

                # Check if we should show title for this context
                if nav_controller.should_show_title():
                    title_text = nav_controller.get_current_title()
                    if title_text:
                        self.title_label = self.add_title(
                            title=title_text,
                            on_click=self.on_title_click
                        )
            # Fallback to manual title if NavigationController not available
            elif self.title:
                self.title_label = self.add_title(
                    title=self.title,
                    on_click=self.on_title_click
                )

        except Exception as e:
            logger.error(f"Failed to add contextual title: {e}")

    def _update_contextual_title(self) -> None:
        """Update title when navigation state changes"""
        try:
            # Clear existing title first
            if self.title_label and self.center_content:
                self.center_content.clear()
                self.title_label = None

            # Re-add contextual title with current state
            self._add_contextual_title()
            logger.debug("Contextual title updated for state change")

        except Exception as e:
            logger.error(f"Failed to update contextual title: {e}")

    def _add_title_label(self) -> None:
        """Add title label to center (legacy method - use _add_contextual_title instead)"""
        try:
            if self.title:
                self.title_label = self.add_title(
                    title=self.title,
                    on_click=self.on_title_click
                )

        except Exception as e:
            logger.error(f"Failed to add title label: {e}")

    def _add_edit_mode_support(self) -> None:
        """Add edit mode button support - but don't add to UI yet"""
        try:
            # Create edit button with right-aligned styling using base toolbar's system
            self.edit_button = self.create_button(
                text=_("Edit"),
                on_press=self._on_edit_pressed,
                style_class="right_aligned"  # Use proper right-aligned style
            )
            self.buttons["edit"] = self.edit_button

            # Create done button with left-aligned styling for edit mode
            self.done_button = self.create_button(
                text=_("Done"),
                on_press=self._on_done_pressed,
                style_class="default"  # Standard styling for left side
            )
            self.buttons["done"] = self.done_button

            logger.debug("Edit mode buttons created using standard toolbar styling")

        except Exception as e:
            logger.error(f"Failed to add edit mode support: {e}")

    def _add_custom_content(self) -> None:
        """Hook for subclasses to add custom content"""
        pass

    # Event handlers
    def _on_back_pressed(self, widget) -> None:
        """Handle back button press"""
        try:
            if self.on_back:
                self.on_back()
            else:
                logger.warning("No back handler configured")

        except Exception as e:
            logger.error(f"Failed to handle back press: {e}")

    def _on_edit_pressed(self, widget) -> None:
        """Handle edit button press"""
        try:
            if self.coordinator:
                self.coordinator.set_edit_mode(EditModeState.EDIT)
            else:
                # Fallback without coordinator
                self.set_edit_mode(EditModeState.EDIT)

        except Exception as e:
            logger.error(f"Failed to handle edit press: {e}")

    def _on_done_pressed(self, widget) -> None:
        """Handle done button press"""
        try:
            if self.coordinator:
                self.coordinator.set_edit_mode(EditModeState.NORMAL)
            else:
                # Fallback without coordinator
                self.set_edit_mode(EditModeState.NORMAL)

        except Exception as e:
            logger.error(f"Failed to handle done press: {e}")

    # ToolbarProtocol implementation
    def set_edit_mode(self, state: EditModeState, context: Dict[str, Any] = None) -> None:
        """Set edit mode and update UI with smart rebuilding"""
        try:
            # Update base state
            super().set_edit_mode(state, context)

            # Universal edit mode handling (works on all platforms)
            if state == EditModeState.EDIT:
                self._enter_edit_mode(context)
            else:
                self._exit_edit_mode()

            logger.debug(f"TopToolbar edit mode set to {state.value}")

        except Exception as e:
            logger.error(f"Failed to set edit mode: {e}")

    def _enter_edit_mode(self, context: Dict[str, Any] = None) -> None:
        """Enter universal edit mode (inspired by iOS HIG but works on all platforms)"""
        try:
            logger.debug(f"TopToolbar._enter_edit_mode() called with context keys: {list(context.keys()) if context else 'None'}")

            # Clear all content
            self.clear_content()

            # iOS HIG: Done button on left
            if self.done_button:
                self.left_content.add(self.done_button)
                logger.debug("Added Done button to left side")

            # iOS HIG: Title disappears in edit mode (center stays empty)

            # Add top edit actions (delete/rename) to right side in edit mode
            if context:
                top_edit_actions = context.get("top_edit_actions", [])
                logger.debug(f"Found top_edit_actions in context: {top_edit_actions}")

                if top_edit_actions:
                    logger.debug(f"Creating {len(top_edit_actions)} top edit buttons for right side")
                    for i, action in enumerate(top_edit_actions):
                        logger.debug(f"Creating button {i+1}: {action}")
                        # Support both text and icon buttons
                        button_text = action.get("text", None)
                        button_icon = action.get("icon", None)
                        button_label = action.get("label", None)
                        button = self.add_button_right(
                            text=button_text,  # Use text if provided
                            icon=button_icon,  # Use icon if provided
                            on_press=self._create_top_edit_button_handler(action["id"]),
                            button_id=f"edit_{action['id']}",
                            label=button_label  # Add label if provided
                        )
                        logger.debug(f"Button {i+1} added to toolbar successfully")

                    logger.debug(f"Added {len(top_edit_actions)} top edit actions to right side")
                else:
                    logger.warning("No top_edit_actions found in context!")
            else:
                logger.warning("No context provided to _enter_edit_mode()!")

            # Add any regular buttons that should persist (non-edit related)
            # For example, desktop preview button should remain
            for button_info in self._regular_buttons.values():
                if button_info.get("persist_in_edit", False):
                    self._add_button_to_position(button_info["button"], button_info["position"])

            logger.debug("Entered iOS HIG-compliant edit mode")

        except Exception as e:
            logger.error(f"Failed to enter iOS edit mode: {e}")

    def _exit_edit_mode(self) -> None:
        """Exit universal edit mode and restore normal toolbar state"""
        try:
            # Clear all content
            self.clear_content()

            # Restore navigation elements (back button and title) based on context
            self._add_navigation_elements()

            # Use base toolbar's smart rebuilding system for all buttons
            # This automatically handles all registered buttons including the Edit button
            for button_info in self._regular_buttons.values():
                self._add_button_to_position(button_info["button"], button_info["position"])

            logger.debug("Exited universal edit mode using smart button management")

        except Exception as e:
            logger.error(f"Failed to exit universal edit mode: {e}")

    def _create_top_edit_button_handler(self, action_id: str):
        """Create handler for top edit buttons (delete/rename)"""
        def handler(widget=None):
            try:
                if self.coordinator:
                    # Use the coordinator's navigation handler
                    nav_handler = self.coordinator.get_navigation_handler(action_id)
                    if nav_handler:
                        nav_handler(widget)
                    else:
                        logger.warning(f"No handler found for top edit action: {action_id}")
                else:
                    logger.warning("No coordinator available for top edit action handling")
            except Exception as e:
                logger.error(f"Failed to handle top edit action {action_id}: {e}")

        return handler

    # Composition methods for backward compatibility
    def add_centered_title_only(self, title_text: str, on_title_click: Optional[Callable] = None) -> toga.Label:
        """Add centered title (backward compatibility method)"""
        self.title = title_text
        self.on_title_click = on_title_click
        return self.add_title(title_text, on_title_click)

    def add_title_only(self, title_text: str) -> toga.Label:
        """Add title only (backward compatibility method)"""
        return self.add_centered_title_only(title_text)

    def add_button_text_right(self, text: str, on_press: Optional[Callable] = None, tooltip: Optional[str] = None) -> toga.Button:
        """Add text button to right (backward compatibility method)"""
        return self.add_button_right(text=text, on_press=on_press, tooltip=tooltip)

    def register_edit_callback(self, callback: Callable) -> None:
        """Register edit callback (backward compatibility method)"""
        if self.edit_button:
            self.edit_button.on_press = callback

    def register_navigation_callbacks(self, **kwargs) -> None:
        """Register navigation callbacks (backward compatibility method)"""
        # Handled automatically by NavigationController integration
        pass

