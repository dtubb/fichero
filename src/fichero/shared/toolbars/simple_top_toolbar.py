"""
Simple Top Toolbar for Fichero

Standard toolbar for secondary windows (Settings, About, Processing, Plans, Activity Monitor)
Uses the existing base toolbar system with consistent back button + title pattern.
"""

import toga
import logging
from typing import Optional, Callable
from fichero.shared.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class SimpleTopToolbar(TopToolbar):
    """Simple top toolbar with back button and title for secondary windows"""
    
    def __init__(self, app, title: str, on_back: Optional[Callable] = None, is_mobile: bool = None):
        """Initialize simple top toolbar with title and back callback"""
        self.window_title = title
        self.on_back_callback = on_back
        
        # Call parent constructor
        super().__init__(app, is_mobile=is_mobile)
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the simple top toolbar content using existing base system"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Use the existing smart helper method for back button + title
            if self.is_mobile:
                # Mobile: back button + title on left (where we came from)
                self.back_button, self.title_label = self.add_back_button_with_title(
                    title_text="Library",  # Where we're going back to
                    on_back=self._on_back_pressed,
                    on_title_click=self._on_title_pressed
                )
            else:
                # Desktop: just centered title, no back button needed
                self.back_button = None
                self.title_label = self.add_centered_title_only(
                    title_text=self.window_title,
                    on_title_click=None
                )
            
            logger.info(f"Simple top toolbar created for: {self.window_title}")
            
        except Exception as e:
            logger.error(f"Failed to create simple top toolbar: {e}")
    
    def _on_back_pressed(self, widget):
        """Handle back button press"""
        logger.debug(f"Back button pressed in {self.window_title}")
        if self.on_back_callback:
            self.on_back_callback()
    
    def _on_title_pressed(self, widget):
        """Handle title press (goes back like back button)"""
        logger.debug(f"Title pressed in {self.window_title}")
        if self.on_back_callback:
            self.on_back_callback()
    
    def set_back_callback(self, callback: Callable):
        """Set or update the back button callback"""
        self.on_back_callback = callback
    
    def update_title(self, new_title: str):
        """Update the toolbar title"""
        self.window_title = new_title
        if self.title_label:
            if hasattr(self.title_label, 'text'):
                self.title_label.text = new_title 