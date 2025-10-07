"""
Refactored Main Window for Fichero

Simple event-driven main window that listens to NavigationController events.
Replaces the complex NavigationManager/PaneManager system with clean event handling.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation, NavigationEvents
from fichero.shared.navigation.navigation_controller import NavigationController
from fichero.windows.main.views.library.library_view import LibraryView
from fichero.windows.main.views.collection.collection_view import CollectionView
from fichero.windows.main.views.output.output_view import OutputView

logger = logging.getLogger(__name__)


class MainWindow:
    """Simple event-driven main window"""

    def __init__(self, app):
        """Initialize main window with event-driven navigation"""
        self.app = app
        self.is_mobile = app.is_mobile

        # Window
        self.window: Optional[toga.Window] = None

        # Simple view containers
        self.main_container: Optional[toga.Box] = None
        self.current_view: Optional = None
        self.current_view_key: Optional[str] = None

        # Desktop layout containers
        self.left_pane: Optional[toga.Box] = None
        self.center_pane: Optional[toga.Box] = None
        self.right_pane: Optional[toga.Box] = None

        # Mobile layout container
        self.mobile_container: Optional[toga.Box] = None

        # Cached views to maintain state
        self.cached_library_view: Optional[LibraryView] = None
        self.cached_output_view: Optional[OutputView] = None

        # Collection view cache - key by collection_id to prevent duplicates
        self.cached_collection_views: Dict[str, CollectionView] = {}

        # Get NavigationController from app
        self.navigation_controller = self._get_navigation_controller()

        # Create window and layout
        self._create_window()
        self._create_layout()

        # Subscribe to navigation events
        self._subscribe_to_events()

        # Set up initial view
        self._show_initial_view()

        logger.info("Refactored main window initialized successfully")

    def _get_navigation_controller(self) -> Optional[NavigationController]:
        """Get NavigationController from app"""
        try:
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                return self.app.view_integration.get_navigation_controller()
            else:
                logger.warning("No view_integration found in app")
                return None
        except Exception as e:
            logger.error(f"Failed to get NavigationController: {e}")
            return None

    def _create_window(self):
        """Create the main window"""
        try:
            self.window = toga.MainWindow(
                title=self.app.formal_name,  # Set window title
                size=self._get_window_size()
            )

            if not self.is_mobile:
                self.window.min_size = (1000, 600)

            logger.debug("Main window created")

        except Exception as e:
            logger.error(f"Failed to create main window: {e}")

    def _get_window_size(self) -> tuple:
        """Get appropriate window size for platform"""
        if self.is_mobile:
            return (375, 667)  # iPhone dimensions
        else:
            return (1200, 800)  # Desktop dimensions

    def _create_layout(self):
        """Create layout containers"""
        try:
            if self.is_mobile:
                self._create_mobile_layout()
            else:
                self._create_desktop_layout()

            # Set window content
            if self.window and self.main_container:
                self.window.content = self.main_container
                logger.debug("Window content set")

        except Exception as e:
            logger.error(f"Failed to create layout: {e}")

    def _create_mobile_layout(self):
        """Create mobile single-pane layout"""
        try:
            self.mobile_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            self.main_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            self.main_container.add(self.mobile_container)
            logger.debug("Mobile layout created")

        except Exception as e:
            logger.error(f"Failed to create mobile layout: {e}")

    def _create_desktop_layout(self):
        """Create desktop three-pane layout"""
        try:
            # Left pane for library
            self.left_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=0,
                    width=300,
                    background_color="#FFFFFF"
                )
            )

            # Center pane for collection (same width as library pane)
            self.center_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=0,
                    width=300,
                    background_color="#FFFFFF"
                )
            )

            # Right pane for preview
            self.right_pane = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            # Main container with three panes
            self.main_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    flex=1,
                    background_color="#FFFFFF"
                )
            )

            self.main_container.add(self.left_pane)
            self.main_container.add(self.center_pane)
            self.main_container.add(self.right_pane)

            logger.debug("Desktop layout created")

        except Exception as e:
            logger.error(f"Failed to create desktop layout: {e}")

    def _subscribe_to_events(self):
        """Subscribe to navigation events"""
        try:
            subscribe_to_navigation(NavigationEvents.SHOW_LIBRARY, self._on_show_library)
            subscribe_to_navigation(NavigationEvents.SHOW_COLLECTION, self._on_show_collection)
            subscribe_to_navigation(NavigationEvents.SHOW_PREVIEW, self._on_show_preview)
            subscribe_to_navigation(NavigationEvents.SHOW_MODAL, self._on_show_modal)
            subscribe_to_navigation(NavigationEvents.NAVIGATION_ERROR, self._on_navigation_error)

            logger.debug("Subscribed to navigation events")

        except Exception as e:
            logger.error(f"Failed to subscribe to navigation events: {e}")

    def _show_initial_view(self):
        """Show the initial library view"""
        try:
            # Get or create library view (will cache for later reuse)
            library_view = self._get_or_create_library_view()

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("library", library_view)
            else:
                self._show_view_desktop("library", library_view, "left")

            logger.info("Initial library view displayed")

        except Exception as e:
            logger.error(f"Failed to show initial view: {e}")

    def _get_or_create_library_view(self) -> LibraryView:
        """Get cached library view or create new one if needed"""
        try:
            if self.cached_library_view is None:
                logger.debug("Creating new LibraryView instance")
                self.cached_library_view = LibraryView(self.app, self.is_mobile)
                self.cached_library_view.register_collection_callback(self._on_collection_selected)
            else:
                logger.debug("Reusing cached LibraryView instance")
                # Refresh the view when reusing it
                if hasattr(self.cached_library_view, 'show'):
                    self.cached_library_view.show()

            return self.cached_library_view
        except Exception as e:
            logger.error(f"Failed to get or create library view: {e}")
            # Fallback: create new instance
            library_view = LibraryView(self.app, self.is_mobile)
            library_view.register_collection_callback(self._on_collection_selected)
            return library_view

    def _get_or_create_collection_view(self, collection_id: str, collection_name: str) -> CollectionView:
        """Get cached collection view or create new one if needed"""
        try:
            # Check if we have a cached view for this collection_id
            if collection_id in self.cached_collection_views:
                logger.debug(f"Reusing cached CollectionView instance for {collection_name}")
                collection_view = self.cached_collection_views[collection_id]

                # Refresh the view when reusing it (but don't recreate content completely)
                if hasattr(collection_view, 'show'):
                    collection_view.show()
                return collection_view
            else:
                logger.debug(f"Creating new CollectionView instance for {collection_name}")
                collection_view = CollectionView(self.app, collection_name, self.is_mobile)
                collection_view.set_collection_id(collection_id)
                collection_view.register_preview_callback(self._on_file_preview_requested)

                # Cache the view for future use
                self.cached_collection_views[collection_id] = collection_view
                return collection_view

        except Exception as e:
            logger.error(f"Failed to get or create collection view: {e}")
            # Fallback: create new instance (but don't cache it to avoid corrupt cache)
            collection_view = CollectionView(self.app, collection_name, self.is_mobile)
            collection_view.set_collection_id(collection_id)
            collection_view.register_preview_callback(self._on_file_preview_requested)
            return collection_view

    # ===== EVENT HANDLERS =====

    def _on_show_library(self, event):
        """Handle show library event"""
        try:
            logger.info(f"Event: Show library - {event}")

            # Get or create library view (reuses cached instance to maintain state)
            library_view = self._get_or_create_library_view()

            # Check if force refresh is requested (e.g., after collection rename)
            force_refresh = False
            if hasattr(event, 'data') and event.data:
                force_refresh = event.data.get('force_refresh', False)
            elif hasattr(event, 'get'):
                force_refresh = event.get('force_refresh', False)

            if force_refresh:
                logger.info("🔄 LIBRARY REFRESH: Force refresh requested - reloading collections")
                # Force reload collections from database before showing
                if hasattr(library_view, '_load_collections_async'):
                    import asyncio
                    asyncio.create_task(library_view._load_collections_async())

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("library", library_view)
            else:
                self._show_view_desktop("library", library_view, "left")

        except Exception as e:
            logger.error(f"Failed to handle show library event: {e}")

    def _on_show_collection(self, event):
        """Handle show collection event with improved view lifecycle management"""
        try:
            data = event.data
            collection_id = data.get('collection_id')
            collection_name = data.get('collection_name', collection_id)

            logger.info(f"Event: Show collection {collection_name}")

            view_key = f"collection_{collection_id}"

            # Check if we already have the same collection view active
            current_view = self.current_view
            if (current_view and
                hasattr(current_view, 'collection_id') and
                current_view.collection_id == collection_id):
                # This is the same collection - just refresh its show() method
                logger.info(f"Refreshing existing active collection view for {collection_name}")
                if hasattr(current_view, 'show'):
                    current_view.show()
                return

            # Get or create collection view from cache
            collection_view = self._get_or_create_collection_view(collection_id, collection_name)

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile(view_key, collection_view)
            else:
                self._show_view_desktop(view_key, collection_view, "center")

        except Exception as e:
            logger.error(f"Failed to handle show collection event: {e}")

    def _on_show_preview(self, event):
        """Handle show preview event - now shows OutputView with optional Director outputs"""
        try:
            data = event.data
            file_path = data.get('file_path')
            output_path = data.get('output_path')  # NEW: Optional Director output folder path
            file_metadata = data.get('file_metadata', {})
            collection_items = data.get('collection_items', [])
            item_index = data.get('item_index', 0)

            logger.info(f"Event: Show output for {file_path}")
            if output_path:
                logger.info(f"📊 With processing outputs from: {output_path}")

            # Create or reuse OutputView
            if not self.cached_output_view:
                self.cached_output_view = OutputView(self.app, self.is_mobile)
                logger.debug("Created new OutputView")

            # Get collection items from current center view if not provided
            if not collection_items:
                # The center view is stored in self.current_view (from _show_view_desktop)
                center_view = self.current_view if hasattr(self, 'current_view') else None
                logger.info(f"📋 Getting collection items from center view: {center_view}")
                if center_view and hasattr(center_view, 'collection_items'):
                    collection_items = center_view.collection_items
                    logger.info(f"📋 Found {len(collection_items)} items in collection_items")
                else:
                    logger.warning(f"📋 No collection_items found on center view")

            # Convert collection items to source file paths
            source_files = []
            source_index = 0

            if collection_items:
                for i, item in enumerate(collection_items):
                    item_file_path = item.get('file_path') or item.get('path')
                    if item_file_path:
                        source_files.append(Path(item_file_path))
                        # Track which index matches our current file
                        if str(item_file_path) == str(file_path):
                            source_index = i

                logger.info(f"📋 Extracted {len(source_files)} source files, current index={source_index}")

            # Note: output_path should already be provided by collection_view when available
            # collection_view queries the library and passes output_path in the event data

            # Determine what to load into OutputView
            if output_path:
                # Load from Director output folder - pass output_root_path directly
                output_root = Path(output_path)
                logger.info(f"📊 Loading from Director output folder: {output_root}")

                # Pass output_root_path directly to OutputView - it will handle loading steps
                # Also pass original file_path for context
                self.cached_output_view.load_output(
                    file_path=Path(file_path),
                    source_files=source_files,
                    source_index=source_index,
                    output_root_path=output_root
                )
            else:
                # Load original file (no processing outputs)
                self.cached_output_view.load_output(
                    file_path=Path(file_path),
                    source_files=source_files,
                    source_index=source_index
                )

            # Show in appropriate pane
            if self.is_mobile:
                self._show_view_mobile("output", self.cached_output_view)
            else:
                self._show_view_desktop("output", self.cached_output_view, "right")

        except Exception as e:
            logger.error(f"Failed to handle show preview event: {e}")

    def _on_show_modal(self, event):
        """Handle show modal event - now handles desktop window creation directly"""
        try:
            data = event.data
            modal_type = data.get('modal_type')
            context = data.get('context')
            view = data.get('view')

            logger.info(f"Event: Show modal {modal_type}")

            if not view:
                logger.error(f"No view provided for modal {modal_type}")
                return

            # For desktop (non-mobile), create a standalone window (not modal)
            # Only rename/delete dialogs should be truly modal
            if not self.is_mobile:
                window_size = self._get_modal_size(modal_type)
                is_dialog = modal_type in ['collection', 'rename', 'delete']

                standalone_window = toga.Window(
                    title=self._get_modal_title(modal_type),
                    size=window_size,
                    minimizable=not is_dialog,  # Dialogs can't minimize
                    resizable=not is_dialog,    # Dialogs can't resize
                    closable=True
                )

                # Set the view content in the window
                container = view.get_container() if hasattr(view, 'get_container') else view

                # For standalone windows, temporarily remove toolbars (they have window chrome)
                removed_top = None
                removed_bottom = None
                if hasattr(view, 'container') and view.container:
                    if hasattr(view, 'top_toolbar_container') and view.top_toolbar_container:
                        try:
                            view.container.remove(view.top_toolbar_container)
                            removed_top = view.top_toolbar_container
                            logger.debug(f"Removed top toolbar for standalone window {modal_type}")
                        except Exception as e:
                            logger.debug(f"Could not remove top toolbar: {e}")

                    if hasattr(view, 'bottom_toolbar_container') and view.bottom_toolbar_container:
                        try:
                            view.container.remove(view.bottom_toolbar_container)
                            removed_bottom = view.bottom_toolbar_container
                            logger.debug(f"Removed bottom toolbar for standalone window {modal_type}")
                        except Exception as e:
                            logger.debug(f"Could not remove bottom toolbar: {e}")

                standalone_window.content = container

                # Store removed toolbars on the view for potential restoration
                if removed_top or removed_bottom:
                    view._desktop_removed_toolbars = {
                        'top': removed_top,
                        'bottom': removed_bottom
                    }

                # Set the window reference on the view for closing
                if hasattr(view, 'set_modal_window'):
                    view.set_modal_window(standalone_window)

                # Show the window (non-blocking for standalone windows, blocking for dialogs)
                standalone_window.show()

                window_type = "dialog" if is_dialog else "standalone window"
                logger.info(f"{modal_type} shown as {window_type} on desktop")
            else:
                # Mobile is handled by NavigationController's _show_modal_overlay
                logger.info(f"Modal {modal_type} handled by NavigationController overlay")

        except Exception as e:
            logger.error(f"Failed to handle show modal event: {e}")

    def _get_modal_title(self, modal_type: str) -> str:
        """Get user-friendly title for modal windows with translation support"""
        # Use the globally installed _() function from gettext.install()
        try:
            title_map = {
                'settings': _('preferences_title'),
                'activity_monitor': _('activity_monitor_title'),
                'processing': _('document_processing'),
                'plans': _('menu_plans'),
                'prompts': _('menu_prompts'),
                'about': _('about_window_title'),
                'url': _('Add URL'),
                'website': _('Add Website'),
                'file': _('Add File'),
                'folder': _('Add Folder'),
                'camera': _('Add Picture'),
                'collection': _('Rename')
            }
            return title_map.get(modal_type, modal_type.title())
        except NameError:
            # Fallback if _ is not defined
            logger.warning("Translation function _ not available, using English fallbacks")
            fallback_map = {
                'settings': 'Settings',
                'activity_monitor': 'Activity Monitor',
                'processing': 'Processing',
                'plans': 'Plans',
                'prompts': 'Prompts',
                'about': 'About Fichero',
                'url': 'Add URL',
                'website': 'Add Website',
                'file': 'Add File',
                'folder': 'Add Folder',
                'camera': 'Add Picture',
                'collection': 'Rename'
            }
            return fallback_map.get(modal_type, modal_type.title())

    def _get_modal_size(self, modal_type: str) -> tuple:
        """Get appropriate size for modal windows based on type"""
        size_map = {
            'settings': (700, 600),
            'activity_monitor': (800, 600),
            'processing': (700, 600),
            'plans': (700, 600),
            'prompts': (700, 600),
            'about': (300, 400),
            'url': (600, 500),
            'website': (800, 600),
            'file': (600, 500),
            'folder': (600, 500),
            'camera': (600, 500),
            'collection': (400, 200)  # Smaller for simple rename dialog
        }
        return size_map.get(modal_type, (700, 600))

    def _on_navigation_error(self, event):
        """Handle navigation error event"""
        try:
            data = event.data
            title = data.get('title', 'Navigation Error')
            message = data.get('message', 'Unknown error')

            logger.error(f"Navigation error: {title} - {message}")

            # Could show error dialog here
            # For now, just log the error

        except Exception as e:
            logger.error(f"Failed to handle navigation error event: {e}")

    # ===== VIEW MANAGEMENT =====

    def _cleanup_current_view_callbacks(self):
        """Clean up NavigationController callbacks from the current view before replacing it"""
        try:
            if hasattr(self, 'current_view') and self.current_view:
                # Clean up view callbacks
                if hasattr(self.current_view, 'cleanup_callbacks'):
                    self.current_view.cleanup_callbacks()
                    logger.debug(f"Cleaned up callbacks for view: {getattr(self.current_view, '__class__', type(self.current_view)).__name__}")

                # Clean up toolbar callbacks in the view
                if hasattr(self.current_view, 'top_toolbar') and hasattr(self.current_view.top_toolbar, 'cleanup_callbacks'):
                    self.current_view.top_toolbar.cleanup_callbacks()
                    logger.debug("Cleaned up top toolbar callbacks")

                if hasattr(self.current_view, 'bottom_toolbar') and hasattr(self.current_view.bottom_toolbar, 'cleanup_callbacks'):
                    self.current_view.bottom_toolbar.cleanup_callbacks()
                    logger.debug("Cleaned up bottom toolbar callbacks")

        except Exception as e:
            logger.error(f"Failed to cleanup current view callbacks: {e}")

    def _cleanup_all_cached_views(self):
        """Clean up all cached views to prevent memory leaks and orphaned callbacks"""
        try:
            # Clean up cached collection views
            for collection_id, collection_view in self.cached_collection_views.items():
                try:
                    if hasattr(collection_view, 'cleanup_callbacks'):
                        collection_view.cleanup_callbacks()

                    if hasattr(collection_view, 'top_toolbar') and hasattr(collection_view.top_toolbar, 'cleanup_callbacks'):
                        collection_view.top_toolbar.cleanup_callbacks()

                    if hasattr(collection_view, 'bottom_toolbar') and hasattr(collection_view.bottom_toolbar, 'cleanup_callbacks'):
                        collection_view.bottom_toolbar.cleanup_callbacks()

                    logger.debug(f"Cleaned up cached CollectionView for {collection_id}")
                except Exception as e:
                    logger.error(f"Failed to cleanup cached collection view {collection_id}: {e}")

            # Clean up cached library view
            if self.cached_library_view:
                try:
                    if hasattr(self.cached_library_view, 'cleanup_callbacks'):
                        self.cached_library_view.cleanup_callbacks()

                    if hasattr(self.cached_library_view, 'top_toolbar') and hasattr(self.cached_library_view.top_toolbar, 'cleanup_callbacks'):
                        self.cached_library_view.top_toolbar.cleanup_callbacks()

                    if hasattr(self.cached_library_view, 'bottom_toolbar') and hasattr(self.cached_library_view.bottom_toolbar, 'cleanup_callbacks'):
                        self.cached_library_view.bottom_toolbar.cleanup_callbacks()

                    logger.debug("Cleaned up cached LibraryView")
                except Exception as e:
                    logger.error(f"Failed to cleanup cached library view: {e}")

            logger.debug("All cached views cleaned up")

        except Exception as e:
            logger.error(f"Failed to cleanup all cached views: {e}")

    def _show_view_mobile(self, view_key: str, view):
        """Show view in mobile layout"""
        try:
            if not self.mobile_container:
                logger.error("No mobile container available")
                return

            # Clean up callbacks from previous view to prevent duplicate events
            self._cleanup_current_view_callbacks()

            # Clear current view
            self.mobile_container.clear()

            # Add new view
            view_container = view.get_container() if hasattr(view, 'get_container') else view
            self.mobile_container.add(view_container)

            # Update tracking
            self.current_view = view
            self.current_view_key = view_key

            # Show the view
            if hasattr(view, 'show'):
                view.show()

            logger.debug(f"Mobile view '{view_key}' displayed")

        except Exception as e:
            logger.error(f"Failed to show mobile view {view_key}: {e}")

    def _show_view_desktop(self, view_key: str, view, pane: str):
        """Show view in desktop layout"""
        try:
            # Get target pane
            if pane == "left":
                target_pane = self.left_pane
            elif pane == "center":
                target_pane = self.center_pane
            elif pane == "right":
                target_pane = self.right_pane
            else:
                logger.error(f"Invalid pane: {pane}")
                return

            if not target_pane:
                logger.error(f"Pane '{pane}' not available")
                return

            # Clean up callbacks if replacing center pane (where current_view is tracked)
            if pane == "center":
                self._cleanup_current_view_callbacks()

            # Clear target pane
            target_pane.clear()

            # Add new view
            view_container = view.get_container() if hasattr(view, 'get_container') else view
            target_pane.add(view_container)

            # Update tracking (for mobile fallback)
            if pane == "center":  # Track center pane as current view
                self.current_view = view
                self.current_view_key = view_key

            # Show the view
            if hasattr(view, 'show'):
                view.show()

            logger.debug(f"Desktop view '{view_key}' displayed in '{pane}' pane")

        except Exception as e:
            logger.error(f"Failed to show desktop view {view_key} in {pane}: {e}")

    # ===== LEGACY CALLBACKS (for views that haven't been updated yet) =====

    def _on_collection_selected(self, collection_id: str, collection_name: str = ""):
        """Handle collection selection - delegate to NavigationController"""
        try:
            if self.navigation_controller:
                self.navigation_controller.navigate_to_collection(collection_id, collection_name)
            else:
                logger.error("No NavigationController available for collection selection")

        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")

    def _on_file_preview_requested(self, file_path: str, file_data: Dict[str, Any] = None):
        """Handle file preview request - delegate to NavigationController"""
        try:
            if self.navigation_controller:
                self.navigation_controller.navigate_to_preview(file_path, file_data)
            else:
                logger.error("No NavigationController available for preview request")

        except Exception as e:
            logger.error(f"Failed to handle file preview request: {e}")

    # ===== PUBLIC INTERFACE =====

    def show(self):
        """Show the main window"""
        try:
            if self.window:
                self.window.show()
                logger.info("Main window shown")
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")

    def close(self):
        """Close the main window with proper cleanup"""
        try:
            # Clean up all cached views before closing
            self._cleanup_all_cached_views()

            if self.window:
                self.window.close()
                logger.info("Main window closed")
        except Exception as e:
            logger.error(f"Failed to close main window: {e}")


    def get_window_info(self) -> Dict[str, Any]:
        """Get window information for debugging"""
        return {
            "is_mobile": self.is_mobile,
            "current_view_key": self.current_view_key,
            "has_navigation_controller": self.navigation_controller is not None,
            "window_size": self._get_window_size()
        }