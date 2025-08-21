"""
Mobile View for Fichero

Single-pane mobile layout using Toga's native colors.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


class MobileView:
    """Mobile-specific view with single-pane layout - simplified without BaseView inheritance"""
    
    def __init__(self, app):
        """Initialize mobile view"""
        self.app = app
        
        # Mobile-specific components
        self.content_stack: list[toga.Widget] = []
        self.current_content: Optional[toga.Widget] = None
        
        # Create mobile layout
        self._create_mobile_layout()
    
    def _create_mobile_layout(self):
        """Create the single-pane mobile layout"""
        try:
            # Create main container
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create content container
            self.content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Add content container to main container
            self.container.add(self.content_container)
            
            # Create initial mobile content
            mobile_content = self._create_mobile_content_area()
            self.content_container.add(mobile_content)
            
            logger.debug("Mobile single-pane layout created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create mobile layout: {e}")
    
    def _create_mobile_content_area(self) -> toga.Box:
        """Create the mobile content area"""
        content_area = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1,
                margin=(10, 5)
            )
        )
        
        # Add mobile header
        mobile_header = toga.Label(
            "📱 Mobile View",
            style=Pack(
                font_size=18,
                font_weight="bold",
                margin=(0, 0, 10, 0)
            )
        )
        content_area.add(mobile_header)
        
        # Add placeholder for mobile content
        placeholder = toga.Label(
            "Mobile content will be displayed here",
            style=Pack(
                margin=(10, 5)
            )
        )
        content_area.add(placeholder)
        
        return content_area
    
    def push_content(self, content: toga.Widget):
        """Push new content onto the mobile view stack"""
        try:
            # Store current content in stack
            if self.current_content:
                self.content_stack.append(self.current_content)
            
            # Set new content
            self.current_content = content
            
            # Update the view
            self._update_mobile_content(content)
            
            logger.debug("Content pushed to mobile view stack")
            
        except Exception as e:
            logger.error(f"Failed to push content: {e}")
    
    def pop_content(self) -> Optional[toga.Widget]:
        """Pop content from the mobile view stack"""
        try:
            if self.content_stack:
                # Get previous content
                previous_content = self.content_stack.pop()
                self.current_content = previous_content
                
                # Update the view
                self._update_mobile_content(previous_content)
                
                logger.debug("Content popped from mobile view stack")
                return previous_content
            else:
                logger.debug("No content to pop from stack")
                return None
                
        except Exception as e:
            logger.error(f"Failed to pop content: {e}")
            return None
    
    def _update_mobile_content(self, content: toga.Widget):
        """Update the mobile view with new content"""
        try:
            if self.content_container:
                # Clear existing content
                self.content_container.clear()
                
                # Add new content
                self.content_container.add(content)
                
                logger.debug("Mobile content updated")
                
        except Exception as e:
            logger.error(f"Failed to update mobile content: {e}")
    
    def set_content(self, content: toga.Widget, clear_stack: bool = False):
        """Set content directly, optionally clearing the stack"""
        try:
            if clear_stack:
                self.content_stack.clear()
            
            self.current_content = content
            self._update_mobile_content(content)
            
            logger.debug("Mobile content set directly")
            
        except Exception as e:
            logger.error(f"Failed to set mobile content: {e}")
    
    def get_current_content(self) -> Optional[toga.Widget]:
        """Get the current content being displayed"""
        return self.current_content
    
    def get_stack_depth(self) -> int:
        """Get the current depth of the content stack"""
        return len(self.content_stack)
    
    def clear_stack(self):
        """Clear the content stack"""
        self.content_stack.clear()
        logger.debug("Mobile content stack cleared")
    
    def get_container(self) -> toga.Box:
        """Get the main container for this view"""
        return self.container 