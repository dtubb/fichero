"""
Scroll Container for Fichero

Implements vertical scrolling for view content with support for:
- Scrolling above and below toolbars
- Proper content sizing
- Smooth scrolling behavior
- Toolbar coordination
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from typing import Optional, List, Any

logger = logging.getLogger(__name__)


class ScrollableContainer:
    """Container that provides scrolling functionality for view content"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize scrollable container"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Container components
        self.main_container: Optional[toga.Box] = None
        self.scroll_container: Optional[toga.ScrollContainer] = None
        self.content_container: Optional[toga.Box] = None
        
        # Toolbar management
        self.top_toolbar: Optional[toga.Widget] = None
        self.bottom_toolbar: Optional[toga.Widget] = None
        
        # Content management
        self.content_widgets: List[toga.Widget] = []
        
        # Scrolling state
        self.scroll_position = 0
        self.is_scrolling = False
        
        # Create container structure
        self._create_container_structure()
    
    def _create_container_structure(self):
        """Create the container structure with scrolling support"""
        try:
            # Create main container
            self.main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create content container FIRST
            self.content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create scroll container with content - Toga's recommended pattern
            self.scroll_container = toga.ScrollContainer(
                content=self.content_container,  # Pass content in constructor
                horizontal=False,  # Disable horizontal scrolling
                vertical=True,     # Enable vertical scrolling only
                style=Pack(
                    flex=1
                )
            )
            
            # Add scroll container to main container
            self.main_container.add(self.scroll_container)
            
            # Ensure vertical-only scrolling
            self.ensure_vertical_scrolling()
            
            # Safety check: ensure scroll container has valid content
            if not self.scroll_container.content:
                logger.warning("Scroll container content not set, setting fallback content")
                self.scroll_container.content = self.content_container
            
            logger.debug("Scrollable container structure created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create scrollable container structure: {e}")
            # Create fallback container
            self.main_container = toga.Box(style=Pack(direction=COLUMN))
    
    def set_top_toolbar(self, toolbar: toga.Widget):
        """Set the top toolbar"""
        try:
            # Remove existing top toolbar if any
            if self.top_toolbar and self.top_toolbar in self.main_container.children:
                self.main_container.remove(self.top_toolbar)
            
            # Add new top toolbar at the beginning
            self.top_toolbar = toolbar
            self.main_container.insert(0, toolbar)
            
            logger.debug("Top toolbar set")
            
        except Exception as e:
            logger.error(f"Failed to set top toolbar: {e}")
    
    def set_bottom_toolbar(self, toolbar: toga.Widget):
        """Set the bottom toolbar"""
        try:
            # Remove existing bottom toolbar if any
            if self.bottom_toolbar and self.bottom_toolbar in self.main_container.children:
                self.main_container.remove(self.bottom_toolbar)
            
            # Add new bottom toolbar at the end
            self.bottom_toolbar = toolbar
            self.main_container.add(toolbar)
            
            logger.debug("Bottom toolbar set")
            
        except Exception as e:
            logger.error(f"Failed to set bottom toolbar: {e}")
    
    def add_content(self, widget: toga.Widget):
        """Add content to the scrollable area"""
        try:
            if self.content_container:
                self.content_container.add(widget)
                self.content_widgets.append(widget)
                logger.debug("Content added to scrollable container")
                
        except Exception as e:
            logger.error(f"Failed to add content: {e}")
    
    def remove_content(self, widget: toga.Widget):
        """Remove content from the scrollable area"""
        try:
            if self.content_container and widget in self.content_widgets:
                self.content_container.remove(widget)
                self.content_widgets.remove(widget)
                logger.debug("Content removed from scrollable container")
                
        except Exception as e:
            logger.error(f"Failed to remove content: {e}")
    
    def clear_content(self):
        """Clear all content from the scrollable area"""
        try:
            if self.content_container:
                self.content_container.clear()
                self.content_widgets.clear()
                logger.debug("Content cleared from scrollable container")
                
        except Exception as e:
            logger.error(f"Failed to clear content: {e}")
    
    def insert_content(self, index: int, widget: toga.Widget):
        """Insert content at a specific index"""
        try:
            if self.content_container and 0 <= index <= len(self.content_widgets):
                self.content_container.insert(index, widget)
                self.content_widgets.insert(index, widget)
                logger.debug(f"Content inserted at index {index}")
                
        except Exception as e:
            logger.error(f"Failed to insert content: {e}")
    
    def get_content_at_index(self, index: int) -> Optional[toga.Widget]:
        """Get content at a specific index"""
        try:
            if 0 <= index < len(self.content_widgets):
                return self.content_widgets[index]
            return None
            
        except Exception as e:
            logger.error(f"Failed to get content at index {index}: {e}")
            return None
    
    def get_content_count(self) -> int:
        """Get the number of content widgets"""
        return len(self.content_widgets)
    
    def scroll_to_top(self):
        """Scroll to the top of the content"""
        try:
            if self.scroll_container:
                # Note: Toga may not support direct scroll control
                # This is a placeholder for future implementation
                self.scroll_position = 0
                logger.debug("Scroll position set to top")
                
        except Exception as e:
            logger.error(f"Failed to scroll to top: {e}")
    
    def scroll_to_bottom(self):
        """Scroll to the bottom of the content"""
        try:
            if self.scroll_container:
                # Note: Toga may not support direct scroll control
                # This is a placeholder for future implementation
                self.scroll_position = 100  # Arbitrary value for bottom
                logger.debug("Scroll position set to bottom")
                
        except Exception as e:
            logger.error(f"Failed to scroll to bottom: {e}")
    
    def scroll_to_position(self, position: float):
        """Scroll to a specific position (0.0 = top, 1.0 = bottom)"""
        try:
            if self.scroll_container:
                # Clamp position between 0.0 and 1.0
                position = max(0.0, min(1.0, position))
                self.scroll_position = position
                logger.debug(f"Scroll position set to {position}")
                
        except Exception as e:
            logger.error(f"Failed to scroll to position {position}: {e}")
    
    def get_scroll_position(self) -> float:
        """Get the current scroll position"""
        return self.scroll_position
    
    def is_at_top(self) -> bool:
        """Check if scrolled to the top"""
        return self.scroll_position == 0.0
    
    def is_at_bottom(self) -> bool:
        """Check if scrolled to the bottom"""
        return self.scroll_position == 1.0
    
    def scroll_up(self, amount: float = 0.1):
        """Scroll up by a specified amount"""
        try:
            new_position = max(0.0, self.scroll_position - amount)
            self.scroll_to_position(new_position)
            
        except Exception as e:
            logger.error(f"Failed to scroll up: {e}")
    
    def scroll_down(self, amount: float = 0.1):
        """Scroll down by a specified amount"""
        try:
            new_position = min(1.0, self.scroll_position + amount)
            self.scroll_to_position(new_position)
            
        except Exception as e:
            logger.error(f"Failed to scroll down: {e}")
    
    def set_scroll_enabled(self, enabled: bool):
        """Enable or disable scrolling"""
        try:
            if self.scroll_container:
                # Note: Toga may not support disabling scrolling
                # This is a placeholder for future implementation
                logger.debug(f"Scroll enabled set to: {enabled}")
                
        except Exception as e:
            logger.error(f"Failed to set scroll enabled: {e}")
    
    def set_scroll_direction(self, horizontal: bool = False, vertical: bool = True):
        """Set scroll direction"""
        try:
            if self.scroll_container:
                # Use Toga's built-in scroll control properties
                self.scroll_container.horizontal = horizontal
                self.scroll_container.vertical = vertical
                
                if vertical and not horizontal:
                    logger.debug("Scroll direction set to vertical-only using Toga properties")
                else:
                    logger.warning("Horizontal scrolling not supported - views are vertical-only")
                
        except Exception as e:
            logger.error(f"Failed to set scroll direction: {e}")
    
    def ensure_vertical_scrolling(self):
        """Ensure the container is configured for vertical-only scrolling"""
        try:
            if self.scroll_container:
                # Use Toga's built-in scroll control properties
                self.scroll_container.horizontal = False  # Disable horizontal scrolling
                self.scroll_container.vertical = True     # Enable vertical scrolling only
                
                # Set content container to expand vertically
                self.content_container.style.flex = 1
                
                logger.debug("Container configured for vertical-only scrolling using Toga properties")
                
        except Exception as e:
            logger.error(f"Failed to ensure vertical scrolling: {e}")
    
    def get_container(self) -> toga.Box:
        """Get the main container with safety checks"""
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
            
            return self.main_container
        except Exception as e:
            logger.error(f"Error in get_container: {e}")
            # Return fallback container
            fallback = toga.Box(style=Pack(direction=COLUMN))
            fallback.add(toga.Label("Scroll container unavailable"))
            return fallback
    
    def get_scroll_container(self) -> toga.ScrollContainer:
        """Get the scroll container with safety checks"""
        try:
            if self.scroll_container and self.scroll_container.content:
                return self.scroll_container
            else:
                logger.warning("Scroll container not properly initialized")
                # Return a fallback scroll container if needed
                return None
        except Exception as e:
            logger.error(f"Error accessing scroll container: {e}")
            return None
    
    def get_content_container(self) -> toga.Box:
        """Get the content container"""
        return self.content_container
    
    def refresh(self):
        """Refresh the scrollable container"""
        try:
            # Trigger a refresh of the scroll container
            if self.scroll_container:
                # Note: Toga may not support direct refresh
                # This is a placeholder for future implementation
                logger.debug("Scrollable container refreshed")
                
        except Exception as e:
            logger.error(f"Failed to refresh scrollable container: {e}")
    
    def get_scroll_info(self) -> dict[str, Any]:
        """Get information about the scroll state"""
        return {
            'scroll_position': self.scroll_position,
            'is_scrolling': self.is_scrolling,
            'content_count': self.get_content_count(),
            'has_top_toolbar': self.top_toolbar is not None,
            'has_bottom_toolbar': self.bottom_toolbar is not None,
            'is_at_top': self.is_at_top(),
            'is_at_bottom': self.is_at_bottom()
        }
    
    def set_content_spacing(self, spacing: int):
        """Set spacing between content items"""
        try:
            if self.content_container:
                # Update spacing for all content widgets
                for widget in self.content_widgets:
                    if hasattr(widget, 'style') and hasattr(widget.style, 'margin'):
                        widget.style.margin = (spacing, 0)
                
                logger.debug(f"Content spacing set to {spacing}")
                
        except Exception as e:
            logger.error(f"Failed to set content spacing: {e}")
    
    def set_content_padding(self, padding: int):
        """Set padding around content"""
        try:
            if self.content_container:
                self.content_container.style.padding = padding
                logger.debug(f"Content padding set to {padding}")
                
        except Exception as e:
            logger.error(f"Failed to set content padding: {e}")
    
    def set_scroll_margins(self, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0):
        """Set scroll margins for the content container"""
        try:
            if self.content_container:
                # Set margins around the content container
                self.content_container.style.margin = (top, right, bottom, left)
                logger.debug(f"Scroll margins set: top={top}, right={right}, bottom={bottom}, left={left}")
                
        except Exception as e:
            logger.error(f"Failed to set scroll margins: {e}")
    
    def set_background_color(self, color: str):
        """Set the background color of the container"""
        try:
            if self.main_container:
                self.main_container.style.background_color = color
            if self.content_container:
                self.content_container.style.background_color = color
            logger.debug(f"Background color set to {color}")
            
        except Exception as e:
            logger.error(f"Failed to set background color: {e}")
    
    def set_border(self, width: int = 1, color: str = "#CCCCCC"):
        """Set border for the container"""
        try:
            if self.main_container:
                # Note: Toga may not support border styling directly
                # This is a placeholder for future implementation
                logger.debug(f"Border set: width={width}, color={color}")
                
        except Exception as e:
            logger.error(f"Failed to set border: {e}")
    
    def set_corner_radius(self, radius: int):
        """Set corner radius for the container"""
        try:
            if self.main_container:
                # Note: Toga may not support corner radius directly
                # This is a placeholder for future implementation
                logger.debug(f"Corner radius set to {radius}")
                
        except Exception as e:
            logger.error(f"Failed to set corner radius: {e}") 