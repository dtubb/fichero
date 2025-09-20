"""
Content Pane for Fichero

Manages the middle pane content for collections and fiches with:
- View switching
- Content management
- Toolbar coordination
- Scroll support
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import logging
from typing import Optional, Dict, Any, List

from fichero.shared.views.base_view import BaseView
from fichero.windows.main.containers.scroll_container import ScrollableContainer

logger = logging.getLogger(__name__)


class ContentPane:
    """Manages the middle pane content for collections and fiches"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize content pane"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Pane container
        self.container: Optional[toga.Box] = None
        
        # Current view
        self.current_view: Optional[BaseView] = None
        self.current_view_name: Optional[str] = None
        
        # View history for navigation
        self.view_history: List[Dict[str, Any]] = []
        
        # Content management
        self.content_container: Optional[toga.Box] = None
        self.scroll_container: Optional[ScrollableContainer] = None
        
        # Callbacks
        self.on_view_changed: Optional[Any] = None
        self.on_content_updated: Optional[Any] = None
        
        # Create pane
        self._create_pane()
        
        logger.info("Content pane initialized successfully")
    
    def _create_pane(self):
        """Create the content pane structure"""
        try:
            # Create main container
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )
            
            # Create content container
            self.content_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create scrollable container for content
            self.scroll_container = ScrollableContainer(self.app, self.is_mobile)
            
            # Add scroll container to content container
            self.content_container.add(self.scroll_container.get_container())
            
            # Add content container to main container
            self.container.add(self.content_container)
            
            # Create initial placeholder content
            self._create_placeholder_content()
            
        except Exception as e:
            logger.error(f"Failed to create content pane: {e}")
    
    def _create_placeholder_content(self):
        """Create placeholder content for the content pane"""
        try:
            # Create welcome message
            welcome_label = toga.Label(
                "Welcome to Fichero",
                style=Pack(
                    font_size=24,
                    font_weight="bold",
                    margin=(50, 20),
                    color="#333333"
                )
            )
            self.scroll_container.add_content(welcome_label)
            
            # Create subtitle
            subtitle_label = toga.Label(
                "Select a collection from the library to get started",
                style=Pack(
                    font_size=16,
                    margin=(20, 20),
                    color="#666666"
                )
            )
            self.scroll_container.add_content(subtitle_label)
            
            # Create feature list
            features = [
                "📁 Manage document collections",
                "🔄 Process documents automatically",
                "📝 Create searchable fiches",
                "🔍 Search and organize content",
                "📤 Export and share results"
            ]
            
            for feature in features:
                feature_label = toga.Label(
                    feature,
                    style=Pack(
                        font_size=14,
                        margin=(10, 40),
                        color="#333333"
                    )
                )
                self.scroll_container.add_content(feature_label)
            
        except Exception as e:
            logger.error(f"Failed to create placeholder content: {e}")
    
    def switch_to_view(self, view_name: str, view: BaseView):
        """Switch to a specific view"""
        try:
            # Store previous view in history
            if self.current_view:
                self.view_history.append({
                    'name': self.current_view_name,
                    'view': self.current_view,
                    'timestamp': self.app.clock.now()
                })
                
                # Limit history size
                if len(self.view_history) > 10:
                    self.view_history.pop(0)
            
            # Update current view
            self.current_view = view
            self.current_view_name = view_name
            
            # Clear current content
            self.scroll_container.clear_content()
            
            # Get view container and add to content
            view_container = view.get_container()
            if view_container:
                self.scroll_container.add_content(view_container)
            
            # Notify callback
            if self.on_view_changed:
                self.on_view_changed(view_name, view)
            
            logger.info(f"Content pane switched to view: {view_name}")
            
        except Exception as e:
            logger.error(f"Failed to switch to view {view_name}: {e}")
    
    def go_back(self) -> bool:
        """Navigate back to the previous view"""
        try:
            if self.view_history:
                # Get previous view
                previous_view_info = self.view_history.pop()
                previous_view_name = previous_view_info['name']
                previous_view = previous_view_info['view']
                
                # Switch to previous view
                self.switch_to_view(previous_view_name, previous_view)
                
                logger.info(f"Content pane navigated back to: {previous_view_name}")
                return True
            else:
                logger.debug("No previous view to go back to")
                return False
                
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
            return False
    
    def can_go_back(self) -> bool:
        """Check if navigation back is possible"""
        return len(self.view_history) > 0
    
    def get_current_view(self) -> Optional[BaseView]:
        """Get the current view"""
        return self.current_view
    
    def get_current_view_name(self) -> Optional[str]:
        """Get the current view name"""
        return self.current_view_name
    
    def get_view_history(self) -> List[Dict[str, Any]]:
        """Get the view navigation history"""
        return self.view_history.copy()
    
    def clear_content(self):
        """Clear all content from the pane"""
        try:
            self.scroll_container.clear_content()
            self._create_placeholder_content()
            
            # Clear current view
            self.current_view = None
            self.current_view_name = None
            
            logger.debug("Content pane cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear content pane: {e}")
    
    def add_content(self, content: toga.Widget):
        """Add content to the pane"""
        try:
            self.scroll_container.add_content(content)
            logger.debug("Content added to content pane")
            
        except Exception as e:
            logger.error(f"Failed to add content to pane: {e}")
    
    def remove_content(self, content: toga.Widget):
        """Remove content from the pane"""
        try:
            self.scroll_container.remove_content(content)
            logger.debug("Content removed from content pane")
            
        except Exception as e:
            logger.error(f"Failed to remove content from pane: {e}")
    
    def set_content_visibility(self, visible: bool):
        """Set the visibility of the content pane"""
        try:
            if self.container:
                if visible:
                    self.container.style.visibility = 'visible'
                else:
                    self.container.style.visibility = 'hidden'
                
                logger.debug(f"Content pane visibility set to: {visible}")
            
        except Exception as e:
            logger.error(f"Failed to set content pane visibility: {e}")
    
    def refresh_content(self):
        """Refresh the content pane"""
        try:
            # Refresh scroll container
            if self.scroll_container:
                self.scroll_container.refresh()
            
            # Refresh current view if it has a refresh method
            if self.current_view and hasattr(self.current_view, 'refresh'):
                self.current_view.refresh()
            
            logger.debug("Content pane refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh content pane: {e}")
    
    def set_background_color(self, color: str):
        """Set the background color of the content pane"""
        try:
            if self.container:
                self.container.style.background_color = color
            
            if self.content_container:
                self.content_container.style.background_color = color
            
            logger.debug(f"Content pane background color set to: {color}")
            
        except Exception as e:
            logger.error(f"Failed to set content pane background color: {e}")
    
    def set_text_color(self, color: str):
        """Set the text color for the content pane"""
        try:
            # This would update text colors throughout the content
            # For now, just log the intention
            logger.debug(f"Content pane text color set to: {color}")
            
        except Exception as e:
            logger.error(f"Failed to set content pane text color: {e}")
    
    def get_pane_info(self) -> Dict[str, Any]:
        """Get information about the content pane"""
        return {
            'current_view_name': self.current_view_name,
            'current_view_type': type(self.current_view).__name__ if self.current_view else None,
            'view_history_count': len(self.view_history),
            'can_go_back': self.can_go_back(),
            'is_mobile': self.is_mobile,
            'content_count': len(self.scroll_container.content_widgets) if self.scroll_container else 0
        }
    
    def register_callbacks(self, 
                         on_view_changed: Optional[Any] = None,
                         on_content_updated: Optional[Any] = None):
        """Register callbacks for content pane actions"""
        self.on_view_changed = on_view_changed
        self.on_content_updated = on_content_updated
        
        logger.debug("Content pane callbacks registered")
    
    def get_container(self) -> toga.Box:
        """Get the content pane container"""
        return self.container
    
    def get_content_container(self) -> toga.Box:
        """Get the content container"""
        return self.content_container
    
    def get_scroll_container(self) -> ScrollableContainer:
        """Get the scroll container"""
        return self.scroll_container 