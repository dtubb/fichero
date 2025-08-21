"""
Refactored Preview View for Fichero

Displays document previews with navigation controls and metadata.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any

from .base_view import BaseView
from ..toolbars.preview_top_toolbar import PreviewTopToolbar
from ..toolbars.preview_bottom_toolbar import PreviewBottomToolbar
from ..containers.scroll_container import ScrollableContainer
from ..styling.color_constants import *

logger = logging.getLogger(__name__)


class PreviewView(BaseView):
    """Preview view for displaying document previews"""
    
    def __init__(self, app, document_path: str, is_mobile: bool = False):
        """Initialize preview view"""
        super().__init__(app, is_mobile)
        
        self.document_path = document_path
        self.document_name = self._extract_document_name(document_path)
        self.document_type = self._detect_document_type(document_path)
        
        # Preview state
        self.current_page = 1
        self.total_pages = 1
        self.zoom_level = 100
        self.show_metadata = True
        
        # Create separate top and bottom toolbars
        self.top_toolbar = PreviewTopToolbar(app, self.document_name, is_mobile)
        self.bottom_toolbar = PreviewBottomToolbar(app, is_mobile)
        
        # Set both toolbars
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Content containers
        self.preview_container: Optional[toga.Box] = None
        self.metadata_container: Optional[toga.Box] = None
        self.navigation_container: Optional[toga.Box] = None
        
        # Initialize view
        self._create_content()
        self._setup_toolbar()
        self._setup_scroll_integration()
        
        logger.debug(f"Preview view initialized for document: {document_path}")
    
    def _extract_document_name(self, document_path: str) -> str:
        """Extract document name from path"""
        try:
            import os
            return os.path.basename(document_path) if document_path else "Unknown Document"
        except Exception as e:
            logger.error(f"Failed to extract document name: {e}")
            return "Unknown Document"
    
    def _detect_document_type(self, document_path: str) -> str:
        """Detect the type of document"""
        try:
            if not document_path:
                return "unknown"
            
            import os
            _, ext = os.path.splitext(document_path.lower())
            
            if ext in ['.pdf']:
                return "pdf"
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff']:
                return "image"
            elif ext in ['.txt', '.md', '.rtf']:
                return "text"
            elif ext in ['.doc', '.docx']:
                return "word"
            else:
                return "unknown"
                
        except Exception as e:
            logger.error(f"Failed to detect document type: {e}")
            return "unknown"
    
    def _create_content(self):
        """Create the main content of the preview view"""
        try:
            # Create main content container
            content_box = toga.Box(style=Pack(direction=COLUMN, margin=10))
            
            # Create header
            header = self._create_header()
            content_box.add(header)
            
            # Create navigation controls
            navigation = self._create_navigation_controls()
            content_box.add(navigation)
            
            # Create preview area
            preview_area = self._create_preview_area()
            content_box.add(preview_area)
            
            # Create metadata panel
            metadata_panel = self._create_metadata_panel()
            content_box.add(metadata_panel)
            
            # Set the content
            self.set_content(content_box)
            
            logger.debug("Preview view content created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create preview view content: {e}")
    
    def _create_header(self) -> toga.Box:
        """Create the header section"""
        try:
            header_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 20, 0)))
            
            # Document icon based on type
            icon = self._get_document_icon()
            header_box.add(icon)
            
            # Document name
            name_label = toga.Label(
                self.document_name,
                style=Pack(font_size=18, font_weight="bold", color=PREVIEW_TEXT)
            )
            header_box.add(name_label)
            
            # Document type badge
            type_badge = toga.Label(
                f" {self.document_type.upper()} ",
                style=Pack(
                    font_size=10,
                    color="#FFFFFF",
                    background_color=PREVIEW_ACCENT,
                    margin=(0, 0, 0, 10)
                )
            )
            header_box.add(type_badge)
            
            # Spacer
            spacer = toga.Box(style=Pack(flex=1))
            header_box.add(spacer)
            
            # Zoom controls
            zoom_controls = self._create_zoom_controls()
            header_box.add(zoom_controls)
            
            return header_box
            
        except Exception as e:
            logger.error(f"Failed to create preview view header: {e}")
            return toga.Box()
    
    def _get_document_icon(self) -> toga.Label:
        """Get the appropriate icon for the document type"""
        try:
            icon_map = {
                'pdf': '📄',
                'image': '🖼️',
                'text': '📝',
                'word': '📘',
                'unknown': '📄'
            }
            
            icon_char = icon_map.get(self.document_type, '📄')
            return toga.Label(icon_char, style=Pack(margin=(0, 10, 0, 0)))
            
        except Exception as e:
            logger.error(f"Failed to get document icon: {e}")
            return toga.Label("📄", style=Pack(margin=(0, 10, 0, 0)))
    
    def _create_zoom_controls(self) -> toga.Box:
        """Create zoom controls"""
        try:
            zoom_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 0, 10)))
            
            # Zoom out button
            zoom_out_btn = toga.Button(
                "−",
                on_press=self._on_zoom_out,
                style=Pack(margin=(5, 8), width=30)
            )
            zoom_box.add(zoom_out_btn)
            
            # Zoom level display
            zoom_label = toga.Label(
                f"{self.zoom_level}%",
                style=Pack(margin=(5, 10), font_size=12)
            )
            zoom_box.add(zoom_label)
            
            # Zoom in button
            zoom_in_btn = toga.Button(
                "+",
                on_press=self._on_zoom_in,
                style=Pack(margin=(5, 8), width=30)
            )
            zoom_box.add(zoom_in_btn)
            
            return zoom_box
            
        except Exception as e:
            logger.error(f"Failed to create zoom controls: {e}")
            return toga.Box()
    
    def _create_navigation_controls(self) -> toga.Box:
        """Create navigation controls"""
        try:
            nav_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 20, 0)))
            
            # Previous page button
            prev_btn = toga.Button(
                "◀ Previous",
                on_press=self._on_previous_page,
                style=Pack(margin=(5, 10))
            )
            nav_box.add(prev_btn)
            
            # Page info
            page_info = toga.Label(
                f"Page {self.current_page} of {self.total_pages}",
                style=Pack(margin=(5, 20), font_size=14)
            )
            nav_box.add(page_info)
            
            # Next page button
            next_btn = toga.Button(
                "Next ▶",
                on_press=self._on_next_page,
                style=Pack(margin=(5, 10))
            )
            nav_box.add(next_btn)
            
            # Spacer
            spacer = toga.Box(style=Pack(flex=1))
            nav_box.add(spacer)
            
            # Toggle metadata button
            metadata_btn = toga.Button(
                "Toggle Metadata",
                on_press=self._on_toggle_metadata,
                style=Pack(margin=(5, 10))
            )
            nav_box.add(metadata_btn)
            
            return nav_box
            
        except Exception as e:
            logger.error(f"Failed to create navigation controls: {e}")
            return toga.Box()
    
    def _create_preview_area(self) -> toga.Box:
        """Create the preview area"""
        try:
            preview_box = toga.Box(style=Pack(direction=COLUMN, margin=(0, 0, 20, 0)))
            
            # Preview container
            self.preview_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=20,
                    background_color=PREVIEW_BACKGROUND,
                    border_color=COMMON_BORDER,
                    border_width=1
                )
            )
            
            # Add placeholder content
            self._add_placeholder_preview()
            
            preview_box.add(self.preview_container)
            
            return preview_box
            
        except Exception as e:
            logger.error(f"Failed to create preview area: {e}")
            return toga.Box()
    
    def _create_metadata_panel(self) -> toga.Box:
        """Create the metadata panel"""
        try:
            metadata_box = toga.Box(style=Pack(direction=COLUMN))
            
            # Metadata header
            header = toga.Label(
                "Document Metadata",
                style=Pack(font_size=16, font_weight="bold", color=PREVIEW_TEXT, margin=(0, 0, 10, 0))
            )
            metadata_box.add(header)
            
            # Metadata container
            self.metadata_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=15,
                    background_color=PREVIEW_BACKGROUND,
                    border_color=COMMON_BORDER,
                    border_width=1
                )
            )
            
            # Add placeholder metadata
            self._add_placeholder_metadata()
            
            metadata_box.add(self.metadata_container)
            
            return metadata_box
            
        except Exception as e:
            logger.error(f"Failed to create metadata panel: {e}")
            return toga.Box()
    
    def _add_placeholder_preview(self):
        """Add placeholder content for preview"""
        try:
            if not self.preview_container:
                return
            
            # Clear existing content
            self.preview_container.remove_all_children()
            
            # Add placeholder message
            placeholder = toga.Label(
                f"Preview for {self.document_name}\n\nThis is a placeholder preview area.\nThe actual document content would be displayed here.",
                style=Pack(margin=20, color=COMMON_PLACEHOLDER, text_align="center")
            )
            self.preview_container.add(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to add placeholder preview: {e}")
    
    def _add_placeholder_metadata(self):
        """Add placeholder metadata"""
        try:
            if not self.metadata_container:
                return
            
            # Clear existing content
            self.metadata_container.remove_all_children()
            
            # Add placeholder metadata
            metadata_items = [
                ("File Name", self.document_name),
                ("File Type", self.document_type.upper()),
                ("File Path", self.document_path or "Unknown"),
                ("File Size", "Unknown"),
                ("Created", "Unknown"),
                ("Modified", "Unknown"),
                ("Pages", str(self.total_pages)),
                ("Processing Status", "Not Processed")
            ]
            
            for label, value in metadata_items:
                item_box = toga.Box(style=Pack(direction=ROW, margin=(0, 0, 5, 0)))
                
                label_widget = toga.Label(
                    f"{label}:",
                    style=Pack(font_weight="bold", color=PREVIEW_TEXT, width=120)
                )
                item_box.add(label_widget)
                
                value_widget = toga.Label(
                    value,
                    style=Pack(color=COMMON_SECONDARY_TEXT)
                )
                item_box.add(value_widget)
                
                self.metadata_container.add(item_box)
            
        except Exception as e:
            logger.error(f"Failed to add placeholder metadata: {e}")
    
    def _setup_toolbar(self):
        """Set up the preview toolbars"""
        try:
            # Register toolbar callbacks
            self.top_toolbar.register_callbacks(
                on_back_to_fiche=self._on_back_to_fiche,
                on_edit_document=self._on_edit_document
            )
            
            self.bottom_toolbar.register_callbacks(
                on_reprocess_document=self._on_reprocess_document,
                on_export_document=self._on_export_document,
                on_share_document=self._on_share_document,
                on_document_settings=self._on_document_settings
            )
            
            logger.debug("Preview toolbars set up successfully")
            
        except Exception as e:
            logger.error(f"Failed to set up preview toolbars: {e}")
    
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
    
    # ===== NAVIGATION CALLBACKS =====
    
    def _on_previous_page(self, widget):
        """Handle previous page navigation"""
        try:
            if self.current_page > 1:
                self.current_page -= 1
                self._update_page_display()
                logger.debug(f"Navigated to page {self.current_page}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to previous page: {e}")
    
    def _on_next_page(self, widget):
        """Handle next page navigation"""
        try:
            if self.current_page < self.total_pages:
                self.current_page += 1
                self._update_page_display()
                logger.debug(f"Navigated to page {self.current_page}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to next page: {e}")
    
    def _on_zoom_in(self, widget):
        """Handle zoom in"""
        try:
            if self.zoom_level < 200:
                self.zoom_level += 25
                self._update_zoom_display()
                logger.debug(f"Zoomed in to {self.zoom_level}%")
            
        except Exception as e:
            logger.error(f"Failed to zoom in: {e}")
    
    def _on_zoom_out(self, widget):
        """Handle zoom out"""
        try:
            if self.zoom_level > 25:
                self.zoom_level -= 25
                self._update_zoom_display()
                logger.debug(f"Zoomed out to {self.zoom_level}%")
            
        except Exception as e:
            logger.error(f"Failed to zoom out: {e}")
    
    def _on_toggle_metadata(self, widget):
        """Handle metadata toggle"""
        try:
            self.show_metadata = not self.show_metadata
            self._update_metadata_visibility()
            logger.debug(f"Metadata visibility toggled to: {self.show_metadata}")
            
        except Exception as e:
            logger.error(f"Failed to toggle metadata: {e}")
    
    # ===== TOOLBAR CALLBACKS =====
    
    def _on_back_to_fiche(self, widget):
        """Handle back to fiche navigation"""
        try:
            logger.debug("Back to fiche navigation requested")
            # This would typically trigger navigation back to fiche view
            
        except Exception as e:
            logger.error(f"Failed to handle back to fiche: {e}")
    
    def _on_edit_document(self, widget):
        """Handle edit document action"""
        try:
            logger.debug("Edit document action requested")
            # This would typically open document editor
            
        except Exception as e:
            logger.error(f"Failed to handle edit document: {e}")
    
    def _on_reprocess_document(self, widget):
        """Handle reprocess document action"""
        try:
            logger.debug("Reprocess document action requested")
            # This would typically trigger document reprocessing
            
        except Exception as e:
            logger.error(f"Failed to handle reprocess document: {e}")
    
    def _on_export_document(self, widget):
        """Handle export document action"""
        try:
            logger.debug("Export document action requested")
            # This would typically open export dialog
            
        except Exception as e:
            logger.error(f"Failed to handle export document: {e}")
    
    def _on_share_document(self, widget):
        """Handle share document action"""
        try:
            logger.debug("Share document action requested")
            # This would typically open share dialog
            
        except Exception as e:
            logger.error(f"Failed to handle share document: {e}")
    
    def _on_document_settings(self, widget):
        """Handle document settings action"""
        try:
            logger.debug("Document settings action requested")
            # This would typically open document settings dialog
            
        except Exception as e:
            logger.error(f"Failed to handle document settings: {e}")
    
    # ===== UPDATE METHODS =====
    
    def _update_page_display(self):
        """Update the page display"""
        try:
            # This would update the page info label
            # For now, just log the update
            logger.debug(f"Page display updated to {self.current_page}/{self.total_pages}")
            
        except Exception as e:
            logger.error(f"Failed to update page display: {e}")
    
    def _update_zoom_display(self):
        """Update the zoom display"""
        try:
            # This would update the zoom level label
            # For now, just log the update
            logger.debug(f"Zoom display updated to {self.zoom_level}%")
            
        except Exception as e:
            logger.error(f"Failed to update zoom display: {e}")
    
    def _update_metadata_visibility(self):
        """Update metadata visibility"""
        try:
            # This would show/hide the metadata panel
            # For now, just log the update
            logger.debug(f"Metadata visibility updated to: {self.show_metadata}")
            
        except Exception as e:
            logger.error(f"Failed to update metadata visibility: {e}")
    
    # ===== PUBLIC METHODS =====
    
    def set_document(self, document_path: str, total_pages: int = 1):
        """Set the document to preview"""
        try:
            self.document_path = document_path
            self.document_name = self._extract_document_name(document_path)
            self.document_type = self._detect_document_type(document_path)
            self.total_pages = total_pages
            self.current_page = 1
            
            # Update toolbar context
            self.top_toolbar.update_document_name(self.document_name)
            
            # Refresh content
            self._add_placeholder_preview()
            self._add_placeholder_metadata()
            
            logger.debug(f"Document set to: {document_path}")
            
        except Exception as e:
            logger.error(f"Failed to set document: {e}")
    
    def set_page(self, page_number: int):
        """Set the current page"""
        try:
            if 1 <= page_number <= self.total_pages:
                self.current_page = page_number
                self._update_page_display()
                logger.debug(f"Page set to: {page_number}")
            
        except Exception as e:
            logger.error(f"Failed to set page: {e}")
    
    def set_zoom(self, zoom_level: int):
        """Set the zoom level"""
        try:
            if 25 <= zoom_level <= 200:
                self.zoom_level = zoom_level
                self._update_zoom_display()
                logger.debug(f"Zoom set to: {zoom_level}%")
            
        except Exception as e:
            logger.error(f"Failed to set zoom: {e}")
    
    def get_preview_info(self) -> Dict[str, Any]:
        """Get information about the current preview"""
        return {
            'document_path': self.document_path,
            'document_name': self.document_name,
            'document_type': self.document_type,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'zoom_level': self.zoom_level,
            'show_metadata': self.show_metadata,
            'is_mobile': self.is_mobile
        } 