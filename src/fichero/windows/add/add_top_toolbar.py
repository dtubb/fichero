"""
Add Top Toolbar for Fichero

Top toolbar for add view following LibraryTopToolbar pattern.
"""

import toga
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class AddTopToolbar(TopToolbar):
    """Top toolbar for add view with automatic mobile navigation"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize add top toolbar"""
        # Add view needs back navigation - use auto_mobile_nav=True with proper title
        super().__init__(app, title="Add to Library", auto_mobile_nav=True, is_mobile=is_mobile)
        
        # Add-specific callbacks
        self.on_cancel: Optional[Callable] = None
        
        # The toolbar content is created automatically by parent
    
    def _add_custom_content(self):
        """Add custom content for add view"""
        try:
            # For mobile: automatic back button + title is handled by parent
            # For desktop: centered title
            if not self.is_mobile:
                self.add_title_only("Add to Library")
            
            logger.info("Add top toolbar created with automatic navigation")
            
        except Exception as e:
            logger.error(f"Failed to create add toolbar: {e}")
    
    def register_cancel_callback(self, callback: Callable):
        """Register callback for cancel action"""
        self.on_cancel = callback 