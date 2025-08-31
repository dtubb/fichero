"""
Collection Top Toolbar for Fichero

Top toolbar for collection view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class CollectionTopToolbar(TopToolbar):
    """Top toolbar for collection view - currently empty"""
    
    def __init__(self, app, collection_id: str = "", is_mobile: bool = False):
        """Initialize collection top toolbar"""
        super().__init__(app, is_mobile)
        
        # Collection context
        self.collection_id = collection_id
        
        # Collection-specific callbacks (none for now)
        self.on_back_to_library: Optional[Callable] = None
        self.on_add_folder: Optional[Callable] = None
        self.on_add_file: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection top toolbar content with basic collection actions"""
        try:
            # Back to library button
            back_btn = self.create_icon_button(
                button_id="back_to_library",
                icon="chevron.left@10x",
                on_press=self._on_back_to_library,
                tooltip="Back to Library"
            )
            self.add_to_left(back_btn)
            
            # Add folder button
            add_folder_btn = self.create_icon_button(
                button_id="add_folder",
                icon="add_folder",
                on_press=self._on_add_folder,
                tooltip="Add Folder"
            )
            self.add_to_left(add_folder_btn)
            
            # Add file button
            add_file_btn = self.create_icon_button(
                button_id="add_file",
                icon="add_file",
                on_press=self._on_add_file,
                tooltip="Add File"
            )
            self.add_to_left(add_file_btn)
            
            logger.info("Collection top toolbar created successfully with basic collection actions")
            
        except Exception as e:
            logger.error(f"Failed to create collection top toolbar: {e}")
    
    def _on_back_to_library(self, widget):
        """Handle back to library button press"""
        logger.debug("Back to library button pressed")
        if self.on_back_to_library:
            self.on_back_to_library()
    
    def _on_add_folder(self, widget):
        """Handle add folder button press"""
        logger.debug("Add folder button pressed")
        if self.on_add_folder:
            self.on_add_folder()
    
    def _on_add_file(self, widget):
        """Handle add file button press"""
        logger.debug("Add file button pressed")
        if self.on_add_file:
            self.on_add_file()
    
    def set_collection_context(self, collection_id: str):
        """Set the collection context"""
        self.collection_id = collection_id
        if collection_id:
            self.set_title(f"Collection: {collection_id}")
        else:
            self.set_title("Collection View")
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_back_to_library: Optional[Callable] = None,
                         on_add_folder: Optional[Callable] = None,
                         on_add_file: Optional[Callable] = None):
        """Register callbacks for collection top toolbar actions"""
        # Call parent with only the parameters it expects
        super().register_callbacks(on_back, None)  # on_title_click is not used
        self.on_back_to_library = on_back_to_library
        self.on_add_folder = on_add_folder
        self.on_add_file = on_add_file
        logger.debug("Collection top toolbar callbacks registered") 