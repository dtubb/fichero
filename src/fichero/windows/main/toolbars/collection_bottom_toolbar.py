"""
Collection Bottom Toolbar for Fichero

Bottom toolbar for collection view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class CollectionBottomToolbar(BottomToolbar):
    """Bottom toolbar for collection view - currently empty"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize collection bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Collection-specific callbacks (none for now)
        self.on_collection_settings: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection bottom toolbar content - currently empty"""
        try:
            # Base container already created by parent class
            # No need to call super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No status either - completely blank
            
            logger.info("Collection bottom toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create collection bottom toolbar: {e}")
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_collection_settings: Optional[Callable] = None):
        """Register callbacks for collection bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        self.on_collection_settings = on_collection_settings
        logger.debug("Collection bottom toolbar callbacks registered")
    
    def update_status(self, status_text: str):
        """Update the status information"""
        # Find and update the status label
        for child in self.content.children:
            if hasattr(child, 'text') and "Ready" in child.text:
                child.text = status_text
                break 