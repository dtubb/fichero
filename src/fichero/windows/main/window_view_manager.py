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
from toga.style import Pack
from toga.constants import COLUMN

logger = logging.getLogger(__name__)


class WindowType(Enum):
    """Types of windows/views that can be opened"""
    SETTINGS = "settings"
    ABOUT = "about"
    ACTIVITY_MONITOR = "activity_monitor"
    PLANS = "plans"
    PROMPTS = "prompts"
    PROCESSING = "processing"
    PREVIEW = "preview"
    ADD_DIALOG = "add_dialog"


class WindowViewManager:
    """
    Unified manager for windows and views.
    
    Handles both desktop (separate windows) and mobile (main window views) modes.
    This is the single source of truth for all window/view operations.
    """
    
    def __init__(self, app):
        """Initialize the window/view manager"""
        self.app = app
        
        # Desktop windows (separate Toga windows)
        self.desktop_windows: Dict[WindowType, Any] = {}
        
        # Mobile view manager (for main window)
        self.mobile_view_manager: Optional['MobileViewManager'] = None
        
        # Callbacks for mobile navigation
        self.on_mobile_view_changed: Optional[Callable] = None
        
        logger.info(f"WindowViewManager initialized for {'mobile' if self.is_mobile else 'desktop'} platform")
    
    @property
    def is_mobile(self) -> bool:
        """Get current mobile status from app"""
        if hasattr(self.app, 'is_mobile'):
            return self.app.is_mobile
        else:
            # Fallback to platform detection if app property not available
            try:
                import toga.platform
                current_platform = toga.platform.current_platform
                is_mobile = current_platform in ['iOS', 'android']
                logger.debug(f"Fallback platform detection: {current_platform} -> mobile={is_mobile}")
                return is_mobile
            except Exception as e:
                logger.error(f"Platform detection failed: {e}")
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
            
            elif window_type == WindowType.ADD_DIALOG:
                from fichero.windows.add import AddWindow
                option_id = kwargs.get('option_id')
                window = AddWindow(self.app, option_id=option_id)
            
            elif window_type == WindowType.PREVIEW:
                from fichero.windows.preview import PreviewWindow
                window = PreviewWindow(self.app)
            
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
            logger.info(f"Attempting to show mobile view: {window_type.value}")
            logger.info(f"Mobile view manager available: {self.mobile_view_manager is not None}")
            
            if not self.mobile_view_manager:
                logger.error("Mobile view manager not set - cannot show mobile view")
                return False
            
            # Create mobile view
            logger.info(f"Creating mobile view for: {window_type.value}")
            mobile_view = self._create_mobile_view(window_type, **kwargs)
            
            if mobile_view:
                logger.info(f"Mobile view created successfully for: {window_type.value}")
                # Show view in main window
                return self.mobile_view_manager.show_view(window_type, mobile_view)
            else:
                logger.error(f"Failed to create mobile view: {window_type.value}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to show mobile view {window_type.value}: {e}")
            return False
    
    def _create_mobile_view(self, window_type: WindowType, **kwargs):
        """Create a mobile view based on the window type"""
        try:
            logger.info(f"Creating mobile view for window type: {window_type}")

            if window_type == WindowType.ABOUT:
                logger.info("Importing AboutMobileView")
                try:
                    from fichero.windows.about.mobile_view import AboutMobileView
                    logger.info("AboutMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import AboutMobileView: {e}")
                    return None
                
                logger.info("Creating AboutMobileView instance")
                try:
                    mobile_view = AboutMobileView(self.app)
                    logger.info("AboutMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create AboutMobileView instance: {e}")
                    return None

            elif window_type == WindowType.ACTIVITY_MONITOR:
                logger.info("Importing ActivityMobileView")
                try:
                    from fichero.windows.activity_monitor.mobile_view import ActivityMobileView
                    logger.info("ActivityMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import ActivityMobileView: {e}")
                    return None
                
                logger.info("Creating ActivityMobileView instance")
                try:
                    mobile_view = ActivityMobileView(self.app)
                    logger.info("ActivityMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create ActivityMobileView instance: {e}")
                    return None

            elif window_type == WindowType.SETTINGS:
                logger.info("Importing SettingsMobileView")
                try:
                    from fichero.windows.settings.mobile_view import SettingsMobileView
                    logger.info("SettingsMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import SettingsMobileView: {e}")
                    return None
                
                logger.info("Creating SettingsMobileView instance")
                try:
                    mobile_view = SettingsMobileView(self.app)
                    logger.info("SettingsMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create SettingsMobileView instance: {e}")
                    return None

            elif window_type == WindowType.PLANS:
                logger.info("Importing PlansMobileView")
                try:
                    from fichero.windows.plans.mobile_view import PlansMobileView
                    logger.info("PlansMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import PlansMobileView: {e}")
                    return None
                
                logger.info("Creating PlansMobileView instance")
                try:
                    mobile_view = PlansMobileView(self.app)
                    logger.info("PlansMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create PlansMobileView instance: {e}")
                    return None

            elif window_type == WindowType.PROMPTS:
                logger.info("Importing PromptsMobileView")
                try:
                    from fichero.windows.prompts.mobile_view import PromptsMobileView
                    logger.info("PromptsMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import PromptsMobileView: {e}")
                    return None
                
                logger.info("Creating PromptsMobileView instance")
                try:
                    mobile_view = PromptsMobileView(self.app)
                    logger.info("PromptsMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create PromptsMobileView instance: {e}")
                    return None

            elif window_type == WindowType.PROCESSING:
                logger.info("Importing ProcessingMobileView")
                try:
                    from fichero.windows.processing.mobile_view import ProcessingMobileView
                    logger.info("ProcessingMobileView imported successfully")
                except Exception as e:
                    logger.error(f"Failed to import ProcessingMobileView: {e}")
                    return None
                
                logger.info("Creating ProcessingMobileView instance")
                try:
                    mobile_view = ProcessingMobileView(self.app)
                    logger.info("ProcessingMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create ProcessingMobileView instance: {e}")
                    return None
            
            elif window_type == WindowType.ADD_DIALOG:
                logger.info("Creating MobileAddView for mobile")
                try:
                    from fichero.windows.add.mobile_add_view import MobileAddView
                    logger.info("MobileAddView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import MobileAddView: {e}")
                    return None
                
                logger.info("Creating MobileAddView instance")
                try:
                    # For mobile, use MobileAddView
                    option_id = kwargs.get('option_id')
                    mobile_view = MobileAddView(
                        self.app,
                        on_content_added=self._handle_content_added,
                        option_id=option_id
                    )
                    logger.info("MobileAddView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create MobileAddView instance: {e}")
                    return None
            
            else:
                logger.warning(f"Unsupported mobile view type: {window_type}")
                return None
                
        except Exception as e:
            logger.error(f"Failed to create mobile view: {e}")
            return None
    
    def _handle_mobile_add_option(self, option_id: str):
        """Handle add option selection on mobile"""
        try:
            logger.info(f"Mobile add option selected: {option_id}")
            
            # Create the appropriate add view based on option
            if option_id == 'url':
                from fichero.windows.add.views.url_view import URLAddView
                view = URLAddView(
                    self.app, 
                    on_back=self.mobile_view_manager.go_back,
                    on_content_added=self._handle_content_added
                )
                self.mobile_view_manager.show_view(view)
                
            elif option_id == 'website':
                from fichero.windows.add.views.website_view import WebsiteAddView
                view = WebsiteAddView(
                    self.app, 
                    on_back=self.mobile_view_manager.go_back,
                    on_content_added=self._handle_content_added
                )
                self.mobile_view_manager.show_view(view)
                
            elif option_id == 'camera':
                from fichero.windows.add.views.camera_view import CameraAddView
                view = CameraAddView(
                    self.app, 
                    on_back=self.mobile_view_manager.go_back,
                    on_content_added=self._handle_content_added
                )
                self.mobile_view_manager.show_view(view)
                
            else:
                logger.warning(f"Unsupported add option: {option_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle mobile add option: {e}")
    
    def _handle_content_added(self, content_info=None):
        """Handle when content is successfully added"""
        try:
            logger.info("Content added successfully, returning to main view")
            # Return to the main view after adding content
            self.mobile_view_manager.go_back()
        except Exception as e:
            logger.error(f"Failed to handle content added: {e}")
    
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
    
    def __init__(self, main_window_content_container, app):
        """Initialize mobile view manager"""
        self.content_container = main_window_content_container
        self.app = app  # Store app reference for creating views
        
        # View stack for navigation
        self.view_stack: list = []
        self.current_view: Optional[Any] = None
        self.current_view_type: Optional[WindowType] = None
        
        # View instances
        self.view_instances: Dict[WindowType, Any] = {}
        
        # Store the original collection view to prevent duplicates
        self.original_collection_view = None
        
        # Store the main window wrapper to access its content
        self.main_window = None
        if hasattr(self.app, 'main_window_wrapper'):
            self.main_window = self.app.main_window_wrapper
        
        logger.info("MobileViewManager initialized")
    
    def show_view(self, view_type: WindowType, view_instance) -> bool:
        """Show a view as an overlay in the main window"""
        try:
            # Store current view in stack if we have one
            if self.current_view and self.current_view_type:
                self.view_stack.append((self.current_view_type, self.current_view))
            
            # Set new view
            self.current_view = view_instance
            self.current_view_type = view_type
            self.view_instances[view_type] = view_instance
            
            # Mobile navigation is now connected automatically when toolbars are set
            
            # Create view content
            if hasattr(view_instance, 'create'):
                view_content = view_instance.create()
            elif hasattr(view_instance, 'get_container'):
                view_content = view_instance.get_container()
            else:
                view_content = view_instance
            
            # Store the original main window content before overlaying
            if not hasattr(self, 'original_main_content'):
                self.original_main_content = self.main_window.window.content
            
            # Create overlay that covers the entire window
            overlay_content = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )
            overlay_content.add(view_content)
            
            # Replace main window content with overlay
            self.main_window.window.content = overlay_content
            
            # Trigger view show if available
            if hasattr(view_instance, 'show'):
                view_instance.show()
            
            logger.info(f"Mobile view shown as overlay: {view_type.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to show mobile view {view_type.value}: {e}")
            return False
    
    def _create_mobile_view_container(self, view_type: WindowType, view_content):
        """Create a mobile view container - views now handle their own toolbars"""
        # Since our mobile views now extend BaseView and handle their own toolbars,
        # we just return the view content directly
        return view_content
    
    # Old toolbar creation methods removed - mobile views now handle their own toolbars using BaseView
    
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
        """Go back to the main library/collection view by restoring original content"""
        try:
            # Clear current view
            if self.current_view and hasattr(self.current_view, 'hide'):
                self.current_view.hide()
            
            self.current_view = None
            self.current_view_type = None
            
            # Clear the view stack
            self.view_stack.clear()
            
            # Restore the original main window content
            if hasattr(self, 'original_main_content') and self.original_main_content:
                self.main_window.window.content = self.original_main_content
                logger.info("✅ Restored original main window content")
            else:
                logger.error("❌ CRITICAL: No original main content to restore")
                raise ValueError("No original main content available")
            
        except Exception as e:
            logger.error(f"❌ CRITICAL: Failed to restore original content: {e}")
            import traceback
            traceback.print_exc()
            raise  # Don't hide the error - let it bubble up
    
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