"""
Clean Main Window for Fichero

Simplified main window that uses the new LibraryManager integration.
Removes all old library management code.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any

from fichero.windows.main.commands.command_bridge import CommandBridge, CommandContext
from fichero.windows.main.layout.pane_manager import PaneManager
from fichero.windows.main.command_manager import CommandManagerRefactored
from fichero.windows.main.views.collection_management_view import CollectionManagementView
from fichero.windows.main.views.collection_view import CollectionView

logger = logging.getLogger(__name__)


class MainWindow:
    """Wrapper class that provides the interface the app expects"""
    
    def __init__(self, app):
        """Initialize main window wrapper"""
        self.app = app
        self.window: Optional[toga.MainWindow] = None
        self.is_visible = False
        
        # Create the refactored implementation
        self._refactored = MainWindowRefactored(app)
        
        # Expose the window property
        self.window = self._refactored.window
        
        logger.info("MainWindow wrapper initialized")
    
    def show(self):
        """Show the main window"""
        if self.window is None:
            self.window = self._refactored.window
        
        if not self.is_visible:
            self.window.show()
            self.is_visible = True
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
            self.is_visible = False
            logger.info("Main window closed")


class MainWindowRefactored:
    """Clean main window using LibraryManager integration"""
    
    def __init__(self, app):
        """Initialize clean main window"""
        self.app = app
        
        # Platform detection
        self.is_mobile = self._detect_mobile_platform()
        
        # Core components
        self.pane_manager: Optional[PaneManager] = None
        self.command_bridge: Optional[CommandBridge] = None
        self.command_manager: Optional[CommandManagerRefactored] = None
        
        # Window
        self.window: Optional[toga.MainWindow] = None
        
        # Cached views to avoid recreation
        self.cached_library_view: Optional = None
        self.cached_collection_views: Dict[str, Any] = {}  # collection_id -> view
        
        # Initialize components
        self._initialize_components()
        
        # Create window
        self._create_window()
        
        # Set up initial views
        self._setup_initial_views()
        
        # Set up mobile view manager for overlay views (settings, about, etc.)
        if self.is_mobile:
            self._setup_mobile_view_manager()
        
        logger.info("Clean main window initialized successfully")
    
    def _detect_mobile_platform(self) -> bool:
        """Detect if running on mobile platform"""
        return self.app.is_mobile
    
    def _initialize_components(self):
        """Initialize all core components"""
        try:
            # Create pane manager
            self.pane_manager = PaneManager(self.app, self.is_mobile)
            
            # Create command bridge
            self.command_bridge = CommandBridge(self.app, self.pane_manager)
            
            # Use the command manager from the app
            self.command_manager = self.app.command_manager
            if self.command_manager:
                self.command_manager.set_command_bridge(self.command_bridge)
            
            # Register all commands
            self.command_bridge.register_all_commands()
            
            logger.debug("All components initialized and integrated")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
    
    def _create_window(self):
        """Create the main window"""
        try:
            print("🔍 Creating Toga MainWindow...")
            # Create main window
            self.window = toga.MainWindow(
                title="Fichero",
                size=self._get_window_size()
            )
            print("✅ Toga MainWindow created successfully")
            
            # Set minimum window size
            if not self.is_mobile:
                self.window.min_size = (1000, 600)
            
            logger.debug("Main window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
    
    def _get_window_size(self) -> tuple:
        """Get appropriate window size for platform"""
        if self.is_mobile:
            # Mobile: portrait orientation
            return (375, 667)  # iPhone 12 mini dimensions
        else:
            # Desktop: three-pane layout
            return (1200, 800)
    
    def _setup_initial_views(self):
        """Set up initial views for the main window"""
        try:
            if not self.is_mobile:
                # Desktop: Set up three-pane layout
                self._setup_desktop_views()
            else:
                # Mobile: Set up single-pane layout
                self._setup_mobile_views()
                    
        except Exception as e:
            logger.error(f"Failed to set up initial views: {e}")
    
    def _setup_desktop_views(self):
        """Set up desktop three-pane layout"""
        try:
            print("🔍 Creating CollectionManagementView...")
            # Left pane: Collection management view
            collection_mgmt_view = CollectionManagementView(self.app, self.is_mobile)
            print("✅ CollectionManagementView created successfully")
            collection_mgmt_view.register_collection_callback(self._on_collection_selected)
            self.pane_manager.switch_to_view("collection_management", collection_mgmt_view, "left")
            
            # Middle pane: Collection view (empty initially)
            collection_view = CollectionView(self.app, "", self.is_mobile)
            collection_view.register_preview_callback(self._on_file_preview_requested)
            
            # Register back navigation callback
            if hasattr(collection_view, 'top_toolbar') and collection_view.top_toolbar:
                collection_view.top_toolbar.register_navigation_callbacks(
                    on_back_to_library=self._on_mobile_back_to_library,  # Even on desktop, use consistent callback
                    on_navigate_back=collection_view._on_navigate_back,
                    on_navigate_to_path=collection_view._on_navigate_to_path,
                    on_add_folder=collection_view._on_add_folder,
                    on_add_file=collection_view._on_add_file
                )
            
            self.pane_manager.switch_to_view("collection", collection_view, "middle")
            
            # Right pane: Preview pane (empty initially)
            from fichero.windows.main.layout.preview_pane import PreviewPane
            self.preview_pane = PreviewPane(self.app, self.is_mobile)
            self.pane_manager.switch_to_view("preview", self.preview_pane, "right")
            
            # Set the pane manager's main container as the window content
            main_container = self.pane_manager.get_main_container()
            if main_container:
                self.window.content = main_container
                logger.debug("Desktop three-pane layout set up successfully")
            else:
                logger.error("Failed to get main container from pane manager")
                
        except Exception as e:
            logger.error(f"Failed to set up desktop views: {e}")
    
    def _setup_mobile_views(self):
        """Set up mobile single-pane layout using same views as desktop"""
        try:
            print("🔍 Setting up mobile views using same container system...")
            
            # For mobile, start with the collection management view
            # Cache and reuse the library view
            if not self.cached_library_view:
                self.cached_library_view = CollectionManagementView(self.app, self.is_mobile)
                self.cached_library_view.register_collection_callback(self._on_collection_selected)
                logger.info("📚 Created and cached library view")
            else:
                logger.info("📚 Reusing cached library view")
            
            # In mobile mode, pane_manager should show single view at a time
            self.pane_manager.switch_to_view("collection_management", self.cached_library_view, "mobile")
            
            # Set the pane manager's main container as the window content
            main_container = self.pane_manager.get_main_container()
            if main_container:
                self.window.content = main_container
                print("✅ Mobile views set up successfully using same container system")
                logger.debug("Mobile views set up successfully using same container system")
            else:
                logger.error("Failed to get main container from pane manager for mobile")
                    
        except Exception as e:
            logger.error(f"Failed to set up mobile views: {e}")
    
    def _setup_mobile_view_manager(self):
        """Set up the mobile view manager for overlay views (settings, about, etc.)"""
        try:
            from fichero.windows.main.window_view_manager import MobileViewManager
            
            # Create a separate overlay container for mobile views
            # DO NOT use the main container - that breaks pane manager navigation
            overlay_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )
                
            # Create mobile view manager with the overlay container
            mobile_view_manager = MobileViewManager(overlay_container, self.app)
            
            # Store reference to main window and pane manager for proper restoration
            mobile_view_manager.main_window = self
            mobile_view_manager.pane_manager = self.pane_manager
            
            # Connect it to the app's window view manager
            if hasattr(self.app, 'window_view_manager'):
                self.app.window_view_manager.set_mobile_view_manager(mobile_view_manager)
                logger.info("Mobile view manager connected successfully")
            else:
                logger.warning("App doesn't have window_view_manager")
                
        except Exception as e:
            logger.error(f"Failed to set up mobile view manager: {e}")
    
    def _on_collection_selected(self, collection_id: str, collection_name: str = ""):
        """Handle collection selection"""
        try:
            logger.debug(f"Collection selected: {collection_id} - {collection_name}")
            
            # Update command context
            self.command_bridge.set_context(CommandContext.COLLECTION)
            
            # Cache and reuse collection views
            if collection_id not in self.cached_collection_views:
                collection_view = CollectionView(self.app, collection_name or collection_id, self.is_mobile)
                collection_view.set_collection_id(collection_id)
                collection_view.register_preview_callback(self._on_file_preview_requested)
                
                # Register navigation callbacks for BOTH desktop and mobile 
                if hasattr(collection_view, 'top_toolbar') and collection_view.top_toolbar:
                    logger.info(f"🔙 Registering navigation callbacks for collection: {collection_name} (mobile: {self.is_mobile})")
                    logger.info(f"🔙 Collection view has top_toolbar: {hasattr(collection_view, 'top_toolbar')}")
                    logger.info(f"🔙 Top toolbar is not None: {collection_view.top_toolbar is not None}")
                    logger.info(f"🔙 Top toolbar type: {type(collection_view.top_toolbar)}")
                    
                    collection_view.top_toolbar.register_navigation_callbacks(
                        on_back_to_library=self._on_mobile_back_to_library if self.is_mobile else self._on_back_to_library,
                        on_navigate_back=collection_view._on_navigate_back,  # Keep hierarchy navigation internal
                        on_navigate_to_path=collection_view._on_navigate_to_path,
                        on_add_folder=collection_view._on_add_folder,
                        on_add_file=collection_view._on_add_file
                    )
                    
                    logger.info("🔙 Navigation callbacks registered successfully")
                else:
                    logger.warning(f"🔙 Cannot register navigation callbacks - has_top_toolbar: {hasattr(collection_view, 'top_toolbar')}, toolbar_not_none: {hasattr(collection_view, 'top_toolbar') and collection_view.top_toolbar is not None}")
                
                self.cached_collection_views[collection_id] = collection_view
                logger.info(f"📁 Created and cached collection view: {collection_name or collection_id}")
            else:
                collection_view = self.cached_collection_views[collection_id]
                logger.info(f"📁 Reusing cached collection view: {collection_name or collection_id}")
            
            pane = "mobile" if self.is_mobile else "middle"
            self.pane_manager.switch_to_view("collection", collection_view, pane)
            
            logger.info(f"Successfully navigated to collection view: {collection_name or collection_id}")
            
        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")
    
    def _on_file_preview_requested(self, file_path: str, file_data: Dict[str, Any] = None):
        """Handle file preview requests from collection view"""
        try:
            logger.debug(f"File preview requested: {file_path}")
            
            # Prepare document data for preview pane
            if not file_data:
                from pathlib import Path
                path = Path(file_path)
                file_data = {
                    'name': path.name,
                    'type': path.suffix.lower().replace('.', '') if path.suffix else 'unknown',
                    'size': f"{path.stat().st_size} bytes" if path.exists() else 'Unknown',
                    'file_path': str(path),
                    'created_date': 'Unknown',
                    'modified_date': 'Unknown',
                    'author': 'Unknown',
                    'tags': [],
                    'processing_status': 'Not processed'
                }
            
            # Show preview - different behavior for mobile vs desktop
            if self.is_mobile:
                # Mobile: Push preview pane as new full-screen view
                from fichero.windows.main.layout.preview_pane import PreviewPane
                preview_pane = PreviewPane(self.app, self.is_mobile)
                preview_pane.show_file(file_path, file_data)
                
                # Register back navigation callback and update back label with collection name
                if hasattr(preview_pane, 'top_toolbar') and preview_pane.top_toolbar:
                    preview_pane.top_toolbar.register_callbacks(
                        on_back_to_fiche=self._on_mobile_back_to_collection
                    )
                    
                    # Update back label with collection name if available
                    collection_name = self._get_current_collection_name()
                    if collection_name and hasattr(preview_pane.top_toolbar, 'update_back_label'):
                        preview_pane.top_toolbar.update_back_label(collection_name)
                        logger.debug(f"Updated preview back label to: {collection_name}")
                
                # Switch to preview view in mobile mode (full screen)
                self.pane_manager.switch_to_view("preview", preview_pane, "mobile")
                logger.info(f"File preview shown in mobile full-screen: {file_path}")
            else:
                # Desktop: Show in right pane
                if hasattr(self, 'preview_pane') and self.preview_pane:
                    self.preview_pane.show_file(file_path, file_data)
                    logger.info(f"File preview shown in right pane: {file_path}")
                else:
                    logger.warning("Preview pane not available, falling back to separate window")
                    # Fallback to separate window if needed
                    if hasattr(self.app, 'show_preview'):
                        self.app.show_preview(file_path=file_path)
                    
        except Exception as e:
            logger.error(f"Failed to handle file preview request: {e}")
    
    def _get_current_collection_name(self) -> str:
        """Get the name of the currently active collection"""
        try:
            # Get the current collection view from the pane manager
            current_views = getattr(self.pane_manager, 'current_views', {})
            collection_view = current_views.get('collection')
            
            if collection_view and hasattr(collection_view, 'collection_name'):
                return collection_view.collection_name or "Collection"
            
            # Fallback: check mobile view if in mobile mode
            if self.is_mobile and hasattr(self.pane_manager, 'current_mobile_view'):
                current_mobile_view_name = getattr(self.pane_manager, 'current_mobile_view', '')
                if current_mobile_view_name == 'collection':
                    mobile_view = current_views.get('collection')
                    if mobile_view and hasattr(mobile_view, 'collection_name'):
                        return mobile_view.collection_name or "Collection"
            
            return "Collection"  # Default fallback
            
        except Exception as e:
            logger.error(f"Failed to get current collection name: {e}")
            return "Collection"
    
    def _on_back_to_library(self):
        """Handle desktop back navigation from collection to library"""
        try:
            logger.debug("Desktop back navigation: collection -> library")
            
            # For desktop, show the library view in the left pane
            if not self.cached_library_view:
                self.cached_library_view = CollectionManagementView(self.app, self.is_mobile)
                self.cached_library_view.register_collection_callback(self._on_collection_selected)
                logger.info("📚 Created cached library view for desktop navigation")
            
            # Update pane to show library view
            self.pane_manager.switch_to_view("collection_management", self.cached_library_view, "left")
            logger.info("Navigated back to library view on desktop")
            
            # Update command context
            self.command_bridge.set_context(CommandContext.LIBRARY)
            
        except Exception as e:
            logger.error(f"Failed to navigate back to library: {e}")
    
    def _on_mobile_back_to_library(self):
        """Handle mobile back navigation from collection to library"""
        try:
            logger.debug("Mobile back navigation: collection -> library")
            
            # Use pane manager's navigation stack
            if self.pane_manager.mobile_navigate_back():
                logger.info("Navigated back using mobile navigation stack")
            else:
                # Fallback: use cached library view
                logger.debug("No navigation stack, using cached library view")
                if not self.cached_library_view:
                    self.cached_library_view = CollectionManagementView(self.app, self.is_mobile)
                    self.cached_library_view.register_collection_callback(self._on_collection_selected)
                    logger.info("📚 Created cached library view for fallback")
                
                self.pane_manager.switch_to_view("collection_management", self.cached_library_view, "mobile")
                logger.info("Navigated back to library view (cached)")
            
        except Exception as e:
            logger.error(f"Failed to navigate back to library: {e}")
    
    def _on_mobile_back_to_collection(self):
        """Handle mobile back navigation from preview to collection"""
        try:
            logger.debug("Mobile back navigation: preview -> collection")
            
            # Use pane manager's navigation stack
            if self.pane_manager.mobile_navigate_back():
                logger.info("Navigated back to collection using mobile navigation stack")
            else:
                # Fallback: go back to library
                logger.debug("No navigation stack, going back to library")
                self._on_mobile_back_to_library()
            
        except Exception as e:
            logger.error(f"Failed to navigate back from preview: {e}")
    
    def show(self):
        """Show the main window"""
        try:
            if self.window:
                self.window.show()
                logger.info("Main window shown")
            
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")
    
    def close(self):
        """Close the main window"""
        try:
            if self.window:
                self.window.close()
                logger.info("Main window closed")
            
        except Exception as e:
            logger.error(f"Failed to close main window: {e}")
    
    def refresh(self):
        """Refresh the main window"""
        try:
            # Refresh all panes
            if self.pane_manager:
                self.pane_manager.refresh_all_panes()
            
            logger.debug("Main window refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh main window: {e}")
    
    def get_window_info(self) -> Dict[str, Any]:
        """Get window information for debugging"""
        return {
            "is_mobile": self.is_mobile,
            "has_pane_manager": self.pane_manager is not None,
            "has_command_bridge": self.command_bridge is not None,
            "has_command_manager": self.command_manager is not None,
            "window_size": self._get_window_size()
        }
