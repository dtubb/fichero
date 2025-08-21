"""
Preview Pane for Fichero

Manages the right pane content for document previews with:
- Document display
- Preview controls
- Zoom and navigation
- Metadata display
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, Dict, Any, List

from ..containers.scroll_container import ScrollableContainer

logger = logging.getLogger(__name__)


class PreviewPane:
    """Manages the right pane content for document previews"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize preview pane"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Pane container
        self.container: Optional[toga.Box] = None
        
        # Current document
        self.current_document: Optional[Dict[str, Any]] = None
        self.current_page: int = 1
        self.total_pages: int = 1
        
        # Preview controls
        self.zoom_level: float = 1.0
        self.show_metadata: bool = True
        
        # Content management
        self.preview_container: Optional[toga.Box] = None
        self.scroll_container: Optional[ScrollableContainer] = None
        
        # Callbacks
        self.on_document_changed: Optional[Any] = None
        self.on_page_changed: Optional[Any] = None
        self.on_zoom_changed: Optional[Any] = None
        
        # Create pane
        self._create_pane()
        
        logger.info("Preview pane initialized successfully")
    
    def _create_pane(self):
        """Create the preview pane structure"""
        try:
            # Create main container
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FAFAFA"
                )
            )
            
            # Create preview container
            self.preview_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create scrollable container for preview content
            self.scroll_container = ScrollableContainer(self.app, self.is_mobile)
            
            # Add scroll container to preview container
            self.preview_container.add(self.scroll_container.get_container())
            
            # Add preview container to main container
            self.container.add(self.preview_container)
            
            # Create initial placeholder content
            self._create_placeholder_content()
            
        except Exception as e:
            logger.error(f"Failed to create preview pane: {e}")
    
    def _create_placeholder_content(self):
        """Create placeholder content for the preview pane"""
        try:
            # Create preview header
            header_label = toga.Label(
                "📄 Document Preview",
                style=Pack(
                    font_size=16,
                    font_weight="bold",
                    margin=(20, 15),
                    color="#333333"
                )
            )
            self.scroll_container.add_content(header_label)
            
            # Create placeholder message
            placeholder_label = toga.Label(
                "No document selected for preview",
                style=Pack(
                    font_size=14,
                    margin=(20, 15),
                    color="#666666"
                )
            )
            self.scroll_container.add_content(placeholder_label)
            
            # Create instruction
            instruction_label = toga.Label(
                "Select a document from the collection to view it here",
                style=Pack(
                    font_size=12,
                    margin=(20, 15),
                    color="#999999"
                )
            )
            self.scroll_container.add_content(instruction_label)
            
        except Exception as e:
            logger.error(f"Failed to create placeholder content: {e}")
    
    def set_document(self, document_data: Dict[str, Any]):
        """Set the current document for preview"""
        try:
            self.current_document = document_data
            
            # Extract document information
            self.current_page = 1
            self.total_pages = document_data.get('page_count', 1)
            
            # Clear current content
            self.scroll_container.clear_content()
            
            # Create document preview
            self._create_document_preview(document_data)
            
            # Notify callback
            if self.on_document_changed:
                self.on_document_changed(document_data)
            
            logger.info(f"Preview pane set to document: {document_data.get('name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to set document: {e}")
    
    def _create_document_preview(self, document_data: Dict[str, Any]):
        """Create the document preview content"""
        try:
            # Document header
            header_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=(15, 15),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Document name
            name_label = toga.Label(
                document_data.get('name', 'Unknown Document'),
                style=Pack(
                    font_size=16,
                    font_weight="bold",
                    color="#333333"
                )
            )
            header_container.add(name_label)
            
            # Document type
            doc_type = document_data.get('type', 'Unknown')
            type_label = toga.Label(
                f"Type: {doc_type}",
                style=Pack(
                    margin=(5, 0, 0, 0),
                    font_size=12,
                    color="#666666"
                )
            )
            header_container.add(type_label)
            
            # Document size
            size = document_data.get('size', 'Unknown')
            size_label = toga.Label(
                f"Size: {size}",
                style=Pack(
                    margin=(5, 0, 0, 0),
                    font_size=12,
                    color="#666666"
                )
            )
            header_container.add(size_label)
            
            self.scroll_container.add_content(header_container)
            
            # Page navigation controls
            if self.total_pages > 1:
                self._create_page_navigation()
            
            # Document content preview
            self._create_content_preview(document_data)
            
            # Metadata section
            if self.show_metadata:
                self._create_metadata_section(document_data)
            
        except Exception as e:
            logger.error(f"Failed to create document preview: {e}")
    
    def _create_page_navigation(self):
        """Create page navigation controls"""
        try:
            nav_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(10, 15),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Previous page button
            prev_button = toga.Button(
                "◀",
                on_press=self._on_previous_page,
                style=Pack(
                    margin=(8, 12),
                    background_color="#F0F0F0"
                )
            )
            nav_container.add(prev_button)
            
            # Page info
            page_info = toga.Label(
                f"Page {self.current_page} of {self.total_pages}",
                style=Pack(
                    margin=(0, 15),
                    font_size=12,
                    color="#333333"
                )
            )
            nav_container.add(page_info)
            
            # Next page button
            next_button = toga.Button(
                "▶",
                on_press=self._on_next_page,
                style=Pack(
                    margin=(8, 12),
                    background_color="#F0F0F0"
                )
            )
            nav_container.add(next_button)
            
            self.scroll_container.add_content(nav_container)
            
        except Exception as e:
            logger.error(f"Failed to create page navigation: {e}")
    
    def _create_content_preview(self, document_data: Dict[str, Any]):
        """Create the document content preview"""
        try:
            content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=(15, 15),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Content preview header
            preview_header = toga.Label(
                "Content Preview",
                style=Pack(
                    font_size=14,
                    font_weight="bold",
                    margin=(0, 0, 10, 0),
                    color="#333333"
                )
            )
            content_container.add(preview_header)
            
            # Content preview (placeholder for now)
            content_preview = toga.Label(
                "[Document content preview would appear here]",
                style=Pack(
                    margin=(20, 20),
                    background_color="#F8F8F8",
                    border_color="#E0E0E0",
                    border_width=1,
                    color="#666666"
                )
            )
            content_container.add(content_preview)
            
            # Zoom controls
            zoom_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(15, 0, 0, 0)
                )
            )
            
            zoom_out_button = toga.Button(
                "🔍-",
                on_press=self._on_zoom_out,
                style=Pack(
                    margin=(5, 8),
                    background_color="#F0F0F0"
                )
            )
            zoom_container.add(zoom_out_button)
            
            zoom_level_label = toga.Label(
                f"{int(self.zoom_level * 100)}%",
                style=Pack(
                    margin=(0, 10),
                    font_size=12,
                    color="#666666"
                )
            )
            zoom_container.add(zoom_level_label)
            
            zoom_in_button = toga.Button(
                "🔍+",
                on_press=self._on_zoom_in,
                style=Pack(
                    margin=(5, 8),
                    background_color="#F0F0F0"
                )
            )
            zoom_container.add(zoom_in_button)
            
            content_container.add(zoom_container)
            
            self.scroll_container.add_content(content_container)
            
        except Exception as e:
            logger.error(f"Failed to create content preview: {e}")
    
    def _create_metadata_section(self, document_data: Dict[str, Any]):
        """Create the metadata display section"""
        try:
            metadata_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=(15, 15),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Metadata header
            metadata_header = toga.Label(
                "Document Metadata",
                style=Pack(
                    font_size=14,
                    font_weight="bold",
                    margin=(0, 0, 10, 0),
                    color="#333333"
                )
            )
            metadata_container.add(metadata_header)
            
            # Metadata fields
            metadata_fields = [
                ('Created', document_data.get('created_date', 'Unknown')),
                ('Modified', document_data.get('modified_date', 'Unknown')),
                ('Author', document_data.get('author', 'Unknown')),
                ('Tags', ', '.join(document_data.get('tags', [])) or 'None'),
                ('Processing Status', document_data.get('processing_status', 'Unknown')),
                ('File Path', document_data.get('file_path', 'Unknown'))
            ]
            
            for field_name, field_value in metadata_fields:
                field_container = toga.Box(
                    style=Pack(
                        direction=ROW,
                        margin=(5, 0)
                    )
                )
                
                field_label = toga.Label(
                    f"{field_name}:",
                    style=Pack(
                        font_size=12,
                        font_weight="bold",
                        width=120,
                        color="#666666"
                    )
                )
                field_container.add(field_label)
                
                field_value_label = toga.Label(
                    str(field_value),
                    style=Pack(
                        font_size=12,
                        color="#333333"
                    )
                )
                field_container.add(field_value_label)
                
                metadata_container.add(field_container)
            
            self.scroll_container.add_content(metadata_container)
            
        except Exception as e:
            logger.error(f"Failed to create metadata section: {e}")
    
    def _on_previous_page(self, widget):
        """Handle previous page navigation"""
        try:
            if self.current_page > 1:
                self.current_page -= 1
                self._update_page_display()
                
                if self.on_page_changed:
                    self.on_page_changed(self.current_page)
                
                logger.debug(f"Navigated to previous page: {self.current_page}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to previous page: {e}")
    
    def _on_next_page(self, widget):
        """Handle next page navigation"""
        try:
            if self.current_page < self.total_pages:
                self.current_page += 1
                self._update_page_display()
                
                if self.on_page_changed:
                    self.on_page_changed(self.current_page)
                
                logger.debug(f"Navigated to next page: {self.current_page}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to next page: {e}")
    
    def _on_zoom_in(self, widget):
        """Handle zoom in"""
        try:
            if self.zoom_level < 3.0:
                self.zoom_level = min(3.0, self.zoom_level + 0.25)
                self._update_zoom_display()
                
                if self.on_zoom_changed:
                    self.on_zoom_changed(self.zoom_level)
                
                logger.debug(f"Zoomed in to: {self.zoom_level}")
            
        except Exception as e:
            logger.error(f"Failed to zoom in: {e}")
    
    def _on_zoom_out(self, widget):
        """Handle zoom out"""
        try:
            if self.zoom_level > 0.25:
                self.zoom_level = max(0.25, self.zoom_level - 0.25)
                self._update_zoom_display()
                
                if self.on_zoom_changed:
                    self.on_zoom_changed(self.zoom_level)
                
                logger.debug(f"Zoomed out to: {self.zoom_level}")
            
        except Exception as e:
            logger.error(f"Failed to zoom out: {e}")
    
    def _update_page_display(self):
        """Update the page display"""
        try:
            # This would update the page navigation display
            # For now, just log the update
            logger.debug(f"Page display updated to: {self.current_page}")
            
        except Exception as e:
            logger.error(f"Failed to update page display: {e}")
    
    def _update_zoom_display(self):
        """Update the zoom display"""
        try:
            # This would update the zoom level display
            # For now, just log the update
            logger.debug(f"Zoom display updated to: {self.zoom_level}")
            
        except Exception as e:
            logger.error(f"Failed to update zoom display: {e}")
    
    def clear_document(self):
        """Clear the current document from preview"""
        try:
            self.current_document = None
            self.current_page = 1
            self.total_pages = 1
            
            # Clear content and show placeholder
            self.scroll_container.clear_content()
            self._create_placeholder_content()
            
            logger.debug("Document cleared from preview pane")
            
        except Exception as e:
            logger.error(f"Failed to clear document: {e}")
    
    def set_zoom_level(self, zoom: float):
        """Set the zoom level"""
        try:
            self.zoom_level = max(0.25, min(3.0, zoom))
            self._update_zoom_display()
            
            logger.debug(f"Zoom level set to: {self.zoom_level}")
            
        except Exception as e:
            logger.error(f"Failed to set zoom level: {e}")
    
    def set_metadata_visibility(self, visible: bool):
        """Set metadata section visibility"""
        try:
            self.show_metadata = visible
            
            # Recreate document preview if document is set
            if self.current_document:
                self.scroll_container.clear_content()
                self._create_document_preview(self.current_document)
            
            logger.debug(f"Metadata visibility set to: {visible}")
            
        except Exception as e:
            logger.error(f"Failed to set metadata visibility: {e}")
    
    def get_current_document(self) -> Optional[Dict[str, Any]]:
        """Get the current document"""
        return self.current_document
    
    def get_current_page(self) -> int:
        """Get the current page number"""
        return self.current_page
    
    def get_total_pages(self) -> int:
        """Get the total number of pages"""
        return self.total_pages
    
    def get_zoom_level(self) -> float:
        """Get the current zoom level"""
        return self.zoom_level
    
    def get_pane_info(self) -> Dict[str, Any]:
        """Get information about the preview pane"""
        return {
            'has_document': self.current_document is not None,
            'current_page': self.current_page,
            'total_pages': self.total_pages,
            'zoom_level': self.zoom_level,
            'show_metadata': self.show_metadata,
            'is_mobile': self.is_mobile
        }
    
    def register_callbacks(self, 
                         on_document_changed: Optional[Any] = None,
                         on_page_changed: Optional[Any] = None,
                         on_zoom_changed: Optional[Any] = None):
        """Register callbacks for preview pane actions"""
        self.on_document_changed = on_document_changed
        self.on_page_changed = on_page_changed
        self.on_zoom_changed = on_zoom_changed
        
        logger.debug("Preview pane callbacks registered")
    
    def get_container(self) -> toga.Box:
        """Get the preview pane container"""
        return self.container
    
    def refresh(self):
        """Refresh the preview pane"""
        try:
            # Refresh scroll container
            if self.scroll_container:
                self.scroll_container.refresh()
            
            logger.debug("Preview pane refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh preview pane: {e}") 