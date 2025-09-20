"""
Library Top Toolbar for Fichero

Top toolbar for library view with library system integration.
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.shared.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class LibraryTopToolbar(TopToolbar):
    """Top toolbar for library view with library system integration"""
    
    def __init__(self, app, is_mobile: bool = None):
        """Initialize library top toolbar"""
        # Library view is the root - don't auto-create mobile nav (no back button needed)
        super().__init__(app, title="Library", auto_mobile_nav=False, is_mobile=is_mobile)
        
        # Library-specific callbacks
        self.on_add_collection: Optional[Callable] = None
        self.on_activity_monitor: Optional[Callable] = None
        self.on_import_collection: Optional[Callable] = None
        self.on_export_collection: Optional[Callable] = None
        self.on_edit_collection: Optional[Callable] = None
        self.on_manage_collections: Optional[Callable] = None
        
        # Create the toolbar content - this will call _create_toolbar automatically
    
    def _add_custom_content(self):
        """Add custom content for library view"""
        try:
            # Library is the root view - show title and edit button
            self.add_title_only("Library")
            
            # Don't add edit support here - it will be added via register_edit_callback
            
            logger.info("Library top toolbar created with title")
            
        except Exception as e:
            logger.error(f"Failed to create library toolbar: {e}")
    
    def register_edit_callback(self, callback: Callable):
        """Register the edit callback and add the edit button"""
        self.on_edit_collection = callback
        self.add_edit_support(callback)
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_add_collection: Optional[Callable] = None,
                         on_edit_collection: Optional[Callable] = None,
                         on_share_collections: Optional[Callable] = None):
        """Register library-specific callbacks"""
        self.on_edit_collection = on_edit_collection
        
        logger.debug("Simplified library top toolbar callbacks registered") 
