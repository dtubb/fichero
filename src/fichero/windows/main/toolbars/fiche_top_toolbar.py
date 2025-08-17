"""
Fiche Top Toolbar for Fichero

Top toolbar for fiche view - currently empty as requested.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class FicheTopToolbar(TopToolbar):
    """Top toolbar for fiche view - currently empty"""
    
    def __init__(self, app, collection_id: str = "", folder_path: str = "", is_mobile: bool = False):
        """Initialize fiche top toolbar"""
        super().__init__(app, is_mobile)
        
        # Fiche context
        self.collection_id = collection_id
        self.folder_path = folder_path
        
        # Fiche-specific callbacks (none for now)
        self.on_back_to_collection: Optional[Callable] = None
        self.on_process_folder: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the fiche top toolbar content - currently empty"""
        try:
            # Base container already created by parent class
            # No need to call super()._create_toolbar()
            
            # No buttons for now - toolbar is empty as requested
            # No title either - completely blank
            
            logger.info("Fiche top toolbar created successfully (completely empty)")
            
        except Exception as e:
            logger.error(f"Failed to create fiche top toolbar: {e}")
    
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
                         on_process_folder: Optional[Callable] = None):
        """Register callbacks for fiche top toolbar actions"""
        super().register_callbacks(on_back, on_settings, on_about, on_help)
        self.on_back_to_collection = on_back_to_collection
        self.on_process_folder = on_process_folder
        logger.debug("Fiche top toolbar callbacks registered") 