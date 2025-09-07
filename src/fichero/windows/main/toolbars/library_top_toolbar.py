"""
Library Top Toolbar for Fichero

Top toolbar for library view with library system integration.D!3
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from fichero.windows.main.toolbars.top_toolbar import TopToolbar

logger = logging.getLogger(__name__)


class LibraryTopToolbar(TopToolbar):
    """Top toolbar for library view with library system integration"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize library top toolbar"""
        super().__init__(app, "Collections", is_mobile)  # Fixed: pass title parameter
        
        # Library-specific callbacks
        self.on_add_collection: Optional[Callable] = None
        self.on_activity_monitor: Optional[Callable] = None
        self.on_import_collection: Optional[Callable] = None
        self.on_export_collection: Optional[Callable] = None
        self.on_edit_collection: Optional[Callable] = None
        self.on_manage_collections: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_library_buttons(self):
        """Legacy method - no longer needed"""
        pass
    
    def _create_toolbar(self):
        """Create the library top toolbar content with simplified 3-button layout"""
        try:
            # Call parent to set up basic structure
            super()._create_toolbar()
            
            # Left: Add Collection button
            self.add_button_left(
                icon="add_collection",
                on_press=self._on_add_collection_pressed,
                tooltip="Add Collection (Local/External/URL)"
            )
            
            # Center: Collections title using smart helper
            self.add_centered_title_only("Collections", on_title_click=self._on_title_pressed)
            
            # Right: Edit and Share buttons using smart helper
            self.add_standard_right_buttons([
                {
                    'icon': 'collection_settings',
                    'on_press': self._on_edit_pressed,
                    'tooltip': 'Edit Collections'
                },
                {
                    'icon': 'export',
                    'on_press': self._on_share_pressed,
                    'tooltip': 'Share/Export Collections'
                }
            ])
            
            logger.info("Library top toolbar created using smart base methods")
            
        except Exception as e:
            logger.error(f"Failed to create library toolbar: {e}")
    
    def _on_add_collection_pressed(self, widget):
        """Handle add collection button press - opens collection type options"""
        logger.debug("Add collection button pressed - should open collection type options view")
        if self.on_add_collection:
            self.on_add_collection()
    
    def _on_edit_pressed(self, widget):
        """Handle edit collections button press"""
        logger.debug("Edit collections button pressed")
        if self.on_edit_collection:
            self.on_edit_collection()
    
    def _on_share_pressed(self, widget):
        """Handle share/export button press"""
        logger.debug("Share collections button pressed")
        if self.on_share_collections:
            self.on_share_collections()
    
    def _on_title_pressed(self, widget):
        """Handle title button press (mobile only)"""
        logger.debug("Library title pressed")
        # Could show library info, statistics, or context menu
        pass
    
    def register_callbacks(self, on_back: Optional[Callable] = None,
                         on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_add_collection: Optional[Callable] = None,
                         on_edit_collection: Optional[Callable] = None,
                         on_share_collections: Optional[Callable] = None):
        """Register callbacks for simplified library top toolbar actions"""
        # Call parent with only the parameters it expects
        super().register_callbacks(on_back, None)  # on_title_click is not used
        self.on_add_collection = on_add_collection
        self.on_edit_collection = on_edit_collection
        self.on_share_collections = on_share_collections
        logger.debug("Simplified library top toolbar callbacks registered") 