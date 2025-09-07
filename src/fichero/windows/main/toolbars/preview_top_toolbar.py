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
        """Create the preview top toolbar content with back button and title"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Create back button (left side) using the correct method
            back_button = self.create_navigation_button(
                button_id="back",
                text="← Back", 
                on_press=self._on_back_pressed,
                tooltip="Go back to collection"
            )
            
            # Create title (center)
            self.title_label = toga.Label(
                "Preview",
                style=Pack(
                    flex=1,
                    text_align="center",
                    font_weight="bold",
                    color="#007AFF"  # iOS system blue
                )
            )
            
            # Add to toolbar using proper BaseToolbar methods
            self.add_to_left(back_button)
            self.add_to_center(self.title_label)
            
            logger.info("Preview top toolbar created successfully with back button and title")
            
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