"""
Collection Top Toolbar for Fichero

Top toolbar for collection view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .top_toolbar import TopToolbar

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
        """Create the collection top toolbar content - currently empty"""
        try:
            # Base container already created by parent class
            # No need to call super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No title either - completely blank
            
            logger.info("Collection top toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create collection top toolbar: {e}")
    
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