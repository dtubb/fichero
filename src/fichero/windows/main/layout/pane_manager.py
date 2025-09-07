"""
Pane Manager for Fichero

Manages the three-pane layout system for desktop with:
- Pane sizing and organization
- Content switching
- Toolbar coordination
- View management
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any, List

from fichero.windows.main.views.base_view import BaseView
from fichero.windows.main.views.mobile_view import MobileView
# from ..toolbars.toolbar_manager import ToolbarManager, ToolbarType  # No longer needed

logger = logging.getLogger(__name__)


class PaneManager:
    """Manages the three-pane layout system for desktop"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize pane manager"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Layout components
        self.main_container: Optional[toga.Box] = None
        self.left_pane: Optional[toga.Box] = None
        self.middle_pane: Optional[toga.Box] = None
        self.right_pane: Optional[toga.Box] = None
        
        # View management
        self.current_views: Dict[str, BaseView] = {}
        self.view_history: List[str] = []
        
        # Toolbar management
        # self.toolbar_manager = ToolbarManager(app, is_mobile) # No longer needed
        
        # Pane sizing - fixed widths for left and middle, flex for right
        self.left_pane_width = 200
        self.middle_pane_width = 200
        self.right_pane_flex = True
        
        # Create layout
        self._create_layout()
        
        logger.info("Pane manager initialized successfully")
    
    def _create_layout(self):
        """Create the pane layout structure"""
        try:
            if self.is_mobile:
                self._create_mobile_layout()
            else:
                self._create_desktop_layout()
                
        except Exception as e:
            logger.error(f"Failed to create pane layout: {e}")
    
    def _create_desktop_layout(self):
        """Create the three-pane desktop layout with resizable panes"""
        try:
            # Create main container
            self.main_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1
                )
            )
            
            # Create left pane (Library navigation) - 25% width
            self.left_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,  # Use flex instead of fixed width
                    width=300  # Set a reasonable default width
                )
            )
            
            # Create middle pane (Content) - 25% width
            self.middle_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,  # Use flex instead of fixed width
                    width=300  # Set a reasonable default width
                )
            )
            
            # Create right pane (Preview) - 50% width (flex to fill remainder)
            self.right_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=2,  # Give it more flex to make it wider
                    width=400  # Set a reasonable default width
                )
            )
            
            # Add panes to main container
            self.main_container.add(self.left_pane)
            self.main_container.add(self.middle_pane)
            self.main_container.add(self.right_pane)
            
            logger.debug("Desktop three-pane layout created with resizable panes")
            
        except Exception as e:
            logger.error(f"Failed to create desktop layout: {e}")
    
    def _create_mobile_layout(self):
        """Create the single-pane mobile layout"""
        try:
            # Create main container
            self.main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Create single content pane
            self.middle_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )
            
            # Add content pane to main container
            self.main_container.add(self.middle_pane)
            
            logger.debug("Mobile single-pane layout created")
            
        except Exception as e:
            logger.error(f"Failed to create mobile layout: {e}")
    
    def set_left_pane_content(self, content: toga.Widget):
        """Set content for the left pane"""
        try:
            if self.left_pane:
                # Clear existing content
                self.left_pane.clear()
                
                # Add new content
                self.left_pane.add(content)
                
                logger.debug("Left pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set left pane content: {e}")
    
    def set_middle_pane_content(self, content: toga.Widget):
        """Set content for the middle pane"""
        try:
            if self.middle_pane:
                # Clear existing content
                self.middle_pane.clear()
                
                # Add new content
                self.middle_pane.add(content)
                
                logger.debug("Middle pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set middle pane content: {e}")
    
    def set_right_pane_content(self, content: toga.Widget):
        """Set content for the right pane"""
        try:
            if self.right_pane:
                # Clear existing content
                self.right_pane.clear()
                
                # Add new content
                self.right_pane.add(content)
                
                logger.debug("Right pane content updated")
                
        except Exception as e:
            logger.error(f"Failed to set right pane content: {e}")
    
    def set_pane_sizes(self, left_width: Optional[int] = None, middle_width: Optional[int] = None, right_width: Optional[int] = None):
        """Set the widths of the panes (now works with width-based layout)"""
        try:
            if left_width and self.left_pane:
                # Update width for left pane
                self.left_pane.style.width = max(250, left_width)
                logger.debug(f"Left pane width updated to: {self.left_pane.style.width}")
            
            if middle_width and self.middle_pane:
                # Update width for middle pane
                self.middle_pane.style.width = max(250, middle_width)
                logger.debug(f"Middle pane width updated to: {self.middle_pane.style.width}")
            
            if right_width and self.right_pane:
                # Update width for right pane
                self.right_pane.style.width = max(300, right_width)
                logger.debug(f"Right pane width updated to: {self.right_pane.style.width}")
            
            logger.debug(f"Pane sizes updated: left={left_width}, middle={middle_width}, right={right_width}")
            
        except Exception as e:
            logger.error(f"Failed to set pane sizes: {e}")
    
    def switch_to_view(self, view_name: str, view: BaseView, pane: str = "middle"):
        """Switch to a specific view in a specific pane"""
        try:
            # Store view reference
            self.current_views[view_name] = view
            
            # Add to view history
            if view_name not in self.view_history:
                self.view_history.append(view_name)
            
            # Get view container
            view_container = view.get_container()
            
            # Set content in appropriate pane
            if pane == "left":
                self.set_left_pane_content(view_container)
            elif pane == "middle":
                self.set_middle_pane_content(view_container)
            elif pane == "right":
                self.set_right_pane_content(view_container)
            else:
                logger.warning(f"Unknown pane: {pane}")
                return False
            
            # Views now manage their own toolbars - no need to switch here
            # self._switch_toolbar_for_view(view_name, view)
            
            logger.info(f"Switched to view {view_name} in {pane} pane")
            return True
            
        except Exception as e:
            logger.error(f"Failed to switch to view {view_name}: {e}")
            return False
    
    def _switch_toolbar_for_view(self, view_name: str, view: BaseView):
        """Switch toolbar to match the current view"""
        try:
            # Determine toolbar type based on view name
            if "library" in view_name.lower() or "management" in view_name.lower():
                toolbar_type = ToolbarType.LIBRARY
            elif "collection" in view_name.lower():
                toolbar_type = ToolbarType.COLLECTION
            elif "fiche" in view_name.lower():
                toolbar_type = ToolbarType.FICHE
            elif "preview" in view_name.lower():
                toolbar_type = ToolbarType.PREVIEW
            else:
                # Default to library toolbar
                toolbar_type = ToolbarType.LIBRARY
            
            # Views now manage their own toolbars - no need to switch here
            # self.toolbar_manager.switch_to_toolbar(toolbar_type)
            
            logger.debug(f"View {view_name} added to pane {pane} (toolbars managed by view)")
            
        except Exception as e:
            logger.error(f"Failed to switch toolbar for view {view_name}: {e}")
    
    def get_current_view(self, pane: str = "middle") -> Optional[BaseView]:
        """Get the current view in a specific pane"""
        try:
            # Find view by pane content
            if pane == "left" and self.left_pane:
                # Search for view that has this pane as its container
                for view_name, view in self.current_views.items():
                    if view.get_container() == self.left_pane:
                        return view
            elif pane == "middle" and self.middle_pane:
                for view_name, view in self.current_views.items():
                    if view.get_container() == self.middle_pane:
                        return view
            elif pane == "right" and self.right_pane:
                for view_name, view in self.current_views.items():
                    if view.get_container() == self.right_pane:
                        return view
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get current view for pane {pane}: {e}")
            return None
    
    def get_view_history(self) -> List[str]:
        """Get the view navigation history"""
        return self.view_history.copy()
    
    def go_back(self) -> bool:
        """Navigate back to the previous view"""
        try:
            if len(self.view_history) > 1:
                # Remove current view
                current_view = self.view_history.pop()
                
                # Get previous view
                previous_view_name = self.view_history[-1]
                previous_view = self.current_views.get(previous_view_name)
                
                if previous_view:
                    # Switch to previous view
                    self.switch_to_view(previous_view_name, previous_view, "middle")
                    logger.info(f"Navigated back to {previous_view_name}")
                    return True
                else:
                    logger.warning(f"Previous view not found: {previous_view_name}")
                    return False
            else:
                logger.debug("No previous view to go back to")
                return False
                
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
            return False
    
    def clear_pane(self, pane: str):
        """Clear content from a specific pane"""
        try:
            if pane == "left" and self.left_pane:
                self.left_pane.clear()
            elif pane == "middle" and self.middle_pane:
                self.middle_pane.clear()
            elif pane == "right" and self.right_pane:
                self.right_pane.clear()
            else:
                logger.warning(f"Unknown pane: {pane}")
                return
            
            logger.debug(f"Pane {pane} cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear pane {pane}: {e}")
    
    def set_pane_visibility(self, pane: str, visible: bool):
        """Set the visibility of a specific pane"""
        try:
            target_pane = None
            
            if pane == "left":
                target_pane = self.left_pane
            elif pane == "middle":
                target_pane = self.middle_pane
            elif pane == "right":
                target_pane = self.right_pane
            else:
                logger.warning(f"Unknown pane: {pane}")
                return
            
            if target_pane:
                if visible:
                    target_pane.style.visibility = 'visible'
                else:
                    target_pane.style.visibility = 'hidden'
                
                logger.debug(f"Pane {pane} visibility set to {visible}")
            
        except Exception as e:
            logger.error(f"Failed to set pane {pane} visibility: {e}")
    
    def get_pane_info(self) -> Dict[str, Any]:
        """Get information about all panes"""
        return {
            'is_mobile': self.is_mobile,
            'left_pane_width': self.left_pane_width,
            'right_pane_width': self.right_pane_width,
            'left_pane_visible': self.left_pane.style.visibility != 'hidden' if self.left_pane else False,
            'middle_pane_visible': self.middle_pane.style.visibility != 'hidden' if self.middle_pane else False,
            'right_pane_visible': self.right_pane.style.visibility != 'hidden' if self.right_pane else False,
            'current_views': list(self.current_views.keys()),
            'view_history': self.view_history.copy()
        }
    
    def refresh_all_panes(self):
        """Refresh all panes"""
        try:
            # Refresh all current views
            for view_name, view in self.current_views.items():
                if hasattr(view, 'refresh'):
                    view.refresh()
            
            logger.debug("All panes refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh all panes: {e}")
    
    def get_main_container(self) -> toga.Box:
        """Get the main container"""
        return self.main_container
    
    def get_left_pane(self) -> Optional[toga.Box]:
        """Get the left pane container"""
        return self.left_pane
    
    def get_middle_pane(self) -> Optional[toga.Box]:
        """Get the middle pane container"""
        return self.middle_pane
    
    def get_right_pane(self) -> Optional[toga.Box]:
        """Get the right pane container"""
        return self.right_pane
    
    def get_toolbar_manager(self):
        """Get the toolbar manager - no longer used since views manage their own toolbars"""
        # Views now manage their own toolbars - this method is deprecated
        logger.warning("get_toolbar_manager() is deprecated - views manage their own toolbars")
        return None 