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
    ADD_URL = "add_url"
    ADD_WEBSITE = "add_website"
    ADD_FILE = "add_file"
    ADD_FOLDER = "add_folder"
    ADD_CAMERA = "add_camera"


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
        
        # Mobile modal overlay state
        self._current_modal_overlay: Optional[toga.Box] = None
        self._current_modal_view = None
        
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
        """Legacy method - no longer needed with modal overlay system"""
        logger.debug("set_mobile_view_manager called but mobile_view_manager is deprecated")
    
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
        """Show a modal view on mobile using navigation system"""
        try:
            logger.info(f"Showing mobile modal view: {window_type.value}")

            # For add views, register with NavigationController first
            if window_type.value.startswith('add'):
                self._register_add_view_with_navigation(window_type)

            # Create the mobile view
            mobile_view = self._create_mobile_view(window_type, **kwargs)
            if not mobile_view:
                logger.error(f"Failed to create mobile view: {window_type.value}")
                return False

            # Get main window to show modal overlay
            main_window = getattr(self.app, 'main_window_wrapper', None)
            if not main_window:
                logger.error("Main window not available for modal view")
                return False

            # Show as modal overlay in main window
            return self._show_modal_overlay(mobile_view, window_type)

        except Exception as e:
            logger.error(f"Failed to show mobile modal view {window_type.value}: {e}")
            return False

    def _register_add_view_with_navigation(self, window_type: WindowType):
        """Register add view with NavigationController for proper back navigation"""
        try:
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                navigation_controller = self.app.view_integration.get_navigation_controller()
                if navigation_controller:
                    # Determine the add type based on window_type
                    add_type_map = {
                        'add_dialog': 'dialog',
                        'add_url': 'url',
                        'add_website': 'website',
                        'add_file': 'file',
                        'add_folder': 'folder',
                        'add_camera': 'camera'
                    }
                    add_type = add_type_map.get(window_type.value, 'dialog')

                    # Navigate to add using NavigationController
                    navigation_controller.navigate_to_add(add_type)
                    logger.info(f"Registered add view '{add_type}' with NavigationController")
                else:
                    logger.warning("NavigationController not available")
            else:
                logger.warning("ViewIntegration not available")
        except Exception as e:
            logger.error(f"Failed to register add view with navigation: {e}")

    def _show_modal_overlay(self, view, window_type: WindowType) -> bool:
        """Show a view as a modal overlay in the main window"""
        try:
            # For now, let's replace the main window content temporarily
            # This is a simple modal implementation - we can enhance it later
            main_window = self.app.main_window_wrapper
            if hasattr(main_window, 'main_container') and main_window.main_container:
                container = main_window.main_container

                # Store current content
                self._modal_previous_content = list(container.children)

                # Clear container and add modal view
                container.clear()
                container.add(view.container if hasattr(view, 'container') else view)

                logger.info(f"Modal view {window_type.value} shown in main window")
                return True
            else:
                logger.error("Cannot access main window container for modal")
                return False

        except Exception as e:
            logger.error(f"Failed to show modal overlay: {e}")
            return False

    def _close_modal_overlay(self) -> bool:
        """Close modal overlay and restore previous content"""
        try:
            main_window = self.app.main_window_wrapper
            if hasattr(main_window, 'main_container') and main_window.main_container:
                container = main_window.main_container

                # Restore previous content if we have it
                if hasattr(self, '_modal_previous_content') and self._modal_previous_content:
                    container.clear()
                    for child in self._modal_previous_content:
                        container.add(child)

                    # Clear stored content
                    self._modal_previous_content = None

                    logger.info("Modal overlay closed, content restored")
                    return True
                else:
                    logger.warning("No previous content to restore")
                    return False
            else:
                logger.error("Cannot access main window container to close modal")
                return False

        except Exception as e:
            logger.error(f"Failed to close modal overlay: {e}")
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
                logger.info("Importing ActivityMonitorMobileView")
                try:
                    from fichero.windows.activity_monitor.mobile_view import ActivityMonitorMobileView
                    logger.info("ActivityMonitorMobileView imported successfully")
                except ImportError as e:
                    logger.error(f"Failed to import ActivityMonitorMobileView: {e}")
                    return None

                logger.info("Creating ActivityMonitorMobileView instance")
                try:
                    mobile_view = ActivityMonitorMobileView(self.app)
                    logger.info("ActivityMonitorMobileView instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create ActivityMonitorMobileView instance: {e}")
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
                logger.info("ADD_DIALOG requested - using NavigationController")
                # Redirect to NavigationController for direct add navigation
                option_id = kwargs.get('option_id', 'url')  # Default to URL
                if hasattr(self.app, 'view_integration') and self.app.view_integration:
                    navigation_controller = self.app.view_integration.get_navigation_controller()
                    if navigation_controller:
                        add_type = option_id if option_id in ['url', 'website', 'file', 'folder', 'camera'] else 'url'
                        logger.info(f"Delegating to NavigationController add navigation: {add_type}")
                        navigation_controller.navigate_to_add(add_type)
                        return None  # NavigationController handles this
                logger.error("NavigationController not available for add dialog")
                return None

            elif window_type == WindowType.ADD_URL:
                logger.info("Creating URL Add View for mobile")
                try:
                    from fichero.windows.add.views.url_view import URLAddView
                    mobile_view = URLAddView(
                        self.app,
                        on_content_added=self._handle_content_added
                    )
                    logger.info("URL Add View instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create URL Add View instance: {e}")
                    return None

            elif window_type == WindowType.ADD_WEBSITE:
                logger.info("Creating Website Add View for mobile")
                try:
                    from fichero.windows.add.views.website_view import WebsiteAddView
                    mobile_view = WebsiteAddView(
                        self.app,
                        on_content_added=self._handle_content_added
                    )
                    logger.info("Website Add View instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create Website Add View instance: {e}")
                    return None

            elif window_type == WindowType.ADD_FILE:
                logger.info("Creating File Add View for mobile")
                try:
                    from fichero.windows.add.views.file_view import FileAddView
                    mobile_view = FileAddView(
                        self.app,
                        on_content_added=self._handle_content_added
                    )
                    logger.info("File Add View instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create File Add View instance: {e}")
                    return None

            elif window_type == WindowType.ADD_FOLDER:
                logger.info("Creating Folder Add View for mobile")
                try:
                    from fichero.windows.add.views.folder_view import FolderAddView
                    mobile_view = FolderAddView(
                        self.app,
                        on_content_added=self._handle_content_added
                    )
                    logger.info("Folder Add View instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create Folder Add View instance: {e}")
                    return None

            elif window_type == WindowType.ADD_CAMERA:
                logger.info("Creating Camera Add View for mobile")
                try:
                    from fichero.windows.add.views.camera_view import CameraAddView
                    mobile_view = CameraAddView(
                        self.app,
                        on_content_added=self._handle_content_added
                    )
                    logger.info("Camera Add View instance created successfully")
                    return mobile_view
                except Exception as e:
                    logger.error(f"Failed to create Camera Add View instance: {e}")
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
            
            # Create NavigationController callback for consistent navigation
            from fichero.shared.navigation.navigation_controller import NavigationController
            navigation_callback = NavigationController.create_back_handler(self.app)

            # Create the appropriate add view based on option
            if option_id == 'url':
                from fichero.windows.add.views.url_view import URLAddView
                view = URLAddView(
                    self.app,
                    on_back=navigation_callback,
                    on_content_added=self._handle_content_added
                )
                self._show_modal_overlay(view)

            elif option_id == 'website':
                from fichero.windows.add.views.website_view import WebsiteAddView
                view = WebsiteAddView(
                    self.app,
                    on_back=navigation_callback,
                    on_content_added=self._handle_content_added
                )
                self._show_modal_overlay(view)

            elif option_id == 'camera':
                from fichero.windows.add.views.camera_view import CameraAddView
                view = CameraAddView(
                    self.app,
                    on_back=navigation_callback,
                    on_content_added=self._handle_content_added
                )
                self._show_modal_overlay(view)
                
            else:
                logger.warning(f"Unsupported add option: {option_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle mobile add option: {e}")
    
    async def _handle_content_added(self, content_info=None):
        """Handle when content is successfully added"""
        try:
            logger.info(f"Content added successfully: {content_info}")

            # Connect to library backend to actually add the content
            if content_info and hasattr(self.app, 'library_manager') and self.app.library_manager:
                option_id = content_info.get('option_id')

                if option_id == 'file' and 'files' in content_info:
                    # Create a new collection for the selected files
                    files = content_info['files']
                    if files:
                        first_file = files[0]
                        # Create a collection name based on the first file's directory
                        collection_name = f"Files from {first_file.parent.name}"

                        # Create collection using library backend
                        collection_id = await self.app.library_manager.add_collection(
                            name=collection_name,
                            collection_type="local",
                            source_path=str(first_file.parent)
                        )

                        if collection_id:
                            # Add each file to the collection
                            for file_path in files:
                                await self.app.library_manager.add_item_to_collection(
                                    collection_id=collection_id,
                                    item_type="file",
                                    source=str(file_path),
                                    name=file_path.name,
                                    operation="link"
                                )
                            logger.info(f"Successfully added {len(files)} files to new collection: {collection_name}")

                elif option_id == 'folder' and 'folders' in content_info:
                    # Create a new collection for each selected folder
                    folders = content_info['folders']
                    for folder_path in folders:
                        collection_name = f"Folder: {folder_path.name}"

                        # Create collection using library backend
                        collection_id = await self.app.library_manager.add_collection(
                            name=collection_name,
                            collection_type="local",
                            source_path=str(folder_path)
                        )

                        if collection_id:
                            # Add the folder to the collection
                            await self.app.library_manager.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="folder",
                                source=str(folder_path),
                                name=folder_path.name,
                                operation="link"
                            )
                            logger.info(f"Successfully created collection from folder: {collection_name}")

            # Return to the main view after adding content using NavigationController
            from fichero.shared.navigation.navigation_controller import NavigationController
            back_handler = NavigationController.create_back_handler(self.app)
            back_handler()
        except Exception as e:
            logger.error(f"Failed to handle content added: {e}")

    def _handle_add_back(self):
        """Handle back navigation from specific add views using NavigationController"""
        try:
            logger.info("Navigating back from specific add view using NavigationController")
            # Use NavigationController for proper back navigation
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                navigation_controller = self.app.view_integration.get_navigation_controller()
                if navigation_controller:
                    navigation_controller.navigate_back()
                else:
                    logger.warning("NavigationController not available, falling back to modal close")
                    self._close_modal_overlay()
            else:
                logger.warning("ViewIntegration not available, falling back to modal close")
                self._close_modal_overlay()
        except Exception as e:
            logger.error(f"Failed to handle add back navigation: {e}")
    
    def close_window_or_view(self, window_type: WindowType) -> bool:
        """Close a window or view"""
        try:
            if self.is_mobile:
                return self._close_modal_overlay()
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
                self._close_modal_overlay()
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
                return self._current_modal_overlay is not None
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
            'mobile_modal_active': self._current_modal_overlay is not None,
            'open_windows': [wt.value for wt in self.desktop_windows.keys()] if not self.is_mobile else [],
            'mobile_modal_view': type(self._current_modal_view).__name__ if self._current_modal_view else None
        }

 