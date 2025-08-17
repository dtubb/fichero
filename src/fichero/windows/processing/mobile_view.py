"""
Processing Mobile View

Mobile-specific view for document processing that can be embedded in main window.
Uses the clean modular ProcessingContent with mobile-specific navigation.
"""

import logging
from typing import Optional, Callable

from fichero.windows.processing.processing_content import ProcessingContent

logger = logging.getLogger(__name__)


class ProcessingMobileView:
    """Mobile view for processing content that can be embedded in main window"""
    
    def __init__(self, app):
        """Initialize the mobile processing view"""
        self.app = app
        
        # Create the processing content (toolbar handles navigation)
        self.processing_content = ProcessingContent(app=app)
    
    def create(self):
        """Create the mobile processing view UI"""
        return self.processing_content.create()
    
    def show(self):
        """Show method for compatibility"""
        # Mobile view doesn't need separate show logic
        # Content is embedded in main window
        pass
    
    def hide(self):
        """Hide method for compatibility"""
        # Mobile view doesn't need separate hide logic
        # Content is embedded in main window
        pass
    
    def get_selected_folder(self):
        """Get currently selected folder"""
        return self.processing_content.get_selected_folder()
    
    def get_current_plan(self):
        """Get current plan"""
        return self.processing_content.get_current_plan()
    
    def is_processing(self) -> bool:
        """Check if currently processing"""
        return self.processing_content.is_processing() 