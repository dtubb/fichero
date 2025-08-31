"""
Refactored Fiche View for Fichero

Displays the contents of a specific folder within a collection,
showing both original files and processed fiches.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, List, Dict, Any

from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.toolbars.fiche_top_toolbar import FicheTopToolbar
from fichero.windows.main.toolbars.fiche_bottom_toolbar import FicheBottomToolbar
from fichero.windows.main.containers.scroll_container import ScrollableContainer
from fichero.windows.main.styling.color_constants import *

logger = logging.getLogger(__name__)


class FicheView(BaseView):
    """Fiche view for displaying folder contents"""
    
    def __init__(self, app, collection_id: str, folder_path: str, is_mobile: bool = False):
        """Initialize fiche view"""
        super().__init__(app, is_mobile)
        
        self.collection_id = collection_id
        self.folder_path = folder_path
        self.folder_name = self._extract_folder_name(folder_path)
        
        # Create separate top and bottom toolbars
        self.top_toolbar = FicheTopToolbar(app, self.folder_name, is_mobile)
        self.bottom_toolbar = FicheBottomToolbar(app, is_mobile)
        
        # Set both toolbars
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Content containers
        self.originals_container: Optional[toga.Box] = None
        self.fiches_container: Optional[toga.Box] = None
        
        # Data
        self.original_files: List[Dict[str, Any]] = []
        self.fiche_files: List[Dict[str, Any]] = []
        
        # Initialize view
        self._create_content()
        self._setup_toolbar()
        self._setup_scroll_integration()
        
        logger.debug(f"Fiche view initialized for folder: {folder_path}")
    
    def _extract_folder_name(self, folder_path: str) -> str:
        """Extract folder name from path"""
        try:
            import os
            return os.path.basename(folder_path) if folder_path else "Unknown Folder"
        except Exception as e:
            logger.error(f"Failed to extract folder name: {e}")
            return "Unknown Folder"
    
    def _create_content(self):
        """Create the main content of the fiche view"""
        try:
            # Create main content container
            content_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
            
            # Create header
            header = self._create_header()
            content_box.add(header)
            
            # Create content sections
            content_sections = self._create_content_sections()
            content_box.add(content_sections)
            
            # Set the content
            self.set_content(content_box)
            
            logger.debug("Fiche view content created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create fiche view content: {e}")
    
    def _create_header(self) -> toga.Box:
        """Create the header section"""
        try:
            header_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 20, 0)))
            
            # Folder icon
            folder_icon = toga.Label("📁", style=Pack(margin=(0, 10, 0, 0)))
            header_box.add(folder_icon)
            
            # Folder name and path
            name_label = toga.Label(
                self.folder_name,
                style=Pack(font_size=18, font_weight="bold", color=FICHE_TEXT)
            )
            header_box.add(name_label)
            
            # Path info
            if self.folder_path:
                path_label = toga.Label(
                    f" ({self.folder_path})",
                    style=Pack(font_size=12, color=COMMON_SECONDARY_TEXT, margin=(0, 0, 0, 10))
                )
                header_box.add(path_label)
            
            # Spacer
            spacer = toga.Box(style=Pack(flex=1))
            header_box.add(spacer)
            
            # Status indicator
            status_label = toga.Label(
                "Ready",
                style=Pack(font_size=12, color=STATUS_SUCCESS, margin=(0, 10, 0, 0))
            )
            header_box.add(status_label)
            
            return header_box
            
        except Exception as e:
            logger.error(f"Failed to create fiche view header: {e}")
            return toga.Box()
    
    def _create_content_sections(self) -> toga.Box:
        """Create the main content sections"""
        try:
            sections_box = toga.Box(style=Pack(direction=COLUMN))
            
            # Originals section
            originals_section = self._create_originals_section()
            sections_box.add(originals_section)
            
            # Fiches section
            fiches_section = self._create_fiches_section()
            sections_box.add(fiches_section)
            
            return sections_box
            
        except Exception as e:
            logger.error(f"Failed to create content sections: {e}")
            return toga.Box()
    
    def _create_originals_section(self) -> toga.Box:
        """Create the originals section"""
        try:
            section_box = toga.Box(style=Pack(direction=COLUMN, margin=(0, 0, 20, 0)))
            
            # Section header
            header_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 10, 0)))
            
            # Icon and title
            icon = toga.Label("📄", style=Pack(margin=(0, 5, 0, 0)))
            header_box.add(icon)
            
            title = toga.Label(
                "Original Files",
                style=Pack(font_size=16, font_weight="bold", color=FICHE_TEXT)
            )
            header_box.add(title)
            
            # Count
            count_label = toga.Label(
                f" ({len(self.original_files)})",
                style=Pack(font_size=14, color=COMMON_SECONDARY_TEXT)
            )
            header_box.add(count_label)
            
            # Spacer
            spacer = toga.Box(style=Pack(flex=1))
            header_box.add(spacer)
            
            # Add button
            add_button = toga.Button(
                "Add Files",
                on_press=self._on_add_files,
                style=Pack(margin=(5, 10))
            )
            header_box.add(add_button)
            
            section_box.add(header_box)
            
            # Content container
            self.originals_container = toga.Box(style=Pack(direction=COLUMN))
            section_box.add(self.originals_container)
            
            # Add placeholder content
            self._add_placeholder_originals()
            
            return section_box
            
        except Exception as e:
            logger.error(f"Failed to create originals section: {e}")
            return toga.Box()
    
    def _create_fiches_section(self) -> toga.Box:
        """Create the fiches section"""
        try:
            section_box = toga.Box(style=Pack(direction=COLUMN, margin=(0, 0, 20, 0)))
            
            # Section header
            header_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 10, 0)))
            
            # Icon and title
            icon = toga.Label("⚡", style=Pack(margin=(0, 5, 0, 0)))
            header_box.add(icon)
            
            title = toga.Label(
                "Processed Fiches",
                style=Pack(font_size=16, font_weight="bold", color=FICHE_TEXT)
            )
            header_box.add(title)
            
            # Count
            count_label = toga.Label(
                f" ({len(self.fiche_files)})",
                style=Pack(font_size=14, color=COMMON_SECONDARY_TEXT)
            )
            header_box.add(count_label)
            
            # Spacer
            spacer = toga.Box(style=Pack(flex=1))
            header_box.add(spacer)
            
            # Process button
            process_button = toga.Button(
                "Process Folder",
                on_press=self._on_process_folder,
                style=Pack(margin=(5, 10))
            )
            header_box.add(process_button)
            
            section_box.add(header_box)
            
            # Content container
            self.fiches_container = toga.Box(style=Pack(direction=COLUMN))
            section_box.add(self.fiches_container)
            
            # Add placeholder content
            self._add_placeholder_fiches()
            
            return section_box
            
        except Exception as e:
            logger.error(f"Failed to create fiches section: {e}")
            return toga.Box()
    
    def _add_placeholder_originals(self):
        """Add placeholder content for originals"""
        try:
            if not self.originals_container:
                return
            
            # Clear existing content
            self.originals_container.remove_all_children()
            
            # Add placeholder message
            placeholder = toga.Label(
                "No original files found. Add files to this folder to get started.",
                style=Pack(margin=20, color=COMMON_PLACEHOLDER)
            )
            self.originals_container.add(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to add placeholder originals: {e}")
    
    def _add_placeholder_fiches(self):
        """Add placeholder content for fiches"""
        try:
            if not self.fiches_container:
                return
            
            # Clear existing content
            self.fiches_container.remove_all_children()
            
            # Add placeholder message
            placeholder = toga.Label(
                "No processed fiches found. Process this folder to create fiches.",
                style=Pack(margin=20, color=COMMON_PLACEHOLDER)
            )
            self.fiches_container.add(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to add placeholder fiches: {e}")
    
    def _setup_toolbar(self):
        """Set up the fiche toolbars"""
        try:
            # Register toolbar callbacks
            self.top_toolbar.register_callbacks(
                on_back_to_collection=self._on_back_to_collection,
                on_process_folder=self._on_process_folder
            )
            
            self.bottom_toolbar.register_callbacks(
                on_export_fiches=self._on_export_fiches,
                on_share_fiches=self._on_share_fiches,
                on_search_fiches=self._on_search_fiches,
                on_folder_settings=self._on_folder_settings
            )
            
            logger.debug("Fiche toolbars set up successfully")
            
        except Exception as e:
            logger.error(f"Failed to set up fiche toolbars: {e}")
    
    def _setup_scroll_integration(self):
        """Set up scroll container integration"""
        try:
            # Create scrollable container
            scroll_container = ScrollableContainer(self.app)
            
            # Set the scroll container as the main content wrapper
            self.set_scroll_container(scroll_container)
            
            logger.debug("Scroll container integration set up successfully")
            
        except Exception as e:
            logger.error(f"Failed to set up scroll container integration: {e}")
    
    # ===== TOOLBAR CALLBACKS =====
    
    def _on_back_to_collection(self, widget):
        """Handle back to collection navigation"""
        try:
            logger.debug("Back to collection navigation requested")
            # This would typically trigger navigation back to collection view
            
        except Exception as e:
            logger.error(f"Failed to handle back to collection: {e}")
    
    def _on_add_folder(self, widget):
        """Handle add folder action"""
        try:
            logger.debug("Add folder action requested")
            # This would typically open a folder picker dialog
            
        except Exception as e:
            logger.error(f"Failed to handle add folder: {e}")
    
    def _on_process_folder(self, widget):
        """Handle process folder action"""
        try:
            logger.debug("Process folder action requested")
            # This would typically trigger folder processing
            
        except Exception as e:
            logger.error(f"Failed to handle process folder: {e}")
    
    def _on_export_fiches(self, widget):
        """Handle export fiches action"""
        try:
            logger.debug("Export fiches action requested")
            # This would typically open export dialog
            
        except Exception as e:
            logger.error(f"Failed to handle export fiches: {e}")
    
    def _on_share_fiches(self, widget):
        """Handle share fiches action"""
        try:
            logger.debug("Share fiches action requested")
            # This would typically open share dialog
            
        except Exception as e:
            logger.error(f"Failed to handle share fiches: {e}")
    
    def _on_search_fiches(self, widget):
        """Handle search fiches action"""
        try:
            logger.debug("Search fiches action requested")
            # This would typically open search interface
            
        except Exception as e:
            logger.error(f"Failed to handle search fiches: {e}")
    
    def _on_folder_settings(self, widget):
        """Handle folder settings action"""
        try:
            logger.debug("Folder settings action requested")
            # This would typically open folder settings dialog
            
        except Exception as e:
            logger.error(f"Failed to handle folder settings: {e}")
    
    # ===== CONTENT CALLBACKS =====
    
    def _on_add_files(self, widget):
        """Handle add files button press"""
        try:
            logger.debug("Add files button pressed")
            # This would typically open a file picker dialog
            
        except Exception as e:
            logger.error(f"Failed to handle add files: {e}")
    
    # ===== PUBLIC METHODS =====
    
    def refresh_content(self):
        """Refresh the view content"""
        try:
            # Refresh original files
            self._refresh_originals()
            
            # Refresh fiches
            self._refresh_fiches()
            
            # Update counts
            self._update_counts()
            
            logger.debug("Fiche view content refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh fiche view content: {e}")
    
    def _refresh_originals(self):
        """Refresh the originals section"""
        try:
            # This would typically reload original files from disk
            # For now, just update the placeholder
            self._add_placeholder_originals()
            
        except Exception as e:
            logger.error(f"Failed to refresh originals: {e}")
    
    def _refresh_fiches(self):
        """Refresh the fiches section"""
        try:
            # This would typically reload processed fiches from disk
            # For now, just update the placeholder
            self._add_placeholder_fiches()
            
        except Exception as e:
            logger.error(f"Failed to refresh fiches: {e}")
    
    def _update_counts(self):
        """Update the file counts in headers"""
        try:
            # This would update the count labels in section headers
            # For now, just log the update
            logger.debug(f"Updated counts - Originals: {len(self.original_files)}, Fiches: {len(self.fiche_files)}")
            
        except Exception as e:
            logger.error(f"Failed to update counts: {e}")
    
    def set_folder_data(self, original_files: List[Dict[str, Any]], fiche_files: List[Dict[str, Any]]):
        """Set the folder data for display"""
        try:
            self.original_files = original_files or []
            self.fiche_files = fiche_files or []
            
            # Refresh the display
            self.refresh_content()
            
            logger.debug(f"Folder data set - Originals: {len(self.original_files)}, Fiches: {len(self.fiche_files)}")
            
        except Exception as e:
            logger.error(f"Failed to set folder data: {e}")
    
    def get_folder_info(self) -> Dict[str, Any]:
        """Get information about the current folder"""
        return {
            'collection_id': self.collection_id,
            'folder_path': self.folder_path,
            'folder_name': self.folder_name,
            'original_count': len(self.original_files),
            'fiche_count': len(self.fiche_files),
            'is_mobile': self.is_mobile
        } 