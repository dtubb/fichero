"""
Base Toolbar for Fichero

Provides common toolbar functionality using Toga's native colors.
Only applies custom colors to icons and active states.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable, Dict
from fichero.windows.main.styling.color_constants import (
    ICON_PRIMARY, ICON_SECONDARY, TOOLBAR_BACKGROUND, TOOLBAR_BORDER, VIEW_BACKGROUND
)


logger = logging.getLogger(__name__)


class BaseToolbar(ABC):
    """Base class for all toolbars in Fichero"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize base toolbar"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Toolbar components
        self.container: Optional[toga.Box] = None
        self.buttons: Dict[str, toga.Button] = {}
        self.commands: Dict[str, toga.Command] = {}
        
        # Callbacks
        self.action_callbacks: Dict[str, Callable] = {}
        
        # Create toolbar
        self._create_base_container()
        # Note: _create_toolbar() is abstract and should be called by derived classes
    
    def _create_base_container(self):
        """Create the base toolbar container with white background and borders on all sides"""
        try:
            # Create toolbar container with white background, fixed height, and borders on all sides
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    height=50,  # Fixed height of 50px
                    margin=(0, 0),  # No margins
                    padding=(0, 0),  # No padding
                    background_color=VIEW_BACKGROUND  # White background
                )
            )
            
            # Add top border
            top_border = toga.Box(
                style=Pack(
                    background_color=TOOLBAR_BORDER,
                    height=1,
                    margin=(0, 0)
                )
            )
            self.container.add(top_border)
            
            # Create main content wrapper with left and right borders
            content_wrapper = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1,
                    margin=(0, 0),
                    padding=(0, 0)
                )
            )
            
            # Left border
            left_border = toga.Box(
                style=Pack(
                    background_color=TOOLBAR_BORDER,
                    width=1,
                    margin=(0, 0)
                )
            )
            content_wrapper.add(left_border)
            
            # Create main content area with proper padding and ROW direction for horizontal buttons
            self.content = toga.Box(
                style=Pack(
                    direction=ROW,  # This ensures buttons are horizontal
                    padding=(8, 12),  # Reduced internal padding for smaller height
                    margin=(0, 0),
                    flex=1  # Take up available space
                )
            )
            
            # Create left-aligned content area for navigation/context tools
            self.left_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(0, 0)
                )
            )
            
            # Create right-aligned content area for action tools
            self.right_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(0, 0)
                )
            )
            
            # Add left and right content to main content area
            self.content.add(self.left_content)
            self.content.add(toga.Box(style=Pack(flex=1)))  # Spacer to push right content to the right
            self.content.add(self.right_content)
            
            content_wrapper.add(self.content)
            
            # Right border
            right_border = toga.Box(
                style=Pack(
                    background_color=TOOLBAR_BORDER,
                    width=1,
                    margin=(0, 0)
                )
            )
            content_wrapper.add(right_border)
            
            self.container.add(content_wrapper)
            
            # Add bottom border
            bottom_border = toga.Box(
                style=Pack(
                    background_color=TOOLBAR_BORDER,
                    height=1,
                    margin=(0, 0)
                )
            )
            self.container.add(bottom_border)
            
            logger.debug("Base toolbar container created with 50px height, white background, and borders on all sides")
            
        except Exception as e:
            logger.error(f"Failed to create base toolbar container: {e}")
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=ROW))
            self.content = toga.Box(style=Pack(direction=ROW))
            self.left_content = toga.Box(style=Pack(direction=ROW))
            self.right_content = toga.Box(style=Pack(direction=ROW))
    
    @abstractmethod
    def _create_toolbar(self):
        """Create the specific toolbar content - must be implemented by derived classes"""
        pass
    
    def create_navigation_button(self, 
                                button_id: str,
                                text: str,
                                on_press: Optional[Callable] = None,
                                tooltip: Optional[str] = None,
                                enabled: bool = True) -> toga.Button:
        """Create a navigation button with consistent sizing"""
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22,
                color=ICON_PRIMARY
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add default icon
        try:
            button.icon = toga.Icon("resources/icons/toolbar/chevron.left@10x.png")
        except Exception:
            pass
        
        self.buttons[button_id] = button
        return button
    
    def create_action_button(self, 
                            button_id: str,
                            text: str,
                            icon: Optional[str] = None,
                            on_press: Optional[Callable] = None,
                            tooltip: Optional[str] = None,
                            enabled: bool = True) -> toga.Button:
        """Create an action button with consistent sizing"""
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22,
                color=ICON_PRIMARY
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add icon if specified
        if icon:
            try:
                button.icon = toga.Icon(f"resources/icons/toolbar/{icon}.png")
            except Exception:
                pass
        
        self.buttons[button_id] = button
        return button
    
    def create_icon_button(self, 
                           button_id: str,
                           icon: str,
                           on_press: Optional[Callable] = None,
                           tooltip: Optional[str] = None,
                           enabled: bool = True) -> toga.Button:
        """Create an icon-only button with consistent sizing"""
        button = toga.Button(
            text="",
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add icon
        try:
            button.icon = toga.Icon(f"resources/icons/toolbar/{icon}.png")
        except Exception:
            pass
        
        self.buttons[button_id] = button
        return button
    
    def create_display_button(self, 
                              button_id: str,
                              text: str,
                              tooltip: Optional[str] = None) -> toga.Button:
        """Create a display-only button with consistent sizing"""
        button = toga.Button(
            text=text,
            enabled=False,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22,
                color=ICON_PRIMARY
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add default icon
        try:
            button.icon = toga.Icon("resources/icons/toolbar/text_document.png")
        except Exception:
            pass
        
        self.buttons[button_id] = button
        return button
    
    def add_to_left(self, widget):
        """Add a widget to the left side of the toolbar (navigation/context tools)"""
        if hasattr(self, 'left_content'):
            self.left_content.add(widget)
        else:
            # Fallback to main content if left_content not available
            self.content.add(widget)
    
    def add_to_right(self, widget):
        """Add a widget to the right side of the toolbar (action tools)"""
        if hasattr(self, 'right_content'):
            self.right_content.add(widget)
        else:
            # Fallback to main content if right_content not available
            self.content.add(widget)
    
    def add_to_center(self, widget):
        """Add a widget to the center of the toolbar (main content area)"""
        self.content.add(widget)
    
    def create_separator(self, width: int = 20) -> toga.Box:
        """Create a visual separator between toolbar sections"""
        return toga.Box(style=Pack(width=width))
    
    def create_button(self, 
                      button_id: str,
                      text: str,
                      icon: Optional[str] = None,
                      on_press: Optional[Callable] = None,
                      enabled: bool = True) -> toga.Button:
        """Create a generic button with consistent sizing"""
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22,
                color=ICON_PRIMARY
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add icon if specified
        if icon:
            try:
                button.icon = toga.Icon(f"resources/icons/toolbar/{icon}.png")
            except Exception:
                pass
        
        self.buttons[button_id] = button
        return button
    
    def create_command_button(self, 
                             button_id: str,
                             command: toga.Command,
                             icon_path: Optional[str] = None) -> toga.Button:
        """Create a command button with consistent sizing"""
        button = toga.Button(
            text=command.text,
            icon=icon_path and toga.Icon(icon_path) or command.icon,
            on_press=lambda widget: command.action(widget),
            enabled=command.enabled,
            style=Pack(
                margin=(4, 4),
                width=22,
                height=22,
                color=ICON_PRIMARY
            )
        )
        
        # Remove background color
        if hasattr(button.style, 'background_color'):
            del button.style.background_color
        
        # Add default icon if none provided
        if not button.icon:
            try:
                button.icon = toga.Icon("resources/icons/toolbar/gear.png")
            except Exception:
                pass
        
        self.buttons[button_id] = button
        self.register_command(button_id, command)
        return button
    
    def register_command(self, command_id: str, command: toga.Command):
        """Register a command with the toolbar"""
        self.commands[command_id] = command
        logger.debug(f"Registered command: {command_id}")
    
    def register_action_callback(self, action_id: str, callback: Callable):
        """Register a callback for a specific action"""
        self.action_callbacks[action_id] = callback
        logger.debug(f"Registered action callback: {action_id}")
    
    def _default_button_handler(self, widget):
        """Default button handler for buttons without specific callbacks"""
        logger.debug(f"Default button handler called for: {widget}")
    
    def get_container(self) -> toga.Box:
        """Get the toolbar container"""
        return self.container
    
    def get_buttons(self) -> Dict[str, toga.Button]:
        """Get all buttons in the toolbar"""
        return self.buttons
    
    def get_button(self, button_id: str) -> Optional[toga.Button]:
        """Get a specific button by ID"""
        return self.buttons.get(button_id)
    
    def enable_button(self, button_id: str, enabled: bool = True):
        """Enable or disable a button"""
        if button_id in self.buttons:
            self.buttons[button_id].enabled = enabled
    
    def show_button(self, button_id: str, visible: bool = True):
        """Show or hide a button"""
        if button_id in self.buttons:
            self.buttons[button_id].visible = visible
    
    def show(self):
        """Show the toolbar"""
        if self.container:
            self.container.visible = True
    
    def hide(self):
        """Hide the toolbar"""
        if self.container:
            self.container.visible = False
    
    def is_visible(self) -> bool:
        """Check if the toolbar is visible"""
        return self.container.visible if self.container else False
    
    def set_background_color(self, color: str):
        """Set the background color of the toolbar"""
        if self.container:
            self.container.style.background_color = color
    
    def set_icon_color(self, color: str):
        """Set the icon color for all buttons in the toolbar"""
        for button in self.buttons.values():
            if hasattr(button.style, 'color'):
                button.style.color = color 