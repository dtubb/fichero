"""
Add Bottom Toolbar for Fichero

Bottom toolbar for add view following LibraryBottomToolbar pattern.
"""

import toga
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class AddBottomToolbar(BottomToolbar):
    """Bottom toolbar for add view - empty like LibraryBottomToolbar"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize add bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Add-specific callbacks (none for now)
        self.on_help: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the add bottom toolbar content"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # For now, keep it empty like LibraryBottomToolbar initially was
            # Add buttons here if needed in the future
            
            logger.info("Add bottom toolbar created (empty)")
            
        except Exception as e:
            logger.error(f"Failed to create add bottom toolbar: {e}")
    
    def register_callbacks(self, on_help: Optional[Callable] = None):
        """Register callbacks for add bottom toolbar actions"""
        self.on_help = on_help
        logger.debug("Add bottom toolbar callbacks registered") 