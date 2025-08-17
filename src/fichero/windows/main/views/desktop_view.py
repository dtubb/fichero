"""
Desktop View for Fichero

Three-pane desktop layout using Toga's native colors.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Callable, Dict, Any

from .base_view import BaseView
from ..toolbars.base_toolbar import BaseToolbar

logger = logging.getLogger(__name__)


class DesktopView(BaseView):
    """Desktop-specific view with three-pane layout"""
    
    def __init__(self, app):
        """Initialize desktop view"""
        super().__init__(app)
        
        # Pane containers
        self.left_pane: Optional[toga.Box] = None
        self.middle_pane: Optional[toga.Box] = None
        self.right_pane: Optional[toga.Box] = None
        
        # Create desktop layout
        self._create_desktop_layout()
    
    def _create_content(self):
        """Create desktop-specific content layout"""
        # This will be overridden by _create_desktop_layout
        pass
    
    def _create_desktop_layout(self):
        """Create the three-pane desktop layout"""
        try:
            # Clear existing content
            if self.content_container:
                self.content_container.clear()
            
            # Create three-pane layout
            self.left_pane = self._create_left_pane()
            self.middle_pane = self._create_middle_pane()
            self.right_pane = self._create_right_pane()
            
            # Create horizontal container for panes - let Toga handle colors
            panes_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1
                )
            )
            
            # Add panes to container
            panes_container.add(self.left_pane)
            panes_container.add(self.middle_pane)
            panes_container.add(self.right_pane)
            
            # Add panes container to content
            self.content_container.add(panes_container)
            
            logger.debug("Desktop three-pane layout created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create desktop layout: {e}")
    
    def _create_left_pane(self) -> toga.Box:
        """Create the left pane (Library navigation)"""
        left_pane = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=250,
                margin=(0, 5, 0, 0)
            )
        )
        
        # Add library navigation content
        library_header = toga.Label(
            "📚 Library",
            style=Pack(
                font_size=16,
                font_weight="bold",
                margin=(10, 5)
            )
        )
        left_pane.add(library_header)
        
        # Add placeholder for library content
        placeholder = toga.Label(
            "Library navigation will be added here",
            style=Pack(
                margin=(10, 5)
            )
        )
        left_pane.add(placeholder)
        
        return left_pane
    
    def _create_middle_pane(self) -> toga.Box:
        """Create the middle pane (Collection/Fiche content)"""
        middle_pane = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=(0, 5, 0, 5)
            )
        )
        
        # Add content header
        content_header = toga.Label(
            "📁 Content",
            style=Pack(
                font_size=16,
                font_weight="bold",
                margin=(10, 5)
            )
        )
        middle_pane.add(content_header)
        
        # Add placeholder for content
        placeholder = toga.Label(
            "Collection or fiche content will be displayed here",
            style=Pack(
                margin=(10, 5)
            )
        )
        middle_pane.add(placeholder)
        
        return middle_pane
    
    def _create_right_pane(self) -> toga.Box:
        """Create the right pane (Preview)"""
        right_pane = toga.Box(
            style=Pack(
                direction=COLUMN,
                width=300,
                margin=(0, 0, 0, 5)
            )
        )
        
        # Add preview header
        preview_header = toga.Label(
            "👁️ Preview",
            style=Pack(
                font_size=16,
                font_weight="bold",
                margin=(10, 5)
            )
        )
        right_pane.add(preview_header)
        
        # Add placeholder for preview content
        placeholder = toga.Label(
            "Document preview will be shown here",
            style=Pack(
                margin=(10, 5)
            )
        )
        right_pane.add(placeholder)
        
        return right_pane
    
    def set_left_pane_content(self, content: toga.Widget):
        """Set the content for the left pane"""
        try:
            if self.left_pane:
                # Clear existing content (except header)
                if len(self.left_pane.children) > 1:
                    # Remove all children except the first (header)
                    while len(self.left_pane.children) > 1:
                        self.left_pane.remove(self.left_pane.children[-1])
                
                # Add new content
                self.left_pane.add(content)
                logger.debug("Left pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set left pane content: {e}")
    
    def set_middle_pane_content(self, content: toga.Widget):
        """Set the content for the middle pane"""
        try:
            if self.middle_pane:
                # Clear existing content (except header)
                if len(self.middle_pane.children) > 1:
                    # Remove all children except the first (header)
                    while len(self.middle_pane.children) > 1:
                        self.middle_pane.remove(self.middle_pane.children[-1])
                
                # Add new content
                self.middle_pane.add(content)
                logger.debug("Middle pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set middle pane content: {e}")
    
    def set_right_pane_content(self, content: toga.Widget):
        """Set the content for the right pane"""
        try:
            if self.right_pane:
                # Clear existing content (except header)
                if len(self.right_pane.children) > 1:
                    # Remove all children except the first (header)
                    while len(self.right_pane.children) > 1:
                        self.right_pane.remove(self.right_pane.children[-1])
                
                # Add new content
                self.right_pane.add(content)
                logger.debug("Right pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set right pane content: {e}")
    
    def update_pane_headers(self, 
                           left_header: Optional[str] = None,
                           middle_header: Optional[str] = None,
                           right_header: Optional[str] = None):
        """Update the headers for the three panes"""
        try:
            if left_header and self.left_pane and len(self.left_pane.children) > 0:
                header = self.left_pane.children[0]
                if isinstance(header, toga.Label):
                    header.text = left_header
            
            if middle_header and self.middle_pane and len(self.middle_pane.children) > 0:
                header = self.middle_pane.children[0]
                if isinstance(header, toga.Label):
                    header.text = middle_header
            
            if right_header and self.right_pane and len(self.right_pane.children) > 0:
                header = self.right_pane.children[0]
                if isinstance(header, toga.Label):
                    header.text = right_header
            
            logger.debug("Pane headers updated")
            
        except Exception as e:
            logger.error(f"Failed to update pane headers: {e}")
    
    def get_left_pane(self) -> Optional[toga.Box]:
        """Get the left pane container"""
        return self.left_pane
    
    def get_middle_pane(self) -> Optional[toga.Box]:
        """Get the middle pane container"""
        return self.middle_pane
    
    def get_right_pane(self) -> Optional[toga.Box]:
        """Get the right pane container"""
        return self.right_pane
    
    def set_pane_sizes(self, left_width: Optional[int] = None, right_width: Optional[int] = None):
        """Set the widths of the left and right panes"""
        try:
            if left_width and self.left_pane:
                self.left_pane.style.width = left_width
            
            if right_width and self.right_pane:
                self.right_pane.style.width = right_width
            
            logger.debug(f"Pane sizes updated: left={left_width}, right={right_width}")
            
        except Exception as e:
            logger.error(f"Failed to set pane sizes: {e}")
    
    def _on_initialize(self):
        """Desktop-specific initialization"""
        try:
            # Set up desktop-specific features
            logger.debug("Desktop view initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize desktop view: {e}")
    
    def refresh(self):
        """Refresh the desktop view"""
        try:
            # Refresh all panes
            if self.left_pane:
                # Trigger left pane refresh
                pass
            
            if self.middle_pane:
                # Trigger middle pane refresh
                pass
            
            if self.right_pane:
                # Trigger right pane refresh
                pass
            
            logger.debug("Desktop view refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh desktop view: {e}") 