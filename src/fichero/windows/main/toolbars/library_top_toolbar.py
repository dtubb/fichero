"""
Library Top Toolbar for Fichero

Top toolbar for library view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class LibraryTopToolbar(TopToolbar):
    """Top toolbar for library view - currently empty"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize library top toolbar"""
        super().__init__(app, is_mobile)
        
        # Library-specific callbacks (none for now)
        self.on_add_collection: Optional[Callable] = None
        self.on_activity_monitor: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the library top toolbar content - currently empty"""
        try:
            # Base container already created by parent class
            # No need to call super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No title either - completely blank
            
            logger.info("Library top toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create library top toolbar: {e}")
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_add_collection: Optional[Callable] = None,
                         on_activity_monitor: Optional[Callable] = None):
        """Register callbacks for library top toolbar actions"""
        super().register_callbacks(on_back, on_settings, on_about, on_help)
        self.on_add_collection = on_add_collection
        self.on_activity_monitor = on_activity_monitor
        logger.debug("Library top toolbar callbacks registered") 