"""
Top Toolbar for Fichero

Toolbar for the top of views with:
- Title and navigation
- Back buttons
- Primary actions
- Context information
"""

import toga
from toga.style import Pack
from toga.constants import ROW
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.base_toolbar import BaseToolbar

logger = logging.getLogger(__name__)


class TopToolbar(BaseToolbar):
    """Top toolbar for views with title, navigation, and primary actions"""
    
    def __init__(self, app, title: str = "", is_mobile: bool = False):
        """Initialize top toolbar"""
        self.title = title
        super().__init__(app, is_mobile)
        
        # Top toolbar callbacks
        self.on_back: Optional[Callable] = None
        self.on_title_click: Optional[Callable] = None
        
        # Note: _create_toolbar() should be called by derived classes
    
    def _create_toolbar(self):
        """Create the top toolbar content - completely empty"""
        try:
            # No content - completely empty as requested
            # No title area, no primary actions
            
            logger.info("Top toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create top toolbar: {e}")
    
    def _create_title_area(self):
        """Create the title and navigation area - disabled"""
        # Title area disabled - completely empty
        pass
    
    def _create_primary_actions(self):
        """Create the primary actions area - disabled"""
        # Primary actions disabled - completely empty
        pass
    
    def set_title(self, title: str):
        """Set the toolbar title"""
        self.title = title
        # Find and update the title label
        for child in self.content.children:
            if isinstance(child, toga.Label) and child.text == self.title:
                child.text = title
                break
    
    def add_back_button(self, text: str = "← Back", on_press: Optional[Callable] = None):
        """Add a back button to the left side"""
        back_btn = self.create_navigation_button(
            button_id="back",
            text=text,
            on_press=on_press or self._on_back_clicked,
            tooltip="Go back"
        )
        self.add_to_left(back_btn)
        return back_btn
    
    def add_primary_action(self, button_id: str, text: str, icon: Optional[str] = None, 
                          on_press: Optional[Callable] = None, tooltip: Optional[str] = None):
        """Add a primary action button to the right side"""
        action_btn = self.create_action_button(
            button_id=button_id,
            text=text,
            icon=icon,
            on_press=on_press,
            tooltip=tooltip
        )
        self.add_to_right(action_btn)
        return action_btn
    
    def _on_back_clicked(self, widget):
        """Handle back button click"""
        logger.debug("Back button clicked")
        if self.on_back:
            self.on_back()
    
    def register_callbacks(self, on_back: Optional[Callable] = None, 
                         on_title_click: Optional[Callable] = None):
        """Register callbacks for top toolbar actions"""
        self.on_back = on_back
        self.on_title_click = on_title_click
        logger.debug("Top toolbar callbacks registered") 