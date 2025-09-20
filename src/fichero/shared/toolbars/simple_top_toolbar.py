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
    """Simple top toolbar with automatic mobile navigation for secondary windows"""
    
    def __init__(self, app, title: str, on_back: Optional[Callable] = None, is_mobile: bool = None):
        """Initialize simple top toolbar with title and back callback"""
        self.window_title = title
        self.on_back_callback = on_back
        
        # Use automatic mobile navigation with "Library" as back destination
        super().__init__(app, title="Library", auto_mobile_nav=True, is_mobile=is_mobile)
        
        # Set the back callback
        if on_back:
            self.on_back = on_back
    
    def _add_custom_content(self):
        """Add custom content - desktop title for non-mobile"""
        try:
            if not self.is_mobile:
                # Desktop: centered title (mobile navigation is automatic)
                self.title_label = self.add_centered_title_only(
                    title_text=self.window_title,
                    on_title_click=None
                )
            
            logger.info(f"Simple top toolbar created for: {self.window_title}")
            
        except Exception as e:
            logger.error(f"Failed to create simple top toolbar: {e}")
    
    def update_title(self, new_title: str):
        """Update the toolbar title"""
        self.window_title = new_title
        if self.title_label:
            if hasattr(self.title_label, 'text'):
                self.title_label.text = new_title 