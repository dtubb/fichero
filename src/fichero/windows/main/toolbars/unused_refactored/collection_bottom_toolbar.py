"""
Collection Bottom Toolbar for Fichero

Bottom toolbar for collection view with:
- Secondary collection actions
- Settings and utilities
- Collection-specific tools
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class CollectionBottomToolbar(BottomToolbar):
    """Bottom toolbar for collection view"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize collection bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Collection-specific callbacks
        self.on_collection_settings: Optional[Callable] = None
        self.on_process_collection: Optional[Callable] = None
        self.on_export_collection: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the collection bottom toolbar content"""
        try:
            # Create secondary actions area (handled by parent)
            super()._create_toolbar()
            
            # Add collection-specific secondary actions
            self._create_collection_secondary_actions()
            
            logger.info("Collection bottom toolbar created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create collection bottom toolbar: {e}")
    
    def _create_collection_secondary_actions(self):
        """Create collection-specific secondary actions"""
        # Process Collection button on the left
        process_btn = self.add_secondary_action(
            button_id="process_collection",
            text="Process Collection",
            icon="process",
            on_press=self._on_process_collection_clicked,
            tooltip="Process all items in this collection"
        )
        
        # Export Collection button on the left
        export_btn = self.add_secondary_action(
            button_id="export_collection",
            text="Export Collection",
            icon="export",
            on_press=self._on_export_collection_clicked,
            tooltip="Export collection data"
        )
        
        # Collection Settings button on the left
        settings_btn = self.add_secondary_action(
            button_id="collection_settings",
            text="Settings",
            icon="gear",
            on_press=self._on_collection_settings_clicked,
            tooltip="Collection settings"
        )
        
        # Add status info in the center
        self.add_status_info("Ready")
    
    def _on_process_collection_clicked(self, widget):
        """Handle process collection button click"""
        logger.debug("Process collection clicked")
        if self.on_process_collection:
            self.on_process_collection()
    
    def _on_export_collection_clicked(self, widget):
        """Handle export collection button click"""
        logger.debug("Export collection clicked")
        if self.on_export_collection:
            self.on_export_collection()
    
    def _on_collection_settings_clicked(self, widget):
        """Handle collection settings button click"""
        logger.debug("Collection settings clicked")
        if self.on_collection_settings:
            self.on_collection_settings()
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_collection_settings: Optional[Callable] = None,
                         on_process_collection: Optional[Callable] = None,
                         on_export_collection: Optional[Callable] = None):
        """Register callbacks for collection bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        self.on_collection_settings = on_collection_settings
        self.on_process_collection = on_process_collection
        self.on_export_collection = on_export_collection
        logger.debug("Collection bottom toolbar callbacks registered")
    
    def set_processing_state(self, is_processing: bool):
        """Update the process button state"""
        process_btn = self.get_button("process_collection")
        if process_btn:
            if is_processing:
                process_btn.text = "⏳ Processing..."
                process_btn.enabled = False
            else:
                process_btn.text = "Process Collection"
                process_btn.enabled = True
    
    def set_export_available(self, available: bool):
        """Set whether export is available"""
        export_btn = self.get_button("export_collection")
        if export_btn:
            export_btn.enabled = available
    
    def update_status(self, status_text: str):
        """Update the status information"""
        # Find and update the status label
        for child in self.content.children:
            if isinstance(child, toga.Label) and child.text == "Ready":
                child.text = status_text
                break 