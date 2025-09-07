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
    TOOLBAR_BORDER, VIEW_BACKGROUND, ICON_PRIMARY, ICON_SECONDARY
)


logger = logging.getLogger(__name__)


class BaseToolbar(ABC):
    """Base class for all toolbars in Fichero"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize base toolbar"""
        self.app = app
        
        # Use provided is_mobile parameter or get from app
        if is_mobile is not None:
            self.is_mobile = is_mobile
        else:
            # Use the app's platform detection (set once at startup)
            self.is_mobile = self.app.is_mobile
        
        # Platform-appropriate styling constants - use Toga defaults
        if self.is_mobile:
            self.TITLE_COLOR = "#007AFF"  # iOS system blue for mobile
            self.TITLE_FONT_WEIGHT = "bold"
        else:
            self.TITLE_COLOR = None  # Use default system color for desktop
            self.TITLE_FONT_WEIGHT = "normal"  # Normal weight on desktop
        # Don't set TITLE_FONT_SIZE - let Toga use system default
        
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
        """Create the base toolbar container with smart platform-specific sizing"""
        try:
            # Platform-specific sizing - no bottom margin here (handled by subclasses)
            if self.is_mobile:
                toolbar_height = 56  # Taller for mobile touch targets
            else:
                toolbar_height = 40  # Taller than before (was 32)
            
            # Create toolbar container with system grey background
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=(0, 0),  # No margins in base - handled by subclasses
                    background_color="#E5E5EA" if self.is_mobile else "#F2F2F7"  # iOS/macOS system greys
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
            
            # Create main content wrapper - no side borders to eliminate white space
            content_wrapper = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1,
                    margin=(0, 0),
                    height=toolbar_height
                )
            )
            
            # Create main content area - reduced margins for better button positioning
            self.content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(4, 8),  # Further reduced margins - (4, 8) instead of (8, 12)
                    flex=1,
                    height=toolbar_height - 8  # Account for reduced padding
                )
            )
            
            # Create left-aligned content area
            self.left_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(0, 0),
                    flex=0  # Don't expand
                )
            )
            
            # Create center-aligned content area with proper centering
            self.center_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(0, 16),  # Side margins for spacing
                    flex=1,  # Expand to take remaining space
                    text_align="center"  # For text elements
                )
            )
            
            # Create right-aligned content area
            self.right_content = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(0, 0),
                    flex=0  # Don't expand
                )
            )
            
            # Add content areas in proper order for layout
            self.content.add(self.left_content)
            self.content.add(self.center_content)
            self.content.add(self.right_content)
            
            content_wrapper.add(self.content)
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
            
            logger.debug(f"Smart toolbar container created - height: {toolbar_height}, mobile: {self.is_mobile}")
            
        except Exception as e:
            logger.error(f"Failed to create smart toolbar container: {e}")
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=ROW))
            self.content = toga.Box(style=Pack(direction=ROW))
            self.left_content = toga.Box(style=Pack(direction=ROW))
            self.center_content = toga.Box(style=Pack(direction=ROW))
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
        """Create a navigation button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(8, 12),  # Larger margin for touch targets
                width=44, height=44,  # 44px minimum for touch
                color=ICON_PRIMARY
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 8),  # Smaller margin
                width=22, height=22,  # 22px for desktop
                color=ICON_PRIMARY
            )
        
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=button_style
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
        """Create an action button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(8, 12),  # Larger margin for touch targets
                width=44, height=44,  # 44px minimum for touch
                color=ICON_PRIMARY
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 8),  # Smaller margin
                width=22, height=22,  # 22px for desktop
                color=ICON_PRIMARY
            )
        
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=button_style
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
        """Create an icon-only button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(4, 4),   # Reduced from (8, 8) to prevent excessive spacing
                width=44, height=44  # 44px minimum for touch
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 4),   # Smaller square margin
                width=22, height=22  # 22px for desktop
            )
        
        button = toga.Button(
            text="",
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=button_style
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
        """Create a display-only button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(8, 12),  # Larger margin for touch targets
                width=44, height=44,  # 44px minimum for touch
                color=ICON_PRIMARY
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 8),  # Smaller margin
                width=22, height=22,  # 22px for desktop
                color=ICON_PRIMARY
            )
        
        button = toga.Button(
            text=text,
            enabled=False,
            style=button_style
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
        """Add a widget to the center of the toolbar (titles, etc.)"""
        if hasattr(self, 'center_content'):
            self.center_content.add(widget)
        else:
            # Fallback to main content if center_content not available
            self.content.add(widget)
    
    def add_button_center(self, icon: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add an icon button to the center with consistent styling"""
        button = self.create_icon_button(
            button_id=f"center_{icon}",
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_center(button)
        return button
    
    def add_button_text_center(self, text: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add a text button to the center with consistent styling"""
        button = toga.Button(
            text=text,
            on_press=on_press,
            style=Pack(
                margin=(0, 8),
                color=self.TITLE_COLOR
            )
        )
        self.add_to_center(button)
        return button
    
    def create_separator(self, width: int = 20) -> toga.Box:
        """Create a visual separator between toolbar sections"""
        return toga.Box(style=Pack(width=width))
    
    def create_button(self, 
                      button_id: str,
                      text: str,
                      icon: Optional[str] = None,
                      on_press: Optional[Callable] = None,
                      enabled: bool = True) -> toga.Button:
        """Create a generic button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(8, 12),  # Larger margin for touch targets
                width=44, height=44,  # 44px minimum for touch
                color=ICON_PRIMARY
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 8),  # Smaller margin
                width=22, height=22,  # 22px for desktop
                color=ICON_PRIMARY
            )
        
        button = toga.Button(
            text=text,
            on_press=on_press or self._default_button_handler,
            enabled=enabled,
            style=button_style
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
        """Create a command button with platform-appropriate sizing"""
        # Platform-specific button sizing
        if self.is_mobile:
            # Mobile: larger buttons for touch (44px minimum for iOS)
            button_style = Pack(
                margin=(8, 12),  # Larger margin for touch targets
                width=44, height=44,  # 44px minimum for touch
                color=ICON_PRIMARY
            )
        else:
            # Desktop: smaller buttons to fit all 5 buttons
            button_style = Pack(
                margin=(4, 8),  # Smaller margin
                width=22, height=22,  # 22px for desktop
                color=ICON_PRIMARY
            )
        
        button = toga.Button(
            text=command.text,
            icon=icon_path and toga.Icon(icon_path) or command.icon,
            on_press=lambda widget: command.action(widget),
            enabled=command.enabled,
            style=button_style
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
    
    def add_button_left(self, icon: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add an icon button to the left side with consistent styling"""
        button = self.create_icon_button(
            button_id=f"left_{icon}",
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_left(button)
        return button
    
    def add_button_right(self, icon: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add an icon button to the right side with consistent styling"""
        button = self.create_icon_button(
            button_id=f"right_{icon}",
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_right(button)
        return button
    
    def add_button_text_left(self, text: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add a text button to the left side with consistent styling"""
        style_props = {'margin': (0, 8)}
        if self.TITLE_COLOR:  # Only set color on mobile
            style_props['color'] = self.TITLE_COLOR
            
        button = toga.Button(
            text=text,
            on_press=on_press,
            style=Pack(**style_props)
        )
        self.add_to_left(button)
        return button
    
    def add_button_text_right(self, text: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add a text button to the right side with consistent styling"""
        style_props = {'margin': (0, 8)}
        if self.TITLE_COLOR:  # Only set color on mobile
            style_props['color'] = self.TITLE_COLOR
            
        button = toga.Button(
            text=text,
            on_press=on_press,
            style=Pack(**style_props)
        )
        self.add_to_right(button)
        return button
    
    def add_button_text_center(self, text: str, on_press: Callable, tooltip: str = "") -> toga.Button:
        """Add a text button to the center with consistent styling"""
        style_props = {'margin': (0, 8)}
        if self.TITLE_COLOR:  # Only set color on mobile
            style_props['color'] = self.TITLE_COLOR
            
        button = toga.Button(
            text=text,
            on_press=on_press,
            style=Pack(**style_props)
        )
        self.add_to_center(button)
        return button
    
    def add_title_left(self, text: str, margin_left: int = 0, on_click: Callable = None) -> toga.Widget:
        """Add a title label to the left side with automatic mobile/desktop styling and proper centering"""
        # Automatically handle mobile vs desktop behavior
        clickable = self.is_mobile and on_click is not None
        
        # Calculate proper top margin to center title with buttons
        if self.is_mobile:
            # Mobile: button is 44px + 4px margin = 48px total, center title with button
            title_top_margin = 12  # Centers text with 44px buttons
        else:
            # Desktop: button is 22px + 4px margin = 26px total, center title with button  
            title_top_margin = 6   # Centers text with 22px buttons
        
        if clickable:
            # Create clickable title as button (mobile only) - use blue color
            style_props = {
                'margin_left': margin_left,
                'margin_top': title_top_margin,
                'font_weight': self.TITLE_FONT_WEIGHT,
                'background_color': "transparent"
            }
            if self.TITLE_COLOR:  # Blue color for clickable buttons
                style_props['color'] = self.TITLE_COLOR
            
            title = toga.Button(
                text=text,
                on_press=on_click,
                style=Pack(**style_props)
            )
        else:
            # Create non-clickable title as label - use default system color
            style_props = {
                'margin_left': margin_left,
                'margin_top': title_top_margin,
                'font_weight': self.TITLE_FONT_WEIGHT,
                # No color specified - use system default
            }
                
            title = toga.Label(
                text,
                style=Pack(**style_props)
            )
        self.add_to_left(title)
        return title
    
    def add_title_center(self, text: str, on_click: Callable = None) -> toga.Widget:
        """Add a title label to the center with automatic mobile/desktop styling and proper centering"""
        # Automatically handle mobile vs desktop behavior
        clickable = self.is_mobile and on_click is not None
        
        # Calculate proper top margin to center title with buttons
        if self.is_mobile:
            title_top_margin = 12  # Centers text with 44px buttons
        else:
            title_top_margin = 6   # Centers text with 22px buttons
        
        if clickable:
            # Create clickable title as button (mobile only) - use blue color
            style_props = {
                'flex': 1,
                'text_align': "center",
                'margin_top': title_top_margin,
                'font_weight': self.TITLE_FONT_WEIGHT,
                'background_color': "transparent"
            }
            if self.TITLE_COLOR:  # Blue color for clickable buttons
                style_props['color'] = self.TITLE_COLOR
                
            title = toga.Button(
                text=text,
                on_press=on_click,
                style=Pack(**style_props)
            )
        else:
            # Create non-clickable title as label - use default system color
            style_props = {
                'flex': 1,
                'text_align': "center",
                'margin_top': title_top_margin,
                'font_weight': self.TITLE_FONT_WEIGHT,
                # No color specified - use system default
            }
                
            title = toga.Label(
                text,
                style=Pack(**style_props)
            )
        self.add_to_center(title)
        return title
    
    def add_spacer(self, width: int = None, height: int = None, flex: bool = False) -> toga.Box:
        """Add a spacer/invisible element to maintain toolbar height"""
        style_props = {}
        if width:
            style_props['width'] = width
        if height:
            style_props['height'] = height
        if flex:
            style_props['flex'] = 1
            
        spacer = toga.Box(style=Pack(**style_props))
        self.add_to_center(spacer)
        return spacer 

    def add_back_button_with_title(self, title_text: str, on_back: Callable, on_title_click: Callable = None) -> tuple:
        """Smart helper: Add back button + title with automatic mobile/desktop layout"""
        if self.is_mobile:
            # Mobile: back button + title on left
            back_button = self.add_button_left(
                icon="chevron.left@10x",
                on_press=on_back,
                tooltip="Back"
            )
            
            title = self.add_title_left(
                title_text,
                margin_left=10,
                on_click=on_title_click
            )
            
            return back_button, title
        else:
            # Desktop: just centered title, no back button
            title = self.add_centered_title_only(title_text, on_title_click=on_title_click)
            return None, title
    
    def add_centered_title_only(self, title_text: str, on_title_click: Callable = None) -> toga.Widget:
        """Smart helper: Add only a centered title (common desktop pattern)"""
        return self.add_title_center(title_text, on_click=on_title_click)
    
    def add_standard_right_buttons(self, buttons: list) -> list:
        """Smart helper: Add multiple right-aligned buttons with consistent spacing"""
        created_buttons = []
        for button_config in buttons:
            if button_config.get('text'):
                # Text button
                btn = self.add_button_text_right(
                    text=button_config['text'],
                    on_press=button_config['on_press'],
                    tooltip=button_config.get('tooltip', '')
                )
            else:
                # Icon button
                btn = self.add_button_right(
                    icon=button_config['icon'],
                    on_press=button_config['on_press'],
                    tooltip=button_config.get('tooltip', '')
                )
            created_buttons.append(btn)
        return created_buttons 

    def add_standard_center_buttons(self, buttons: list) -> list:
        """Smart helper: Add multiple center-aligned buttons with consistent spacing"""
        created_buttons = []
        for button_config in buttons:
            if button_config.get('text'):
                # Text button
                btn = self.add_button_text_center(
                    text=button_config['text'],
                    on_press=button_config['on_press'],
                    tooltip=button_config.get('tooltip', '')
                )
            else:
                # Icon button
                btn = self.add_button_center(
                    icon=button_config['icon'],
                    on_press=button_config['on_press'],
                    tooltip=button_config.get('tooltip', '')
                )
            created_buttons.append(btn)
        return created_buttons 

    def add_title_only(self, title_text: str, on_title_click: Callable = None) -> toga.Widget:
        """Smart helper: Add only a centered title (simple toolbar pattern)"""
        return self.add_centered_title_only(title_text, on_title_click=on_title_click) 

    def add_centered_button_group(self, buttons: list) -> list:
        """Add a group of buttons centered in the toolbar"""
        # Create a wrapper box for centering multiple buttons
        button_wrapper = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1,
                text_align="center"
            )
        )
        
        # Add flexible spacer before buttons
        left_spacer = toga.Box(style=Pack(flex=1))
        button_wrapper.add(left_spacer)
        
        # Add buttons
        created_buttons = []
        for button_config in buttons:
            if button_config.get('text'):
                # Text button
                btn = toga.Button(
                    text=button_config['text'],
                    on_press=button_config['on_press'],
                    style=Pack(margin=(0, 4))  # Small horizontal margin between buttons
                )
            else:
                # Icon button
                btn = self.create_icon_button(
                    button_id=f"center_group_{button_config['icon']}",
                    icon=button_config['icon'],
                    on_press=button_config['on_press'],
                    tooltip=button_config.get('tooltip', '')
                )
            button_wrapper.add(btn)
            created_buttons.append(btn)
        
        # Add flexible spacer after buttons
        right_spacer = toga.Box(style=Pack(flex=1))
        button_wrapper.add(right_spacer)
        
        # Add the wrapper to center content
        self.add_to_center(button_wrapper)
        return created_buttons

    def add_collection_back_button_with_title(self, title_text: str, on_back: Callable, on_title_click: Callable = None, desktop_title_left_aligned: bool = False) -> tuple:
        """Smart helper: Add back button + title for collection view with hierarchy navigation support"""
        # Mobile: always show back button
        # Desktop: show back button for hierarchy navigation (hidden when at root, shown when in folders)
        
        back_button = self.add_button_left(
            icon="chevron.left@10x",
            on_press=on_back,
            tooltip="Back"
        )
        
        if self.is_mobile:
            # Mobile: title on left next to back button
            title = self.add_title_left(
                title_text,
                margin_left=10,
                on_click=on_title_click
            )
        else:
            # Desktop: back button on left (initially hidden)
            back_button.style.visibility = "hidden"  # Hide by default on desktop
            
            # Desktop title positioning depends on context
            if desktop_title_left_aligned:
                # In hierarchy - left-aligned title next to back button
                title = self.add_title_left(
                    title_text,
                    margin_left=10,
                    on_click=on_title_click
                )
            else:
                # At collection root - centered title
                title = self.add_centered_title_only(title_text, on_title_click=on_title_click)
        
        return back_button, title 