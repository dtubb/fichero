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

from fichero.shared.toolbars.color_constants import ICON_PRIMARY, ICON_SECONDARY, VIEW_BACKGROUND

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
        """Set the top toolbar for this view"""
        try:
            self.top_toolbar = toolbar
            
            # Create toolbar container
            self.top_toolbar_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    height=50,  # Fixed height for toolbar
                    padding=(5, 5)
                    # No background_color = transparent
                )
            )
            
            # Add toolbar content to container
            if hasattr(toolbar, 'get_container'):
                toolbar_content = toolbar.get_container()
            else:
                toolbar_content = toolbar
            
            self.top_toolbar_container.add(toolbar_content)
            
            # Insert toolbar at the beginning of the main container
            if self.container and self.top_toolbar_container:
                self.container.insert(0, self.top_toolbar_container)
                logger.debug("Top toolbar added to view")
            
            # CRITICAL FIX: Connect mobile navigation AFTER toolbar is set
            if self.is_mobile:
                self.connect_mobile_navigation()
            
        except Exception as e:
            logger.error(f"Failed to set top toolbar: {e}")
    
    def set_bottom_toolbar(self, toolbar: 'BaseToolbar'):
        """Set the bottom toolbar for this view"""
        try:
            self.bottom_toolbar = toolbar
            
            # Create toolbar container
            self.bottom_toolbar_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    height=50,  # Fixed height for toolbar
                    padding=(10, 5)
                    # No background_color = transparent
                )
            )
            
            # Add toolbar content to container
            if hasattr(toolbar, 'get_container'):
                toolbar_content = toolbar.get_container()
            else:
                toolbar_content = toolbar
            
            self.bottom_toolbar_container.add(toolbar_content)
            
            # Add toolbar at the end of the main container
            if self.container and self.bottom_toolbar_container:
                self.container.add(self.bottom_toolbar_container)
                logger.debug("Bottom toolbar added to view")
            
        except Exception as e:
            logger.error(f"Failed to set bottom toolbar: {e}")
    
    def set_toolbars(self, top_toolbar: 'BaseToolbar', bottom_toolbar: 'BaseToolbar'):
        """Set both top and bottom toolbars at once"""
        self.set_top_toolbar(top_toolbar)
        self.set_bottom_toolbar(bottom_toolbar)
    
    def get_container(self) -> toga.Box:
        """Get the main container for this view"""
        return self.container
    
    def show(self):
        """Show this view"""
        self.is_visible = True
        if self.on_view_ready:
            self.on_view_ready()
    
    def hide(self):
        """Hide this view"""
        self.is_visible = False
    
    def connect_mobile_navigation(self):
        """Connect back button to mobile view manager for proper navigation"""
        if not self.is_mobile:
            logger.debug("🔙 Not mobile - skipping mobile navigation setup")
            return
            
        if not self.top_toolbar:
            logger.warning("🔙 No top toolbar - cannot connect mobile navigation")
            return
            
        if not hasattr(self.top_toolbar, 'set_back_callback'):
            logger.warning("🔙 Top toolbar doesn't support back callbacks")
            return
            
        try:
            logger.info("🔙 Attempting to connect mobile navigation...")
            
            # Create a simple debug callback first to test if button works at all
            def debug_back_callback():
                logger.info("🔙 DEBUG: Back button callback fired!")
                
                # Check if app has window_view_manager
                if not hasattr(self.app, 'window_view_manager'):
                    logger.warning("🔙 App missing window_view_manager")
                    return False
                    
                window_view_manager = self.app.window_view_manager
                if not hasattr(window_view_manager, 'mobile_view_manager'):
                    logger.warning("🔙 WindowViewManager missing mobile_view_manager")
                    return False
                    
                mobile_view_manager = window_view_manager.mobile_view_manager
                if not mobile_view_manager:
                    logger.warning("🔙 mobile_view_manager is None")
                    return False
                
                # Call go_back
                try:
                    result = mobile_view_manager.go_back()
                    logger.info(f"🔙 go_back() result: {result}")
                    return result
                except Exception as e:
                    logger.error(f"🔙 Error in go_back(): {e}")
                    return False
            
            # Set the callback on the toolbar
            self.top_toolbar.set_back_callback(debug_back_callback)
            logger.info("🔙 Mobile navigation connected successfully!")
            
        except Exception as e:
            logger.error(f"🔙 Failed to connect mobile navigation: {e}")
    
    def reconnect_mobile_navigation(self):
        """Reconnect mobile navigation after mobile_view_manager becomes available"""
        if self.is_mobile and self.top_toolbar:
            logger.info("🔙 Attempting to reconnect mobile navigation...")
            self.connect_mobile_navigation()
    
    def refresh_content(self):
        """Refresh the view content"""
        if self.on_content_changed:
            self.on_content_changed()
    
    def get_view_info(self) -> dict:
        """Get information about this view"""
        return {
            'is_mobile': self.is_mobile,
            'is_visible': self.is_visible,
            'is_initialized': self.is_initialized,
            'has_top_toolbar': self.top_toolbar is not None,
            'has_bottom_toolbar': self.bottom_toolbar is not None
        }
