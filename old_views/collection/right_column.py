"""
Right Column - Preview Component

Preview panel for desktop collection view and full-screen mobile preview.
Uses the new modular preview system for different file types.
Shared between desktop (right column) and mobile (full screen).
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, List
from pathlib import Path

from .base_components import BaseComponent
from .preview import PreviewManager

logger = logging.getLogger(__name__)


class PreviewColumn(BaseComponent):
    """Preview component using modular preview system"""
    
    def __init__(self, presenter, width=300, is_mobile=False):
        super().__init__(presenter)
        self.width = width
        self.is_mobile = is_mobile
        
        # Use the new preview manager
        self.preview_manager = PreviewManager(presenter, width, is_mobile)
        
        # For backward compatibility
        self.container = self.preview_manager.container
        self.preview_content = self.preview_manager.content_container
        
        # Legacy image state (for backward compatibility)
        self.current_image_path = None
        self.image_list = []
        self.current_image_index = 0
    
    def _create_ui(self):
        """Create preview UI - now handled by PreviewManager"""
        # The UI is now created by the PreviewManager
        pass
    

    
    def _handle_mobile_back(self, widget):
        """Handle mobile back navigation"""
        # Find mobile collection view and use its back navigation
        for ui_display in self.presenter.ui_displays:
            if hasattr(ui_display, 'handle_back_navigation') and hasattr(ui_display, 'view_stack'):
                ui_display.handle_back_navigation()
                return
        
        # Fallback to standard navigation
        self.presenter.handle_back_navigation()
    
    def show_image_preview(self, image_path: Path, image_name: str):
        """Show image preview with navigation support"""
        try:
            self.current_image_path = image_path
            
            # Use the preview manager to show the image
            self.preview_manager.preview_file(image_path)
            
            logger.info(f"Showing image preview: {image_name}")
            
        except Exception as e:
            logger.error(f"Failed to show image preview: {e}")
    
    # Keyboard navigation support (delegates to preview manager)
    def handle_key_left(self):
        """Handle left arrow key press"""
        self.preview_manager.handle_key_left()
    
    def handle_key_right(self):
        """Handle right arrow key press"""
        self.preview_manager.handle_key_right()
    
    def handle_key_escape(self):
        """Handle escape key press"""
        self.preview_manager.handle_key_escape()
    
    def _update_preview(self, current_item, breadcrumb_path):
        """Update the preview panel with current context"""
        try:
            # Reset image state
            self.current_image_path = None
            
            # Clear the preview manager
            self.preview_manager.clear()
            
            # Show navigation context in the preview manager
            if current_item:
                # If it's a file, try to preview it
                if hasattr(current_item, 'path') and current_item.path.is_file():
                    self.preview_manager.preview_file(current_item.path)
                else:
                    # Show item info
                    self.preview_manager.header.text = f"Item: {current_item.name}"
                    self.preview_manager.content_container.add(toga.Label(f"Type: {current_item.level.value}"))
                    
                    # Show current level summary
                    items = self.presenter.get_current_items()
                    folders = sum(1 for item in items if item.level.value == "folder")
                    files = sum(1 for item in items if item.level.value == "file")
                    
                    self.preview_manager.content_container.add(toga.Label(""))  # Spacer
                    self.preview_manager.content_container.add(toga.Label("Current Level:"))
                    self.preview_manager.content_container.add(toga.Label(f"• {folders} folders"))
                    self.preview_manager.content_container.add(toga.Label(f"• {files} files"))
                    
            elif breadcrumb_path:
                # Show breadcrumb context
                self.preview_manager.header.text = "Navigation"
                self.preview_manager.content_container.add(toga.Label(f"Level: {breadcrumb_path[-1].name if breadcrumb_path else 'Collections'}"))
                
                items = self.presenter.get_current_items()
                self.preview_manager.content_container.add(toga.Label(f"Items: {len(items)}"))
            else:
                self.preview_manager.header.text = "Collections Library"
                self.preview_manager.content_container.add(toga.Label("Select a collection to begin browsing"))
                
        except Exception as e:
            logger.error(f"Failed to update preview: {e}")
    
    # BaseComponent interface implementations  
    def update_navigation(self, current_item, breadcrumb_path):
        """Update preview when navigation changes"""
        # Only update if we're not showing an image preview
        if not self.current_image_path:
            self._update_preview(current_item, breadcrumb_path)
    
    def update_collections(self, collections):
        """Update preview when collections are loaded"""
        try:
            # Only update if we're not showing an image preview
            if not self.current_image_path:
                self.preview_manager.clear()
                self.preview_manager.header.text = "Collections Library"
                self.preview_manager.content_container.add(toga.Label(f"{len(collections)} collections available"))
                
                # Show collection summary
                if collections:
                    self.preview_manager.content_container.add(toga.Label(""))  # Spacer
                    self.preview_manager.content_container.add(toga.Label("Collections:"))
                    for collection in collections[:5]:  # Show first 5
                        self.preview_manager.content_container.add(toga.Label(f"• {collection.name}"))
                    if len(collections) > 5:
                        self.preview_manager.content_container.add(toga.Label(f"... and {len(collections) - 5} more"))
        except Exception as e:
            logger.error(f"Failed to update preview collections: {e}") 