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
    
    def __init__(self, app, document_name: str = "", is_mobile: bool = None):
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
        """Create the preview top toolbar content"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Use smart helper for back button + title pattern
            self.back_button, self.title_label = self.add_back_button_with_title(
                title_text="Preview",
                on_back=self._on_back_pressed,
                on_title_click=self._on_title_pressed
            )
            
            # Add Edit button on the right using smart helper
            self.add_standard_right_buttons([{
                'text': 'Edit',
                'on_press': self._on_edit_pressed,
                'tooltip': 'Edit document'
            }])
            
            logger.info("Preview top toolbar created using standard form")
            
        except Exception as e:
            logger.error(f"Failed to create preview top toolbar: {e}")
    
    def _on_back_pressed(self, widget):
        """Handle back button press"""
        logger.debug("Preview back button pressed")
        if self.on_back_to_fiche:
            self.on_back_to_fiche()
        elif hasattr(self, 'on_back') and self.on_back:
            self.on_back()
        else:
            logger.debug("No back callback registered")
    
    def _on_title_pressed(self, widget):
        """Handle title button press (mobile only)"""
        logger.debug("Preview title pressed")
        # Could show document info or context menu
        pass
    
    def _on_edit_pressed(self, widget):
        """Handle edit button press"""
        logger.debug("Preview edit button pressed")
        if self.on_edit_document:
            self.on_edit_document()
    
    def update_document_name(self, document_name: str):
        """Update the document name display"""
        self.document_name = document_name
        if document_name:
            self.set_title(f"Preview: {document_name}")
        else:
            self.set_title("Preview View")
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_back_to_fiche: Optional[Callable] = None,
                         on_edit_document: Optional[Callable] = None):
        """Register callbacks for preview top toolbar actions"""
        super().register_callbacks(on_back=on_back)
        self.on_back_to_fiche = on_back_to_fiche
        self.on_edit_document = on_edit_document
        logger.debug("Preview top toolbar callbacks registered") 