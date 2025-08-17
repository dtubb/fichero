"""
Collection Top Toolbar for Fichero

Top toolbar for collection view with:
- Title and navigation
- Back to library button
- Collection name display
- Primary collection actions
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class CollectionTopToolbar(TopToolbar):
    """Top toolbar for collection view"""
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = False):
        """Initialize collection top toolbar"""
        title = f"📁 {collection_name}" if collection_name else "📁 Collection"
        super().__init__(app, title, is_mobile)
        
        self.collection_name = collection_name
        
        # Collection-specific callbacks
        self.on_back_to_library: Optional[Callable] = None
        self.on_add_folder: Optional[Callable] = None
        self.on_add_file: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection top toolbar content"""
        try:
            # Create title and navigation area (handled by parent)
            super()._create_toolbar()
            
            # Add back button to library
            self.add_back_button("← Library", self._on_back_to_library_clicked)
            
            # Add collection-specific primary actions
            self._create_collection_actions()
            
            logger.info("Collection top toolbar created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create collection top toolbar: {e}")
    
    def _create_collection_actions(self):
        """Create collection-specific primary actions"""
        # Add Folder button on the right
        add_folder_btn = self.add_primary_action(
            button_id="add_folder",
            text="Add Folder",
            icon="add_folder",
            on_press=self._on_add_folder_clicked,
            tooltip="Add a new folder"
        )
        
        # Add File button on the right
        add_file_btn = self.add_primary_action(
            button_id="add_file",
            text="Add File",
            icon="add_file",
            on_press=self._on_add_file_clicked,
            tooltip="Add a new file"
        )
    
    def _on_back_to_library_clicked(self, widget):
        """Handle back to library button click"""
        logger.debug("Back to library clicked")
        if self.on_back_to_library:
            self.on_back_to_library()
    
    def _on_add_folder_clicked(self, widget):
        """Handle add folder button click"""
        logger.debug("Add folder clicked")
        if self.on_add_folder:
            self.on_add_folder()
    
    def _on_add_file_clicked(self, widget):
        """Handle add file button click"""
        logger.debug("Add file clicked")
        if self.on_add_file:
            self.on_add_file()
    
    def update_collection_name(self, name: str):
        """Update the collection name display"""
        self.collection_name = name
        title = f"📁 {name}" if name else "📁 Collection"
        self.set_title(title)
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_title_click: Optional[Callable] = None,
                         on_back_to_library: Optional[Callable] = None,
                         on_add_folder: Optional[Callable] = None,
                         on_add_file: Optional[Callable] = None):
        """Register callbacks for collection top toolbar actions"""
        super().register_callbacks(on_back, on_title_click)
        self.on_back_to_library = on_back_to_library
        self.on_add_folder = on_add_folder
        self.on_add_file = on_add_file
        logger.debug("Collection top toolbar callbacks registered") 