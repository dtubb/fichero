"""
Mobile View for Fichero

Single-pane mobile layout using Toga's native colors.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Callable, Dict, Any

from .base_view import BaseView

logger = logging.getLogger(__name__)


class MobileView(BaseView):
    """Mobile-specific view with single-pane layout"""
    
    def __init__(self, app):
        """Initialize mobile view"""
        super().__init__(app)
        
        # Mobile-specific components
        self.content_stack: list[toga.Widget] = []
        self.current_content: Optional[toga.Widget] = None
        
        # Create mobile layout
        self._create_mobile_layout()
    
    def _create_content(self):
        """Create mobile-specific content layout"""
        # This will be overridden by _create_mobile_layout
        pass
    
    def _create_mobile_layout(self):
        """Create the single-pane mobile layout"""
        try:
            # Clear existing content
            if self.content_container:
                self.content_container.clear()
            
            # Create mobile content area
            mobile_content = self._create_mobile_content_area()
            
            # Add to content container
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
    
    def can_go_back(self) -> bool:
        """Check if we can navigate back"""
        return len(self.content_stack) > 0
    
    def go_back(self) -> bool:
        """Navigate back to previous content"""
        if self.can_go_back():
            self.pop_content()
            return True
        return False
    
    def clear_stack(self):
        """Clear the content stack"""
        self.content_stack.clear()
        logger.debug("Mobile content stack cleared")
    
    def set_mobile_header(self, title: str, subtitle: Optional[str] = None):
        """Set the mobile view header"""
        try:
            # Find and update the header
            if self.content_container and len(self.content_container.children) > 0:
                first_child = self.content_container.children[0]
                if isinstance(first_child, toga.Box) and len(first_child.children) > 0:
                    header = first_child.children[0]
                    if isinstance(header, toga.Label):
                        header.text = title
                        logger.debug(f"Mobile header updated: {title}")
                        
        except Exception as e:
            logger.error(f"Failed to set mobile header: {e}")
    
    def add_mobile_action_button(self, text: str, on_press: Optional[Callable] = None):
        """Add an action button to the mobile view"""
        try:
            if self.content_container:
                # Create action button
                action_button = toga.Button(
                    text=text,
                    on_press=on_press,
                    style=Pack(
                        margin=(5, 0),
                        padding=(10, 15),
                        background_color=self.accent_color
                    )
                )
                
                # Add to content
                self.content_container.add(action_button)
                
                logger.debug(f"Mobile action button added: {text}")
                
        except Exception as e:
            logger.error(f"Failed to add mobile action button: {e}")
    
    def set_mobile_background_color(self, color: str):
        """Set the mobile view background color"""
        self.set_background_color(color)
        logger.debug(f"Mobile background color set to: {color}")
    
    def set_mobile_text_color(self, color: str):
        """Set the mobile view text color"""
        self.set_text_color(color)
        logger.debug(f"Mobile text color set to: {color}")
    
    def set_mobile_accent_color(self, color: str):
        """Set the mobile view accent color"""
        self.set_accent_color(color)
        logger.debug(f"Mobile accent color set to: {color}")
    
    def _on_initialize(self):
        """Mobile-specific initialization"""
        try:
            # Set up mobile-specific features
            logger.debug("Mobile view initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize mobile view: {e}")
    
    def refresh(self):
        """Refresh the mobile view"""
        try:
            # Refresh current content
            if self.current_content:
                # Trigger content refresh if it has a refresh method
                if hasattr(self.current_content, 'refresh'):
                    self.current_content.refresh()
            
            logger.debug("Mobile view refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh mobile view: {e}")
    
    def get_navigation_info(self) -> Dict[str, Any]:
        """Get navigation information for the mobile view"""
        return {
            'can_go_back': self.can_go_back(),
            'stack_depth': self.get_stack_depth(),
            'current_content': self.current_content is not None
        } 