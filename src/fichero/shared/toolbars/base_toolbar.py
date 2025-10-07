"""
Base Toolbar for Fichero - HIG Compliant

Provides HIG-compliant toolbar functionality for both iOS and macOS.
Integrates with ToolbarCoordinator for edit mode management.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN, CENTER
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict, Any
from fichero.shared.toolbars.toolbar_coordinator import ToolbarCoordinator, EditModeState, ToolbarProtocol
from fichero.shared.toolbars.color_constants import (
    TOOLBAR_BORDER, VIEW_BACKGROUND, ICON_PRIMARY, ICON_SECONDARY
)

logger = logging.getLogger(__name__)


class BaseToolbar(ABC, ToolbarProtocol):
    """HIG-compliant base class for all toolbars in Fichero"""

    def __init__(self, app, is_mobile: bool = None, coordinator: Optional[ToolbarCoordinator] = None):
        """Initialize base toolbar with HIG compliance"""
        self.app = app

        # Use provided is_mobile parameter or get from app
        if is_mobile is not None:
            self.is_mobile = is_mobile
        else:
            self.is_mobile = getattr(app, 'is_mobile', False)

        # Coordinator for edit mode management
        self.coordinator = coordinator

        # Edit mode state
        self._edit_mode_state = EditModeState.NORMAL
        self._edit_context: Dict[str, Any] = {}

        # Get HIG specifications for current platform
        self.hig_specs = self._get_hig_specs()

        # Toolbar components
        self.container: Optional[toga.Box] = None
        self.content: Optional[toga.Box] = None
        self.left_content: Optional[toga.Box] = None
        self.center_content: Optional[toga.Box] = None
        self.right_content: Optional[toga.Box] = None

        # Button storage
        self.buttons: Dict[str, toga.Button] = {}
        self.labels: Dict[str, toga.Label] = {}

        # Smart button registry for edit mode management
        self._regular_buttons: Dict[str, Dict[str, Any]] = {}  # Persistent buttons
        self._edit_buttons: Dict[str, Dict[str, Any]] = {}     # Edit mode only buttons
        self._current_mode: EditModeState = EditModeState.NORMAL

        # Create the base container
        self._create_base_container()

        logger.debug(f"BaseToolbar initialized (mobile: {self.is_mobile}, platform: {self.hig_specs['platform']})")

    def _get_hig_specs(self) -> Dict[str, Any]:
        """Get Human Interface Guidelines specifications for current platform"""
        if self.is_mobile:
            # iOS HIG specifications (adjusted for retina desktop display)
            return {
                "platform": "ios",
                "toolbar_height": 44,  # Standard navigation bar height
                "button_min_touch_target": 44,
                "icon_size": 22,  # SF Symbols recommendation
                "margin_horizontal": 16,
                "margin_vertical": 8,
                "button_spacing": 8,
                "corner_radius": 8,
                "font_size_title": 11,  # 17pt iOS → ~11px desktop (retina adjusted)
                "font_size_caption": 11,  # 17pt iOS → ~11px desktop (retina adjusted)
                "font_weight_title": "normal"  # iOS default weight
            }
        else:
            # macOS HIG specifications
            return {
                "platform": "macos",
                "toolbar_height": 52,  # Standard macOS toolbar
                "button_min_touch_target": 32,
                "icon_size": 16,  # macOS standard icon size
                "margin_horizontal": 12,
                "margin_vertical": 8,
                "button_spacing": 6,
                "corner_radius": 6,
                "font_size_title": 13,  # macOS system font
                "font_size_caption": 11,  # macOS caption
                "font_weight_title": "normal"
            }

    def _create_base_container(self):
        """Create stable HIG-compliant base container with consistent alignment and horizontal scrolling"""
        try:
            # Inner toolbar container with button content
            # This will be wrapped in a ScrollContainer for horizontal scrolling
            inner_container = toga.Box(
                style=Pack(
                    direction=ROW,  # Horizontal layout for left/center/right
                    height=self.hig_specs["toolbar_height"],
                    margin=0,
                    align_items="center",  # Vertically center all children
                    background_color="transparent",
                    flex=0  # Size based on content width (may exceed parent)
                )
            )

            # Wrap inner container in ScrollContainer for horizontal scrolling
            # This prevents toolbar from expanding the window when there are too many buttons
            self.container = toga.ScrollContainer(
                content=inner_container,
                horizontal=True,  # Enable horizontal scrolling
                vertical=False,   # Disable vertical scrolling (toolbar is fixed height)
                style=Pack(
                    height=self.hig_specs["toolbar_height"],
                    flex=1  # Take all available width from parent
                )
            )

            # For backward compatibility and button addition, content points to inner container
            self.content = inner_container

            # Left section: Flexible width that grows with content
            self.left_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=0,  # Size based on content, no fixed width
                    margin=(0, self.hig_specs["margin_horizontal"]),
                    align_items="center"
                    # justify_content not supported in Toga
                )
            )

            # Center section: True center alignment with balanced flex
            self.center_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1,  # Takes remaining space
                    margin=0,
                    align_items="center"
                    # text_align="center" for centering content
                )
            )

            # Right section: Flexible width that grows with content
            self.right_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=0,  # Size based on content, no fixed width
                    margin=(0, self.hig_specs["margin_horizontal"]),
                    align_items="center"
                    # Right alignment handled by container flex
                )
            )

            # Add sections to inner container (not the ScrollContainer wrapper)
            inner_container.add(self.left_content)
            inner_container.add(self.center_content)
            inner_container.add(self.right_content)

            logger.debug("Stable HIG-compliant base container created with consistent alignment")

        except Exception as e:
            logger.error(f"Failed to create base container: {e}")
            # Create minimal fallback
            self.container = toga.Box(style=Pack(direction=ROW, flex=1))
            self.content = self.container

    # ToolbarProtocol implementation
    def set_edit_mode(self, state: EditModeState, context: Dict[str, Any] = None) -> None:
        """Set edit mode state - to be implemented by subclasses"""
        self._edit_mode_state = state
        self._edit_context = context or {}
        logger.debug(f"Edit mode set to {state.value}")

    def get_edit_mode(self) -> EditModeState:
        """Get current edit mode state"""
        return self._edit_mode_state

    # Button creation methods with HIG compliance
    def create_button(self,
                     text: Optional[str] = None,
                     icon: Optional[str] = None,
                     on_press: Optional[Callable] = None,
                     style_class: str = "default",
                     label: Optional[str] = None):
        """Create HIG-compliant button"""
        try:
            # Determine button style based on platform and class
            if style_class == "primary":
                if self.is_mobile:
                    # iOS primary button style
                    button_style = Pack(
                        background_color="#007AFF",  # iOS blue
                        color="white",
                        margin=(8, 16),
                        font_size=self.hig_specs["font_size_caption"],
                        font_weight="normal"
                    )
                else:
                    # macOS primary button style
                    button_style = Pack(
                        background_color="#0066CC",  # macOS blue
                        color="white",
                        margin=(6, 12),
                        font_size=self.hig_specs["font_size_caption"]
                    )
            elif style_class == "right_aligned":
                # Simplified right-aligned button (container handles alignment)
                button_style = Pack(
                    margin=(6, 8),  # Standard button margins - container handles positioning
                    font_size=self.hig_specs["font_size_caption"]
                )
            else:
                # Default button style
                button_style = Pack(
                    margin=(6, 12),
                    font_size=self.hig_specs["font_size_caption"]
                )

            # Create button
            if icon and text:
                # TODO: Icon + text buttons when Toga supports it
                button = toga.Button(text=text, on_press=on_press, style=button_style)
            elif icon:
                # Icon-only button with proper sizing
                try:
                    icon_resource = toga.Icon(icon)
                    # Add icon sizing to button style
                    icon_button_style = Pack(
                        width=self.hig_specs["icon_size"] + 16,  # Icon size + padding
                        height=self.hig_specs["icon_size"] + 16,  # Icon size + padding
                        margin=button_style.margin if hasattr(button_style, 'margin') else (6, 8),
                        font_size=button_style.font_size if hasattr(button_style, 'font_size') else self.hig_specs["font_size_caption"]
                    )
                    button = toga.Button(icon=icon_resource, on_press=on_press, style=icon_button_style)
                except:
                    # Fallback to text if icon fails
                    button = toga.Button(text=text or "⚙", on_press=on_press, style=button_style)
            else:
                # Text-only button
                button = toga.Button(text=text or "Button", on_press=on_press, style=button_style)

            # If label is provided, wrap button in vertical container with label below
            if label:
                container = toga.Box(
                    style=Pack(
                        direction=COLUMN,
                        alignment=CENTER,
                        margin=(2, 4, 0, 4)  # Small top margin, side margins, no bottom margin
                    )
                )

                # Create small label below button
                label_widget = toga.Label(
                    text=label,
                    style=Pack(
                        font_size=7,  # Small text
                        text_align=CENTER,
                        margin=(0, 0, 2, 0)  # Small bottom margin for label
                    )
                )

                container.add(button)
                container.add(label_widget)
                return container
            else:
                return button

        except Exception as e:
            logger.error(f"Failed to create button: {e}")
            # Fallback button
            return toga.Button(text=text or "Button", on_press=on_press)

    def create_label(self,
                    text: str,
                    style_class: str = "default") -> toga.Label:
        """Create HIG-compliant label"""
        try:
            if style_class == "title":
                label_style = Pack(
                    font_size=self.hig_specs["font_size_title"],
                    font_weight=self.hig_specs["font_weight_title"],
                    text_align="center",
                    margin=self.hig_specs["button_spacing"]
                )
            else:
                label_style = Pack(
                    font_size=self.hig_specs["font_size_caption"],
                    margin=self.hig_specs["button_spacing"]
                )

            return toga.Label(text=text, style=label_style)

        except Exception as e:
            logger.error(f"Failed to create label: {e}")
            return toga.Label(text=text)

    # Layout helper methods
    def add_button_left(self,
                       text: Optional[str] = None,
                       icon: Optional[str] = None,
                       on_press: Optional[Callable] = None,
                       tooltip: Optional[str] = None,
                       button_id: Optional[str] = None,
                       label: Optional[str] = None):
        """Add button to left side of toolbar"""
        button = self.create_button(text=text, icon=icon, on_press=on_press, label=label)
        self.left_content.add(button)

        if button_id:
            self.buttons[button_id] = button

        return button

    def add_button_right(self,
                        text: Optional[str] = None,
                        icon: Optional[str] = None,
                        on_press: Optional[Callable] = None,
                        tooltip: Optional[str] = None,
                        button_id: Optional[str] = None,
                        label: Optional[str] = None):
        """Add button to right side of toolbar"""
        button = self.create_button(text=text, icon=icon, on_press=on_press, label=label)
        self.right_content.add(button)

        if button_id:
            self.buttons[button_id] = button

        return button

    def add_button_center(self,
                         text: Optional[str] = None,
                         icon: Optional[str] = None,
                         on_press: Optional[Callable] = None,
                         tooltip: Optional[str] = None,
                         button_id: Optional[str] = None,
                         label: Optional[str] = None):
        """Add button to center of toolbar"""
        button = self.create_button(text=text, icon=icon, on_press=on_press, label=label)
        self.center_content.add(button)

        if button_id:
            self.buttons[button_id] = button

        return button

    def add_title(self,
                 title: str,
                 on_click: Optional[Callable] = None) -> toga.Label:
        """Add title to center of toolbar"""
        logger.info(f"🎯 add_title called with: '{title}', is_mobile={getattr(self, 'is_mobile', 'unknown')}")
        label = self.create_label(title, style_class="title")
        self.center_content.add(label)

        self.labels["title"] = label
        return label

    def clear_content(self, area: str = "all") -> None:
        """Clear content from toolbar areas"""
        try:
            if area in ["all", "left"]:
                self.left_content.clear()
            if area in ["all", "center"]:
                self.center_content.clear()
            if area in ["all", "right"]:
                self.right_content.clear()

            # Clear button references
            if area == "all":
                self.buttons.clear()
                self.labels.clear()

        except Exception as e:
            logger.error(f"Failed to clear content: {e}")

    def setup_navigation_controller_integration(self) -> None:
        """Set up NavigationController integration"""
        try:
            from fichero.shared.navigation.navigation_controller import NavigationController

            # This will be implemented by subclasses as needed
            logger.debug("NavigationController integration available")

        except ImportError:
            logger.warning("NavigationController not available")

    @abstractmethod
    def _create_toolbar(self) -> None:
        """Create the specific toolbar content - implemented by subclasses"""
        pass

    def get_container(self) -> toga.Box:
        """Get the toolbar container widget"""
        return self.container

    # Smart button management API
    def add_regular_button(self,
                          button_id: str,
                          position: str = "right",
                          text: Optional[str] = None,
                          icon: Optional[str] = None,
                          on_press: Optional[Callable] = None,
                          style_class: str = "default",
                          label: Optional[str] = None):
        """Add a regular button that persists across edit mode transitions"""
        button = self.create_button(text=text, icon=icon, on_press=on_press, style_class=style_class, label=label)

        # Store button info for smart management
        self._regular_buttons[button_id] = {
            "button": button,
            "position": position,
            "text": text,
            "icon": icon,
            "on_press": on_press,
            "style_class": style_class,
            "label": label
        }

        # Add to appropriate position
        self._add_button_to_position(button, position)
        return button

    def add_edit_button(self,
                       button_id: str,
                       position: str = "right",
                       text: Optional[str] = None,
                       icon: Optional[str] = None,
                       on_press: Optional[Callable] = None,
                       style_class: str = "default",
                       label: Optional[str] = None):
        """Add an edit mode button (only shown during edit mode)"""
        button = self.create_button(text=text, icon=icon, on_press=on_press, style_class=style_class, label=label)

        # Store button info for edit mode
        self._edit_buttons[button_id] = {
            "button": button,
            "position": position,
            "text": text,
            "icon": icon,
            "on_press": on_press,
            "style_class": style_class,
            "label": label
        }

        # Don't add to UI yet - will be added during edit mode
        return button

    def _add_button_to_position(self, button: toga.Button, position: str) -> None:
        """Add button to the specified position"""
        if position == "left":
            self.left_content.add(button)
        elif position == "center":
            self.center_content.add(button)
        elif position == "right":
            self.right_content.add(button)
        else:
            logger.warning(f"Unknown button position: {position}, defaulting to right")
            self.right_content.add(button)

    def update_button_text(self, button_id: str, new_text: str) -> bool:
        """Update button text dynamically"""
        try:
            if button_id in self.buttons:
                button = self.buttons[button_id]
                button.text = new_text
                logger.debug(f"Updated button {button_id} text to: {new_text}")
                return True
            else:
                logger.warning(f"Button {button_id} not found")
                return False
        except Exception as e:
            logger.error(f"Failed to update button text: {e}")
            return False

    def _rebuild_toolbar_for_mode(self, mode: EditModeState) -> None:
        """Smart rebuild of toolbar preserving regular buttons"""
        try:
            # Clear all content
            self.clear_content()

            if mode == EditModeState.NORMAL:
                # Show only regular buttons
                for button_info in self._regular_buttons.values():
                    self._add_button_to_position(button_info["button"], button_info["position"])

            elif mode == EditModeState.EDIT:
                # Show regular buttons + edit buttons, but handle special cases
                # This will be overridden by subclasses for specific behavior
                for button_info in self._regular_buttons.values():
                    self._add_button_to_position(button_info["button"], button_info["position"])

                for button_info in self._edit_buttons.values():
                    self._add_button_to_position(button_info["button"], button_info["position"])

            self._current_mode = mode
            logger.debug(f"Toolbar rebuilt for mode: {mode.value}")

        except Exception as e:
            logger.error(f"Failed to rebuild toolbar for mode {mode}: {e}")