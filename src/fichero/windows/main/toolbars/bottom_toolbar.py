"""
Bottom Toolbar for Fichero

Toolbar for the bottom of views with:
- Secondary actions
- Settings and utilities
- Status information
- Context-specific tools
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable, List

from fichero.windows.main.toolbars.base_toolbar import BaseToolbar

logger = logging.getLogger(__name__)


class BottomToolbar(BaseToolbar):
    """Bottom toolbar for views with secondary actions and utilities"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize bottom toolbar"""
        
        # Use app.is_mobile if not provided
        if is_mobile is None:
            is_mobile = app.is_mobile
            
        super().__init__(app, is_mobile)
        
        # Make bottom toolbar taller on mobile for iOS home gesture (no white space below)
        if self.is_mobile and hasattr(self, 'container') and self.container:
            # Find the content wrapper and make it taller instead of adding margin
            try:
                # The container has: top_border, content_wrapper, bottom_border
                content_wrapper = self.container.children[1]  # Middle element
                if hasattr(content_wrapper, 'style'):
                    # Make content wrapper taller to accommodate iOS home gesture
                    content_wrapper.style.height = 56 + 34  # Normal height + iOS safe area
                    logger.info(f"Made mobile bottom toolbar taller (90px) for iOS home gesture")
            except Exception as e:
                logger.error(f"Failed to adjust mobile bottom toolbar height: {e}")
        else:
            logger.info(f"Standard bottom toolbar height - is_mobile: {self.is_mobile}")
        
        # Bottom toolbar callbacks
        self.on_settings: Optional[Callable] = None
        self.on_about: Optional[Callable] = None
        self.on_help: Optional[Callable] = None
        
        # Note: _create_toolbar() should be called by derived classes
    
    def _create_toolbar(self):
        """Create the bottom toolbar content - completely empty"""
        try:
            # No content - completely empty as requested
            # No secondary actions, no utilities
            
            logger.info("Bottom toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create bottom toolbar: {e}")
    
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
            text=text,
            style=Pack(
                font_size=12,
                color="#666666"
            )
        )
        self.add_to_center(status_label)
        return status_label
    
    def _on_settings_clicked(self, widget):
        """Handle settings button click"""
        logger.debug("Settings button clicked")
        if self.on_settings:
            self.on_settings()
    
    def _on_about_clicked(self, widget):
        """Handle about button click"""
        logger.debug("About button clicked")
        if self.on_about:
            self.on_about()
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None):
        """Register callbacks for bottom toolbar actions"""
        self.on_settings = on_settings
        self.on_about = on_about
        self.on_help = on_help
        logger.debug("Bottom toolbar callbacks registered") 