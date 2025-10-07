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
            # Enable both horizontal and vertical scrolling to prevent content overflow
            self.scroll_container = toga.ScrollContainer(
                content=self.content_container,  # Pass content in constructor
                horizontal=True,  # Enable horizontal scrolling for wide content
                vertical=True,    # Enable vertical scrolling (default)
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
        """Set the top toolbar for this view with simplified container structure"""
        try:
            self.top_toolbar = toolbar

            # Get HIG-compliant height from toolbar (no more fixed 50px)
            toolbar_height = toolbar.hig_specs["toolbar_height"] if hasattr(toolbar, 'hig_specs') else 50

            # Simplified: Use toolbar's container directly without extra wrapper
            if hasattr(toolbar, 'get_container'):
                toolbar_container = toolbar.get_container()

                # Ensure toolbar container uses proper height and full width
                if toolbar_container and hasattr(toolbar_container, 'style'):
                    # Update toolbar's own container to ensure consistent sizing
                    # Add small vertical margins for visual separation
                    toolbar_container.style.update(
                        height=toolbar_height,
                        margin=(4, 0),  # Small vertical margins for visual separation
                        flex=0  # Fixed height, full width
                    )

                # Insert toolbar container directly into main container
                if self.container:
                    self.container.insert(0, toolbar_container)
                    self.top_toolbar_container = toolbar_container
                    logger.debug(f"Top toolbar added with HIG height: {toolbar_height}px")
            else:
                # Fallback for non-BaseToolbar implementations
                self.top_toolbar_container = toga.Box(
                    style=Pack(
                        direction=ROW,
                        height=toolbar_height,
                        margin=0,
                        flex=0
                    )
                )
                self.top_toolbar_container.add(toolbar)
                self.container.insert(0, self.top_toolbar_container)
                logger.debug("Top toolbar added with fallback container")

        except Exception as e:
            logger.error(f"Failed to set top toolbar: {e}")
    
    def set_bottom_toolbar(self, toolbar: 'BaseToolbar'):
        """Set the bottom toolbar for this view with simplified container structure"""
        try:
            self.bottom_toolbar = toolbar

            # Get HIG-compliant height from toolbar (includes safe area for mobile)
            toolbar_height = toolbar.hig_specs["toolbar_height"] if hasattr(toolbar, 'hig_specs') else 50

            # For mobile bottom toolbars, add safe area if specified
            if hasattr(toolbar, 'hig_specs') and hasattr(toolbar, 'is_mobile') and toolbar.is_mobile:
                safe_area = toolbar.hig_specs.get("safe_area_bottom", 0)
                additional_margin = toolbar.hig_specs.get("additional_bottom_margin", 0)
                total_height = toolbar_height + safe_area + additional_margin
            else:
                total_height = toolbar_height

            # Simplified: Use toolbar's container directly without extra wrapper
            if hasattr(toolbar, 'get_container'):
                toolbar_container = toolbar.get_container()

                # Ensure toolbar container uses proper height and full width
                if toolbar_container and hasattr(toolbar_container, 'style'):
                    # Update toolbar's own container to ensure consistent sizing
                    # Add small vertical margins for visual separation (both mobile and desktop)
                    if total_height > 0:
                        margin_value = (4, 0)
                        toolbar_container.style.update(
                            height=total_height,
                            margin=margin_value,  # Small vertical margins for visual separation
                            flex=0  # Fixed height, full width
                        )
                        logger.debug(f"Bottom toolbar container configured: height={total_height}px, is_mobile={getattr(toolbar, 'is_mobile', 'unknown')}")
                    else:
                        # For hidden toolbars (desktop with height=0), only set safe properties (avoid height=None errors)
                        toolbar_container.style.update(
                            margin=(0, 0),
                            flex=0
                            # Don't set height=None - it causes Toga validation errors
                        )
                        logger.debug("Bottom toolbar hidden (height=0)")

                # Add toolbar container directly to main container
                if self.container and total_height > 0:  # Only add if visible
                    self.container.add(toolbar_container)
                    self.bottom_toolbar_container = toolbar_container
                    logger.debug(f"Bottom toolbar added with HIG height: {total_height}px")
                elif total_height == 0:
                    logger.debug("Bottom toolbar hidden (height=0 for desktop)")
            else:
                # Fallback for non-BaseToolbar implementations
                if total_height > 0:
                    self.bottom_toolbar_container = toga.Box(
                        style=Pack(
                            direction=ROW,
                            height=total_height,
                            margin=0,
                            flex=0
                        )
                    )
                    self.bottom_toolbar_container.add(toolbar)
                    self.container.add(self.bottom_toolbar_container)
                    logger.debug("Bottom toolbar added with fallback container")

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
            
            # Use NavigationController for reliable back navigation
            from fichero.shared.navigation.navigation_controller import NavigationController
            navigation_controller_back_callback = NavigationController.create_back_handler(self.app)
            
            # Set the callback on the toolbar
            self.top_toolbar.set_back_callback(navigation_controller_back_callback)
            logger.info("🔙 Mobile navigation connected successfully!")
            
        except Exception as e:
            logger.error(f"🔙 Failed to connect mobile navigation: {e}")
    
    def reconnect_mobile_navigation(self):
        """Reconnect mobile navigation after modal overlay system becomes available"""
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
