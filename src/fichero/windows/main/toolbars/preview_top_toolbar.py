"""
Preview Top Toolbar for Fichero

Top toolbar for preview view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class PreviewTopToolbar(TopToolbar):
    """Top toolbar for preview view - currently empty"""
    
    def __init__(self, app, document_name: str = "", is_mobile: bool = False):
        """Initialize preview top toolbar"""
        super().__init__(app, is_mobile)
        
        # Preview context
        self.document_name = document_name
        
        # Preview-specific callbacks (none for now)
        self.on_back_to_fiche: Optional[Callable] = None
        self.on_edit_document: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the preview top toolbar content - currently empty"""
        try:
            # Base container already created by parent class
            # No need to call super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No title either - completely blank
            
            logger.info("Preview top toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create preview top toolbar: {e}")
    
    def update_document_name(self, document_name: str):
        """Update the document name display"""
        self.document_name = document_name
        if document_name:
            self.set_title(f"Preview: {document_name}")
        else:
            self.set_title("Preview View")
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_back_to_fiche: Optional[Callable] = None,
                         on_edit_document: Optional[Callable] = None):
        """Register callbacks for preview top toolbar actions"""
        super().register_callbacks(on_back, on_settings, on_about, on_help)
        self.on_back_to_fiche = on_back_to_fiche
        self.on_edit_document = on_edit_document
        logger.debug("Preview top toolbar callbacks registered") 