"""
Fiche Top Toolbar for Fichero

Top toolbar for fiche view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class FicheTopToolbar(TopToolbar):
    """Top toolbar for fiche view - currently empty"""
    
    def __init__(self, app, collection_id: str = "", folder_path: str = "", is_mobile: bool = None):
        """Initialize fiche top toolbar"""
        super().__init__(app, is_mobile)
        
        # Fiche context
        self.collection_id = collection_id
        self.folder_path = folder_path
        
        # Fiche-specific callbacks (none for now)
        self.on_back_to_collection: Optional[Callable] = None
        self.on_process_folder: Optional[Callable] = None
        self.on_preview: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the fiche top toolbar content with basic fiche actions"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Back to collection button
            back_btn = self.create_icon_button(
                button_id="back_to_collection",
                icon="chevron.left@10x",
                on_press=self._on_back_to_collection,
                tooltip="Back to Collection"
            )
            self.add_to_left(back_btn)
            
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
            
            logger.info("Fiche top toolbar created successfully with basic fiche actions")
            
        except Exception as e:
            logger.error(f"Failed to create fiche top toolbar: {e}")
    
    def _on_back_to_collection(self, widget):
        """Handle back to collection button press"""
        logger.debug("Back to collection button pressed")
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
        # This would typically open a preview window
        pass
    
    def set_collection_context(self, collection_id: str, folder_path: str):
        """Set the collection and folder context"""
        self.collection_id = collection_id
        self.folder_path = folder_path
        
        # Update title to show current context
        if collection_id and folder_path:
            self.set_title(f"{collection_id} / {folder_path}")
        elif collection_id:
            self.set_title(f"{collection_id}")
        else:
            self.set_title("Fiche View")
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_back_to_collection: Optional[Callable] = None,
                         on_process_folder: Optional[Callable] = None,
                         on_preview: Optional[Callable] = None):
        """Register callbacks for fiche top toolbar actions"""
        super().register_callbacks(on_back, on_settings, on_about, on_help)
        self.on_back_to_collection = on_back_to_collection
        self.on_process_folder = on_process_folder
        self.on_preview = on_preview
        logger.debug("Fiche top toolbar callbacks registered") 