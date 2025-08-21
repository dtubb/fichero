"""
Base View for Fichero

Provides common functionality for all views.
Uses Toga's native colors by default.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from abc import ABC, abstractmethod
from typing import Optional, Callable

from ..styling.color_constants import ICON_PRIMARY, ICON_SECONDARY, VIEW_BACKGROUND

logger = logging.getLogger(__name__)


class BaseView(ABC):
    """Base class for all views in Fichero"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize base view"""
        self.app = app
        self.is_mobile = is_mobile
        
        # View containers
        self.container: Optional[toga.Box] = None
        self.content_container: Optional[toga.Box] = None
        self.scroll_container: Optional[toga.ScrollContainer] = None
        
        # Toolbars
        self.top_toolbar: Optional['BaseToolbar'] = None
        self.top_toolbar_container: Optional[toga.Box] = None
        self.bottom_toolbar: Optional['BaseToolbar'] = None
        self.bottom_toolbar_container: Optional[toga.Box] = None
        
        # Icon colors for line art icons only
        self.icon_primary = ICON_PRIMARY      # For active states, buttons, etc.
        self.icon_secondary = ICON_SECONDARY  # For inactive states
        
        # Text color for labels and text elements
        self.text_color = "#000000"  # Default black text
        
        # View state
        self.is_visible = False
        self.is_initialized = False
        
        # Callbacks
        self.on_view_ready: Optional[Callable] = None
        self.on_content_changed: Optional[Callable] = None
        
        # Create view structure
        self._create_view_structure()
    
    @abstractmethod
    def _create_content(self):
        """Create the view content - must be implemented by subclasses"""
        pass
    
    def _create_view_structure(self):
        """Create the basic view structure with top and bottom toolbars"""
        try:
            # Create main container with white background
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color=VIEW_BACKGROUND  # White background
                )
            )
            
            # Top toolbar will be inserted here (index 0)
            # Content will be in the middle (index 1)
            # Bottom toolbar will be at the end (index 2)
            
            # Create content container with white background FIRST
            self.content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color=VIEW_BACKGROUND  # White background
                )
            )
            
            # Create scroll container with content - Toga's recommended pattern
            self.scroll_container = toga.ScrollContainer(
                content=self.content_container,  # Pass content in constructor
                style=Pack(
                    flex=1,
                    background_color=VIEW_BACKGROUND  # White background
                )
            )
            
            # Add scroll container to main container
            self.container.add(self.scroll_container)
            
            # Create content AFTER scroll container is fully set up
            self._create_content()
            
            logger.debug("Base view structure created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create base view structure: {e}")
            # Create fallback container
            self.container = toga.Box(style=Pack(direction=COLUMN))
    
    def set_toolbar(self, toolbar: 'BaseToolbar'):
        """Set the toolbar for this view (legacy method - now sets top toolbar)"""
        self.set_top_toolbar(toolbar)
    
    def set_top_toolbar(self, toolbar: 'BaseToolbar'):
        """Set the top toolbar for this view (navigation, title, back button)"""
        try:
            self.top_toolbar = toolbar
            
            # Get toolbar container
            if hasattr(toolbar, 'get_container'):
                self.top_toolbar_container = toolbar.get_container()
                
                # Add top toolbar to main container (at the beginning)
                if self.top_toolbar_container and self.container:
                    # Insert top toolbar at the beginning
                    self.container.insert(0, self.top_toolbar_container)
                    logger.debug("Top toolbar added to view")
            
        except Exception as e:
            logger.error(f"Failed to set top toolbar: {e}")
    
    def set_bottom_toolbar(self, toolbar: 'BaseToolbar'):
        """Set the bottom toolbar for this view (view-specific actions)"""
        try:
            self.bottom_toolbar = toolbar
            
            # Get toolbar container
            if hasattr(toolbar, 'get_container'):
                self.bottom_toolbar_container = toolbar.get_container()
                
                # Add bottom toolbar to main container (at the end)
                if self.bottom_toolbar_container and self.container:
                    # Add bottom toolbar at the end
                    self.container.add(self.bottom_toolbar_container)
                    logger.debug("Bottom toolbar added to view")
            
        except Exception as e:
            logger.error(f"Failed to set bottom toolbar: {e}")
    
    def set_toolbars(self, top_toolbar: 'BaseToolbar', bottom_toolbar: 'BaseToolbar'):
        """Set both top and bottom toolbars at once"""
        self.set_top_toolbar(top_toolbar)
        self.set_bottom_toolbar(bottom_toolbar)
    
    def remove_top_toolbar(self):
        """Remove the top toolbar from the view"""
        try:
            if self.top_toolbar_container and self.container:
                self.container.remove(self.top_toolbar_container)
                self.top_toolbar = None
                self.top_toolbar_container = None
                logger.debug("Top toolbar removed from view")
        except Exception as e:
            logger.error(f"Failed to remove top toolbar: {e}")
    
    def remove_bottom_toolbar(self):
        """Remove the bottom toolbar from the view"""
        try:
            if self.bottom_toolbar_container and self.container:
                self.container.remove(self.bottom_toolbar_container)
                self.bottom_toolbar = None
                self.bottom_toolbar_container = None
                logger.debug("Bottom toolbar removed from view")
        except Exception as e:
            logger.error(f"Failed to remove bottom toolbar: {e}")
    
    def get_top_toolbar(self) -> Optional['BaseToolbar']:
        """Get the current top toolbar"""
        return self.top_toolbar
    
    def get_bottom_toolbar(self) -> Optional['BaseToolbar']:
        """Get the current bottom toolbar"""
        return self.bottom_toolbar
    
    def get_icon_primary_color(self) -> str:
        """Get the primary icon color for active states"""
        return self.icon_primary
    
    def get_icon_secondary_color(self) -> str:
        """Get the secondary icon color for inactive states"""
        return self.icon_secondary
    
    def add_content(self, widget: toga.Widget):
        """Add content to the view"""
        try:
            if self.content_container:
                self.content_container.add(widget)
                logger.debug("Content added to view")
                
                # Notify content changed
                if self.on_content_changed:
                    self.on_content_changed()
                    
        except Exception as e:
            logger.error(f"Failed to add content: {e}")
    
    def clear_content(self):
        """Clear all content from the view"""
        try:
            if self.content_container:
                self.content_container.clear()
                logger.debug("Content cleared from view")
                
                # Notify content changed
                if self.on_content_changed:
                    self.on_content_changed()
                    
        except Exception as e:
            logger.error(f"Failed to clear content: {e}")
    
    def show(self):
        """Show the view"""
        if self.container:
            self.container.style.visibility = 'visible'
            self.is_visible = True
            logger.debug("View shown")
    
    def hide(self):
        """Hide the view"""
        if self.container:
            self.container.style.visibility = 'hidden'
            self.is_visible = False
            logger.debug("View hidden")
    
    def is_view_visible(self) -> bool:
        """Check if the view is visible"""
        return self.is_visible
    
    def initialize(self):
        """Initialize the view (called when view becomes active)"""
        try:
            if not self.is_initialized:
                self._on_initialize()
                self.is_initialized = True
                logger.debug("View initialized")
            
            # Notify view is ready
            if self.on_view_ready:
                self.on_view_ready()
                
        except Exception as e:
            logger.error(f"Failed to initialize view: {e}")
    
    def _on_initialize(self):
        """Called when view is first initialized - override in subclasses"""
        pass
    
    def refresh(self):
        """Refresh the view content - override in subclasses"""
        pass
    
    def cleanup(self):
        """Clean up view resources - override in subclasses"""
        pass
    
    def get_container(self) -> toga.Box:
        """Get the main container for this view with safety checks"""
        try:
            # Safety check: ensure scroll container has content before returning
            if self.scroll_container and not self.scroll_container.content:
                logger.warning("Scroll container missing content, setting fallback content")
                if self.content_container:
                    self.scroll_container.content = self.content_container
                else:
                    # Create minimal fallback content
                    fallback_content = toga.Box(style=Pack(direction=COLUMN))
                    self.scroll_container.content = fallback_content
            
            return self.container
        except Exception as e:
            logger.error(f"Error in get_container: {e}")
            # Return fallback container
            fallback = toga.Box(style=Pack(direction=COLUMN))
            fallback.add(toga.Label("View content unavailable"))
            return fallback
    
    def get_scroll_container(self) -> Optional[toga.ScrollContainer]:
        """Get the scroll container with safety checks"""
        try:
            # Only return scroll container if it's fully initialized
            if (self.scroll_container and 
                self.scroll_container.content and 
                hasattr(self.scroll_container, '_interface') and 
                self.scroll_container._interface is not None):
                return self.scroll_container
            else:
                logger.warning("Scroll container not properly initialized")
                return None
        except Exception as e:
            logger.error(f"Error accessing scroll container: {e}")
            return None
    
    def is_scroll_container_ready(self) -> bool:
        """Check if scroll container is ready for use"""
        try:
            return (self.scroll_container is not None and 
                   self.scroll_container.content is not None and
                   hasattr(self.scroll_container, '_interface') and 
                   self.scroll_container._interface is not None)
        except Exception:
            return False 