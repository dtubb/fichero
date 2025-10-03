"""
Bottom Toolbar for Fichero - HIG Compliant

Provides HIG-compliant bottom toolbar with:
- Edit mode variations (normal/edit buttons)
- iOS HIG compliance (tab bar style)
- macOS HIG compliance (minimal or hidden)
- ToolbarCoordinator integration
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, Dict, Any

from fichero.shared.toolbars.base_toolbar import BaseToolbar
from fichero.shared.toolbars.toolbar_coordinator import ToolbarCoordinator, EditModeState

logger = logging.getLogger(__name__)


class BottomToolbar(BaseToolbar):
    """HIG-compliant bottom toolbar with edit mode support"""

    def __init__(self,
                 app,
                 is_mobile: bool = None,
                 coordinator: Optional[ToolbarCoordinator] = None):
        """Initialize bottom toolbar with HIG compliance"""

        # Initialize base toolbar
        super().__init__(app, is_mobile, coordinator)

        # Edit mode button storage
        self.normal_buttons: Dict[str, toga.Button] = {}
        self.edit_buttons: Dict[str, toga.Button] = {}

        # Register with coordinator if provided
        if self.coordinator:
            self.coordinator.register_bottom_toolbar(self)

        # Create toolbar content
        self._create_toolbar()

        logger.debug(f"BottomToolbar initialized (mobile: {self.is_mobile})")

    def _get_hig_specs(self) -> Dict[str, Any]:
        """Override to get bottom toolbar specific HIG specs"""
        specs = super()._get_hig_specs()

        if self.is_mobile:
            # iOS HIG bottom toolbar (tab bar) specifications
            specs.update({
                "toolbar_height": 49,  # Tab bar height (83 with home indicator)
                "safe_area_bottom": 64,  # Home indicator safe area + 30px additional margin
                "icon_size": 22,  # Tab bar icon size (reduced for better density)
                "touch_target": 36,  # Minimum touch target (reduced for better density)
                "spacing": 2,  # Between buttons (much tighter spacing)
                "button_margin": 2,  # Individual button margin
                "additional_bottom_margin": 30  # Additional bottom margin for iOS
            })
        else:
            # Desktop: Enable bottom toolbar to match mobile behavior (user requested)
            specs.update({
                "toolbar_height": 44,  # Standard desktop toolbar height (match mobile)
                "icon_size": 16,
                "touch_target": 32,
                "spacing": 6
            })

        return specs

    def _create_base_container(self):
        """Create stable HIG-compliant base container for bottom toolbar"""
        try:
            # Desktop now shows bottom toolbar like mobile (user requested)
            # Create consistent toolbar container for both platforms

            # Create stable bottom toolbar container matching BaseToolbar pattern
            # Both mobile and desktop use the same structure now
            tab_bar_height = self.hig_specs["toolbar_height"]

            # Main container with consistent alignment system
            # Note: BaseView handles outer positioning, toolbar handles inner spacing only
            self.container = toga.Box(
                style=Pack(
                    direction=ROW,
                    height=tab_bar_height,
                    margin=0,  # No outer margins - BaseView handles container positioning
                    align_items="center",
                    # justify_content not supported in Toga - use flex instead
                    background_color="transparent",
                    flex=0  # Fixed height container
                )
            )

            # For backward compatibility, content points to the same container
            self.content = self.container

            # Left section: Flexible width that grows with content
            self.left_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=0,  # Size based on content, no fixed width
                    margin=(0, self.hig_specs["margin_horizontal"]),
                    align_items="center"
                )
            )

            # Center section: Balanced flex for proper centering
            self.center_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1,
                    margin=0,
                    align_items="center"
                )
            )

            # Right section: Flexible width that grows with content
            self.right_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=0,  # Size based on content, no fixed width
                    margin=(0, self.hig_specs["margin_horizontal"]),
                    align_items="center"
                )
            )

            # Add sections with stable ordering
            self.container.add(self.left_content)
            self.container.add(self.center_content)
            self.container.add(self.right_content)

            logger.debug("Stable HIG-compliant bottom toolbar container created")

        except Exception as e:
            logger.error(f"Failed to create bottom toolbar container: {e}")
            # Create minimal fallback
            self.container = toga.Box(style=Pack(direction=ROW, flex=0))
            self.content = self.container

    def _create_toolbar(self) -> None:
        """Create the bottom toolbar content"""
        try:
            if not self.is_mobile:
                # macOS: no bottom toolbar by default
                return

            # Create normal mode buttons
            self._create_normal_mode_buttons()

            # Create edit mode buttons (initially hidden)
            self._create_edit_mode_buttons()

            # Start in normal mode
            self._show_normal_mode()

            logger.debug("BottomToolbar content created")

        except Exception as e:
            logger.error(f"Failed to create BottomToolbar: {e}")

    def _create_normal_mode_buttons(self) -> None:
        """Create buttons for normal mode"""
        try:
            # Typical bottom toolbar buttons for normal mode
            # These can be customized by views using composition

            # Example normal mode buttons - views will add their own
            logger.debug("Normal mode button area prepared")

        except Exception as e:
            logger.error(f"Failed to create normal mode buttons: {e}")

    def _create_edit_mode_buttons(self) -> None:
        """Create buttons for edit mode"""
        try:
            # Common edit mode buttons
            self.edit_buttons["delete"] = self.create_button(
                text="Delete",
                on_press=self._on_delete_pressed,
                style_class="destructive"
            )

            self.edit_buttons["select_all"] = self.create_button(
                text="Select All",
                on_press=self._on_select_all_pressed
            )

            self.edit_buttons["share"] = self.create_button(
                text="Share",
                on_press=self._on_share_pressed
            )

            logger.debug("Edit mode buttons created")

        except Exception as e:
            logger.error(f"Failed to create edit mode buttons: {e}")

    def create_button(self,
                     text: Optional[str] = None,
                     icon: Optional[str] = None,
                     on_press: Optional[Callable] = None,
                     style_class: str = "default") -> toga.Button:
        """Create HIG-compliant bottom toolbar button"""
        try:
            # iOS tab bar button styling
            if style_class == "destructive":
                button_style = Pack(
                    background_color="#FF3B30",  # iOS red
                    color="white",
                    margin=(8, 12),
                    font_size=self.hig_specs["font_size_caption"]
                )
            elif style_class == "primary":
                button_style = Pack(
                    background_color="#007AFF",  # iOS blue
                    color="white",
                    margin=(8, 12),
                    font_size=self.hig_specs["font_size_caption"]
                )
            else:
                # Default tab bar button with tighter spacing
                button_style = Pack(
                    margin=(self.hig_specs.get("button_margin", 6), self.hig_specs.get("spacing", 8)),
                    font_size=self.hig_specs["font_size_caption"],
                    width=self.hig_specs["touch_target"],
                    height=self.hig_specs["touch_target"]
                )

            # Create button
            if icon:
                try:
                    icon_resource = toga.Icon(icon)
                    # Use consistent icon sizing to match BaseToolbar
                    icon_button_style = Pack(
                        width=self.hig_specs["icon_size"] + 16,  # Icon size + padding
                        height=self.hig_specs["icon_size"] + 16,  # Icon size + padding
                        margin=button_style.margin if hasattr(button_style, 'margin') else (8, 12),
                        font_size=button_style.font_size if hasattr(button_style, 'font_size') else self.hig_specs["font_size_caption"]
                    )
                    button = toga.Button(icon=icon_resource, on_press=on_press, style=icon_button_style)
                except:
                    button = toga.Button(text=text or "⚙", on_press=on_press, style=button_style)
            else:
                button = toga.Button(text=text or "Button", on_press=on_press, style=button_style)

            return button

        except Exception as e:
            logger.error(f"Failed to create bottom toolbar button: {e}")
            return toga.Button(text=text or "Button", on_press=on_press)

    # ToolbarProtocol implementation
    def set_edit_mode(self, state: EditModeState, context: Dict[str, Any] = None) -> None:
        """Set edit mode and update button layout using smart system"""
        try:
            # Update base state
            super().set_edit_mode(state, context)

            # Use smart system for context-aware button management
            if state == EditModeState.EDIT:
                self._show_smart_edit_mode(context)
            else:
                self._show_smart_normal_mode()

            logger.debug(f"BottomToolbar edit mode set to {state.value}")

        except Exception as e:
            logger.error(f"Failed to set edit mode in BottomToolbar: {e}")

    def _show_normal_mode(self) -> None:
        """Show normal mode buttons, hide edit mode buttons"""
        try:
            # Clear current edit mode buttons if any
            self._clear_edit_mode_buttons()

            # Restore normal mode buttons that were added by views
            self._restore_normal_mode_buttons()

            logger.debug("BottomToolbar showing normal mode")

        except Exception as e:
            logger.error(f"Failed to show normal mode: {e}")

    def _clear_edit_mode_buttons(self) -> None:
        """Clear edit mode buttons from UI"""
        try:
            # Remove dynamically created edit mode buttons
            for child in list(self.left_content.children):
                if hasattr(child, '_is_edit_mode_button'):
                    self.left_content.remove(child)

            for child in list(self.center_content.children):
                if hasattr(child, '_is_edit_mode_button'):
                    self.center_content.remove(child)

            for child in list(self.right_content.children):
                if hasattr(child, '_is_edit_mode_button'):
                    self.right_content.remove(child)

        except Exception as e:
            logger.error(f"Failed to clear edit mode buttons: {e}")

    def _restore_normal_mode_buttons(self) -> None:
        """Restore normal mode buttons that views added"""
        try:
            # Add back normal mode buttons that were stored
            for button_id, button in self.normal_buttons.items():
                if button not in self.center_content.children:
                    self.center_content.add(button)

        except Exception as e:
            logger.error(f"Failed to restore normal mode buttons: {e}")

    def _show_edit_mode(self, context: Dict[str, Any] = None) -> None:
        """Show edit mode buttons based on context type"""
        try:
            # Clear all content
            self.clear_content()

            if not context:
                return

            edit_type = context.get("edit_type", "selection")

            if edit_type == "add_items":
                # Show add buttons for adding new items
                self._show_add_buttons_mode(context)
            else:
                # Show selection edit buttons
                self._show_selection_edit_mode(context)

        except Exception as e:
            logger.error(f"Failed to show edit mode: {e}")

    def _show_add_buttons_mode(self, context: Dict[str, Any]) -> None:
        """Show bottom edit actions (add buttons + add collection)"""
        try:
            # Use the new separated bottom edit actions
            all_actions = context.get("bottom_edit_actions", [])

            # Distribute buttons across the bottom toolbar
            for i, action in enumerate(all_actions):
                button = self.create_button(
                    text=action["title"],
                    icon=action.get("icon"),
                    on_press=self._create_add_button_handler(action["id"]),
                    style_class="default"
                )

                # Distribute across left, center, right for visual balance
                if i % 3 == 0:
                    self.left_content.add(button)
                elif i % 3 == 1:
                    self.center_content.add(button)
                else:
                    self.right_content.add(button)

            logger.debug(f"Bottom toolbar showing {len(all_actions)} edit actions (add + collection)")

        except Exception as e:
            logger.error(f"Failed to show add buttons mode: {e}")

    def _show_selection_edit_mode(self, context: Dict[str, Any]) -> None:
        """Show traditional selection edit buttons"""
        try:
            selected_count = context.get("selected_count", 0)

            # Select All button (left)
            if "select_all" in self.edit_buttons:
                self.left_content.add(self.edit_buttons["select_all"])

            # Share button (center) - only if items are selected
            if selected_count > 0 and "share" in self.edit_buttons:
                self.center_content.add(self.edit_buttons["share"])

            # Delete button (right) - only if items are selected
            if selected_count > 0 and "delete" in self.edit_buttons:
                self.right_content.add(self.edit_buttons["delete"])

            logger.debug(f"Selection edit mode (selected: {selected_count})")

        except Exception as e:
            logger.error(f"Failed to show selection edit mode: {e}")

    def _create_add_button_handler(self, action_id: str) -> Callable:
        """Create handler for add button"""
        def handler(widget):
            try:
                if self.coordinator:
                    nav_handler = self.coordinator.get_navigation_handler(action_id)
                    if nav_handler:
                        nav_handler()
                        # KEEP edit mode active - user should explicitly click Done to exit
                    else:
                        logger.warning(f"No navigation handler for {action_id}")
                else:
                    logger.warning("No coordinator available for add button")

            except Exception as e:
                logger.error(f"Failed to handle add button {action_id}: {e}")

        return handler

    def _show_smart_normal_mode(self) -> None:
        """Show normal mode using smart button system"""
        try:
            # Clear all content
            self.clear_content()

            # Restore regular buttons that views added
            for button_info in self._regular_buttons.values():
                self._add_button_to_position(button_info["button"], button_info["position"])

            logger.debug("BottomToolbar showing smart normal mode")

        except Exception as e:
            logger.error(f"Failed to show smart normal mode: {e}")

    def _show_smart_edit_mode(self, context: Dict[str, Any] = None) -> None:
        """Show edit mode using smart button system and context"""
        try:
            if not context:
                return

            # Clear all content
            self.clear_content()

            edit_type = context.get("edit_type", "selection")

            if edit_type == "add_items":
                # Create dynamic add buttons from context
                self._create_dynamic_add_buttons(context)
            else:
                # Show traditional selection edit buttons
                self._show_selection_edit_buttons(context)

            logger.debug(f"BottomToolbar showing smart edit mode (type: {edit_type})")

        except Exception as e:
            logger.error(f"Failed to show smart edit mode: {e}")

    def _create_dynamic_add_buttons(self, context: Dict[str, Any]) -> None:
        """Create dynamic bottom edit actions based on platform context"""
        try:
            # Use the new separated bottom edit actions
            all_actions = context.get("bottom_edit_actions", [])

            # Create buttons dynamically and distribute them
            for i, action in enumerate(all_actions):
                button = self.create_button(
                    text=action["title"],
                    icon=action.get("icon"),
                    on_press=self._create_add_button_handler(action["id"]),
                    style_class="default"
                )

                # Mark as dynamic edit mode button
                button._is_edit_mode_button = True

                # Distribute across left, center, right for balance
                position = ["left", "center", "right"][i % 3]
                self._add_button_to_position(button, position)

            logger.debug(f"Created {len(all_actions)} bottom edit action buttons")

        except Exception as e:
            logger.error(f"Failed to create dynamic add buttons: {e}")

    def _show_selection_edit_buttons(self, context: Dict[str, Any]) -> None:
        """Show traditional selection edit buttons"""
        try:
            selected_count = context.get("selected_count", 0)

            # Use pre-created edit buttons for selection operations
            if "select_all" in self.edit_buttons:
                button = self.edit_buttons["select_all"]
                button._is_edit_mode_button = True
                self.left_content.add(button)

            if selected_count > 0:
                if "share" in self.edit_buttons:
                    button = self.edit_buttons["share"]
                    button._is_edit_mode_button = True
                    self.center_content.add(button)

                if "delete" in self.edit_buttons:
                    button = self.edit_buttons["delete"]
                    button._is_edit_mode_button = True
                    self.right_content.add(button)

            logger.debug(f"Selection edit buttons (selected: {selected_count})")

        except Exception as e:
            logger.error(f"Failed to show selection edit buttons: {e}")

    # Event handlers for edit mode buttons
    def _on_delete_pressed(self, widget) -> None:
        """Handle delete button press"""
        try:
            logger.info("Delete button pressed in bottom toolbar")
            # This would be handled by the coordinator or view
            if self.coordinator:
                context = self.coordinator.get_edit_context()
                logger.info(f"Delete action for {context.get('selected_count', 0)} items")

        except Exception as e:
            logger.error(f"Failed to handle delete press: {e}")

    def _on_select_all_pressed(self, widget) -> None:
        """Handle select all button press"""
        try:
            logger.info("Select all button pressed in bottom toolbar")
            # This would be handled by the coordinator or view

        except Exception as e:
            logger.error(f"Failed to handle select all press: {e}")

    def _on_share_pressed(self, widget) -> None:
        """Handle share button press"""
        try:
            logger.info("Share button pressed in bottom toolbar")
            # This would be handled by the coordinator or view

        except Exception as e:
            logger.error(f"Failed to handle share press: {e}")

    # Composition methods for views to add their own buttons
    def add_normal_mode_button(self,
                              text: Optional[str] = None,
                              icon: Optional[str] = None,
                              on_press: Optional[Callable] = None,
                              position: str = "center",
                              key: Optional[str] = None,
                              tooltip: Optional[str] = None) -> toga.Button:
        """Add button for normal mode using smart button system"""
        # Support both new (text) and legacy (key) parameter styles
        button_id = key or text or icon or "button"
        return self.add_regular_button(
            button_id=button_id,
            position=position,
            text=text,
            icon=icon,
            on_press=on_press
        )

    def add_edit_mode_button(self,
                            text: Optional[str] = None,
                            icon: Optional[str] = None,
                            on_press: Optional[Callable] = None,
                            style_class: str = "default",
                            position: str = "center") -> toga.Button:
        """Add button for edit mode using BaseToolbar's proper system"""
        button_id = text or icon or "edit_button"
        return self.add_edit_button(
            button_id=button_id,
            position=position,
            text=text,
            icon=icon,
            on_press=on_press,
            style_class=style_class
        )