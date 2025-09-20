"""
Bottom Toolbar for Fichero

Toolbar for the bottom of views following iOS Human Interface Guidelines.
- Regular iOS: 49 points height
- iOS with home indicator: 83 points height (49pt + 34pt safe area)
- Icons: 25x25 points (regular) or 18x18 points (compact)
- Touch targets: Minimum 44x44 points
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, List

from fichero.shared.toolbars.base_toolbar import BaseToolbar

logger = logging.getLogger(__name__)


class BottomToolbar(BaseToolbar):
    """Bottom toolbar following iOS HIG specifications"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize bottom toolbar with iOS HIG dimensions"""
        
        # Use app.is_mobile if not provided
        if is_mobile is None:
            is_mobile = app.is_mobile
            
        super().__init__(app, is_mobile)
        
        # Apply iOS HIG specifications for bottom toolbar
        if self.is_mobile and hasattr(self, 'container') and self.container:
            self._apply_ios_hig_dimensions()
        
        # Bottom toolbar callbacks
        self.on_settings: Optional[Callable] = None
        self.on_about: Optional[Callable] = None
        self.on_help: Optional[Callable] = None
        
        # Note: _create_toolbar() should be called by derived classes
    
    def _apply_ios_hig_dimensions(self):
        """Apply iOS HIG specifications for bottom toolbar dimensions"""
        try:
            # iOS HIG specifications:
            # - Standard tab bar: 49 points
            # - With home indicator: 49pt + 34pt safe area = 83 points
            # - Icon sizes: 25x25 points (regular), 18x18 points (compact)
            # - Touch targets: minimum 44x44 points
            
            # The container structure: top_border, content_wrapper, bottom_border
            content_wrapper = self.container.children[1]  # Middle element
            if hasattr(content_wrapper, 'style'):
                # iOS HIG: 49pt base + 34pt safe area for home indicator devices
                ios_hig_height = 49 + 34  # 83 points total
                content_wrapper.style.height = ios_hig_height
                logger.info(f"Applied iOS HIG bottom toolbar height: {ios_hig_height}pt (49pt + 34pt safe area)")
                
        except Exception as e:
            logger.error(f"Failed to apply iOS HIG dimensions: {e}")
    
    def _create_toolbar(self):
        """Create the bottom toolbar content - empty by default"""
        try:
            # Empty by default - subclasses can add content
            logger.info("iOS HIG-compliant bottom toolbar created (empty)")
            
        except Exception as e:
            logger.error(f"Failed to create bottom toolbar: {e}")
    
    def create_ios_hig_button(self, button_id: str, icon: str, text: str = "", 
                              on_press: Optional[Callable] = None) -> toga.Button:
        """Create a button following iOS HIG specifications for bottom toolbar"""
        # iOS HIG specifications for tab bar buttons:
        # - Touch target: minimum 44x44 points
        # - Icon size: 25x25 points (regular) or 18x18 points (compact)
        # - Font size: 10 points, Medium weight for labels
        
        if self.is_mobile:
            # iOS HIG mobile specifications
            button_style = Pack(
                margin=(8, 4),    # Reduced horizontal margin for better spacing
                width=44,         # Minimum touch target width
                height=44,        # Minimum touch target height
            )
        else:
            # Desktop adaptations
            button_style = Pack(
                margin=(6, 4),
                width=32,
                height=32,
            )
        
        try:
            # Try to create button with icon (iOS HIG: 25x25 or 18x18 points)
            icon_path = self.app.paths.app / f"resources/icons/toolbar/{icon}.png"
            button = toga.Button(
                icon=toga.Icon(icon_path),
                on_press=on_press or self._default_button_handler,
                style=button_style
            )
            logger.debug(f"Created iOS HIG-compliant button: {button_id} with icon")
            
        except Exception as e:
            logger.warning(f"Failed to load icon {icon}: {e}, using text fallback")
            # Fallback to text if icon fails
            button = toga.Button(
                text=text or icon[:1].upper(),
                on_press=on_press or self._default_button_handler,
                style=button_style
            )
        
        self.buttons[button_id] = button
        return button
    
    def _create_secondary_actions(self):
        """Create the secondary actions area - disabled"""
        # Secondary actions disabled - completely empty
        pass
    
    def _create_utilities(self):
        """Create the utilities area - disabled"""
        # Utilities disabled - completely empty
        pass
    
    def add_secondary_action(self, button_id: str, text: str, icon: Optional[str] = None,
                           on_press: Optional[Callable] = None, tooltip: Optional[str] = None):
        """Add a secondary action button to the left side"""
        action_btn = self.create_action_button(
            button_id=button_id,
            text=text,
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_left(action_btn)
        return action_btn
    
    def add_utility_action(self, button_id: str, text: str, icon: Optional[str] = None,
                          on_press: Optional[Callable] = None, tooltip: Optional[str] = None):
        """Add a utility action button to the right side"""
        utility_btn = self.create_action_button(
            button_id=button_id,
            text=text,
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_right(utility_btn)
        return utility_btn
    
    def add_status_info(self, text: str):
        """Add status information to the center"""
        status_label = toga.Label(
            text,
            style=Pack(
                margin=(0, 10),
                text_align="center",
                color="#666666"
            )
        )
        self.add_to_center(status_label)
        return status_label
    
    def clear_buttons(self):
        """Clear all buttons from toolbar"""
        try:
            if hasattr(self, 'left_content'):
                self.left_content.clear()
            if hasattr(self, 'center_content'):
                self.center_content.clear()
            if hasattr(self, 'right_content'):
                self.right_content.clear()
            
        except Exception as e:
            logger.error(f"Failed to clear buttons: {e}")
    
    def set_edit_mode(self, is_edit_mode: bool):
        """Base implementation for edit mode - override in subclasses"""
        pass
    
    def register_callbacks(self, **kwargs):
        """Register callbacks - empty base implementation"""
        pass 