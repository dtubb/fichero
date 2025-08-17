"""
Refactored Main Window for Fichero

Uses modular view and toolbar architecture:
- ViewManager for navigation between views
- Separate desktop and mobile toolbars
- Modular view components (Collection, About, Preferences)
- Clean separation between desktop and mobile UI patterns
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
import asyncio
import logging
from typing import Optional

# Import platform detection
import toga.platform

# Import debug constants for easier development
from fichero.config.debug_constants import (
    get_debug_mobile_override, 
    get_debug_platform_override,
    get_debug_window_size,
    VERBOSE_UI_LOGGING
)

# Import our new modular components
from fichero.windows.main.views import ViewManager, ViewType, CollectionView
from fichero.windows.settings.mobile_view import SettingsMobileView as PreferencesView
from fichero.shared.toolbars import DesktopToolbar, MobileToolbar
from fichero.windows.main.command_manager import CommandManager

logger = logging.getLogger(__name__)


class MainWindow:
    """
    Refactored main window with modular architecture.
    
    Features:
    - ViewManager for clean navigation between views
    - Platform-specific toolbars (desktop commands vs mobile buttons)
    - Modular view components for maintainability
    - Shared code where possible, clean separation where needed
    """
    
    def __init__(self, app):
        """Initialize main window"""
        self.app = app
        self.window: Optional[toga.MainWindow] = None
        self.is_visible = False
        
        # Platform detection with debug overrides
        current_platform = toga.platform.current_platform
        debug_platform = get_debug_platform_override()
        debug_mobile = get_debug_mobile_override()
        
        # Determine platform flags
        if debug_platform == 'ios':
            self.is_ios = True
            self.is_android = False
            if VERBOSE_UI_LOGGING:
                logger.info("🐛 DEBUG: Forcing iOS behavior")
        elif debug_platform == 'android':
            self.is_ios = False
            self.is_android = True
            if VERBOSE_UI_LOGGING:
                logger.info("🐛 DEBUG: Forcing Android behavior")
        else:
            # Use actual platform
            self.is_ios = current_platform == 'iOS'
            self.is_android = current_platform == 'android'
        
        # Determine mobile mode
        if debug_mobile is not None:
            self.is_mobile = debug_mobile
            if VERBOSE_UI_LOGGING:
                mode = "mobile" if debug_mobile else "desktop"
                logger.info(f"🐛 DEBUG: Forcing {mode} UI mode")
        else:
            self.is_mobile = self.is_ios or self.is_android
        
        # Core components
        self.view_manager: Optional[ViewManager] = None
        self.toolbar: Optional[DesktopToolbar | MobileToolbar] = None
        self.command_manager: Optional[CommandManager] = None
        
        # UI containers
        self.main_container: Optional[toga.Box] = None
        self.content_container: Optional[toga.Box] = None
        
        # Views
        self.collection_view: Optional[CollectionView] = None
        self.about_view: Optional = None  # AboutMobileView from refactored components
        self.preferences_view: Optional[PreferencesView] = None
        
        # Log final configuration
        if VERBOSE_UI_LOGGING:
            logger.info(f"Main window initialized - Platform: {current_platform}, "
                       f"Mobile: {self.is_mobile}, iOS: {self.is_ios}, Android: {self.is_android}")
        else:
            logger.info(f"Main window initialized for platform: {current_platform}")
    
    def show(self):
        """Show the main window"""
        if self.window is None:
            self._create_window()
        
        if not self.is_visible:
            # Set up toolbar
            self._setup_toolbar()
            
            self.window.show()
            self.is_visible = True
            
            # Load initial view (collection view)
            if self.view_manager:
                self.view_manager.show_view(ViewType.COLLECTION)
                
                # Initialize collection view
                if self.collection_view:
                    asyncio.create_task(self.collection_view.initialize())
            
            logger.info("Main window shown")
    
    def hide(self):
        """Hide the main window"""
        if self.window and self.is_visible:
            self.window.hide()
            self.is_visible = False
            logger.info("Main window hidden")
    
    def close(self):
        """Close the main window"""
        if self.window:
            self.window.close()
            self.window = None
            self.is_visible = False
    
    def _create_window(self):
        """Create the main window with modular architecture"""
        try:
            # Create main window with appropriate sizing
            window_size = self._get_window_size()
            
            self.window = toga.MainWindow(
                title=self._get_window_title(),
                size=window_size,
                resizable=True,
                minimizable=True
            )
            
            # Set minimum window size
            self.window.min_size = (800, 600) if self.is_mobile else (1200, 800)
            
            # Create modular UI
            self._create_modular_ui()
            
            # Set up window close handler
            self.window.on_close = self._on_close
            
            logger.info("Main window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
            raise
    
    def _get_window_size(self) -> tuple:
        """Get appropriate window size based on platform"""
        # Check for debug window size override first
        debug_size = get_debug_window_size()
        if debug_size:
            if VERBOSE_UI_LOGGING:
                logger.info(f"🐛 DEBUG: Using window size override: {debug_size}")
            return debug_size
        
        # Use platform-appropriate sizes
        if self.is_mobile:
            if self.is_ios:
                # iPhone 12 mini portrait [[memory:5042213]]
                return (375, 812)
            elif self.is_android:
                # Android dimensions (Pixel 7: 412x915) - Portrait
                return (412, 915)
            else:
                # Generic mobile
                return (400, 800)
        else:
            # Desktop: use reasonable default
            return (1400, 900)
    
    def _get_window_title(self) -> str:
        """Get appropriate window title"""
        # Use empty title for iOS to remove redundant title bar
        if self.is_ios:
            return ""
        else:
            return getattr(self.app, 'formal_name', 'Fichero')
    
    def _create_modular_ui(self):
        """Create the modular UI structure"""
        # Main container
        self.main_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Use shared command manager (don't create duplicate)
        self.command_manager = getattr(self.app, 'command_manager', None)
        
        # Create view manager
        self.view_manager = ViewManager(
            app=self.app, 
            is_mobile=self.is_mobile
        )
        
        # Create view instances
        self._create_view_instances()
        
        # Create content container for views
        self.content_container = toga.Box(
            style=Pack(
                direction=COLUMN,
                flex=1
            )
        )
        
        # Set view manager container
        self.view_manager.set_container(self.content_container)
        
        # Create toolbar
        self._create_toolbar()
        
        # Layout containers based on platform
        self._layout_containers()
        
        # Set window content
        self.window.content = self.main_container
    
    def _create_view_instances(self):
        """Create instances of all views"""
        # Collection view - the main collection view with maximum code sharing
        from fichero.windows.main.views.collection_view_new import CollectionView
        self.collection_view = CollectionView(
            app=self.app,
            is_mobile=self.is_mobile
        )
        
        # Set up collection view callbacks
        self.collection_view.on_process_collection = self._on_process_collection
        self.collection_view.on_add_collection = self._on_add_collection
        
        # About view - always use the new refactored pixel-perfect version
        from fichero.windows.about import AboutMobileView
        self.about_view = AboutMobileView(
            app=self.app,
            on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
        )
        
        # Activity monitor view
        from fichero.windows.activity_monitor.mobile_view import ActivityMonitorMobileView
        self.activity_view = ActivityMonitorMobileView(
            app=self.app,
            on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
        )
        
        # Processing view (mobile only)
        if self.is_mobile:
            from fichero.windows.processing import ProcessingMobileView
            self.processing_view = ProcessingMobileView(
                app=self.app,
                on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
            )
        
        # Preferences view
        self.preferences_view = PreferencesView(
            app=self.app,
            on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
        )
        
        # Plans view - HIDDEN
        # from fichero.windows.plans.mobile_view import PlansMobileView
        # self.plans_view = PlansMobileView(
        #     app=self.app,
        #     on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
        # )
        
        # Prompts view - HIDDEN
        # from fichero.windows.prompts.mobile_view import PromptsMobileView
        # self.prompts_view = PromptsMobileView(
        #     app=self.app,
        #     on_back=lambda widget: self.view_manager.show_view(ViewType.COLLECTION)
        # )
        
        # Register views with view manager
        self.view_manager.register_view(ViewType.COLLECTION, self.collection_view)
        self.view_manager.register_view(ViewType.ACTIVITY, self.activity_view)
        if self.is_mobile and hasattr(self, 'processing_view'):
            self.view_manager.register_view(ViewType.PROCESSING, self.processing_view)
        # self.view_manager.register_view(ViewType.PLANS, self.plans_view)  # HIDDEN
        # self.view_manager.register_view(ViewType.PROMPTS, self.prompts_view)  # HIDDEN
        self.view_manager.register_view(ViewType.ABOUT, self.about_view)
        self.view_manager.register_view(ViewType.PREFERENCES, self.preferences_view)
        
        # Set up view change callback
        self.view_manager.on_view_change = self._on_view_change
    
    def _create_toolbar(self):
        """Create platform-appropriate toolbar"""
        if self.is_mobile:
            self.toolbar = MobileToolbar(
                app=self.app,
                view_manager=self.view_manager,
                is_ios=self.is_ios
            )
            
            # Register action callbacks
            self.toolbar.register_action_callback("collection", self._on_show_collection)
            self.toolbar.register_action_callback("add", self._on_add_collection)
            # Process action is handled by the collection view now
            # self.toolbar.register_action_callback("process", self._on_process_collection)
            self.toolbar.register_action_callback("activity", self._on_show_activity)
            # self.toolbar.register_action_callback("plans", self._on_show_plans)  # HIDDEN
            # self.toolbar.register_action_callback("prompts", self._on_show_prompts)  # HIDDEN
            self.toolbar.register_action_callback("settings", self._on_show_preferences)
            self.toolbar.register_action_callback("about", self._on_show_about)
            
        else:
            self.toolbar = DesktopToolbar(
                app=self.app,
                view_manager=self.view_manager,
                command_manager=self.command_manager
            )
            
            # Desktop uses Toga commands automatically - no manual callbacks needed
            # Commands are handled by the CommandManager that's already added to app
    
    def _layout_containers(self):
        """Layout containers based on platform"""
        if self.is_mobile:
            # Both iOS and Android: Content + bottom footer toolbar
            self.main_container.add(self.content_container)
            toolbar_widget = self.toolbar.create_toolbar()
            self.main_container.add(toolbar_widget)
        else:
            # Desktop: Just content (toolbar is handled by window)
            self.main_container.add(self.content_container)
    
    def _setup_toolbar(self):
        """Set up toolbar for the window"""
        if not self.is_mobile and self.toolbar:
            # Desktop: Add commands to window toolbar
            self.toolbar.setup_for_window(self.window)
        # Mobile toolbars are already part of the UI layout
    
    # View navigation methods
    
    def _on_show_collection(self):
        """Show collection view"""
        if self.view_manager:
            self.view_manager.show_view(ViewType.COLLECTION)
    
    def _on_show_about(self):
        """Show about view"""
        if self.view_manager:
            self.view_manager.show_view(ViewType.ABOUT)
    
    def _on_show_activity(self):
        """Show activity monitor view"""
        if self.view_manager:
            self.view_manager.show_view(ViewType.ACTIVITY)
    
    def _on_show_preferences(self):
        """Show preferences view"""
        if self.view_manager:
            self.view_manager.show_view(ViewType.PREFERENCES)
    
    # def _on_show_plans(self):  # HIDDEN
    #     """Show plans view"""
    #     if self.view_manager:
    #         self.view_manager.show_view(ViewType.PLANS)
    
    # def _on_show_prompts(self):  # HIDDEN
    #     """Show prompts view"""
    #     if self.view_manager:
    #         self.view_manager.show_view(ViewType.PROMPTS)
    
    def _on_view_change(self, old_view: Optional[ViewType], new_view: ViewType):
        """Handle view change"""
        logger.info(f"View changed from {old_view} to {new_view}")
        
        # Update mobile toolbar back button visibility
        if self.is_mobile and self.toolbar:
            # Refresh toolbar to show/hide back button
            pass  # Could implement toolbar refresh here
    
    # Action callbacks
    
    def _on_process_collection(self, collection):
        """Handle process collection action"""
        try:
            logger.info(f"Process collection action triggered for: {collection.name}")
            # TODO: Implement process collection functionality
            # This would typically open the processing window with the collection
        except Exception as e:
            logger.error(f"Failed to handle process collection action: {e}")
    
    def _on_add_collection(self):
        """Handle add collection action"""
        try:
            logger.info("Add collection action triggered")
            # The collection view handles this internally now
        except Exception as e:
            logger.error(f"Failed to handle add collection action: {e}")
    
    def _on_close(self, widget):
        """Handle window close"""
        self.close()
        return True  # Allow close
    
    # Public interface methods
    
    def get_current_view(self) -> Optional[ViewType]:
        """Get the currently displayed view"""
        if self.view_manager:
            return self.view_manager.get_current_view()
        return None
    
    def navigate_to_view(self, view_type: ViewType):
        """Navigate to a specific view"""
        if self.view_manager:
            self.view_manager.show_view(view_type)
    
    def refresh_current_view(self):
        """Refresh the current view"""
        current_view = self.get_current_view()
        if current_view == ViewType.COLLECTION and self.collection_view:
            self.collection_view.refresh()
        # Other views don't need refresh currently
    
    def can_go_back(self) -> bool:
        """Check if we can navigate back (mobile)"""
        if self.view_manager:
            return self.view_manager.can_go_back()
        return False
    
    def go_back(self) -> bool:
        """Navigate back to previous view (mobile)"""
        if self.view_manager:
            return self.view_manager.go_back()
        return False 