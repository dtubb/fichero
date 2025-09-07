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
        super().__init__(app, is_mobile)
        
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
        """Create the three main library buttons with proper positioning"""
        try:
            # Left: Add Collection button
            add_collection_btn = self.create_icon_button(
                button_id="add_collection",
                icon="add_collection",
                on_press=self._on_add_collection_pressed,
                tooltip="Add Collection (Local/External/URL)"
            )
            self.add_to_left(add_collection_btn)
            
            # Right: Edit Collections and Share buttons
            edit_btn = self.create_icon_button(
                button_id="edit_collections",
                icon="collection_settings",  # Using collection_settings for edit
                on_press=self._on_edit_pressed,
                tooltip="Edit Collections"
            )
            self.add_to_right(edit_btn)
            
            share_btn = self.create_icon_button(
                button_id="share_collections",
                icon="export",  # Using export for share
                on_press=self._on_share_pressed,
                tooltip="Share/Export Collections"
            )
            self.add_to_right(share_btn)
            
            logger.info(f"Library top toolbar created with 3 buttons: left (+), right (edit, share)")
            
        except Exception as e:
            logger.error(f"Failed to create library buttons: {e}")
    
    def _create_toolbar(self):
        """Create the library top toolbar content with simplified 3-button layout"""
        try:
            # Create simplified library system buttons
            self._create_library_buttons()
            
            # Add "Collections" title to center
            title_label = toga.Label(
                "Collections",
                style=Pack(
                    flex=1,
                    text_align="center",
                    font_weight="bold",
                    color="#007AFF"  # iOS system blue
                )
            )
            self.add_to_center(title_label)
            
            # Ensure toolbar is visible
            self.container.style = Pack(height=50, background_color="white")
            
            logger.info("Library top toolbar created successfully with simplified 3-button layout")
            
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