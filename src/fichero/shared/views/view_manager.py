"""
View Manager for Main Window

Handles navigation between different views (About, Preferences, Collection, etc.)
and manages the view stack for both desktop and mobile platforms.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from typing import Dict, Optional, Callable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ViewType(Enum):
    """Enumeration of available view types"""
    COLLECTION = "collection"
    ACTIVITY = "activity"
    PROCESSING = "processing"  # Added for mobile processing view
    # PLANS = "plans"  # HIDDEN
    # PROMPTS = "prompts"  # HIDDEN
    ABOUT = "about"
    PREFERENCES = "preferences"


class ViewManager:
    """
    Manages navigation between different views in the main window.
    
    Handles both desktop and mobile navigation patterns:
    - Desktop: Views replace content in main window
    - Mobile: Stack-based navigation with back buttons
    """
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize view manager"""
        self.app = app
        self.is_mobile = is_mobile
        
        # View instances
        self.views: Dict[ViewType, Any] = {}
        self.current_view: Optional[ViewType] = None
        
        # Navigation stack for mobile
        self.view_stack: list[ViewType] = []
        
        # Container for views
        self.container: Optional[toga.Box] = None
        
        # Callbacks
        self.on_view_change: Optional[Callable[[ViewType, ViewType], None]] = None
        
    def set_container(self, container: toga.Box):
        """Set the container that will hold the views"""
        self.container = container
        
    def register_view(self, view_type: ViewType, view_instance):
        """Register a view instance with the manager"""
        self.views[view_type] = view_instance
        logger.info(f"Registered view: {view_type.value}")
        
    def show_view(self, view_type: ViewType, push_to_stack: bool = True) -> bool:
        """
        Show a specific view
        
        Args:
            view_type: The type of view to show
            push_to_stack: Whether to add this view to the navigation stack (mobile)
            
        Returns:
            bool: True if view was shown successfully
        """
        if view_type not in self.views:
            logger.error(f"View not registered: {view_type.value}")
            return False
            
        if not self.container:
            logger.error("No container set for view manager")
            return False
            
        try:
            # Get the view instance
            view = self.views[view_type]
            
            # Notify of view change
            old_view = self.current_view
            if self.on_view_change:
                self.on_view_change(old_view, view_type)
            
            # Clear current content
            self.container.clear()
            
            # Add new view content
            if hasattr(view, 'create'):
                view_content = view.create()
            elif hasattr(view, 'get_container'):
                view_content = view.get_container()
            else:
                view_content = view
            self.container.add(view_content)
            
            # Update navigation state
            previous_view = self.current_view
            self.current_view = view_type
            
            # Handle mobile navigation stack
            if self.is_mobile and push_to_stack:
                if previous_view and previous_view != view_type:
                    if previous_view not in self.view_stack:
                        self.view_stack.append(previous_view)
                        
            logger.info(f"Showed view: {view_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to show view {view_type.value}: {e}")
            return False
    
    def go_back(self) -> bool:
        """
        Go back to the previous view (mobile navigation)
        
        Returns:
            bool: True if navigation was successful
        """
        if not self.is_mobile:
            logger.warning("go_back() called on non-mobile platform")
            return False
            
        if not self.view_stack:
            logger.info("No previous view to go back to")
            return False
            
        try:
            # Get previous view from stack
            previous_view = self.view_stack.pop()
            
            # Show previous view without adding to stack
            return self.show_view(previous_view, push_to_stack=False)
            
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
            return False
    
    def can_go_back(self) -> bool:
        """Check if we can go back to a previous view"""
        return self.is_mobile and len(self.view_stack) > 0
    
    def get_current_view(self) -> Optional[ViewType]:
        """Get the currently displayed view type"""
        return self.current_view
    
    def clear_navigation_stack(self):
        """Clear the navigation stack (mobile)"""
        self.view_stack.clear()
        logger.info("Navigation stack cleared")
        
    def get_view_instance(self, view_type: ViewType):
        """Get a registered view instance"""
        return self.views.get(view_type) 