"""
Fiche Bottom Toolbar for Fichero

Bottom toolbar for fiche view with:
- Secondary fiche actions
- Settings and utilities
- Fiche-specific tools
"""

import toga
from toga.style import Pack
import logging
from typing import Optional, Callable

from .bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class FicheBottomToolbar(BottomToolbar):
    """Bottom toolbar for fiche view"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize fiche bottom toolbar"""
        super().__init__(app, is_mobile)
        
        # Fiche-specific callbacks
        self.on_export_fiches: Optional[Callable] = None
        self.on_share_fiches: Optional[Callable] = None
        self.on_search_fiches: Optional[Callable] = None
        self.on_folder_settings: Optional[Callable] = None
        
        # Create the toolbar content
        self._create_toolbar()
    
    def _create_toolbar(self):
        """Create the fiche bottom toolbar content"""
        try:
            # Create secondary actions area (handled by parent)
            super()._create_toolbar()
            
            # Add fiche-specific secondary actions
            self._create_fiche_secondary_actions()
            
            logger.info("Fiche bottom toolbar created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create fiche bottom toolbar: {e}")
    
    def _create_fiche_secondary_actions(self):
        """Create fiche-specific secondary actions"""
        # Export Fiches button on the left
        export_btn = self.add_secondary_action(
            button_id="export_fiches",
            text="Export Fiches",
            icon="export",
            on_press=self._on_export_fiches_clicked,
            tooltip="Export processed fiches"
        )
        
        # Share Fiches button on the left
        share_btn = self.add_secondary_action(
            button_id="share_fiches",
            text="Share",
            icon="archivebox",
            on_press=self._on_share_fiches_clicked,
            tooltip="Share fiches with others"
        )
        
        # Search Fiches button on the left
        search_btn = self.add_secondary_action(
            button_id="search_fiches",
            text="Search",
            icon="magnifyingglass",
            on_press=self._on_search_fiches_clicked,
            tooltip="Search within fiches"
        )
        
        # Folder Settings button on the left
        settings_btn = self.add_secondary_action(
            button_id="folder_settings",
            text="Settings",
            icon="gear",
            on_press=self._on_folder_settings_clicked,
            tooltip="Configure folder settings"
        )
        
        # Add status info in the center
        self.add_status_info("Ready")
    
    def _on_export_fiches_clicked(self, widget):
        """Handle export fiches button click"""
        logger.debug("Export fiches clicked")
        if self.on_export_fiches:
            self.on_export_fiches()
    
    def _on_share_fiches_clicked(self, widget):
        """Handle share fiches button click"""
        logger.debug("Share fiches clicked")
        if self.on_share_fiches:
            self.on_share_fiches()
    
    def _on_search_fiches_clicked(self, widget):
        """Handle search fiches button click"""
        logger.debug("Search fiches clicked")
        if self.on_search_fiches:
            self.on_search_fiches()
    
    def _on_folder_settings_clicked(self, widget):
        """Handle folder settings button click"""
        logger.debug("Folder settings clicked")
        if self.on_folder_settings:
            self.on_folder_settings()
    
    def register_callbacks(self, on_settings: Optional[Callable] = None,
                         on_about: Optional[Callable] = None,
                         on_help: Optional[Callable] = None,
                         on_export_fiches: Optional[Callable] = None,
                         on_share_fiches: Optional[Callable] = None,
                         on_search_fiches: Optional[Callable] = None,
                         on_folder_settings: Optional[Callable] = None):
        """Register callbacks for fiche bottom toolbar actions"""
        super().register_callbacks(on_settings, on_about, on_help)
        self.on_export_fiches = on_export_fiches
        self.on_share_fiches = on_share_fiches
        self.on_search_fiches = on_search_fiches
        self.on_folder_settings = on_folder_settings
        logger.debug("Fiche bottom toolbar callbacks registered")
    
    def set_export_available(self, available: bool):
        """Set whether export is available"""
        export_btn = self.get_button("export_fiches")
        if export_btn:
            export_btn.enabled = available
    
    def set_share_available(self, available: bool):
        """Set whether share is available"""
        share_btn = self.get_button("share_fiches")
        if share_btn:
            share_btn.enabled = available
    
    def update_fiche_count(self, count: int):
        """Update the export button to show fiche count"""
        export_btn = self.get_button("export_fiches")
        if export_btn:
            export_btn.text = f"Export Fiches ({count})"
    
    def update_status(self, status_text: str):
        """Update the status information"""
        # Find and update the status label
        for child in self.content.children:
            if isinstance(child, toga.Label) and child.text == "Ready":
                child.text = status_text
                break 