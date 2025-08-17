"""
Window/View Manager for Fichero

Unified system for managing windows and views across desktop and mobile platforms.
This is the single source of truth for opening settings, about, activity monitor, etc.

Desktop: Opens separate Toga windows
Mobile/Tablet: Opens views in main window with proper navigation
"""

import toga
import logging
from typing import Optional, Dict, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class WindowType(Enum):
    """Types of windows/views that can be opened"""
    SETTINGS = "settings"
    ABOUT = "about"
    ACTIVITY_MONITOR = "activity_monitor"
    PLANS = "plans"
    PROMPTS = "prompts"
    PROCESSING = "processing"


class WindowViewManager:
    """
    Unified manager for windows and views.
    
    Handles both desktop (separate windows) and mobile (main window views) modes.
    This is the single source of truth for all window/view operations.
    """
    
    def __init__(self, app):
        """Initialize the window/view manager"""
        self.app = app
        
        # Platform detection
        self.is_mobile = self._detect_mobile_platform()
        
        # Desktop windows (separate Toga windows)
        self.desktop_windows: Dict[WindowType, Any] = {}
        
        # Mobile view manager (for main window)
        self.mobile_view_manager: Optional['MobileViewManager'] = None
        
        # Callbacks for mobile navigation
        self.on_mobile_view_changed: Optional[Callable] = None
        
        logger.info(f"WindowViewManager initialized for {'mobile' if self.is_mobile else 'desktop'} platform")
    
    def _detect_mobile_platform(self) -> bool:
        """Detect if we're running on mobile/tablet platform"""
        try:
            # Import debug overrides
            from fichero.config.debug_constants import get_debug_mobile_override
            
            # Check debug override first
            debug_mobile = get_debug_mobile_override()
            if debug_mobile is not None:
                logger.info(f"Using debug mobile override: {debug_mobile}")
                return debug_mobile
            
            # Check app's mobile detection if available
            if hasattr(self.app, 'is_mobile'):
                return self.app.is_mobile
            
            # Fall back to platform detection
            import toga.platform
            current_platform = toga.platform.current_platform
            is_mobile = current_platform in ['iOS', 'android']
            
            logger.info(f"Platform detection: {current_platform} -> mobile={is_mobile}")
            return is_mobile
            
        except Exception as e:
            logger.error(f"Failed to detect platform: {e}")
            return False
    
    def set_mobile_view_manager(self, mobile_view_manager):
        """Set the mobile view manager for handling views in main window"""
        self.mobile_view_manager = mobile_view_manager
        logger.info("Mobile view manager set")
    
    def show_window_or_view(self, window_type: WindowType, **kwargs) -> bool:
        """
        Show a window (desktop) or view (mobile) based on platform.
        
        This is the main entry point for all window/view operations.
        """
        try:
            if self.is_mobile:
                return self._show_mobile_view(window_type, **kwargs)
            else:
                return self._show_desktop_window(window_type, **kwargs)
                
        except Exception as e:
            logger.error(f"Failed to show {window_type.value}: {e}")
            return False
    
    def _show_desktop_window(self, window_type: WindowType, **kwargs) -> bool:
        """Show a separate Toga window on desktop"""
        try:
            # Check if window already exists and is still valid
            existing_window = self.desktop_windows.get(window_type)
            
            if existing_window:
                try:
                    # Check if window is still valid (not closed by user)
                    window_obj = getattr(existing_window, 'window', existing_window)
                    
                    if window_obj and not getattr(window_obj, 'closed', False):
                        # Window exists and is valid - bring to front
                        if hasattr(existing_window, 'show'):
                            existing_window.show()  # Use window wrapper's show method
                        elif hasattr(window_obj, 'show'):
                            window_obj.show()  # Use Toga window's show method
                        
                        # Additional bring-to-front technique
                        if hasattr(window_obj, 'visible') and window_obj.visible:
                            # Hide and show to bring to front
                            if hasattr(window_obj, 'hide'):
                                window_obj.hide()
                            if hasattr(window_obj, 'show'):
                                window_obj.show()
                        
                        logger.info(f"Desktop window brought to front: {window_type.value}")
                        return True
                    else:
                        # Window was closed by user - remove from tracking
                        del self.desktop_windows[window_type]
                        logger.info(f"Removed closed window from tracking: {window_type.value}")
                        
                except Exception as e:
                    # Window reference is invalid - remove it
                    logger.warning(f"Window {window_type.value} appears invalid: {e}")
                    if window_type in self.desktop_windows:
                        del self.desktop_windows[window_type]
            
            # Create new window
            window = self._create_desktop_window(window_type, **kwargs)
            if window:
                self.desktop_windows[window_type] = window
                if hasattr(window, 'show'):
                    window.show()
                elif hasattr(window, 'window') and hasattr(window.window, 'show'):
                    window.window.show()
                logger.info(f"Desktop window created and shown: {window_type.value}")
                return True
            else:
                logger.error(f"Failed to create desktop window: {window_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to show desktop window {window_type.value}: {e}")
            return False
    
    def _create_desktop_window(self, window_type: WindowType, **kwargs):
        """Create a desktop window for the specified type with close callback"""
        try:
            # Create the appropriate window
            window = None
            
            if window_type == WindowType.SETTINGS:
                from fichero.windows.settings import SettingsWindow
                window = SettingsWindow(self.app)
            
            elif window_type == WindowType.ABOUT:
                from fichero.windows.about import AboutWindow
                window = AboutWindow(self.app)
            
            elif window_type == WindowType.ACTIVITY_MONITOR:
                from fichero.windows.activity_monitor import ActivityMonitorWindow
                window = ActivityMonitorWindow(self.app)
            
            elif window_type == WindowType.PLANS:
                from fichero.windows.plans import PlansWindow
                window = PlansWindow(self.app)
            
            elif window_type == WindowType.PROMPTS:
                from fichero.windows.prompts import PromptsWindow
                window = PromptsWindow(self.app)
            
            elif window_type == WindowType.PROCESSING:
                from fichero.windows.processing import ProcessingWindow
                window = ProcessingWindow(self.app)
            
            else:
                logger.error(f"Unknown window type: {window_type.value}")
                return None
                
            # Add close callback to notify WindowViewManager when window is closed
            if window and hasattr(window, 'window') and window.window:
                self._add_close_callback(window.window, window_type)
                
            return window
                
        except Exception as e:
            logger.error(f"Failed to create desktop window {window_type.value}: {e}")
            return None
    
    def _add_close_callback(self, toga_window, window_type: WindowType):
        """Add close callback to window to update WindowViewManager state"""
        try:
            # Store original close handler if exists
            original_on_close = getattr(toga_window, 'on_close', None)
            
            def on_window_close(widget, **kwargs):
                try:
                    # Call original handler first if it exists
                    result = True
                    if original_on_close:
                        result = original_on_close(widget, **kwargs)
                    
                    # Remove from our tracking
                    if window_type in self.desktop_windows:
                        del self.desktop_windows[window_type]
                        logger.info(f"Desktop window removed from tracking on close: {window_type.value}")
                    
                    return result
                except Exception as e:
                    logger.error(f"Error in window close callback for {window_type.value}: {e}")
                    return True
            
            # Set the close handler
            toga_window.on_close = on_window_close
            logger.debug(f"Close callback added for {window_type.value}")
            
        except Exception as e:
            logger.warning(f"Failed to add close callback for {window_type.value}: {e}")
    
    def _show_mobile_view(self, window_type: WindowType, **kwargs) -> bool:
        """Show a view in the main window on mobile"""
        try:
            if not self.mobile_view_manager:
                logger.error("Mobile view manager not set")
                return False
            
            # Create mobile view
            mobile_view = self._create_mobile_view(window_type, **kwargs)
            if mobile_view:
                # Show view in main window
                return self.mobile_view_manager.show_view(window_type, mobile_view)
            else:
                logger.error(f"Failed to create mobile view: {window_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to show mobile view {window_type.value}: {e}")
            return False
    
    def _create_mobile_view(self, window_type: WindowType, **kwargs):
        """Create a mobile view for the specified type - no back callback needed as toolbar handles it"""
        try:
            if window_type == WindowType.SETTINGS:
                from fichero.windows.settings.mobile_view import SettingsMobileView
                return SettingsMobileView(self.app)
            
            elif window_type == WindowType.ABOUT:
                from fichero.windows.about.mobile_view import AboutMobileView
                return AboutMobileView(self.app)
            
            elif window_type == WindowType.ACTIVITY_MONITOR:
                from fichero.windows.activity_monitor.mobile_view import ActivityMonitorMobileView
                return ActivityMonitorMobileView(self.app)
            
            elif window_type == WindowType.PLANS:
                from fichero.windows.plans.mobile_view import PlansMobileView
                return PlansMobileView(self.app)
            
            elif window_type == WindowType.PROMPTS:
                from fichero.windows.prompts.mobile_view import PromptsMobileView
                return PromptsMobileView(self.app)
            
            elif window_type == WindowType.PROCESSING:
                from fichero.windows.processing.mobile_view import ProcessingMobileView
                return ProcessingMobileView(self.app)
            
            else:
                logger.error(f"Unknown view type: {window_type.value}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create mobile view {window_type.value}: {e}")
            return None
    
    def close_window_or_view(self, window_type: WindowType) -> bool:
        """Close a window or view"""
        try:
            if self.is_mobile:
                if self.mobile_view_manager:
                    return self.mobile_view_manager.close_view(window_type)
                return False
            else:
                window = self.desktop_windows.get(window_type)
                if window:
                    window.close()
                    del self.desktop_windows[window_type]
                    logger.info(f"Desktop window closed: {window_type.value}")
                    return True
                return False
                
        except Exception as e:
            logger.error(f"Failed to close {window_type.value}: {e}")
            return False
    
    def close_all_windows_or_views(self):
        """Close all windows or views"""
        try:
            if self.is_mobile:
                if self.mobile_view_manager:
                    self.mobile_view_manager.close_all_views()
            else:
                for window_type, window in list(self.desktop_windows.items()):
                    try:
                        window.close()
                    except Exception as e:
                        logger.warning(f"Error closing window {window_type.value}: {e}")
                self.desktop_windows.clear()
                
            logger.info("All windows/views closed")
            
        except Exception as e:
            logger.error(f"Failed to close all windows/views: {e}")
    
    def is_window_or_view_open(self, window_type: WindowType) -> bool:
        """Check if a window or view is currently open"""
        try:
            if self.is_mobile:
                if self.mobile_view_manager:
                    return self.mobile_view_manager.is_view_open(window_type)
                return False
            else:
                window = self.desktop_windows.get(window_type)
                return window is not None and not window.closed
                
        except Exception as e:
            logger.error(f"Failed to check if {window_type.value} is open: {e}")
            return False
    
    def get_platform_info(self) -> Dict[str, Any]:
        """Get platform and configuration information"""
        return {
            'is_mobile': self.is_mobile,
            'desktop_windows_count': len(self.desktop_windows),
            'mobile_view_manager': self.mobile_view_manager is not None,
            'open_windows': [wt.value for wt in self.desktop_windows.keys()] if not self.is_mobile else [],
            'mobile_views_available': self.mobile_view_manager is not None
        }


class MobileViewManager:
    """
    Manages views within the main window for mobile platforms.
    
    Handles navigation, back button behavior, and view stacking.
    """
    
    def __init__(self, main_window_content_container):
        """Initialize mobile view manager"""
        self.content_container = main_window_content_container
        
        # View stack for navigation
        self.view_stack: list = []
        self.current_view: Optional[Any] = None
        self.current_view_type: Optional[WindowType] = None
        
        # View instances
        self.view_instances: Dict[WindowType, Any] = {}
        
        logger.info("MobileViewManager initialized")
    
    def show_view(self, view_type: WindowType, view_instance) -> bool:
        """Show a view in the main window"""
        try:
            # Store current view in stack if we have one
            if self.current_view and self.current_view_type:
                self.view_stack.append((self.current_view_type, self.current_view))
            
            # Set new view
            self.current_view = view_instance
            self.current_view_type = view_type
            self.view_instances[view_type] = view_instance
            
            # Create view content
            if hasattr(view_instance, 'create'):
                view_content = view_instance.create()
            elif hasattr(view_instance, 'get_container'):
                view_content = view_instance.get_container()
            else:
                view_content = view_instance
            
            # Create mobile view with top toolbar
            mobile_view_container = self._create_mobile_view_container(view_type, view_content)
            
            # Update main window content
            self.content_container.clear()
            self.content_container.add(mobile_view_container)
            
            # Trigger view show if available
            if hasattr(view_instance, 'show'):
                view_instance.show()
            
            logger.info(f"Mobile view shown: {view_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to show mobile view {view_type.value}: {e}")
            return False
    
    def _create_mobile_view_container(self, view_type: WindowType, view_content):
        """Create a mobile view container with top toolbar"""
        from toga.style import Pack
        from toga.constants import COLUMN
        
        # Main container
        container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Top toolbar with back button and title
        top_toolbar = self._create_mobile_top_toolbar(view_type)
        container.add(top_toolbar)
        
        # View content
        container.add(view_content)
        
        return container
    
    def _create_mobile_top_toolbar(self, view_type: WindowType):
        """Create top toolbar with back button and title using proper icons"""
        return self._create_simple_mobile_toolbar(view_type)
    

    def _create_simple_mobile_toolbar(self, view_type: WindowType):
        """Create a mobile toolbar with proper chevron icon, centered title, 50px height, and all-around borders"""
        from toga.style import Pack
        from toga.constants import ROW, COLUMN
        from fichero.windows.main.styling.color_constants import TOOLBAR_BORDER, VIEW_BACKGROUND
        
        # Main toolbar container with borders on all sides
        toolbar_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                height=50,  # Fixed 50px height
                margin=(0, 0),
                padding=(0, 0),
                background_color=VIEW_BACKGROUND  # White background
            )
        )
        
        # Top border
        top_border = toga.Box(
            style=Pack(
                background_color=TOOLBAR_BORDER,
                height=1,
                margin=(0, 0)
            )
        )
        toolbar_container.add(top_border)
        
        # Content wrapper with left and right borders
        content_wrapper = toga.Box(
            style=Pack(
                direction=ROW,
                flex=1,
                margin=(0, 0),
                padding=(0, 0)
            )
        )
        
        # Left border
        left_border = toga.Box(
            style=Pack(
                background_color=TOOLBAR_BORDER,
                width=1,
                margin=(0, 0)
            )
        )
        content_wrapper.add(left_border)
        
        # Main content area
        toolbar = toga.Box(
            style=Pack(
                direction=ROW,
                padding=(8, 12),  # Match base toolbar padding
                flex=1
            )
        )
        
        # Back button with proper chevron icon (match toolbar sizing)
        back_button = toga.Button(
            "",  # No text - icon only
            on_press=self._on_back_pressed,
            style=Pack(
                width=22,
                height=22,
                margin=(4, 16, 4, 0)
            )
        )
        
        # Try to set the chevron icon
        try:
            back_button.icon = toga.Icon("resources/icons/toolbar/chevron.left@10x.png")
        except Exception as e:
            logger.warning(f"Could not load chevron icon: {e}")
            # Fallback to Unicode chevron
            back_button.text = "‹"
        
        toolbar.add(back_button)
        
        # Title in center
        title_map = {
            WindowType.SETTINGS: "Settings",
            WindowType.ABOUT: "About Fichero",
            WindowType.ACTIVITY_MONITOR: "Activity Monitor", 
            WindowType.PLANS: "Plans",
            WindowType.PROMPTS: "Prompts",
            WindowType.PROCESSING: "Processing"
        }
        
        title = toga.Label(
            title_map.get(view_type, view_type.value.title()),
            style=Pack(
                font_size=18,
                font_weight="bold",
                flex=1,
                text_align="center"
            )
        )
        toolbar.add(title)
        
        # Right spacer to balance the back button  
        spacer = toga.Box(style=Pack(width=38))  # Match back button + margin width
        toolbar.add(spacer)
        
        content_wrapper.add(toolbar)
        
        # Right border
        right_border = toga.Box(
            style=Pack(
                background_color=TOOLBAR_BORDER,
                width=1,
                margin=(0, 0)
            )
        )
        content_wrapper.add(right_border)
        
        toolbar_container.add(content_wrapper)
        
        # Bottom border
        bottom_border = toga.Box(
            style=Pack(
                background_color=TOOLBAR_BORDER,
                height=1,
                margin=(0, 0)
            )
        )
        toolbar_container.add(bottom_border)
        
        return toolbar_container
    
    def _on_back_pressed(self, widget):
        """Handle back button press"""
        self.go_back()
    
    def go_back(self) -> bool:
        """Navigate back to previous view"""
        try:
            if self.view_stack:
                # Get previous view
                previous_view_type, previous_view = self.view_stack.pop()
                
                # Hide current view if available
                if self.current_view and hasattr(self.current_view, 'hide'):
                    self.current_view.hide()
                
                # Set previous view as current
                self.current_view = previous_view
                self.current_view_type = previous_view_type
                
                # Show previous view
                if hasattr(previous_view, 'create'):
                    view_content = previous_view.create()
                elif hasattr(previous_view, 'get_container'):
                    view_content = previous_view.get_container()
                else:
                    view_content = previous_view
                
                mobile_view_container = self._create_mobile_view_container(previous_view_type, view_content)
                
                self.content_container.clear()
                self.content_container.add(mobile_view_container)
                
                # Trigger view show if available
                if hasattr(previous_view, 'show'):
                    previous_view.show()
                
                logger.info(f"Navigated back to: {previous_view_type.value}")
                return True
            else:
                # No previous view - go back to library/collection view
                self._go_back_to_library()
                return True
                
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
            return False
    
    def _go_back_to_library(self):
        """Go back to the main library/collection view"""
        try:
            # Clear current view
            if self.current_view and hasattr(self.current_view, 'hide'):
                self.current_view.hide()
            
            self.current_view = None
            self.current_view_type = None
            
            # Clear the view stack
            self.view_stack.clear()
            
            # Restore the original collection management view content
            self.content_container.clear()
            
            # Create and add the collection management view
            from .views.collection_management_view import CollectionManagementView
            collection_view = CollectionManagementView(self.content_container.app)
            collection_container = collection_view.get_container()
            self.content_container.add(collection_container)
            
            logger.info("Navigating back to library view")
            
        except Exception as e:
            logger.error(f"Failed to go back to library: {e}")
    
    def close_view(self, view_type: WindowType) -> bool:
        """Close a specific view"""
        try:
            if self.current_view_type == view_type:
                return self.go_back()
            else:
                # Remove from view instances
                if view_type in self.view_instances:
                    view = self.view_instances[view_type]
                    if hasattr(view, 'hide'):
                        view.hide()
                    del self.view_instances[view_type]
                return True
                
        except Exception as e:
            logger.error(f"Failed to close view {view_type.value}: {e}")
            return False
    
    def close_all_views(self):
        """Close all views and return to library"""
        try:
            # Hide all views
            for view in self.view_instances.values():
                if hasattr(view, 'hide'):
                    view.hide()
            
            # Clear state
            self.view_instances.clear()
            self.view_stack.clear()
            self.current_view = None
            self.current_view_type = None
            
            # Go back to library
            self._go_back_to_library()
            
            logger.info("All mobile views closed")
            
        except Exception as e:
            logger.error(f"Failed to close all views: {e}")
    
    def is_view_open(self, view_type: WindowType) -> bool:
        """Check if a view is currently open"""
        return view_type in self.view_instances
    
    def can_go_back(self) -> bool:
        """Check if we can navigate back"""
        return len(self.view_stack) > 0 or self.current_view is not None 