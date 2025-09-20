"""
Fiche Top Toolbar for Fichero

Top toolbar for fiche view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class FicheTopToolbar(TopToolbar):
    """Top toolbar for fiche view - currently empty"""
    
    def __init__(self, app, collection_id: str = "", folder_path: str = "", is_mobile: bool = None):
        """Initialize fiche top toolbar"""
        # Use automatic mobile navigation
        super().__init__(
            app, 
            title="Collection",  # Back to collection
            auto_mobile_nav=True, 
            is_mobile=is_mobile
        )
        
        # Fiche context
        self.collection_id = collection_id
        self.folder_path = folder_path
        
        # Fiche-specific callbacks
        self.on_back_to_collection: Optional[Callable] = None
        self.on_process_folder: Optional[Callable] = None
        self.on_preview: Optional[Callable] = None
        
        logger.info("Fiche top toolbar created with automatic mobile navigation")
    
    def _add_custom_content(self):
        """Add fiche-specific content - called by TopToolbar after auto navigation"""
        try:
            # Process folder button
            process_btn = self.create_icon_button(
                button_id="process_folder",
                icon="process",
                on_press=self._on_process_folder,
                tooltip="Process Folder"
            )
            self.add_to_left(process_btn)
            
            # Preview button
            preview_btn = self.create_icon_button(
                button_id="preview",
                icon="magnifyingglass",
                on_press=self._on_preview,
                tooltip="Preview"
            )
            self.add_to_left(preview_btn)
            
            logger.debug("Added fiche action buttons")
            
        except Exception as e:
            logger.error(f"Failed to add fiche custom content: {e}")
    
    def _on_back_pressed(self, widget):
        """Handle back button press - overrides TopToolbar default"""
        logger.debug("🔙 Fiche back to collection button pressed")
        if self.on_back_to_collection:
            self.on_back_to_collection()
    
    def _on_process_folder(self, widget):
        """Handle process folder button press"""
        logger.debug("Process folder button pressed")
        if self.on_process_folder:
            self.on_process_folder()
    
    def _on_preview(self, widget):
        """Handle preview button press"""
        logger.debug("Preview button pressed")
        if self.on_preview:
            self.on_preview()
    
    def register_callbacks(self, 
                         on_back_to_collection: Optional[Callable] = None,
                         on_process_folder: Optional[Callable] = None,
                         on_preview: Optional[Callable] = None):
        """Register fiche-specific callbacks"""
        self.on_back_to_collection = on_back_to_collection
        self.on_process_folder = on_process_folder
        self.on_preview = on_preview 