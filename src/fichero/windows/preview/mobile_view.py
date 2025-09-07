"""
Preview Mobile View - Mobile View Implementation

Mobile view for file preview and editing capabilities in the main window.
Supports multiple file types with appropriate viewers and editors.
"""

import logging
from typing import Optional
import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
from pathlib import Path

from fichero.windows.preview.preview_content import PreviewContent
from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.toolbars.top_toolbar import TopToolbar
from fichero.windows.main.toolbars.bottom_toolbar import BottomToolbar

logger = logging.getLogger(__name__)


class PreviewMobileView(BaseView):
    """Mobile preview view for file preview and editing"""
    
    def __init__(self, app, file_path=None, **kwargs):
        """Initialize the preview mobile view"""
        self.app = app
        self.file_path = file_path
        self.kwargs = kwargs
        
        # Initialize BaseView
        super().__init__(app, app.is_mobile)
        
        # Create the preview content
        self.preview_content = PreviewContent(app, file_path=file_path, **kwargs)
        
        # Create toolbars
        self._create_toolbars()
        
        logger.info(f"PreviewMobileView initialized for: {file_path or 'no file'}")
    
    def _create_toolbars(self):
        """Create top and bottom toolbars for preview view"""
        try:
            # Top toolbar with back button and collection/folder name
            class PreviewTopToolbar(TopToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    if self.is_mobile:
                        # Mobile: back button + collection/folder name label  
                        self.back_button = self.add_button_left(
                            icon="chevron.left@10x",
                            on_press=self._on_back_pressed,
                            tooltip="Back to Collection"
                        )
                        self.title_label = self.add_title_left(
                            "Collection",  # Default, will be updated when back source is known
                            margin_left=10,
                            on_click=self._on_title_pressed
                        )
                    else:
                        self.back_button = None
                        self.title_label = None
                        
                def _on_back_pressed(self, widget):
                    if hasattr(self, 'on_back') and self.on_back:
                        self.on_back()
                        
                def _on_title_pressed(self, widget):
                    if hasattr(self, 'on_back') and self.on_back:
                        self.on_back()
                        
                def update_back_label(self, back_label: str):
                    """Update the back label to show where we came from"""
                    if self.is_mobile and hasattr(self, 'title_label') and self.title_label:
                        self.title_label.text = back_label
                        logger.debug(f"Preview back label updated to: {back_label}")
            
            # Bottom toolbar with edit actions
            class PreviewBottomToolbar(BottomToolbar):
                def _create_toolbar(self):
                    super()._create_toolbar()
                    # Add Edit button
                    self.add_button_right(
                        text="Edit",
                        on_press=self._on_edit_pressed,
                        tooltip="Edit file"
                    )
                    
                def _on_edit_pressed(self, widget):
                    logger.info("Preview edit requested")
                    # Edit functionality could be added here
            
            # Create toolbar instances
            self.top_toolbar = PreviewTopToolbar(self.app, is_mobile=self.is_mobile)
            self.bottom_toolbar = PreviewBottomToolbar(self.app, is_mobile=self.is_mobile)
            
            # Set toolbars on the view
            self.set_top_toolbar(self.top_toolbar)
            self.set_bottom_toolbar(self.bottom_toolbar)
            
            logger.info("Preview toolbars created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create preview toolbars: {e}")
    
    def _create_content(self):
        """Create the content area"""
        try:
            # Add filename as content title (like collection view does)
            content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    margin=0
                )
            )
            
            # Add filename title if we have a file
            if self.file_path:
                filename = Path(self.file_path).name
                file_title = toga.Label(
                    filename,
                    style=Pack(
                        margin=(15, 20, 10, 20),
                        # Use default font size
                        font_weight="bold",
                        color="#000000"  # Black text
                    )
                )
                content_container.add(file_title)
            
            # Add the preview content
            preview_widget = self.preview_content.create()
            content_container.add(preview_widget)
            
            logger.info("Preview content created")
            return content_container
            
        except Exception as e:
            logger.error(f"Failed to create preview content: {e}")
            
            # Return error view
            error_container = toga.Box(
                style=Pack(direction=COLUMN, margin=10)
            )
            error_label = toga.Label(
                f"Failed to create preview: {e}",
                style=Pack(margin=10, text_align='center')
            )
            error_container.add(error_label)
            return error_container
    
    def create(self):
        """Create the mobile view content"""
        # Use BaseView's get_container which handles toolbar + content layout
        return super().get_container()
    
    def show(self):
        """Show callback - called when view becomes active"""
        try:
            if hasattr(self.preview_content, 'show'):
                self.preview_content.show()
            logger.info("Preview mobile view shown")
        except Exception as e:
            logger.error(f"Failed to show preview mobile view: {e}")
    
    def cleanup(self):
        """Cleanup resources"""
        try:
            if hasattr(self.preview_content, 'cleanup'):
                self.preview_content.cleanup()
            logger.info("Preview mobile view cleaned up")
        except Exception as e:
            logger.error(f"Failed to cleanup preview mobile view: {e}")
    
    def update_file(self, file_path):
        """Update the preview to show a different file"""
        try:
            self.file_path = file_path
            
            # Update content
            if hasattr(self.preview_content, 'update_file'):
                self.preview_content.update_file(file_path)
            
            logger.info(f"Preview mobile view updated for: {file_path}")
        except Exception as e:
            logger.error(f"Failed to update preview mobile view: {e}") 