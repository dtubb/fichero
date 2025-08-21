"""
Refactored Main Window for Fichero

Demonstrates how all the new components work together:
- Pane management (three-pane vs single-pane)
- Toolbar system integration
- View management
- Command integration
- Color system
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any

from .layout.pane_manager import PaneManager
from .commands.command_bridge import CommandBridge
from .command_manager import CommandManagerRefactored
from .views.collection_management_view import CollectionManagementView
from .views.collection_view import CollectionView
from .styling.color_constants import *

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
    """Refactored main window demonstrating the new architecture"""
    
    def __init__(self, app):
        """Initialize refactored main window"""
        self.app = app
        
        # Platform detection
        self.is_mobile = self._detect_mobile_platform()
        
        # Core components
        self.pane_manager: Optional[PaneManager] = None
        self.command_bridge: Optional[CommandBridge] = None
        self.command_manager: Optional[CommandManagerRefactored] = None
        
        # Window
        self.window: Optional[toga.MainWindow] = None
        
        # Initialize components
        self._initialize_components()
        
        # Create window
        self._create_window()
        
        # Set up mobile view manager integration
        self._setup_mobile_view_manager()
        
        logger.info("Refactored main window initialized successfully")
    
    def _detect_mobile_platform(self) -> bool:
        """Detect if running on mobile platform"""
        try:
            # Use the same detection logic as WindowViewManager for consistency
            from fichero.config.debug_constants import get_debug_mobile_override
            
            # Check debug override first
            debug_mobile = get_debug_mobile_override()
            if debug_mobile is not None:
                logger.info(f"MainWindow using debug mobile override: {debug_mobile}")
                return debug_mobile
            
            # Check app's mobile detection if available
            if hasattr(self.app, 'is_mobile'):
                return self.app.is_mobile
            
            # Fall back to platform detection
            import toga.platform
            current_platform = toga.platform.current_platform
            is_mobile = current_platform in ['iOS', 'android']
            
            logger.info(f"MainWindow platform detection: {current_platform} -> mobile={is_mobile}")
            return is_mobile
                
        except Exception as e:
            logger.error(f"Failed to detect platform: {e}")
            return False
    
    def _initialize_components(self):
        """Initialize all core components"""
        try:
            # Create pane manager
            self.pane_manager = PaneManager(self.app, self.is_mobile)
            
            # Create command bridge
            self.command_bridge = CommandBridge(self.app, self.pane_manager)
            
            # Use the command manager from the app (don't create a duplicate)
            self.command_manager = self.app.command_manager
            if self.command_manager:
                self.command_manager.set_command_bridge(self.command_bridge)
            
            # Register all commands
            self.command_bridge.register_all_commands()
            # Don't call add_to_app() again - already done in app.py
            
            logger.debug("All components initialized and integrated")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
    
    def _setup_component_integration(self):
        """Set up integration between components - simplified for now"""
        try:
            # Skip complex integration for now to get basic functionality working
            logger.debug("Component integration skipped for basic functionality")
            
        except Exception as e:
            logger.error(f"Failed to set up component integration: {e}")
    
    def _create_window(self):
        """Create the main window"""
        try:
            # Create main window
            self.window = toga.MainWindow(
                title="Fichero - Refactored",
                size=self._get_window_size()
            )
            
            # Commands are now handled by our custom toolbar system
            # Toga commands only appear in menu bar
            logger.debug("Using custom toolbar system - Toga commands in menu bar only")
            
            # Set up initial views after window is created
            self._setup_initial_views()
            
            logger.debug("Main window created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create main window: {e}")
    
    def _get_window_size(self) -> tuple:
        """Get appropriate window size for platform"""
        try:
            if self.is_mobile:
                # Mobile: smaller window
                return (400, 600)
            else:
                # Desktop: larger window for three-pane layout
                return (1200, 800)
                
        except Exception as e:
            logger.error(f"Failed to get window size: {e}")
            return (800, 600)
    
    def _setup_initial_views(self):
        """Set up initial views for the main window"""
        try:
            # Create functional views instead of just placeholders
            if not self.is_mobile:
                # Desktop: Set up three-pane layout with functional views
                self._setup_desktop_views()
            else:
                # Mobile: Set up single-pane layout
                self._setup_mobile_views()
                    
        except Exception as e:
            logger.error(f"Failed to set up initial views: {e}")
    
    def _setup_desktop_views(self):
        """Set up desktop three-pane layout with functional views"""
        try:
            # Import the views we need
            from .views.collection_management_view import CollectionManagementView
            from .views.collection_view import CollectionView
            
            logger.debug("Creating CollectionManagementView for left pane...")
            # Left pane: Collection management view
            collection_mgmt_view = CollectionManagementView(self.app)
            self.pane_manager.switch_to_view("collection_management", collection_mgmt_view, "left")
            
            logger.debug("Creating CollectionView for middle pane...")
            # Middle pane: Collection view (empty initially)
            collection_view = CollectionView(self.app, "", self.is_mobile)
            self.pane_manager.switch_to_view("collection", collection_view, "middle")
            
            # Right pane: Preview pane (shows when documents are selected)
            # This will be populated when a document is selected
            
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
        """Set up mobile single-pane layout"""
        try:
            from .views.mobile_view import MobileView
            mobile_view = MobileView(self.app)
            
            # Set the mobile view as the window content
            self.window.content = mobile_view.container
            logger.debug("Mobile view set up successfully")
                    
        except Exception as e:
            logger.error(f"Failed to set up mobile views: {e}")
    
    def _create_placeholder_views(self):
        """Create placeholder views for desktop panes"""
        try:
            # Create placeholder collection view for middle pane
            collection_view = CollectionView(self.app, "", self.is_mobile)
            self.pane_manager.switch_to_view("collection", collection_view, "middle")
            
            # Right pane will show preview when a document is selected
            # For now, it shows the default preview pane content
            
            logger.debug("Placeholder views created successfully")
            
        except Exception as e:
            logger.error(f"Failed to create placeholder views: {e}")
    
    # ===== CALLBACK HANDLERS =====
    
    def _on_section_selected(self, section_id: str, section_type: str):
        """Handle section selection in library pane"""
        try:
            logger.debug(f"Section selected: {section_id} of type {section_type}")
            
            # Update command context
            if section_type == "global":
                self.command_bridge.set_context(CommandContext.GLOBAL)
            elif section_type == "collections":
                self.command_bridge.set_context(CommandContext.LIBRARY)
            
            # Handle specific sections
            if section_id == "global_inbox":
                self._show_global_inbox()
            elif section_id == "tags":
                self._show_tags_view()
            elif section_id == "trash":
                self._show_trash_view()
                
        except Exception as e:
            logger.error(f"Failed to handle section selection: {e}")
    
    def _on_collection_selected(self, collection_id: str):
        """Handle collection selection"""
        try:
            logger.debug(f"Collection selected: {collection_id}")
            
            # Update command context
            self.command_bridge.set_context(CommandContext.COLLECTION)
            
            # Switch to collection view in middle pane
            collection_view = CollectionView(self.app, collection_id, self.is_mobile)
            self.pane_manager.switch_to_view("collection", collection_view, "middle")
            
        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")
    
    def _on_external_link_selected(self, link_id: str):
        """Handle external link selection"""
        try:
            logger.debug(f"External link selected: {link_id}")
            
            # This would typically open an external link or database
            # For now, just log the selection
            
        except Exception as e:
            logger.error(f"Failed to handle external link selection: {e}")
    
    def _on_toolbar_changed(self, toolbar_type: str):
        """Handle toolbar changes"""
        try:
            logger.debug(f"Toolbar changed to: {toolbar_type}")
            
            # Update command context based on toolbar type
            if toolbar_type == "library":
                self.command_bridge.set_context(CommandContext.LIBRARY)
            elif toolbar_type == "collection":
                self.command_bridge.set_context(CommandContext.COLLECTION)
            elif toolbar_type == "fiche":
                self.command_bridge.set_context(CommandContext.FICHE)
            elif toolbar_type == "preview":
                self.command_bridge.set_context(CommandContext.PREVIEW)
                
        except Exception as e:
            logger.error(f"Failed to handle toolbar change: {e}")
    
    def _on_add_collection(self, widget):
        """Handle add collection command"""
        try:
            logger.debug("Add collection command executed")
            
            # This would typically open a folder picker dialog
            # For now, just log the action
            
        except Exception as e:
            logger.error(f"Failed to handle add collection: {e}")
    
    def _on_library_settings(self, widget):
        """Handle library settings command"""
        try:
            logger.debug("Library settings command executed")
            
            # This would typically open library settings
            # For now, just log the action
            
        except Exception as e:
            logger.error(f"Failed to handle library settings: {e}")
    
    def _on_global_inbox(self, widget):
        """Handle global inbox command"""
        try:
            logger.debug("Global inbox command executed")
            
            # This would typically navigate to global inbox
            # For now, just log the action
            
        except Exception as e:
            logger.error(f"Failed to handle global inbox: {e}")
    
    def _show_global_inbox(self):
        """Show global inbox view"""
        try:
            logger.debug("Showing global inbox")
            # This would create and show the global inbox view
            
        except Exception as e:
            logger.error(f"Failed to show global inbox: {e}")
    
    def _show_tags_view(self):
        """Show tags view"""
        try:
            logger.debug("Showing tags view")
            # This would create and show the tags view
            
        except Exception as e:
            logger.error(f"Failed to show tags view: {e}")
    
    def _show_trash_view(self):
        """Show trash view"""
        try:
            logger.debug("Showing trash view")
            # This would create and show the trash view
            
        except Exception as e:
            logger.error(f"Failed to show trash view: {e}")
    
    # ===== PUBLIC METHODS =====
    
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
    
    def _setup_mobile_view_manager(self):
        """Set up mobile view manager integration if on mobile platform"""
        try:
            if self.is_mobile and hasattr(self.app, 'window_view_manager'):
                # For mobile mode, we need to create a different container structure
                # The current setup creates a three-pane desktop layout even in mobile mode
                
                # Create a simple mobile container to replace the three-pane layout
                mobile_container = self._create_mobile_container()
                if mobile_container:
                    # Replace window content with mobile container
                    self.window.content = mobile_container
                    
                    # Set up mobile view manager with this container
                    from .window_view_manager import MobileViewManager
                    mobile_view_manager = MobileViewManager(mobile_container)
                    
                    # Store the original collection view to prevent duplicates
                    try:
                        from .views.collection_management_view import CollectionManagementView
                        original_collection_view = CollectionManagementView(self.app)
                        mobile_view_manager.original_collection_view = original_collection_view
                        
                        # Replace the container content with the original view
                        mobile_container.clear()
                        mobile_container.add(original_collection_view.get_container())
                        logger.debug("Set original collection view in mobile view manager")
                    except Exception as e:
                        logger.warning(f"Could not set original collection view: {e}")
                    
                    self.app.window_view_manager.set_mobile_view_manager(mobile_view_manager)
                    logger.info("Mobile view manager integration set up with mobile container")
                else:
                    logger.warning("Could not create mobile container")
            else:
                logger.debug("Desktop mode - no mobile view manager needed")
                
        except Exception as e:
            logger.error(f"Failed to set up mobile view manager: {e}")
    
    def _create_mobile_container(self):
        """Create a mobile-friendly container"""
        try:
            from toga.style import Pack
            from toga.constants import COLUMN
            
            # Create a simple vertical container for mobile
            mobile_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1
                )
            )
            
            # Add default content - the collection management view
            try:
                # This will be replaced by the mobile view manager setup
                # Just add a placeholder for now
                placeholder = toga.Label(
                    "📱 Loading Library View...",
                    style=Pack(margin=20, font_size=18)
                )
                mobile_container.add(placeholder)
                logger.debug("Added placeholder to mobile container")
            except Exception as e:
                logger.warning(f"Could not add placeholder: {e}")
                # Add fallback placeholder
                placeholder = toga.Label(
                    "📱 Mobile Library View",
                    style=Pack(margin=20, font_size=18)
                )
                mobile_container.add(placeholder)
            
            return mobile_container
            
        except Exception as e:
            logger.error(f"Failed to create mobile container: {e}")
            return None
    
    def _get_mobile_content_container(self):
        """Get the mobile content container for view management"""
        try:
            if self.is_mobile and self.window:
                # For mobile mode, we want to get the main container that can be replaced
                # This should be the main content area of the window
                if hasattr(self.window, 'content') and self.window.content:
                    logger.debug(f"Found window content: {type(self.window.content)}")
                    return self.window.content
                else:
                    logger.warning("Window content not available yet")
                    return None
            return None
                
        except Exception as e:
            logger.error(f"Failed to get mobile content container: {e}")
            return None

    def get_window_info(self) -> Dict[str, Any]:
        """Get information about the main window"""
        return {
            'is_mobile': self.is_mobile,
            'pane_info': self.pane_manager.get_pane_info() if self.pane_manager else None,
            'command_info': self.command_manager.get_command_info() if self.command_manager else None
        } 