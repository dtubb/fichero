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

logger = logging.getLogger(__name__)


class PreviewMobileView:
    """Mobile preview view for file preview and editing"""
    
    def __init__(self, app, file_path=None, **kwargs):
        """Initialize the preview mobile view"""
        self.app = app
        self.file_path = file_path
        self.kwargs = kwargs
        
        # Create the preview content
        self.preview_content = PreviewContent(app, file_path=file_path, **kwargs)
        
        logger.info(f"PreviewMobileView initialized for: {file_path or 'no file'}")
    
    def create(self):
        """Create the mobile view content"""
        try:
            # Create main container
            main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    margin=0
                )
            )
            
            # Add the preview content
            preview_widget = self.preview_content.create()
            main_container.add(preview_widget)
            
            logger.info("Preview mobile view created")
            return main_container
            
        except Exception as e:
            logger.error(f"Failed to create preview mobile view: {e}")
            
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
    
    def get_container(self):
        """Get the container (alias for create)"""
        return self.create()
    
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