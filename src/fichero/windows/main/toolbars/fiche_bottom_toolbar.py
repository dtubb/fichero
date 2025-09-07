"""
Fiche Bottom Toolbar for Fichero

Bottom toolbar for fiche view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class FicheBottomToolbar(BottomToolbar):
    """Bottom toolbar for fiche view - currently empty"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize fiche bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Fiche-specific callbacks (none for now)
        self.on_fiche_settings: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the fiche bottom toolbar content - currently empty"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No status either - completely blank
            
            logger.info("Fiche bottom toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create fiche bottom toolbar: {e}")
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_fiche_settings: Optional[Callable] = None):
        """Register callbacks for fiche bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        self.on_fiche_settings = on_fiche_settings
        logger.debug("Fiche bottom toolbar callbacks registered")
    
    def update_status(self, status_text: str):
        """Update the status information"""
        # Find and update the status label
        for child in self.content.children:
            if hasattr(child, 'text') and "Ready" in child.text:
                child.text = status_text
                break 