"""
Fiche Top Toolbar for Fichero

Top toolbar for fiche view with:
- Title and navigation
- Back to collection button
- Folder name display
- Primary fiche actions
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class FicheTopToolbar(TopToolbar):
    """Top toolbar for fiche view"""
    
    def __init__(self, app, folder_name: str = "", is_mobile: bool = False):
        """Initialize fiche top toolbar"""
        title = f"📁 {folder_name}" if folder_name else "📁 Folder"
        super().__init__(app, title, is_mobile)
        
        self.folder_name = folder_name
        
        # Fiche-specific callbacks
        self.on_back_to_collection: Optional[Callable] = None
        self.on_process_folder: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the fiche top toolbar content"""
        try:
            # Create title and navigation area (handled by parent)
            super()._create_toolbar()
            
            # Add back button to collection
            self.add_back_button("← Collection", self._on_back_to_collection_clicked)
            
            # Add fiche-specific primary actions
            self._create_fiche_actions()
            
            logger.info("Fiche top toolbar created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create fiche top toolbar: {e}")
    
    def _create_fiche_actions(self):
        """Create fiche-specific primary actions"""
        # Process Folder button on the right
        process_btn = self.add_primary_action(
            button_id="process_folder",
            text="Process Folder",
            icon="process",
            on_press=self._on_process_folder_clicked,
            tooltip="Process all documents in this folder"
        )
    
    def _on_back_to_collection_clicked(self, widget):
        """Handle back to collection button click"""
        logger.debug("Back to collection clicked")
        if self.on_back_to_collection:
            self.on_back_to_collection()
    
    def _on_process_folder_clicked(self, widget):
        """Handle process folder button click"""
        logger.debug("Process folder clicked")
        if self.on_process_folder:
            self.on_process_folder()
    
    def update_folder_name(self, name: str):
        """Update the folder name display"""
        self.folder_name = name
        title = f"📁 {name}" if name else "📁 Folder"
        self.set_title(title)
    
    def set_processing_state(self, is_processing: bool):
        """Update the process button state"""
        process_btn = self.get_button("process_folder")
        if process_btn:
            if is_processing:
                process_btn.text = "⏳ Processing..."
                process_btn.enabled = False
            else:
                process_btn.text = "Process Folder"
                process_btn.enabled = True
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_title_click: Optional[Callable] = None,
                         on_back_to_collection: Optional[Callable] = None,
                         on_process_folder: Optional[Callable] = None):
        """Register callbacks for fiche top toolbar actions"""
        super().register_callbacks(on_back, on_title_click)
        self.on_back_to_collection = on_back_to_collection
        self.on_process_folder = on_process_folder
        logger.debug("Fiche top toolbar callbacks registered") 