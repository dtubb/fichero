"""
Collection Top Toolbar for Fichero

Top toolbar for collection view with hierarchical navigation and breadcrumbs.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable, List

from fichero.shared.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class CollectionTopToolbar(TopToolbar):
    """Top toolbar for collection view with hierarchical navigation"""
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = None):
        """Initialize collection top toolbar"""
        # Use provided is_mobile parameter or get from app
        if is_mobile is None:
            is_mobile = app.is_mobile
            
        # Always use automatic navigation for collection views (both mobile and desktop need back buttons)
        super().__init__(
            app, 
            title=collection_name or "Collection", 
            auto_mobile_nav=True, 
            is_mobile=is_mobile
        )
        
        # Collection context
        self.collection_name = collection_name
        self.current_path = ""
        self.path_history: List[str] = []
        
        # Navigation callbacks
        self.on_back_to_library: Optional[Callable] = None
        self.on_add_folder: Optional[Callable] = None
        self.on_add_file: Optional[Callable] = None
        self.on_navigate_back: Optional[Callable] = None
        self.on_navigate_to_path: Optional[Callable[[str], None]] = None
        self.on_edit_collection: Optional[Callable] = None
        
        # UI components
        self.breadcrumb_container = None
        
        logger.info("Collection top toolbar created with automatic mobile navigation")
    
    def _add_custom_content(self):
        """Add custom content for collection view"""
        try:
            # Don't add edit support here - it will be added via register_edit_callback
            
            logger.info("Collection top toolbar created")
            
        except Exception as e:
            logger.error(f"Failed to create collection toolbar: {e}")
    
    def register_edit_callback(self, callback: Callable):
        """Register the edit callback and add the edit button"""
        self.on_edit_collection = callback
        self.add_edit_support(callback)
    
    def _on_edit_pressed(self):
        """Handle edit button press"""
        logger.debug("Edit button pressed")
        if self.on_edit_collection:
            self.on_edit_collection()
    
    def register_navigation_callbacks(self, on_back_to_library: Optional[Callable] = None,
                                     on_navigate_back: Optional[Callable] = None,
                                     on_navigate_to_path: Optional[Callable] = None,
                                     on_add_folder: Optional[Callable] = None,
                                     on_add_file: Optional[Callable] = None,
                                     on_edit_collection: Optional[Callable] = None):
        """Register navigation callbacks"""
        try:
            self.on_back_to_library = on_back_to_library
            self.on_navigate_back = on_navigate_back
            self.on_navigate_to_path = on_navigate_to_path
            self.on_add_folder = on_add_folder
            self.on_add_file = on_add_file
            self.on_edit_collection = on_edit_collection
            
            # Set the back callback for the base toolbar
            if on_back_to_library:
                self.on_back = on_back_to_library
            
            logger.info("Navigation callbacks registered successfully")
            
        except Exception as e:
            logger.error(f"Failed to register navigation callbacks: {e}") 