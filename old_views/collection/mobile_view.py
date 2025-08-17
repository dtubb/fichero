"""
Mobile Collection View

Mobile-optimized collection view using shared middle column logic.
Provides DetailedList navigation optimized for touch interfaces.
Supports image preview with stack navigation.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from pathlib import Path

from .base_components import BaseComponent
from .middle_column import MobileCurrentLevelView
from .right_column import PreviewColumn

logger = logging.getLogger(__name__)


class MobileCollectionView(BaseComponent):
    """
    Mobile collection view optimized for iOS/Android.
    
    Uses shared middle column and preview column logic for maximum code reuse.
    Provides single-column DetailedList navigation with shared preview support.
    """
    
    def __init__(self, presenter):
        super().__init__(presenter)
        
        # Navigation stack for mobile views
        self.view_stack = []
        self.current_view = None
        
        # Create views - using shared components
        self.current_level_view = MobileCurrentLevelView(presenter)
        self.preview_view = PreviewColumn(presenter, width=None, is_mobile=True)  # Full width for mobile with back button
        
        # Container manages the current view
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Start with current level view
        self._show_view(self.current_level_view)
        
        logger.info("Created mobile collection view using shared middle column logic")
    
    def _show_view(self, view):
        """Show a specific view in the mobile container"""
        try:
            # Clear container
            self.container.clear()
            
            # Add new view
            self.container.add(view.container)
            self.current_view = view
            
            logger.info(f"Mobile view switched to: {type(view).__name__}")
            
        except Exception as e:
            logger.error(f"Failed to show mobile view: {e}")
    
    def show_image_preview(self, image_path: Path, image_name: str):
        """Show image preview (called by presenter) - using shared preview logic"""
        try:
            # Push current view to stack if not already in preview
            if self.current_view != self.preview_view:
                self.view_stack.append(self.current_view)
            
            # Show image in shared preview component
            self.preview_view.show_image_preview(image_path, image_name)
            
            # Switch to preview view
            self._show_view(self.preview_view)
            
            logger.info(f"Showing image preview: {image_name}")
            
        except Exception as e:
            logger.error(f"Failed to show image preview: {e}")
    
    def handle_back_navigation(self):
        """Handle back navigation with stack support"""
        try:
            # If we're in preview view and have a previous view, go back
            if self.current_view == self.preview_view and self.view_stack:
                previous_view = self.view_stack.pop()
                self._show_view(previous_view)
                logger.info("Navigated back from preview")
                return
            
            # Otherwise, use normal navigation logic
            self.presenter.handle_back_navigation()
            
        except Exception as e:
            logger.error(f"Failed to handle back navigation: {e}")
    
    # BaseComponent interface implementations - delegate to current level view
    def update_navigation(self, current_item, breadcrumb_path):
        """Update navigation - delegate to current level view"""
        # Only update if we're showing the current level view
        if self.current_view == self.current_level_view:
            self.current_level_view.update_navigation(current_item, breadcrumb_path)
    
    def update_collections(self, collections):
        """Update collections - delegate to current level view"""
        self.current_level_view.update_collections(collections) 