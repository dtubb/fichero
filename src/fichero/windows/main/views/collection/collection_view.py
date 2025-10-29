"""
Refactored Collection View for Fichero

Uses the new BaseView system with toolbar integration and proper styling.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
import asyncio
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from fichero.shared.views.base_view import BaseView
from fichero.shared.commands import FicheroCommand, ViewCommandMixin
from fichero.library.library_manager import LibraryManager
from fichero.shared.toolbars import TopToolbar, BottomToolbar
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead

logger = logging.getLogger(__name__)


class CollectionView(BaseView, ViewCommandMixin):
    """Collection view using the new BaseView system"""
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = False, collection_id: Optional[str] = None):
        """Initialize refactored collection view"""
        logger.info(f"🆕 CollectionView.__init__ called with:")
        logger.info(f"   collection_name='{collection_name}'")
        logger.info(f"   collection_id={collection_id}")
        logger.info(f"   is_mobile={is_mobile}")
        logger.info(f"   instance_id={id(self)}")

        # Initialize attributes BEFORE calling super().__init__ to prevent AttributeError
        # during _create_content() which gets called by BaseView's constructor

        # Collection-specific data
        self.collection_name = collection_name
        self.collections: List[Dict[str, Any]] = []
        self.current_collection: Optional[Dict[str, Any]] = None
        self.collection_id: Optional[str] = collection_id  # Set from parameter
        logger.debug(f"🔑 Stored collection_id in instance: {self.collection_id}")
        self.collection_items: List[Dict[str, Any]] = []

        # Preview callback for showing files in right pane
        self.on_file_preview_requested: Optional[Callable] = None

        # Hierarchical navigation state
        self.current_path: str = ""  # Current path within collection (empty = root)
        self.breadcrumb_path: List[str] = []  # For breadcrumb display

        # Navigation loop protection
        self._updating_from_navigation_callback = False

        # Set view_id BEFORE initializing ViewCommandMixin
        # Always use "collection" since we cache a single reusable instance
        self.view_id = "collection"

        # Call parent initializer AFTER initializing our attributes
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)

        # Define and register commands
        self.define_commands()
        self.register_commands()

        # Edit mode state
        self.is_edit_mode: bool = False

        # Initialize library manager
        self._initialize_library_manager()

        # Create toolbars after BaseView is initialized
        self._create_toolbars()

        # Register navigation callbacks for the top toolbar (mobile only)
        if self.top_toolbar:
            self.setup_toolbar_callbacks(self.top_toolbar)

        # Register for NavigationController state changes
        self._register_navigation_controller_callbacks()

        # Create content
        self._create_content()

        # Set up scroll container integration
        self._setup_scroll_integration()

        # Connect bottom toolbar preview callback (mobile only)
        if self.bottom_toolbar and hasattr(self.bottom_toolbar, 'register_callbacks'):
            self.bottom_toolbar.register_callbacks(
                on_preview_file=self._on_preview_file_from_toolbar
            )
            logger.debug("Connected bottom toolbar preview callback")

        # Subscribe to library state events for automatic synchronization
        # Only subscribe if not already subscribed (prevent duplicates on same instance)
        if not hasattr(self, '_events_subscribed'):
            from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
            subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
            subscribe_to_navigation("collection_updated", self._on_collection_updated_event)
            subscribe_to_navigation("collection_items_changed", self._on_collection_items_changed_event)
            subscribe_to_navigation("collection_item_updated", self._on_item_progress_updated)
            subscribe_to_navigation("processing_completed", self._on_processing_completed)
            subscribe_to_navigation("folder_import_started", self._on_folder_import_started)
            subscribe_to_navigation("folder_import_progress", self._on_folder_import_progress)
            subscribe_to_navigation("folder_import_completed", self._on_folder_import_completed)
            self._events_subscribed = True
            logger.info(f"✅ Event subscriptions registered for CollectionView instance {id(self)} (collection_id: {collection_id})")
        else:
            logger.debug(f"⏭️ Event subscriptions already registered for this instance {id(self)} - skipping")

        # Load collection items if collection_id was provided during initialization
        if self.collection_id:
            logger.debug(f"Loading items for collection {self.collection_id} provided during initialization")
            self._load_collection_items()

        logger.info("Refactored collection view created successfully")

    def _get_current_collection_id(self) -> Optional[str]:
        """
        Get the CURRENT collection ID from NavigationController, not from instance state.
        This makes command handlers stateless.
        """
        try:
            # Get navigation controller from app
            if not hasattr(self.app, 'view_integration') or not self.app.view_integration:
                logger.warning("No view_integration found in app")
                return None

            nav_controller = self.app.view_integration.get_navigation_controller()
            if not nav_controller:
                logger.warning("NavigationController not available")
                return None

            # First try to use the view's own collection_id (more reliable)
            if hasattr(self, 'collection_id') and self.collection_id:
                logger.debug(f"📍 Using view's collection_id: {self.collection_id}")
                return self.collection_id

            # Fall back to NavigationController if instance variable not set
            current_state = nav_controller.get_current_state()

            # Check if we're in a collection context
            from fichero.shared.navigation.navigation_state import NavigationContext
            if current_state.context != NavigationContext.COLLECTION:
                logger.warning(f"Not in collection context (current: {current_state.context})")
                return None

            collection_id = current_state.collection_id
            logger.debug(f"📍 Current collection_id from NavigationController: {collection_id}")
            return collection_id

        except Exception as e:
            logger.error(f"Failed to get current collection ID: {e}")
            return None

    def define_commands(self):
        """Define all commands for CollectionView"""
        try:
            # Create custom menu groups (following OutputView/LibraryView pattern)
            tools_group = toga.Group("Tools", order=50)  # After View (30), before Window (90)

            # Note: _() is available globally via gettext.install() in app.py
            self.commands = {
                # ===== TOOLS MENU - SMART PROCESS COMMAND =====
                'process': FicheroCommand(
                    id='collection.process',
                    label=_("Process"),
                    action=self._on_process_requested,
                    shortcut=toga.Key.MOD_1 + toga.Key.ENTER,  # Cmd+Enter
                    icon='resources/icons/toolbar/sparkle@10x.png',
                    description=_("Process selected item or all items"),
                    group=tools_group,  # Tools menu on desktop
                    section=1,  # Section 1 = separator after Inspector
                    order=0,  # First item in this section
                    show_in_menu=True,  # Appear in Tools menu on desktop
                    show_in_toolbar=True,  # Show in desktop toolbar
                    show_in_top_toolbar=False,  # Not in mobile top toolbar
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='right',  # Right side on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal',
                    enabled=True  # Always enabled - smart selection detection
                ),

                # ===== FILE MENU - IMPORT SUBMENU ITEMS =====
                # These commands add items to the current collection
                # These commands are nested under the Import submenu in menus
                # But also appear as individual toolbar buttons on desktop
                'import_file': FicheroCommand(
                    id='collection.import_file',
                    label=_("File…"),
                    action=self._on_import_file,
                    icon='resources/icons/toolbar/document.png',
                    description=_("Add files to current collection"),
                    group=toga.Group.FILE,  # File menu on desktop
                    parent='collection.import',  # Nested under Import submenu in menu
                    section=1,  # Same section as parent Import command
                    order=0,  # First item in Import submenu
                    show_in_menu=True,  # Desktop: File > Import menu (native menu bar)
                    show_in_toolbar=True,  # Desktop: native command bar (window.toolbar)
                    show_in_top_toolbar=False,  # NOT in view's custom top toolbar
                    show_in_bottom_toolbar=False,  # NOT on mobile (desktop only)
                    desktop_only=True,  # Desktop only - mobile uses URL and Camera
                    mobile_only=False,
                    context='normal'  # Always visible
                ),

                'import_folder': FicheroCommand(
                    id='collection.import_folder',
                    label=_("Folder…"),
                    action=self._on_import_folder,
                    icon='resources/icons/toolbar/folder@10x.png',
                    description=_("Add folder to current collection"),
                    group=toga.Group.FILE,  # File menu on desktop
                    parent='collection.import',  # Nested under Import submenu in menu
                    section=1,  # Same section as parent Import command
                    order=1,  # Second item in Import submenu
                    show_in_menu=True,  # Desktop: File > Import menu (native menu bar)
                    show_in_toolbar=True,  # Desktop: native command bar (window.toolbar)
                    show_in_top_toolbar=False,  # NOT in view's custom top toolbar
                    show_in_bottom_toolbar=False,  # NOT on mobile (desktop only)
                    desktop_only=True,  # Desktop only - mobile uses URL and Camera
                    mobile_only=False,
                    context='normal'  # Always visible
                ),

                'import_url': FicheroCommand(
                    id='collection.import_url',
                    label=_("URL…"),
                    action=self._on_import_url,
                    icon='resources/icons/toolbar/link.png',
                    description=_("Add URL to current collection"),
                    group=toga.Group.FILE,  # File menu on desktop
                    parent='collection.import',  # Nested under Import submenu in menu
                    section=1,  # Same section as parent Import command
                    order=10,  # Menu order + toolbar order
                    show_in_menu=True,  # Desktop: File > Import menu (native menu bar)
                    show_in_toolbar=True,  # Desktop: native command bar (window.toolbar)
                    show_in_top_toolbar=False,  # NOT in view's custom top toolbar
                    show_in_bottom_toolbar=True,  # Mobile: show in bottom toolbar
                    toolbar_position='left',  # Position on left side of bottom toolbar
                    desktop_only=False,  # Available on both platforms
                    mobile_only=False,
                    context='normal'  # Always visible
                ),

                # Camera button for normal mode (mobile bottom toolbar)
                'import_camera': FicheroCommand(
                    id='collection.import_camera',
                    label=_("Camera"),
                    action=self._on_open_camera,
                    icon='resources/icons/toolbar/camera.png',
                    description=_("Take photo with camera"),
                    show_in_menu=False,  # Not in menus
                    show_in_toolbar=False,  # Not in desktop toolbar
                    show_in_top_toolbar=False,  # NOT in top toolbar
                    show_in_bottom_toolbar=True,  # Mobile: show in bottom toolbar
                    toolbar_position='left',  # Position on left side of bottom toolbar
                    mobile_only=True,  # Mobile only - camera access
                    desktop_only=False,
                    context='normal',  # Always visible (normal mode)
                    order=11  # Right after URL button
                ),

                # ===== FILE MENU - IMPORT SUBMENU LINK ITEMS (MENU ONLY) =====
                # These appear in Import submenu AFTER a separator
                # They do NOT appear in toolbars
                'link_file': FicheroCommand(
                    id='collection.link_file',
                    label=_("Link File…"),
                    action=self._on_link_file,
                    icon='resources/icons/toolbar/document.png',
                    description=_("Link to file (reference only, no copy)"),
                    group=toga.Group.FILE,  # File menu on desktop
                    parent='collection.import',  # Nested under Import submenu in menu
                    section=2,  # New section - creates separator above
                    order=0,  # First item in link section
                    show_in_menu=True,  # Appear in File > Import menu on desktop
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=False,  # NOT on mobile bottom toolbar
                    desktop_only=True,  # Only show on desktop, not mobile
                    context='normal'  # Always visible on desktop
                ),

                'link_folder': FicheroCommand(
                    id='collection.link_folder',
                    label=_("Link Folder…"),
                    action=self._on_link_folder,
                    icon='resources/icons/toolbar/folder@10x.png',
                    description=_("Link to folder (reference only, no copy)"),
                    group=toga.Group.FILE,  # File menu on desktop
                    parent='collection.import',  # Nested under Import submenu in menu
                    section=2,  # Same section as link commands
                    order=1,  # Second item in link section
                    show_in_menu=True,  # Appear in File > Import menu on desktop
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=False,  # NOT on mobile bottom toolbar
                    desktop_only=True,  # Only show on desktop, not mobile
                    context='normal'  # Always visible on desktop
                ),

                # ===== EDIT MODE COMMANDS =====
                # Import URL button for edit mode (mobile bottom toolbar)
                'edit_import_url': FicheroCommand(
                    id='collection.edit_import_url',
                    label=_("Add URL"),
                    action=self._on_import_url,
                    icon='resources/icons/toolbar/link.png',
                    description=_("Import from URL"),
                    show_in_menu=False,
                    show_in_bottom_toolbar=True,
                    toolbar_position='center',
                    mobile_only=True,  # Mobile only - mobile edit mode
                    desktop_only=False,
                    context='edit'
                ),

                # Camera button for edit mode (mobile bottom toolbar)
                'edit_camera': FicheroCommand(
                    id='collection.edit_camera',
                    label=_("Camera"),
                    action=self._on_open_camera,
                    icon='resources/icons/toolbar/camera.png',
                    description=_("Take photo with camera"),
                    show_in_menu=False,
                    show_in_bottom_toolbar=True,
                    toolbar_position='center',
                    mobile_only=True,  # Mobile only - camera access
                    desktop_only=False,
                    context='edit'
                ),

                # ===== MOBILE TOP TOOLBAR - INSPECTOR BUTTON =====
                'show_inspector': FicheroCommand(
                    id='collection.show_inspector',
                    label=_("Info"),
                    action=self._on_show_inspector,
                    icon='resources/icons/toolbar/info.circle@10x.png',
                    description=_("Show inspector for selected item"),
                    show_in_menu=False,  # Not in menus
                    show_in_toolbar=False,  # Not in desktop toolbar
                    show_in_top_toolbar=True,  # Mobile top toolbar
                    toolbar_position='right',  # Right side of toolbar
                    show_in_bottom_toolbar=False,  # Not in bottom toolbar
                    mobile_only=True,  # Only on mobile
                    desktop_only=False,
                    context='normal',
                    order=99,  # Last on right side (rightmost)
                    enabled=False  # Will be enabled when item is selected
                ),
            }

            logger.info(f"✅ Defined {len(self.commands)} commands for CollectionView")

        except Exception as e:
            logger.error(f"Failed to define CollectionView commands: {e}")
            self.commands = {}

    def show(self):
        """Called when view becomes active - light refresh without recreating content"""
        try:
            # Light refresh - just clear DetailedList selection without rebuilding everything
            if hasattr(self, 'items_list') and self.items_list:
                # Clear any existing selection state but don't recreate the entire list
                try:
                    self.items_list.selection = None
                    logger.debug("🔄 Cleared DetailedList selection state")
                except Exception as e:
                    logger.debug(f"Could not clear DetailedList selection: {e}")

            # Mark view as visible but don't recreate content unnecessarily
            self.is_visible = True
            logger.info("🔄 Collection view refreshed on show() - lightweight refresh")
        except Exception as e:
            logger.error(f"Failed to refresh collection view on show: {e}")
    
    def _create_content(self):
        """Create the collection view content"""
        try:
            # Clear any existing content first to prevent duplicates
            if self.content_container:
                self.content_container.clear()
            
            # Add current folder header (shows what folder we're currently viewing)
            # Only show when we have a collection selected
            if hasattr(self, 'collection_id') and self.collection_id:
                content_title = self._get_content_title()
                if content_title:
                    self.folder_header = toga.Label(
                        content_title,
                        style=Pack(
                            margin=(15, 20, 10, 20),
                            # Use default font size (no font_size specified)
                            font_weight="bold",
                            color=self.text_color
                        )
                    )
                    self.content_container.add(self.folder_header)
            
            # Always show DetailedList (even if empty) - Mac style
            # On Mac, empty folders just show an empty list, not a placeholder message
            items_to_display = self.collection_items if hasattr(self, 'collection_items') else []

            if hasattr(self, 'collection_id') and self.collection_id:
                # We have a collection - show its items (or empty list)
                logger.debug(f"Displaying {len(items_to_display)} collection items")
                self._create_collection_items_list(items_to_display)
            else:
                # No collection selected - just show empty pane (no placeholder text)
                # The back button and toolbar remain available for navigation
                logger.debug("No collection selected - showing empty pane")

            # Update toolbar navigation state (show/hide back button based on path)
            self._update_toolbar_navigation()

        except Exception as e:
            logger.error(f"Failed to create collection content: {e}")

    def setup_toolbar_callbacks(self, toolbar):
        """Setup navigation callbacks with the collection toolbar using NavigationController only"""
        if hasattr(toolbar, 'register_navigation_callbacks'):
            toolbar.register_navigation_callbacks(
                on_back_to_library=self._on_back_to_library,
                on_navigate_back=self._on_navigate_back_via_navigation_helper,
                on_navigate_to_path=self._on_navigate_to_path_via_navigation_controller,
                on_add_folder=self._on_add_folder,
                on_add_file=self._on_add_file
            )
    
    def _get_navigation_controller(self):
        """Get the NavigationController instance"""
        try:
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                return self.app.view_integration.get_navigation_controller()
        except Exception as e:
            logger.debug(f"Could not get NavigationController: {e}")
        return None

    def _on_back_to_library(self):
        """Handle back to library navigation using NavigationController"""
        try:
            # Use NavigationController for consistent navigation
            logger.info("Collection view: Navigating back to library using NavigationController")
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                navigation_controller = self.app.view_integration.get_navigation_controller()
                if navigation_controller:
                    navigation_controller.navigate_back()

        except Exception as e:
            logger.error(f"Failed to navigate back to library: {e}")
            import traceback
            traceback.print_exc()

    def _on_navigate_back_via_navigation_helper(self):
        """Handle hierarchical back navigation using NavigationController"""
        try:
            logger.info("Collection toolbar: Back navigation requested via NavigationController")

            # Clear output view when navigating back (going to folder/collection root)
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                main_window = self.app.main_window_wrapper
                if hasattr(main_window, 'cached_output_view') and main_window.cached_output_view:
                    logger.info("📤 Clearing output view (back button clicked)")
                    main_window.cached_output_view.load_output()

            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                navigation_controller = self.app.view_integration.get_navigation_controller()
                if navigation_controller:
                    navigation_controller.navigate_back()

                    # Reset selection after navigating back (prevents index-based selection carry-over)
                    if hasattr(self, 'items_list') and self.items_list:
                        try:
                            self.items_list.selection = None
                            logger.debug("🔄 Reset selection after toolbar back navigation")
                        except AttributeError:
                            logger.debug("Could not clear selection (read-only property)")

        except Exception as e:
            logger.error(f"Failed to navigate back via NavigationController: {e}")

    def _on_navigate_to_path_via_navigation_controller(self, path: str):
        """Handle navigation to specific path using NavigationController directly"""
        try:
            logger.info(f"Collection toolbar: Navigate to breadcrumb path: {path}")

            # Get NavigationController
            navigation_controller = self._get_navigation_controller()
            if not navigation_controller:
                logger.error("❌ NavigationController not available - cannot navigate to path!")
                raise RuntimeError("NavigationController not available")

            # Use NavigationController for path navigation - NO FALLBACKS!
            success = navigation_controller.navigate_to_path(path)
            if not success:
                logger.error(f"❌ NavigationController: Failed to navigate to path: '{path}'")
                raise RuntimeError(f"NavigationController failed to navigate to path: '{path}'")

            logger.info(f"✅ Successfully navigated to path: '{path}' via NavigationController")

        except Exception as e:
            logger.error(f"Failed to navigate to path {path} via NavigationController: {e}")


    def _on_add_folder(self):
        """Handle add folder action from toolbar"""
        try:
            logger.info("Add folder requested from toolbar")

            # Use Toga folder selection dialog
            import asyncio
            asyncio.create_task(self._select_and_add_folder())

        except Exception as e:
            logger.error(f"Failed to handle add folder: {e}")

    async def _select_and_add_folder(self, operation: str = "link"):
        """Show folder selection dialog and add selected folder to collection"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show folder selection dialog
            import toga
            selected_path = await window.dialog(
                toga.SelectFolderDialog(
                    title=_("Select Folder to Add"),
                    initial_directory=None
                )
            )

            if selected_path:
                logger.info(f"Folder selected: {selected_path}, operation={operation}")
                # Add folder to current collection
                await self._add_folder_to_collection(str(selected_path), operation=operation)
            else:
                logger.info("Folder selection cancelled")

        except Exception as e:
            logger.error(f"Failed to select and add folder: {e}")

    def _on_add_file(self):
        """Handle add file action from toolbar - opens native dialog"""
        try:
            logger.info("Add file requested from toolbar")

            # Use native file dialog (same as link_file but defaults to link operation)
            import asyncio
            asyncio.create_task(self._select_and_import_files_async(operation="link"))

        except Exception as e:
            logger.error(f"Failed to handle add file: {e}")

    def _on_folder_added(self, data: dict):
        """Callback when folder is added from folder view"""
        try:
            folder_path = data.get('path', '')
            logger.info(f"Folder added callback received: {folder_path}")

            # Add folder to current collection
            import asyncio
            asyncio.create_task(self._add_folder_to_collection(folder_path))

        except Exception as e:
            logger.error(f"Failed to handle folder added: {e}")

    def _on_file_added(self, data: dict):
        """Callback when file is added from file view"""
        try:
            file_path = data.get('path', '')
            logger.info(f"File added callback received: {file_path}")

            # Add file to current collection
            import asyncio
            asyncio.create_task(self._add_file_to_collection(file_path))

        except Exception as e:
            logger.error(f"Failed to handle file added: {e}")

    # ===== IMPORT COMMAND HANDLERS =====
    # These handlers add items to the current collection

    def _on_import_file(self, widget=None):
        """Handle import file command - opens native dialog and copies files to collection"""
        try:
            logger.info(f"🎯 Import file requested (copy) - instance_id={id(self)}, collection_id={self.collection_id}, collection_name={getattr(self, 'collection_name', 'UNKNOWN')}")

            # Open native file dialog and import files
            import asyncio
            asyncio.create_task(self._select_and_import_files_async(operation="copy"))

        except Exception as e:
            logger.error(f"Failed to handle import file: {e}")

    def _on_import_file_callback(self, data: dict, operation: str = "copy"):
        """Callback when file is imported"""
        try:
            file_path = data.get('path', '')
            logger.info(f"File import callback received: {file_path}, operation={operation}")

            # Add file to current collection
            import asyncio
            asyncio.create_task(self._add_file_to_collection(file_path, operation=operation))

        except Exception as e:
            logger.error(f"Failed to handle file import callback: {e}")

    def _on_import_folder(self, widget=None):
        """Handle import folder command - copies folder to collection"""
        try:
            logger.info("Import folder requested (copy)")
            import asyncio
            asyncio.create_task(self._select_and_add_folder(operation="copy"))

        except Exception as e:
            logger.error(f"Failed to handle import folder: {e}")

    def _on_import_url(self, widget=None):
        """Handle import URL command - adds URL to collection"""
        try:
            logger.info("Import URL requested")
            from fichero.windows.add.views.url_view import URLAddView
            import toga

            # Get CURRENT collection from NavigationController (not instance state)
            current_collection_id = self._get_current_collection_id()
            if not current_collection_id:
                logger.error("Cannot import URL: no collection is active")
                return

            # Create callback that uses captured collection_id
            def on_url_added_with_context(data):
                return self._on_url_added_with_collection(data, current_collection_id)

            url_view = URLAddView(
                app=self.app,
                on_content_added=on_url_added_with_context
            )

            # On desktop: create new window, on mobile: push view
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                if self.app.main_window_wrapper.is_mobile:
                    # Mobile: use navigation controller to navigate to URL add view
                    if hasattr(self.app, 'view_integration'):
                        nav_controller = self.app.view_integration.get_navigation_controller()
                        if nav_controller:
                            nav_controller.navigate_to_add_url()
                            logger.info("Navigated to URL add view")
                        else:
                            logger.error("NavigationController not available")
                    else:
                        logger.error("view_integration not available")
                else:
                    # Desktop: create new window
                    add_window = toga.Window(
                        title="Import URL",
                        size=(600, 400),
                        resizable=True
                    )
                    add_window.content = url_view.container
                    # Pass window reference to view so it can close itself
                    url_view.window = add_window
                    add_window.show()
                    logger.info("URL add window shown")
            else:
                logger.error("main_window_wrapper not available")

        except Exception as e:
            logger.error(f"Failed to handle import URL: {e}")

    def _on_open_camera(self, widget=None):
        """Handle camera - navigate to Camera add view"""
        try:
            logger.info("Camera requested")
            # Use NavigationController to navigate to camera view (mobile only)
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    nav_controller.navigate_to_add_camera()
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open camera: {e}")

    def _on_url_added_with_collection(self, data: dict, collection_id: str):
        """Callback when URL is added - with captured collection_id"""
        try:
            # URL is passed in 'urls' array from url_view
            urls = data.get('urls', [])
            if not urls:
                logger.error("No URLs provided in callback data")
                return

            url = urls[0]  # Get first URL
            logger.info(f"URL added callback received: {url}")

            # Add URL to specified collection (captured at window creation time)
            import asyncio
            return asyncio.create_task(self._add_url_to_collection(url, collection_id))

        except Exception as e:
            logger.error(f"Failed to handle URL added: {e}")

    async def _add_url_to_collection(self, url: str, collection_id: str = None):
        """Import content from URL to the specified collection - downloads and parses content

        If collection_id is None, creates a new collection for the import.
        """
        try:
            # If collection_id provided, validate it still exists
            if collection_id:
                logger.info(f"🌐 Importing URL to collection {collection_id}: {url}")

                # Validate collection exists (it may have been deleted)
                collection = self.app.library_manager.storage.get_collection(collection_id)
                if not collection:
                    logger.warning(f"⚠️ Collection {collection_id} not found (may have been deleted)")
                    logger.info("Creating new collection for import instead")
                    collection_id = None  # Fall through to create new collection

            # If no collection_id or validation failed, create a new collection
            if not collection_id:
                logger.info(f"🌐 No collection selected - will create new collection for URL: {url}")

                # Extract a collection name from the URL
                from urllib.parse import urlparse
                parsed = urlparse(url)
                hostname = parsed.netloc.replace('www.', '')
                path_parts = [p for p in parsed.path.split('/') if p]

                # Try to make a meaningful name
                if 'eap.bl.uk' in hostname and path_parts:
                    collection_name = f"EAP Import - {path_parts[-1]}"
                else:
                    collection_name = f"Import from {hostname}"

                # Create new collection
                collection_id = await self.app.library_manager.add_collection(
                    name=collection_name,
                    collection_type="url",
                    source_path=url,
                    description=f"Imported from {url}"
                )

                if not collection_id:
                    logger.error("Failed to create new collection")
                    return

                logger.info(f"✅ Created new collection: {collection_name} (ID: {collection_id})")

                # Get the newly created collection
                collection = self.app.library_manager.storage.get_collection(collection_id)

            # Final validation (should never fail at this point)
            if not collection:
                logger.error(f"Collection validation failed: {collection_id}")
                return

            # Use the plugin system to fetch items from URL
            from fichero.library.import_plugins.registry import PluginRegistry
            from fichero.library.import_plugins.eap_plugin import EAPImportPlugin
            from fichero.library.import_plugins.box_plugin import BoxImportPlugin
            from fichero.library.import_plugins.zip_plugin import ZipImportPlugin

            # Create plugin registry and register plugins
            registry = PluginRegistry()
            registry.register(EAPImportPlugin(self.app.library_manager))
            registry.register(BoxImportPlugin(self.app.library_manager))
            registry.register(ZipImportPlugin(self.app.library_manager))

            # Find plugin that can handle this URL
            plugin = registry.find_plugin_for_url(url)
            if not plugin:
                error_msg = f"No plugin found to handle URL: {url}"
                logger.error(error_msg)
                return

            logger.info(f"Using plugin: {plugin.get_plugin_info()['name']}")

            # Use plugin to fetch items (but don't create new collection)
            # We'll manually add items to the current collection
            import tempfile
            import shutil
            from pathlib import Path

            temp_dir = None
            try:
                # For plugins that download files, we need a temp directory
                temp_dir = Path(tempfile.mkdtemp(prefix='fichero_url_import_'))

                # Call plugin's internal methods to get items without creating collection
                # Most plugins have a method to fetch items that we can use
                items = []

                if hasattr(plugin, '_fetch_iiif_manifest') and ('/manifest' in url or '/archive-file/' in url):
                    # EAP plugin with IIIF manifest
                    if '/archive-file/' in url and '/manifest' not in url:
                        # Extract manifest URL from page first
                        manifest_url = await plugin._extract_manifest_url_from_page(url, 600)
                        if manifest_url:
                            items = await plugin._fetch_iiif_manifest(manifest_url, 600)
                    else:
                        items = await plugin._fetch_iiif_manifest(url, 600)
                elif hasattr(plugin, '_fetch_hierarchical_collection'):
                    # EAP plugin with collection/project
                    items = await plugin._fetch_hierarchical_collection(url, 1000, 600)
                else:
                    # Fallback: let plugin create collection then move items
                    logger.warning("Using fallback: plugin will create temporary collection")
                    result = await plugin.download_and_import(
                        url=url,
                        collection_name=f"Temp_{collection.name}",
                        collection_description=f"Imported from {url}",
                        max_items=1000,
                        download_mode="link",
                        timeout=600
                    )

                    if result.success and result.collection_id:
                        # Get items from temporary collection
                        temp_items = await self.app.library_manager.get_collection_items(result.collection_id)
                        # Convert to simple dict format
                        items = [{'title': item.name, 'url': item.source_path, 'type': 'url'} for item in temp_items]
                        # Delete temporary collection
                        await self.app.library_manager.delete_collection(result.collection_id)

                # Now add items to current collection
                if not items:
                    logger.warning("No items found from URL")
                    return

                logger.info(f"Adding {len(items)} items to collection {collection.name}")

                # Separate folders and files for hierarchical import
                folders = [item for item in items if item.get('type') == 'folder' or item.get('is_folder')]
                files = [item for item in items if item.get('type') != 'folder' and not item.get('is_folder')]

                # Track folder_name → item_id mapping and folder_name → full_path
                folder_id_map = {}
                folder_path_map = {}  # folder_name → full relative path
                added_count = 0

                # Create a root folder for this manifest import (named after manifest)
                # Extract manifest name from URL or use first folder's name
                manifest_name = None
                root_folder_metadata = {
                    'type': 'manifest_root',
                    'source_url': url,
                    'import_date': str(__import__('datetime').datetime.now())
                }

                if folders and len(folders) > 0:
                    # Use the collection_label from the first folder's metadata if available
                    first_folder = folders[0]
                    first_folder_meta = first_folder.get('metadata', {})
                    manifest_name = first_folder_meta.get('manifest_label') or first_folder_meta.get('collection_label') or first_folder.get('title')

                    # Extract ALL manifest-level metadata from first folder to root folder
                    # Folders now have flat metadata structure (like items), so just merge directly
                    logger.info(f"📋 First folder has {len(first_folder_meta)} metadata fields: {list(first_folder_meta.keys())}")
                    for key, value in first_folder_meta.items():
                        # Skip folder-specific fields that shouldn't be on root
                        if key not in root_folder_metadata and key not in ['relative_path', 'type', 'page_range']:
                            root_folder_metadata[key] = value

                    logger.info(f"📋 Root folder will have {len(root_folder_metadata)} metadata fields (after copying from first folder)")

                if not manifest_name:
                    # Fallback: extract from URL
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    path_parts = [p for p in parsed.path.split('/') if p]
                    manifest_name = path_parts[-1] if path_parts else "Import"

                # Create root folder for this manifest
                logger.info(f"Creating root folder for manifest: {manifest_name} with {len(root_folder_metadata)} metadata fields")

                root_folder_id = await self.app.library_manager.add_item_to_collection(
                    collection_id=collection_id,
                    item_type="folder",
                    source="",
                    name=manifest_name,
                    operation="link",
                    metadata=root_folder_metadata,
                    parent_id=None  # At collection root
                )

                if not root_folder_id:
                    logger.error(f"Failed to create root folder for manifest: {manifest_name}")
                    return

                logger.info(f"Created root folder: {manifest_name} (ID: {root_folder_id})")

                # First pass: Create folder items with full metadata (as children of root folder)
                for folder in folders:
                    folder_name = folder['title']
                    # For root folders, relative_path is just the folder name
                    # For nested folders, this would include parent path (e.g., "parent/child")
                    relative_path = folder.get('relative_path', folder_name)

                    # Get all metadata from the folder
                    folder_metadata = folder.get('metadata', {})

                    # Add standard fields
                    folder_metadata.update({
                        'relative_path': relative_path,
                        'archive_id': folder.get('archive_id'),
                        'manifest_url': folder.get('manifest_url'),
                        'manifest_id': folder.get('manifest_id'),
                        'type': 'folder',
                        'description': folder.get('description', ''),
                        'attribution': folder.get('attribution', '')
                    })

                    # Add IIIF-specific metadata if present
                    if 'manifest_label' in folder_metadata:
                        logger.info(f"Creating IIIF manifest folder: {folder_name}")

                    folder_id = await self.app.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type="folder",
                        source="",
                        name=folder_name,
                        operation="link",
                        metadata=folder_metadata,
                        parent_id=root_folder_id  # Nested under manifest root folder
                    )

                    if folder_id:
                        folder_id_map[folder_name] = folder_id
                        folder_path_map[folder_name] = relative_path  # Store path for child folders
                        added_count += 1
                        logger.info(f"Created folder: {folder_name} at path '{relative_path}' with {len(folder_metadata)} metadata fields")

                # Second pass: Add files with parent_id references
                for item in files:
                    # Determine parent_id
                    # If item has parent_folder specified, use that
                    # Otherwise, use root_folder_id (manifest root)
                    parent_id = root_folder_id  # Default to root folder
                    if 'parent_folder' in item and item['parent_folder']:
                        # Item specifies a sub-folder
                        parent_id = folder_id_map.get(item['parent_folder'], root_folder_id)

                    # Get URL (prefer image_url over page url)
                    item_url = item.get('image_url') or item.get('url')
                    if not item_url:
                        logger.warning(f"No URL for item: {item.get('title')}")
                        continue

                    # Create comprehensive metadata with all available fields
                    metadata = {
                        'title': item['title'],
                        'image_url': item.get('image_url'),
                        'page_url': item.get('url'),
                        'type': item.get('type', 'url'),
                        'source': 'URL Import',
                        # IIIF-specific metadata
                        'canvas_id': item.get('canvas_id'),
                        'canvas_label': item.get('canvas_label'),
                        'canvas_width': item.get('canvas_width'),
                        'canvas_height': item.get('canvas_height'),
                        'canvas_metadata': item.get('canvas_metadata', []),
                        'collection_label': item.get('collection_label'),
                        'manifest_url': item.get('manifest_url'),
                        'manifest_metadata': item.get('manifest_metadata', []),
                        'manifest_position': item.get('manifest_position'),  # Preserve ordering
                        'attribution': item.get('attribution', ''),
                        'license': item.get('license', ''),
                        # EAP-specific metadata
                        'archive_id': item.get('archive_id')
                    }

                    # Add item to specified collection
                    item_id = await self.app.library_manager.add_item_to_collection(
                        collection_id=collection_id,
                        item_type="url",
                        source=item_url,
                        name=item['title'],
                        operation="link",
                        metadata=metadata,
                        parent_id=parent_id
                    )

                    if item_id:
                        added_count += 1

                logger.info(f"✅ Successfully added {added_count} items to collection {collection.name}")

                # Refresh collection display
                self._load_collection_items()

            finally:
                # Clean up temp directory
                if temp_dir and temp_dir.exists():
                    shutil.rmtree(temp_dir)

        except Exception as e:
            logger.error(f"Failed to import URL to collection: {e}")
            import traceback
            traceback.print_exc()

    def _on_link_file(self, widget=None):
        """Handle link file command - opens native dialog and links to files without copying"""
        try:
            logger.info("Link file requested (link operation)")

            # Open native file dialog and link files
            import asyncio
            asyncio.create_task(self._select_and_import_files_async(operation="link"))

        except Exception as e:
            logger.error(f"Failed to handle link file: {e}")

    def _on_link_folder(self, widget=None):
        """Handle link folder command - links to folder without copying"""
        try:
            logger.info("Link folder requested (reference only)")
            import asyncio
            asyncio.create_task(self._select_and_add_folder(operation="link"))

        except Exception as e:
            logger.error(f"Failed to handle link folder: {e}")

    # ===== MOBILE TOP TOOLBAR HANDLERS =====

    def _on_show_inspector(self, widget=None):
        """Handle show inspector command - shows item, folder, or collection inspector"""
        try:
            logger.info("Show inspector requested")

            # Check if an item is selected
            if hasattr(self, 'items_list') and self.items_list and self.items_list.selection:
                # Item selected - show item inspector
                selected_row = self.items_list.selection
                item_id = getattr(selected_row, 'id', None)

                if item_id:
                    logger.info(f"Showing inspector for selected item: {item_id}")
                    asyncio.create_task(self._show_inspector_with_full_data(item_id))
                    return

            # No item selected - show collection or folder inspector
            collection_id = self._get_current_collection_id()
            if collection_id:
                logger.info(f"No item selected, showing inspector for collection: {collection_id}")
                asyncio.create_task(self._show_collection_inspector(collection_id))
            else:
                logger.warning("No collection ID available for inspector")

        except Exception as e:
            logger.error(f"Failed to show inspector: {e}")

    async def _show_inspector_with_full_data(self, item_id: str):
        """Fetch full item data and show inspector"""
        try:
            # Fetch full item from library
            item_data = None
            if self.library_service and hasattr(self.library_service, 'library_manager'):
                item = await self.library_service.library_manager.get_item(item_id)
                if item:
                    # Pass dictionary directly - inspector supports it
                    item_data = item.to_dict()
                    logger.info(f"Fetched full item from database: {len(item_data)} fields")
                else:
                    logger.warning(f"Item not found in database: {item_id}")
            else:
                logger.warning("Library service not available")

            # Fallback to minimal data if fetch failed
            if not item_data:
                item_data = {'name': 'Unknown', 'id': item_id}

            # Mobile: Use NavigationController to navigate to inspector
            if self.is_mobile:
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        # Pass dictionary directly
                        nav_controller.navigate_to_inspector(item_id=item_id, item_data=item_data)
                        logger.info(f"Navigated to inspector for item: {item_id}")
                    else:
                        logger.error("NavigationController not available")
                else:
                    logger.error("view_integration not available")
            # Desktop: Show inspector window directly
            else:
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    # Update inspector with dictionary
                    self.app.inspector_window.update_metadata(item_data, selection_type='ITEM')
                    self.app.inspector_window.show()
                    logger.info(f"Inspector window shown for item: {item_id}")
                else:
                    logger.warning("Inspector window not available")

        except Exception as e:
            logger.error(f"Failed to show inspector with full data: {e}")
            import traceback
            traceback.print_exc()

    async def _show_collection_inspector(self, collection_id: str):
        """Fetch full collection data and show inspector"""
        try:
            # Fetch full collection from library
            collection_data = None
            if self.library_service and hasattr(self.library_service, 'library_manager'):
                collection = await self.library_service.library_manager.get_collection(collection_id)
                if collection:
                    # Pass dictionary directly - inspector supports it
                    collection_data = collection.to_dict()
                    logger.info(f"Fetched full collection from database: {len(collection_data)} fields")
                else:
                    logger.warning(f"Collection not found in database: {collection_id}")
            else:
                logger.warning("Library service not available")

            # Fallback to minimal data if fetch failed
            if not collection_data:
                collection_data = {'name': 'Unknown', 'id': collection_id}

            # Mobile: Use NavigationController to navigate to inspector
            if self.is_mobile:
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        # Pass dictionary directly with COLLECTION selection type
                        nav_controller.navigate_to_inspector(
                            item_id=collection_id,
                            item_data=collection_data,
                            selection_type='COLLECTION'
                        )
                        logger.info(f"Navigated to inspector for collection: {collection_id}")
                    else:
                        logger.error("NavigationController not available")
                else:
                    logger.error("view_integration not available")
            # Desktop: Show inspector window directly
            else:
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    # Update inspector with dictionary
                    self.app.inspector_window.update_metadata(collection_data, selection_type='COLLECTION')
                    self.app.inspector_window.show()
                    logger.info(f"Inspector window shown for collection: {collection_id}")
                else:
                    logger.warning("Inspector window not available")

        except Exception as e:
            logger.error(f"Failed to show collection inspector: {e}")
            import traceback
            traceback.print_exc()

    async def _add_folder_to_collection(self, folder_path: str, operation: str = "link"):
        """Add a folder to the current collection - blocking operation"""
        try:
            # Get CURRENT collection from NavigationController (not instance state)
            collection_id = self._get_current_collection_id()
            if not collection_id:
                logger.error("No collection ID available from NavigationController")
                return

            # Get folder name
            from pathlib import Path
            folder_name = Path(folder_path).name

            logger.info(f"📥 Importing folder '{folder_name}' to collection_id={collection_id} (CollectionView instance {id(self)})")

            # Add to collection via library service (this will block until complete)
            item_id = await self.app.library_service.add_item_to_collection_for_ui(
                collection_id=collection_id,
                item_type="folder",
                source=folder_path,
                name=folder_name,
                operation=operation  # Use provided operation (copy or link)
            )

            if item_id:
                # Refresh collection display
                self._load_collection_items()
                logger.info(f"Added folder '{folder_name}' to collection")
            else:
                logger.error("Failed to add folder to collection")

        except Exception as e:
            logger.error(f"Failed to add folder to collection: {e}")

    async def _add_file_to_collection(self, file_path: str, operation: str = "link"):
        """Add a file to the current collection - blocking operation"""
        try:
            # Get CURRENT collection from NavigationController (not instance state)
            collection_id = self._get_current_collection_id()
            logger.info(f"🔍 _add_file_to_collection called - instance_id={id(self)}, collection_id={collection_id}, collection_name={getattr(self, 'collection_name', 'UNKNOWN')}")

            if not collection_id:
                logger.error("No collection ID available from NavigationController")
                return

            # Get file name
            from pathlib import Path
            file_name = Path(file_path).name

            # Add to collection via library service (this will block until complete)
            item_id = await self.app.library_service.add_item_to_collection_for_ui(
                collection_id=collection_id,
                item_type="file",
                source=file_path,
                name=file_name,
                operation=operation  # Use provided operation (copy or link)
            )

            if item_id:
                # Refresh collection display
                self._load_collection_items()
                logger.info(f"Added file '{file_name}' to collection")
            else:
                logger.error("Failed to add file to collection")

        except Exception as e:
            logger.error(f"Failed to add file to collection: {e}")

    async def _select_and_import_files_async(self, operation: str = "link"):
        """Show file selection dialog and import/link selected files to collection"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show file selection dialog (can select multiple files)
            # Support all common image formats plus documents
            import toga
            selected_paths = await window.dialog(
                toga.OpenFileDialog(
                    title=_("Select Files to Add"),
                    initial_directory=None,
                    multiple_select=True,
                    file_types=['tif', 'tiff', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'jxl',
                               'pdf', 'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'dng']
                )
            )

            if selected_paths:
                logger.info(f"{len(selected_paths)} file(s) selected, operation={operation}")
                # Add files to collection
                for file_path in selected_paths:
                    await self._add_file_to_collection(str(file_path), operation=operation)

                logger.info(f"✅ Files added to collection successfully")
            else:
                logger.info("File selection cancelled")

        except Exception as e:
            logger.error(f"Failed to select and import files: {e}")

    def _update_toolbar_navigation(self):
        """Update toolbar navigation state"""
        try:
            if hasattr(self.top_toolbar, 'update_navigation_state'):
                self.top_toolbar.update_navigation_state(self.current_path)
        except Exception as e:
            logger.error(f"Failed to update toolbar navigation: {e}")
    
    def _create_collection_items_list(self, items: List[Dict[str, Any]]):
        """Create a detailed list view for collection items (even if empty - Mac style)"""
        try:
            # Always clear any existing DetailedList to reset selection state
            if hasattr(self, 'items_list') and self.items_list:
                try:
                    # Remove from container if it exists
                    if self.content_container and self.items_list in self.content_container.children:
                        self.content_container.remove(self.items_list)
                    logger.info("🔄 Cleared existing DetailedList to reset selection")
                except Exception as e:
                    logger.debug(f"Note: Could not remove existing DetailedList: {e}")
            
            # LibraryService now returns Toga-compatible format directly
            # Create the detailed list with the Toga-compatible data
            # Swipe actions: Delete (left/primary) and Rename (right/secondary) like library view
            self.items_list = toga.DetailedList(
                data=items,  # Direct use of Toga-compatible format
                on_select=self._on_item_selected,
                primary_action="Delete",  # Left swipe = Delete
                on_primary_action=self._on_swipe_delete_item,
                secondary_action="Rename",  # Right swipe = Rename
                on_secondary_action=self._on_swipe_rename_item,
                style=Pack(
                    flex=1,
                    margin=0  # Full width - no margins
                )
            )
            
            if self.content_container:
                self.content_container.add(self.items_list)

            if not items:
                logger.debug("Created empty DetailedList (Mac-style - back button remains functional)")
            else:
                logger.debug(f"Created DetailedList with {len(items)} items in native Toga format")

        except Exception as e:
            logger.error(f"Failed to create collection items list: {e}")

    def _update_items_list(self, force_recreate=False):
        """Update the DetailedList with current collection_items data

        Args:
            force_recreate: If True, recreate the DetailedList widget instead of just updating data.
                          This ensures selection is truly cleared (Toga preserves selection on data update).
        """
        try:
            if hasattr(self, 'items_list') and self.items_list:
                if force_recreate:
                    # Recreate the DetailedList widget to ensure selection is cleared
                    # Get the parent container
                    parent_container = self.items_list.parent if hasattr(self.items_list, 'parent') else None

                    if parent_container and hasattr(parent_container, 'remove'):
                        # Remove old list
                        parent_container.remove(self.items_list)

                        # Create new list with fresh data (no selection)
                        self.items_list = toga.DetailedList(
                            data=self.collection_items,
                            on_select=self._on_item_selected,
                            primary_action="Delete",
                            on_primary_action=self._on_swipe_delete_item,
                            secondary_action="Rename",
                            on_secondary_action=self._on_swipe_rename_item,
                            style=Pack(flex=1, margin=0)
                        )

                        # Add new list back to parent
                        parent_container.add(self.items_list)
                        logger.debug(f"Recreated DetailedList with {len(self.collection_items)} items (no selection)")

                        # Clear output view since selection was cleared by recreation
                        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                            if hasattr(self.app.main_window_wrapper, 'cached_output_view') and self.app.main_window_wrapper.cached_output_view:
                                logger.info("📤 Clearing output view (DetailedList recreated, selection cleared)")
                                self.app.main_window_wrapper.cached_output_view.load_output()
                    else:
                        # Fallback to data update if we can't access parent
                        logger.warning("Cannot recreate DetailedList - parent not accessible, falling back to data update")
                        self.items_list.data = self.collection_items
                        try:
                            self.items_list.selection = None
                        except AttributeError:
                            logger.debug("Could not clear selection (read-only property)")

                        # Clear output view since selection was cleared
                        if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                            if hasattr(self.app.main_window_wrapper, 'cached_output_view') and self.app.main_window_wrapper.cached_output_view:
                                logger.info("📤 Clearing output view (selection cleared in fallback)")
                                self.app.main_window_wrapper.cached_output_view.load_output()
                else:
                    # Just update the data property to refresh the list
                    self.items_list.data = self.collection_items

                    # Reset selection to nothing when updating contents
                    # Note: Toga may still preserve selection index internally
                    try:
                        self.items_list.selection = None
                    except AttributeError:
                        logger.debug("Could not clear selection (read-only property)")

                    logger.debug(f"Updated DetailedList with {len(self.collection_items)} items (selection reset)")

                    # Don't clear output here - this is just a data refresh
                    # Output clearing is handled in _handle_item_navigation and _on_item_selected

            # Update the title label to reflect current folder/collection
            self._update_title()
        except Exception as e:
            logger.error(f"Failed to update items list: {e}")

    def _on_item_selected(self, widget):
        """Handle item selection from detailed list"""
        try:
            # Toga DetailedList gives us the widget
            # widget.selection contains the selected Row object
            if hasattr(widget, 'selection') and widget.selection is not None:
                selected_row = widget.selection

                # Debug: Log all available attributes on the Row object
                logger.debug(f"Row object type: {type(selected_row)}")
                logger.debug(f"Row object attributes: {dir(selected_row)}")
                logger.debug(f"Row object __dict__: {getattr(selected_row, '__dict__', 'No __dict__')}")

                # Try different ways to access the data
                # Method 1: Direct attribute access
                title_direct = getattr(selected_row, 'title', None)
                type_direct = getattr(selected_row, 'type', None)
                is_folder_direct = getattr(selected_row, 'is_folder', None)

                logger.debug(f"Direct access - title: {title_direct}, type: {type_direct}, is_folder: {is_folder_direct}")

                # The Row object has all the attributes we provided in the data
                # Access them directly as Row attributes
                item_data = {
                    'id': getattr(selected_row, 'id', ''),
                    'title': getattr(selected_row, 'title', 'Unknown Item'),
                    'name': getattr(selected_row, 'name', getattr(selected_row, 'title', 'Unknown')),
                    'type': getattr(selected_row, 'type', 'unknown'),
                    'is_folder': getattr(selected_row, 'is_folder', False),
                    'path': getattr(selected_row, 'path', ''),
                    'file_path': getattr(selected_row, 'file_path', '')
                }

                logger.info(f"📌 Item selected: {item_data['title']} (id: {item_data['id']})")
                logger.debug(f"Full item_data extracted: {item_data}")

                # Enable inspector button on mobile when item is selected
                if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                    self.commands['show_inspector'].enable()
                    logger.debug("✅ Enabled 'Show Inspector' button (item selected)")

                # Note: Process button stays enabled always (smart detection)

                # Update inspector with item metadata asynchronously (non-blocking)
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    import asyncio
                    asyncio.create_task(self._update_inspector_async(item_data))

                # Navigate on click (standard behavior)
                # Note: Shift-click to select without navigating would require modifier key detection
                # which Toga's DetailedList doesn't currently expose
                self._handle_item_navigation(item_data)
            else:
                logger.debug("No selection in widget")

                # Disable inspector button on mobile when no selection
                if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                    self.commands['show_inspector'].disable()
                    logger.debug("❌ Disabled 'Show Inspector' button (no selection)")

                # Note: Process button stays enabled always (processes all when no selection)

                # Clear output view when selection is cleared (no item selected)
                if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                    if hasattr(self.app.main_window_wrapper, 'cached_output_view') and self.app.main_window_wrapper.cached_output_view:
                        logger.info("📤 Clearing output view (selection cleared)")
                        self.app.main_window_wrapper.cached_output_view.load_output()

                # Update inspector to show parent folder or collection metadata
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    import asyncio
                    asyncio.create_task(self._update_inspector_with_parent_async())

        except Exception as e:
            logger.error(f"Failed to handle item selection: {e}")
            import traceback
            traceback.print_exc()
    
    def _on_open_item(self, widget, row):
        """Handle open action from swipe gesture"""
        try:
            if row:
                item_name = row.title
                file_path = getattr(row, 'file_path', '')
                logger.info(f"Open requested for item: {item_name}")
                
                # For files, use preview callback to show in right pane
                logger.info(f"FILE NAVIGATION: Opening file: {file_path}")
                
                # Create item data from row attributes
                item_data = {
                    'id': getattr(row, 'id', ''),
                    'title': getattr(row, 'title', 'Unknown Item'),
                    'name': getattr(row, 'name', getattr(row, 'title', 'Unknown')),
                    'type': getattr(row, 'type', 'unknown'),
                    'is_folder': getattr(row, 'is_folder', False),
                    'path': getattr(row, 'path', ''),
                    'file_path': file_path
                }
                
                # Use the preview callback to show in right pane
                print(f"🔧 Attempting preview for: {file_path}")
                print(f"🔧 Preview callback registered: {self.on_file_preview_requested is not None}")
                if self.on_file_preview_requested:
                    print(f"🔧 Calling preview callback...")
                    self.on_file_preview_requested(file_path, item_data)
                    logger.info(f"File preview requested via callback: {file_path}")
                    print(f"✅ Preview callback completed")
                else:
                    print(f"❌ No preview callback registered, using fallback")
                    # Fallback to preview window if no callback registered
                    try:
                        if hasattr(self.app, 'show_preview'):
                            self.app.show_preview(file_path=file_path)
                        else:
                            # Final fallback to system app
                            logger.warning("No preview available, opening with system app")
                            self._open_file(file_path)
                    except Exception as e:
                        logger.error(f"Failed to show preview, falling back to system app: {e}")
                        self._open_file(file_path)
                
        except Exception as e:
            logger.error(f"Failed to handle item open: {e}")
            traceback.print_exc()
    
    def _on_item_info(self, widget, row):
        """Handle info action from swipe gesture"""
        try:
            if row:
                item_name = row.title
                item_subtitle = getattr(row, 'subtitle', '')
                item_description = getattr(row, 'description', '')

                logger.info(f"Info requested for item: {item_name}")

                # Show item information
                info_text = f"Name: {item_name}\n"
                if item_subtitle:
                    info_text += f"Details: {item_subtitle}\n"
                if item_description:
                    info_text += f"Description: {item_description}\n"

                # TODO: Show info dialog
                logger.info(f"Item info: {info_text}")

        except Exception as e:
            logger.error(f"Failed to handle item info: {e}")

    def _on_swipe_delete_item(self, widget, row):
        """Handle delete item swipe action (secondary action)"""
        try:
            if row and hasattr(row, 'item_data'):
                item_data = row.item_data
                item_id = item_data.get('id', '')
                item_name = item_data.get('name', row.title)

                logger.info(f"Swipe delete for item: {item_name}")

                # Delete item from collection
                import asyncio
                asyncio.create_task(self._perform_delete_item(item_id, item_name))
            else:
                logger.warning("No item data found in swipe delete")
        except Exception as e:
            logger.error(f"Failed to handle swipe delete item: {e}")

    def _on_swipe_rename_item(self, widget, row):
        """Handle rename item swipe action"""
        try:
            if row and hasattr(row, 'item_data'):
                item_data = row.item_data
                item_id = item_data.get('id', '')
                item_name = item_data.get('name', row.title)

                logger.info(f"Swipe rename for item: {item_name}")

                # Use NavigationController to navigate to rename view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        # TODO: Implement navigate_to_rename_item in NavigationController
                        success = nav_controller.navigate_to_rename_item(item_id, item_name)
                        if success:
                            logger.info(f"Successfully navigated to rename view for: {item_name}")
                        else:
                            logger.error(f"Failed to navigate to rename view for: {item_name}")
                    else:
                        logger.error("NavigationController not available")
                else:
                    logger.error("view_integration not available")
            else:
                logger.warning("No item data found in swipe rename")
        except Exception as e:
            logger.error(f"Failed to handle swipe rename item: {e}")

    async def _perform_delete_item(self, item_id: str, item_name: str):
        """Perform actual item deletion"""
        try:
            logger.info(f"Deleting item: {item_name} (ID: {item_id})")

            # Delete via library service
            success = await self.library_service.delete_collection_item(item_id)

            if success:
                logger.info(f"✅ Successfully deleted item: {item_name}")
                # Refresh the collection view
                self._load_collection_items()
            else:
                logger.error(f"❌ Failed to delete item: {item_name}")

        except Exception as e:
            logger.error(f"Failed to delete item: {e}")
            import traceback
            traceback.print_exc()

    def _open_file(self, file_path: str):
        """Open a file using the system default application"""
        try:
            import subprocess
            import sys
            from pathlib import Path
            
            path = Path(file_path)
            if not path.exists():
                logger.error(f"File not found: {file_path}")
                return
            
            # Use system default application to open the file
            if sys.platform == "darwin":  # macOS
                subprocess.run(["open", str(path)])
            elif sys.platform == "win32":  # Windows
                subprocess.run(["start", str(path)], shell=True)
            else:  # Linux and others
                subprocess.run(["xdg-open", str(path)])
                
            logger.info(f"Opened file: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to open file {file_path}: {e}")

    async def _update_inspector_async(self, item_data: Dict[str, Any]):
        """Update inspector with item metadata asynchronously (non-blocking)"""
        try:
            if not (hasattr(self.app, 'inspector_window') and self.app.inspector_window):
                return

            # Get full item metadata from database (item_data only has basic fields from Row)
            item_id = item_data.get('id')
            if item_id:
                item = await self.app.library_manager.get_item(item_id)
                if item and item.metadata:
                    # Merge basic fields with database metadata
                    full_metadata = {
                        'id': item_id,
                        'name': item_data.get('name', item_data.get('title', 'Unknown')),
                        'type': item_data.get('type', 'unknown'),
                        'is_folder': item_data.get('is_folder', False),
                    }
                    # Add ALL metadata from database
                    full_metadata.update(item.metadata)

                    logger.info(f"📦 Sending item metadata as dict with {len(full_metadata)} fields (including database metadata)")
                    self.app.inspector_window.update_metadata(full_metadata, selection_type="ITEM")
                else:
                    # No database metadata, use what we have
                    logger.info(f"📦 Sending item metadata as dict with {len(item_data)} fields (no database metadata)")
                    self.app.inspector_window.update_metadata(item_data, selection_type="ITEM")
            else:
                # No item ID, just send what we have
                logger.info(f"📦 Sending item metadata as dict with {len(item_data)} fields (no item ID)")
                self.app.inspector_window.update_metadata(item_data, selection_type="ITEM")

            logger.debug("Inspector updated with item metadata dict (async)")

        except Exception as e:
            logger.error(f"Failed to update inspector asynchronously: {e}")

    async def _update_inspector_with_parent_async(self):
        """Update inspector with parent folder or collection metadata when no item selected"""
        try:
            if not (hasattr(self.app, 'inspector_window') and self.app.inspector_window):
                return

            # If we're in a folder, show folder metadata
            # If we're at root, show collection metadata
            if self.current_path:
                # We're in a subfolder - show folder metadata
                metadata = self._get_current_folder_metadata()
                self.app.inspector_window.update_metadata(metadata, selection_type="FOLDER")
                logger.debug("Inspector updated with folder metadata (async)")
            else:
                # We're at collection root - fetch collection from database and send as dict
                collection_id = self._get_current_collection_id()
                if collection_id and self.library_service and hasattr(self.library_service, 'library_manager'):
                    collection = await self.library_service.library_manager.get_collection(collection_id)
                    if collection:
                        # Pass dictionary directly - inspector supports it
                        collection_data = collection.to_dict()
                        self.app.inspector_window.update_metadata(collection_data, selection_type="COLLECTION")
                        logger.debug(f"Inspector updated with collection dict ({len(collection_data)} fields)")
                    else:
                        logger.warning(f"Collection not found in database: {collection_id}")
                else:
                    logger.warning("Cannot fetch collection - no collection ID or library service")

        except Exception as e:
            logger.error(f"Failed to update inspector with parent metadata: {e}")

    def _get_current_folder_metadata(self) -> Dict[str, Any]:
        """Get metadata for the current folder we're viewing as a dict"""
        try:
            # Build metadata dict for current folder based on path
            folder_name = self.current_path.split('/')[-1] if '/' in self.current_path else self.current_path

            # Start with basic folder info
            metadata_dict = {
                'name': folder_name,
                'path': self.current_path,
                'collection_name': self.collection_name,
                'type': 'folder',
                'is_folder': True,
            }

            # Try to find the folder item in the database to get its full metadata
            folder_item = None
            if self.collection_id:
                all_items = self.app.library_manager.storage.get_collection_items(self.collection_id)
                logger.debug(f"Looking for folder '{folder_name}' among {len(all_items)} items")

                # Find folder by building the path from parent_id chain (more reliable than name matching)
                # First, find all folders
                folders = [item for item in all_items if item.type == "folder"]

                # Build full paths for all folders to find the right one
                for item in folders:
                    # Build path from parent chain
                    path_parts = []
                    current = item
                    visited = set()

                    while current:
                        if current.id in visited:
                            break
                        visited.add(current.id)
                        path_parts.insert(0, current.name)

                        # Find parent
                        if current.parent_id:
                            parent = next((i for i in all_items if i.id == current.parent_id), None)
                            current = parent
                        else:
                            break

                    item_path = '/'.join(path_parts) if path_parts else ''

                    if item_path == self.current_path:
                        folder_item = item
                        logger.debug(f"Found folder item: {item.id} with {len(item.metadata)} metadata fields")
                        break

                if not folder_item:
                    logger.warning(f"Could not find folder item for path '{self.current_path}'")

            # Add folder ID and metadata if found
            if folder_item:
                metadata_dict['id'] = folder_item.id

                # Add ALL metadata from database
                if folder_item.metadata:
                    metadata_dict.update(folder_item.metadata)

            # Add content count
            metadata_dict['total_items'] = len(self.collection_items)

            logger.info(f"📦 Built folder metadata dict with {len(metadata_dict)} fields: {list(metadata_dict.keys())}")
            return metadata_dict

        except Exception as e:
            logger.error(f"Failed to get folder metadata: {e}")
            import traceback
            traceback.print_exc()
            return {'error': 'Error loading folder metadata'}

    def _handle_item_navigation(self, item_data: Dict[str, Any]):
        """Handle navigation to an item or folder (sync version)"""
        try:
            item_name = item_data.get('title', item_data.get('name', 'Unknown'))
            item_type = item_data.get('type', 'unknown')
            is_folder = item_data.get('is_folder', False)
            
            logger.info(f"Navigating to item: {item_name} (type: {item_type}, folder: {is_folder})")
            logger.debug(f"Full item data: {item_data}")
            
            # Handle folder navigation
            if is_folder or item_type == 'folder':
                if item_type == 'back':
                    # Handle ".." back navigation via NavigationController
                    logger.info("FOLDER NAVIGATION: Going back via '..' item using NavigationController")

                    # Clear output view when navigating back (going to folder/collection root)
                    if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                        main_window = self.app.main_window_wrapper
                        if hasattr(main_window, 'cached_output_view') and main_window.cached_output_view:
                            logger.info("📤 Clearing output view (navigating back)")
                            main_window.cached_output_view.load_output()

                    if hasattr(self.app, 'view_integration') and self.app.view_integration:
                        navigation_controller = self.app.view_integration.get_navigation_controller()
                        if navigation_controller:
                            navigation_controller.navigate_back()

                    # Reset selection after navigating back (prevents index-based selection carry-over)
                    if hasattr(self, 'items_list') and self.items_list:
                        try:
                            self.items_list.selection = None
                            logger.debug("🔄 Reset selection after back navigation")
                        except AttributeError:
                            logger.debug("Could not clear selection (read-only property)")
                else:
                    # Regular folder navigation
                    # Use folder ID for navigation (names can be empty/duplicate)
                    folder_id = item_data.get('id', '')
                    folder_name = item_data.get('name', '(unnamed)')
                    logger.info(f"FOLDER NAVIGATION: Navigating to folder: '{folder_name}' (ID: {folder_id})")

                    # Navigate using the folder ID
                    self.navigate_to_folder_by_id(folder_id)

                    # Reset selection after navigating (prevents index-based selection carry-over)
                    if hasattr(self, 'items_list') and self.items_list:
                        try:
                            self.items_list.selection = None
                            logger.debug("🔄 Reset selection after folder navigation")
                        except AttributeError:
                            logger.debug("Could not clear selection (read-only property)")

                    # Clear output view since we're navigating to a folder (not a file)
                    # On desktop: hide right pane or clear its content
                    # On mobile: not relevant since output view is a separate screen
                    if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                        main_window = self.app.main_window_wrapper
                        if hasattr(main_window, 'cached_output_view') and main_window.cached_output_view:
                            # Clear the output view content
                            logger.info("📤 Clearing output view (navigating to folder, not file)")
                            main_window.cached_output_view.load_output()

                    # Update inspector to show folder metadata after navigation
                    if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                        asyncio.create_task(self._update_inspector_with_folder_async(folder_id, folder_name))
            else:
                # Handle file - check if we have a file path
                file_path = item_data.get('file_path')
                if file_path:
                    logger.info(f"FILE NAVIGATION: Opening preview for file: {file_path}")

                    # Load item outputs - this will emit the preview event with output_path if available
                    # If no outputs, it will fall back to emitting without output_path
                    asyncio.create_task(self._load_item_outputs(item_data, file_path))
                else:
                    # No file path - show info
                    logger.info(f"INFO NAVIGATION: Showing info for item")
                    # Create a mock row object for the info call
                    class MockRow:
                        def __init__(self, data):
                            for key, value in data.items():
                                setattr(self, key, value)
                    
                    mock_row = MockRow(item_data)
                    self._on_item_info(None, mock_row)
            
        except Exception as e:
            logger.error(f"Failed to handle item navigation: {e}")
            import traceback
            traceback.print_exc()

    async def _load_item_outputs(self, item_data: Dict[str, Any], file_path: str):
        """Load processing outputs for an item into the OutputView via navigation event

        Always emits a preview event, with filtered output data if processing outputs exist
        """
        try:
            from fichero.shared.navigation.navigation_event_bus import emit_navigation_event

            # Get collection items for file navigation
            collection_items = self.collection_items if hasattr(self, 'collection_items') else []

            # Find current item index
            item_index = 0
            for i, item in enumerate(collection_items):
                if item.get('file_path') == file_path or item.get('path') == file_path:
                    item_index = i
                    break

            # Get file-specific filtered output data via LibraryManager
            item_id = item_data.get('id')
            logger.info(f"📊 Getting filtered outputs - item_id: {item_id}, file_path: {file_path}")

            output_data = None
            if item_id:
                # Call the new library-level filtering API
                output_data = await self.app.library_manager.get_item_output_data(item_id)

                if output_data and output_data.get('has_outputs'):
                    logger.info(f"📊 Found {len(output_data['processing_steps'])} filtered processing steps for item")
                elif output_data:
                    logger.info(f"📊 No processing outputs found for item (not yet processed)")
                else:
                    logger.warning(f"📊 Failed to get output data for item {item_id}")
            else:
                logger.debug("No item ID available - cannot query for outputs")

            # Emit preview event - with or without filtered output data
            event_data = {
                'file_path': str(file_path),
                'file_metadata': item_data,
                'collection_items': collection_items,
                'item_index': item_index,
                'item_id': item_id  # Pass item_id for file-specific filtering
            }

            if output_data and output_data.get('has_outputs'):
                # Pass the filtered output data structure to OutputView
                event_data['output_data'] = output_data
                logger.info(f"📊 Emitting preview event WITH filtered output data ({len(output_data['processing_steps'])} steps)")
            else:
                logger.info(f"📊 Emitting preview event WITHOUT output data (original file only)")

            emit_navigation_event('show_preview', event_data)
            logger.info(f"✅ Emitted preview event for file: {file_path}")

        except Exception as e:
            logger.error(f"Failed to load item outputs: {e}")
            import traceback
            traceback.print_exc()

    def _create_toolbars(self):
        """Create top and bottom toolbars for collection view"""
        try:
            # Create toolbars for both mobile and desktop (like OutputView)
            # Collection is child view - enable automatic mobile back navigation to Library
            self.top_toolbar = TopToolbar(
                app=self.app,
                title="",  # Let NavigationController provide dynamic collection name
                auto_mobile_nav=True,  # Show back button for hierarchical navigation
                is_mobile=self.is_mobile
            )

            self.bottom_toolbar = BottomToolbar(
                app=self.app,
                is_mobile=self.is_mobile
            )

            # Toolbars will be populated automatically by set_toolbars() from command definitions
            self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
            logger.info(f"Toolbars created and set for collection view (mobile={self.is_mobile})")

        except Exception as e:
            logger.error(f"Failed to create collection toolbars: {e}")

    def _add_collection_toolbar_buttons(self):
        """Add collection-specific toolbar buttons"""
        try:
            # Process button is now declared as a FicheroCommand in define_commands()
            # It will be automatically added to toolbars via the command registration system
            logger.debug("Collection toolbar buttons configured via command system")
        except Exception as e:
            logger.error(f"Failed to add collection toolbar buttons: {e}")

    async def _on_process_requested(self, widget):
        """Smart Process handler - process selected item or all items

        Like inspector: if item selected → process it; nothing selected → process all
        """
        try:
            # Use view's collection_id directly (consistent with inspector pattern)
            if not self.collection_id:
                logger.error("No collection ID available")
                return

            logger.info(f"Process clicked - collection_id={self.collection_id}")

            # Check for selected item
            selected_item_id = None
            selected_item_name = None

            if hasattr(self, 'items_list') and self.items_list and self.items_list.selection:
                try:
                    selected_row = self.items_list.selection
                    selected_item_id = getattr(selected_row, 'item_id', None) or getattr(selected_row, 'id', None)
                    selected_item_name = getattr(selected_row, 'title', None) or getattr(selected_row, 'name', None)

                    if selected_item_id:
                        logger.info(f"Processing selected item: {selected_item_name} (id={selected_item_id})")
                except Exception as e:
                    logger.debug(f"Could not get selected item: {e}")

            if not selected_item_id:
                logger.info("No item selected - will process all items in current view")

            # Show processing dialog (handles both single item and all items)
            await self._show_process_dialog(self.collection_id, selected_item_id, selected_item_name)

        except Exception as e:
            logger.error(f"Error handling process request: {e}")
            import traceback
            traceback.print_exc()

    async def _show_process_dialog(self, collection_id: str, selected_item_id: Optional[str] = None, selected_item_name: Optional[str] = None):
        """Show simple confirmation and process directly"""
        try:
            # Get collection first
            collection = await self.app.library_manager.get_collection(collection_id)
            if not collection:
                logger.error("Collection not found")
                # Skip dialog - just return (dialogs cause NSTableView crash)
                return

            # Check if we have items in the database
            all_items = await self.app.library_manager.get_collection_items(collection_id)

            # Determine processing approach based on what we have
            if all_items:
                # We have items in database - use DirectorIntegrationService
                await self._process_via_items(collection_id, collection, all_items, selected_item_id, selected_item_name)
            else:
                # No items in database
                if selected_item_id:
                    # "Process Selected" was clicked but no items in database - show error
                    logger.error("Cannot process selected item: Collection has no items in database. Please index the collection first.")
                    logger.error("Use a 'Scan' or 'Reindex' command to populate the collection with files from the filesystem.")
                    return
                else:
                    # "Process All" was clicked - process folder directly
                    await self._process_via_folder(collection_id, collection)

        except Exception as e:
            logger.error(f"Error in process dialog: {e}")
            # Skip error dialog - just log (dialogs cause NSTableView crash)
            import traceback
            traceback.print_exc()

    async def _process_via_items(self, collection_id: str, collection, all_items, selected_item_id: Optional[str] = None, selected_item_name: Optional[str] = None):
        """Process using DirectorIntegrationService (items from database)"""
        # Determine scope
        if selected_item_id:
            # Use the provided item name from the selection, or fallback to querying
            if selected_item_name:
                scope_text = f"Selected: {selected_item_name}"
            else:
                item = await self.app.library_manager.get_item(selected_item_id)
                scope_text = f"Selected: {item.name}" if item else "All items"
            item_ids = [selected_item_id]
        else:
            # No selection - check if we're in a subfolder
            if self.current_path:
                # In a subfolder - process the folder itself, not individual files
                # Find the folder item for the current path
                folder_item = None
                for item in all_items:
                    if item.type == 'folder':
                        # Build path from parent hierarchy
                        path_parts = []
                        current_item = item
                        while current_item:
                            path_parts.insert(0, current_item.name)
                            if current_item.parent_id:
                                # Find parent in all_items
                                parent_item = next((i for i in all_items if i.id == current_item.parent_id), None)
                                current_item = parent_item
                            else:
                                break

                        item_path = '/'.join(path_parts) if path_parts else ''

                        if item_path == self.current_path:
                            folder_item = item
                            logger.debug(f"Found folder item for '{self.current_path}': {item.id}")
                            break

                if folder_item:
                    # Process the folder as a single item
                    item_ids = [folder_item.id]
                    scope_text = f"Folder: {folder_item.name}"
                    logger.info(f"Processing folder '{folder_item.name}' (path: '{self.current_path}')")
                else:
                    logger.warning(f"Could not find folder item for path '{self.current_path}', falling back to visible files")
                    # Fallback: collect visible files
                    visible_items = []
                    if hasattr(self, 'items_list') and self.items_list and hasattr(self.items_list, 'data'):
                        try:
                            for row in self.items_list.data:
                                item_id = getattr(row, 'item_id', None) or getattr(row, 'id', None)
                                if item_id:
                                    item_type = getattr(row, 'type', 'file')
                                    if item_type == 'file':
                                        visible_items.append(item_id)
                        except Exception as e:
                            logger.warning(f"Could not get visible items from table: {e}")

                    if visible_items:
                        item_ids = visible_items
                        folder_context = f" in '{self.current_path}'"
                        scope_text = f"{len(item_ids)} visible files{folder_context}"
                        logger.info(f"Processing {len(item_ids)} visible files in current folder{folder_context}")
                    else:
                        # Last resort: all items
                        item_ids = [item.id for item in all_items]
                        scope_text = f"All {len(all_items)} items"
                        logger.info(f"No visible items found, processing all {len(all_items)} items")
            else:
                # At collection root - collect visible files
                visible_items = []
                if hasattr(self, 'items_list') and self.items_list and hasattr(self.items_list, 'data'):
                    try:
                        for row in self.items_list.data:
                            # Extract item ID from the row
                            item_id = getattr(row, 'item_id', None) or getattr(row, 'id', None)
                            if item_id:
                                # Only include file items, not folder items
                                item_type = getattr(row, 'type', 'file')
                                if item_type == 'file':
                                    visible_items.append(item_id)
                    except Exception as e:
                        logger.warning(f"Could not get visible items from table: {e}")

                # If we got visible items, use those; otherwise fall back to all items
                if visible_items:
                    item_ids = visible_items
                    scope_text = f"{len(item_ids)} visible files (at collection root, as catalogue)"
                    logger.info(f"Processing {len(item_ids)} visible files at collection root as catalogue unit")
                else:
                    # Fallback to all items (original behavior)
                    item_ids = [item.id for item in all_items]
                    scope_text = f"All {len(all_items)} items"
                    logger.info(f"No visible items found in table, processing all {len(all_items)} items")

        # Get item names for confirmation dialog
        item_names = []
        for idx, item_id in enumerate(item_ids[:5]):  # Show first 5 items
            # For the first item (if it's the selected item), use the provided name
            if idx == 0 and selected_item_id == item_id and selected_item_name:
                name = selected_item_name[:50] + "..." if len(selected_item_name) > 50 else selected_item_name
                item_names.append(f"  • {name}")
            else:
                # Query the library manager for other items
                item = await self.app.library_manager.get_item(item_id)
                if item:
                    # Show item name and truncate if too long
                    name = item.name[:50] + "..." if len(item.name) > 50 else item.name
                    item_names.append(f"  • {name}")

        item_list = "\n".join(item_names)
        if len(item_ids) > 5:
            item_list += f"\n  ... and {len(item_ids) - 5} more"

        # Skip confirmation dialog - just proceed directly (dialogs cause NSTableView crash)
        logger.info(f"Processing {len(item_ids)} items directly (no confirmation dialog to avoid crash)")
        logger.info(f"Collection: {collection.name}")
        logger.info(f"Items:\n{item_list}")
        logger.info(f"Plan: Default, Workflow: Catalogue")

        # Check director integration service
        if not hasattr(self.app, 'director_integration'):
            logger.error("DirectorIntegrationService not available")
            # Skip dialog - just return (dialogs cause NSTableView crash)
            return

        logger.info(f"Processing {len(item_ids)} items via DirectorIntegrationService")
        logger.info(f"Item IDs to process: {item_ids}")
        logger.info(f"Collection ID: {collection_id}")

        # Process items
        # Use first workflow from the plan (typically "Catalogue")
        try:
            logger.info("Calling director_integration.process_items()...")
            task_ids = await self.app.director_integration.process_items(
                collection_id=collection_id,
                item_ids=item_ids,
                plan_name="Default",
                workflow_name="Catalogue"  # Changed from "default" to match actual workflow in plan
            )
            logger.info(f"✅ process_items() returned: {task_ids}")
        except Exception as process_error:
            logger.error(f"❌ CRASH in process_items(): {process_error}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            raise  # Re-raise to show error dialog

        logger.info(f"✅ Submitted {len(task_ids)} task(s) to Director: {task_ids}")

        # Open Activity Window to show processing progress
        if hasattr(self.app, 'show_activity_monitor'):
            self.app.show_activity_monitor()
            logger.info("🪟 Opened Activity Window to show processing progress")
        elif hasattr(self.app, 'activity_monitor_window') and self.app.activity_monitor_window:
            # Fallback: Force Activity Monitor to refresh if already visible
            if self.app.activity_monitor_window.is_visible:
                logger.info("Forcing Activity Monitor refresh after task submission")
                try:
                    content = self.app.activity_monitor_window.activity_content
                    if hasattr(content, 'display') and content.display:
                        content.display.refresh_tasks()
                except Exception as e:
                    logger.error(f"Failed to refresh Activity Monitor: {e}")

        # Log success (skip dialog to avoid NSTableView crash)
        logger.info(f"✅ Processing started successfully!")
        logger.info(f"Submitted {len(task_ids)} task(s) to Director")
        logger.info(f"Task IDs: {', '.join(str(tid)[:8] + '...' for tid in task_ids)}")
        logger.info(f"Processing will run in the background. Check Activity Monitor for progress.")

    async def _process_via_folder(self, collection_id: str, collection):
        """Process using Director directly (folder on disk, no database items)"""
        # Skip confirmation dialog - just proceed directly (dialogs cause NSTableView crash)
        logger.info(f"Processing folder directly (no confirmation dialog to avoid crash)")
        logger.info(f"Collection: {collection.name}")
        logger.info(f"Plan: Default, Workflow: Catalogue")

        # Get the collection folder path
        collection_path = collection.local_path or collection.source_path
        if not collection_path:
            logger.error("No path available for collection")
            # Skip dialog - just return (dialogs cause NSTableView crash)
            return

        from pathlib import Path
        if not Path(collection_path).exists():
            logger.error(f"Path not found: {collection_path}")
            # Skip dialog - just return (dialogs cause NSTableView crash)
            return

        logger.info(f"Processing collection folder: {collection_path}")

        # Generate output path - align with DirectorIntegrationService logic
        # ALWAYS use library's output folder, never the source content folder
        if collection.local_path:
            # Collection has a library location - use local_path/outputs
            output_base = Path(collection.local_path) / "outputs"
            logger.info(f"Using collection's library path for outputs: {output_base}")
        else:
            # No library location - use app data library default
            output_base = Path(self.app.paths.data) / "library" / "outputs"
            logger.info(f"Using library default output path: {output_base}")

        output_base.mkdir(parents=True, exist_ok=True)

        # Create progress callback for real-time updates
        def progress_callback(event_type: str, task_info):
            """Handle progress updates from Director"""
            try:
                logger.info(f"Progress: {event_type} - Task {task_info.task_id}: {task_info.overall_progress}%")
                # In the future, we could update a progress bar here
            except Exception as e:
                logger.error(f"Error in progress callback: {e}")

        # Use Director's process_with_auto_detection for folder processing
        # Note: Director coordinator may not support progress_callback parameter yet
        try:
            task_ids = self.app.director.processing_coordinator.process_with_auto_detection(
                input_path=Path(collection_path),
                output_path=output_base,
                plan_name="Default",
                workflow_name="Catalogue",  # Changed from "default" to match actual workflow in plan
                progress_callback=progress_callback
            )
        except TypeError:
            # Fallback if progress_callback parameter not supported
            logger.info("Director doesn't support progress_callback, processing without progress updates")
            task_ids = self.app.director.processing_coordinator.process_with_auto_detection(
                input_path=Path(collection_path),
                output_path=output_base,
                plan_name="Default",
                workflow_name="Catalogue"  # Changed from "default" to match actual workflow in plan
            )

        # Open Activity Window to show processing progress
        if hasattr(self.app, 'show_activity_monitor'):
            self.app.show_activity_monitor()
            logger.info("🪟 Opened Activity Window to show processing progress")

        # Log success (skip dialog to avoid NSTableView crash)
        logger.info(f"✅ Processing started successfully!")
        logger.info(f"Submitted {len(task_ids)} task(s) to Director")
        logger.info(f"Output location: {output_base}")
        logger.info(f"Processing will run in the background")

    def _register_navigation_controller_callbacks(self):
        """Register callbacks with NavigationController for state changes"""
        try:
            # Skip if already registered to prevent duplicates
            if hasattr(self, '_nav_callback_ref'):
                logger.debug("Collection view already registered - skipping duplicate registration")
                return

            navigation_controller = self._get_navigation_controller()
            if navigation_controller:
                # Store callback reference for later cleanup
                self._nav_callback_ref = self._on_navigation_state_changed
                navigation_controller.add_callback('state_changed', self._nav_callback_ref)
                logger.debug("Collection view registered for NavigationController state changes")
            else:
                logger.warning("NavigationController not available for callback registration")
        except Exception as e:
            logger.error(f"Failed to register NavigationController callbacks: {e}")

    def cleanup_callbacks(self):
        """Unregister ALL callbacks to prevent duplicate events and memory leaks"""
        try:
            # Unregister NavigationController state_changed callback
            if hasattr(self, '_nav_callback_ref'):
                navigation_controller = self._get_navigation_controller()
                if navigation_controller:
                    navigation_controller.remove_callback('state_changed', self._nav_callback_ref)
                    logger.debug("Collection view unregistered NavigationController callback")
                    delattr(self, '_nav_callback_ref')

            # Unsubscribe from navigation event bus events (only if we subscribed)
            if hasattr(self, '_events_subscribed') and self._events_subscribed:
                from fichero.shared.navigation.navigation_event_bus import unsubscribe_from_navigation
                unsubscribe_from_navigation("collection_deleted", self._on_collection_deleted_event)
                unsubscribe_from_navigation("collection_updated", self._on_collection_updated_event)
                unsubscribe_from_navigation("collection_items_changed", self._on_collection_items_changed_event)
                unsubscribe_from_navigation("collection_item_updated", self._on_item_progress_updated)
                unsubscribe_from_navigation("processing_completed", self._on_processing_completed)
                unsubscribe_from_navigation("folder_import_started", self._on_folder_import_started)
                unsubscribe_from_navigation("folder_import_progress", self._on_folder_import_progress)
                unsubscribe_from_navigation("folder_import_completed", self._on_folder_import_completed)
                delattr(self, '_events_subscribed')
                logger.debug("Collection view unsubscribed from navigation event bus")

        except Exception as e:
            logger.error(f"Failed to cleanup CollectionView callbacks: {e}")

    def _on_navigation_state_changed(self, navigation_state):
        """Handle NavigationController state changes - update UI accordingly"""
        try:
            # Prevent infinite callback loops
            if self._updating_from_navigation_callback:
                logger.debug("🔄 Skipping navigation state change - already updating from callback")
                return

            self._updating_from_navigation_callback = True

            try:
                from fichero.shared.navigation.navigation_state import NavigationContext

                logger.info(f"🔄 Navigation state changed: {navigation_state.context.value}")

                # Only update UI if we're in a collection context
                if navigation_state.context == NavigationContext.COLLECTION:
                    # Check if this is our collection OR if collection changed
                    new_collection_id = navigation_state.collection_id
                    new_path = navigation_state.current_path or ""

                    collection_changed = (new_collection_id != self.collection_id)
                    path_changed = (new_path != self.current_path)

                    if collection_changed or path_changed:
                        if collection_changed:
                            logger.info(f"🔄 Collection changed from '{self.collection_id}' to '{new_collection_id}' - updating UI")
                        if path_changed:
                            logger.info(f"🔄 Path changed from '{self.current_path}' to '{new_path}' - updating UI")

                        # Update our local state to match NavigationController
                        self.collection_id = new_collection_id
                        self.collection_name = navigation_state.collection_name or new_collection_id
                        self.current_path = new_path

                        # Update UI elements
                        self._update_breadcrumbs()

                        # Update toolbar navigation state (show/hide back button based on path)
                        if hasattr(self, 'top_toolbar') and self.top_toolbar:
                            self.top_toolbar.update_navigation_state(self.current_path)

                        # Reload items for new collection/path - use silent version to avoid navigation events
                        self._load_collection_items_silent()

                        # Update inspector with parent/collection metadata (no item selected after path change)
                        if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                            import asyncio
                            asyncio.create_task(self._update_inspector_with_parent_async())

                        logger.info(f"✅ UI updated for collection: '{new_collection_id}', path: '{self.current_path}'")
                    else:
                        logger.debug(f"🔄 Collection and path unchanged - skipping reload")
                else:
                    logger.debug(f"State change for different context: {navigation_state.context.value}")
            finally:
                self._updating_from_navigation_callback = False

        except Exception as e:
            logger.error(f"Failed to handle navigation state change: {e}")
            self._updating_from_navigation_callback = False

    
    def _on_add_dialog_requested(self):
        """Handle add dialog request from toolbar"""
        try:
            logger.info("Add dialog requested from edit mode")
            if hasattr(self.app, 'show_add_dialog'):
                self.app.show_add_dialog()
            else:
                logger.warning("Add dialog not available")
        except Exception as e:
            logger.error(f"Failed to show add dialog: {e}")
    
    def _on_activity_monitor(self):
        """Handle activity monitor request"""
        try:
            logger.info("Activity monitor requested")
            if hasattr(self.app, 'show_activity_monitor'):
                self.app.show_activity_monitor()
            else:
                logger.warning("Activity monitor not available")
        except Exception as e:
            logger.error(f"Failed to show activity monitor: {e}")
    
    def _on_collection_settings(self):
        """Handle collection settings action"""
        try:
            logger.info("Collection settings requested")
            # Collection settings functionality would go here
            logger.warning("Collection settings not yet implemented")
        except Exception as e:
            logger.error(f"Failed to show collection settings: {e}")
    
    def _on_process_collection(self):
        """Handle process collection action"""
        logger.debug("Process collection requested")
        # This would typically start collection processing
        if hasattr(self, 'on_process_collection') and self.on_process_collection:
            self.on_process_collection()
    
    def _on_export_collection(self):
        """Handle export collection action"""
        logger.debug("Export collection requested")
        # This would typically open an export dialog
        if hasattr(self, 'on_export_collection') and self.on_export_collection:
            self.on_export_collection()
    
    def set_collection_name(self, name: str):
        """Set the collection name"""
        self.collection_name = name
        if self.top_toolbar:
            self.top_toolbar.update_collection_name(name)
    
    def add_collection(self, collection_data: Dict[str, Any]):
        """Add a collection to the view"""
        try:
            # Add to collections list
            self.collections.append(collection_data)
            
            # Create collection item widget
            collection_item = self._create_collection_item(collection_data)
            
            # Add to scroll container
            self.scroll_container.add_content(collection_item)
            
            # Collection count updated
            pass
            
            logger.debug(f"Collection added: {collection_data.get('name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to add collection: {e}")
    
    def _create_collection_item(self, collection_data: Dict[str, Any]) -> toga.Widget:
        """Create a widget for a collection item"""
        try:
            # Create collection item container
            item_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(10, 15),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Collection icon
            icon_label = toga.Label(
                "📁",
                style=Pack(
                    font_size=24,
                    margin=(0, 10, 0, 0)
                )
            )
            item_container.add(icon_label)
            
            # Collection info
            info_container = toga.Box(
                style=Pack(direction=COLUMN, flex=1)
            )
            
            # Collection name
            name_label = toga.Label(
                collection_data.get('name', 'Unknown Collection'),
                style=Pack(
                    font_size=16,
                    font_weight="bold",
                    color=self.text_color
                )
            )
            info_container.add(name_label)
            
            # Collection description
            description = collection_data.get('description', 'No description available')
            desc_label = toga.Label(
                description,
                style=Pack(
                    margin=(5, 0, 0, 0),
                    color=self.text_color
                )
            )
            info_container.add(desc_label)
            
            # Collection metadata
            metadata = f"Type: {collection_data.get('type', 'Unknown')} | Items: {collection_data.get('item_count', 0)}"
            meta_label = toga.Label(
                metadata,
                style=Pack(
                    margin=(5, 0, 0, 0),
                    font_size=12,
                    color="#666666"
                )
            )
            info_container.add(meta_label)
            
            item_container.add(info_container)
            
            # Action buttons
            actions_container = toga.Box(
                style=Pack(direction=COLUMN, margin=(10, 0, 0, 0))
            )
            
            # Open button
            open_button = toga.Button(
                "Open",
                on_press=lambda widget: self._on_open_collection(collection_data),
                style=Pack(
                    margin=(8, 12),
                    background_color=self.accent_color
                )
            )
            actions_container.add(open_button)
            
            # Settings button
            settings_button = toga.Button(
                "⚙️",
                on_press=lambda widget: self._on_collection_settings(),
                style=Pack(
                    margin=(8, 12),
                    background_color="#F0F0F0"
                )
            )
            actions_container.add(settings_button)
            
            item_container.add(actions_container)
            
            return item_container
            
        except Exception as e:
            logger.error(f"Failed to create collection item: {e}")
            # Return fallback widget
            return toga.Label(f"Error creating collection item: {e}")
    
    def _on_open_collection(self, collection_data: Dict[str, Any]):
        """Handle opening a collection"""
        logger.debug(f"Opening collection: {collection_data.get('name', 'Unknown')}")
        # This would typically navigate to the collection view
        if hasattr(self, 'on_open_collection') and self.on_open_collection:
            self.on_open_collection(collection_data)
    
    def remove_collection(self, collection_id: str):
        """Remove a collection from the view"""
        try:
            # Find and remove from collections list
            for i, collection in enumerate(self.collections):
                if collection.get('id') == collection_id:
                    self.collections.pop(i)
                    
                    # Remove from scroll container
                    if i < len(self.scroll_container.content_widgets):
                        widget = self.scroll_container.get_content_at_index(i)
                        if widget:
                            self.scroll_container.remove_content(widget)
                    
                    # Collection count updated
                    pass
                    
                    logger.debug(f"Collection removed: {collection_id}")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to remove collection: {e}")
    
    def clear_collections(self):
        """Clear all collections from the view"""
        try:
            self.collections.clear()
            self.scroll_container.clear_content()
            
            # Recreate placeholder content
            self._create_content() # This now handles the placeholder
            
            # Collection count updated
            pass
            
            logger.debug("All collections cleared")
            
        except Exception as e:
            logger.error(f"Failed to clear collections: {e}")
    
    def refresh_collections(self):
        """Refresh the collections display"""
        try:
            # Clear current content
            self.scroll_container.clear_content()
            
            # Recreate content
            self._create_content()
            
            # Re-add all collections
            for collection in self.collections:
                collection_item = self._create_collection_item(collection)
                self.scroll_container.add_content(collection_item)
            
            logger.debug("Collections refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh collections: {e}")
    
    def set_processing_state(self, is_processing: bool):
        """Set the processing state of the collection"""
        if self.bottom_toolbar:
            self.bottom_toolbar.set_processing_state(is_processing)
    
    def set_export_available(self, available: bool):
        """Set whether export is available"""
        if self.bottom_toolbar:
            self.bottom_toolbar.set_export_available(available)
    
    def register_callbacks(self,
                         on_back_to_library: Optional[Any] = None,
                         on_add_folder: Optional[Any] = None,
                         on_add_file: Optional[Any] = None,
                         on_collection_settings: Optional[Any] = None,
                         on_process_collection: Optional[Any] = None,
                         on_export_collection: Optional[Any] = None,
                         on_open_collection: Optional[Any] = None):
        """Register callbacks for collection actions"""
        self.on_back_to_library = on_back_to_library
        self.on_add_folder = on_add_folder
        self.on_add_file = on_add_file
        self.on_collection_settings = on_collection_settings
        self.on_process_collection = on_process_collection
        self.on_export_collection = on_export_collection
        self.on_open_collection = on_open_collection

        # ✅ FIX: Pass back navigation callback to top toolbar for desktop back button
        if self.top_toolbar and on_back_to_library:
            self.top_toolbar.on_back = on_back_to_library
            self.top_toolbar.on_back_to_library = on_back_to_library
            logger.debug("🔙 Desktop back navigation callback passed to collection top toolbar")

        logger.debug("Collection view callbacks registered")
    
    def register_preview_callback(self, callback: Callable):
        """Register callback for file preview requests"""
        self.on_file_preview_requested = callback

    def _on_preview_file_from_toolbar(self, file_data: Dict[str, Any]):
        """Handle preview file request from bottom toolbar"""
        try:
            if not file_data:
                logger.warning("No file data provided for preview")
                return

            file_path = file_data.get('file_path') or file_data.get('name')
            if not file_path:
                logger.warning("No file path found in file data for preview")
                return

            logger.info(f"Preview requested from toolbar for file: {file_path}")

            # Use the registered preview callback
            if self.on_file_preview_requested:
                self.on_file_preview_requested(file_path, file_data)
            else:
                logger.warning("No preview callback registered")

        except Exception as e:
            logger.error(f"Failed to handle preview from toolbar: {e}")
    
    def _on_initialize(self):
        """Called when view is initialized"""
        try:
            # Set up collection-specific features
            logger.debug("Collection view initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize collection view: {e}")
    
    def _setup_scroll_integration(self):
        """Set up scroll container integration"""
        try:
            # Ensure scroll container is properly integrated with the view
            if self.scroll_container and self.content_container:
                # Native Toga ScrollContainer doesn't have these custom methods
                # The scroll container is already configured properly in BaseView
                logger.debug("Scroll container integration set up successfully")
                
        except Exception as e:
            logger.error(f"Failed to set up scroll integration: {e}")

    def _initialize_library_manager(self):
        """Use shared library service from app"""
        try:
            # Use the shared library service from the app (not just the manager)
            self.library_service = self.app.library_service
            if self.library_service:
                logger.info("Using shared library service from app")
            else:
                logger.warning("No shared library service available in app")
        except Exception as e:
            logger.error(f"Failed to get shared library service: {e}")
            self.library_service = None
    
    
    def set_collection_id(self, collection_id: str):
        """Set the current collection ID and load its items"""
        self.collection_id = collection_id
        self._load_collection_items()
    
    def _load_collection_items(self):
        """Load items for the current collection and path"""
        try:
            logger.debug(f"📋 _load_collection_items called for instance {id(self)}")
            logger.debug(f"   collection_id: {getattr(self, 'collection_id', 'NOT SET')}")
            logger.debug(f"   library_service: {getattr(self, 'library_service', 'NOT SET')}")

            if self.library_service and hasattr(self, 'collection_id') and self.collection_id:
                # Use hierarchical structure method for folder navigation
                logger.info(f"📥 Loading hierarchical structure for collection {self.collection_id}, path: '{self.current_path}'")
                self.collection_items = self.library_service.get_collection_structure_sync(
                    self.collection_id,
                    self.current_path
                )

                # Debug: Log what we got back
                logger.info(f"Received {len(self.collection_items)} items from hierarchical structure")
                if self.collection_items:
                    first_item = self.collection_items[0]
                    logger.info(f"First item: title='{first_item.get('title', 'NO_TITLE')}', type='{first_item.get('type', 'NO_TYPE')}', is_folder={first_item.get('is_folder', 'NO_IS_FOLDER')}")

                # Update breadcrumbs
                self._update_breadcrumbs()

                # Always recreate content on navigation changes to update title
                # The title label needs to reflect the current collection name or folder path
                logger.debug("Using _create_content for navigation changes (updates title)")
                self._create_content()

                logger.debug(f"Loaded {len(self.collection_items)} items for collection {self.collection_id} at path '{self.current_path}'")

                # Start async thumbnail generation in background
                import asyncio
                asyncio.create_task(self._load_thumbnails_async())
            else:
                logger.warning("Library service not initialized or no collection ID set")
                self._create_content() # This now handles the placeholder

        except Exception as e:
            logger.error(f"Failed to load collection items: {e}")

    def _load_collection_items_silent(self):
        """Load items for the current collection and path - SILENT VERSION without navigation events"""
        try:
            if self.library_service and hasattr(self, 'collection_id') and self.collection_id:
                # Use hierarchical structure method for folder navigation
                logger.debug(f"SILENT: Loading hierarchical structure for collection {self.collection_id}, path: '{self.current_path}'")
                self.collection_items = self.library_service.get_collection_structure_sync(
                    self.collection_id,
                    self.current_path
                )

                # Debug: Log what we got back
                logger.debug(f"SILENT: Received {len(self.collection_items)} items from hierarchical structure")

                # Check if we have an existing items list to update
                if hasattr(self, 'items_list') and self.items_list and self.collection_items:
                    # Recreate the DetailedList to clear selection completely
                    # Toga preserves selection index when just updating data
                    logger.debug("SILENT: Using _update_items_list with force_recreate to clear selection")
                    self._update_items_list(force_recreate=True)
                else:
                    # No existing list or no items - recreate content
                    logger.debug("SILENT: Using _create_content for full rebuild")
                    self._create_content()

                logger.debug(f"SILENT: Loaded {len(self.collection_items)} items for collection {self.collection_id} at path '{self.current_path}'")
            else:
                logger.warning("SILENT: Library service not initialized or no collection ID set")
                self._create_content() # This now handles the placeholder

        except Exception as e:
            logger.error(f"SILENT: Failed to load collection items: {e}")
    
    def _get_current_folder_display_name(self):
        """Get the display name for the current folder"""
        try:
            if not self.current_path:
                # At collection root - show collection name
                return getattr(self, 'collection_name', 'Collection')
            else:
                # In a subfolder - show the current folder name
                path_parts = self.current_path.split('/')
                return path_parts[-1]  # Last part is current folder
        except Exception as e:
            logger.error(f"Failed to get current folder display name: {e}")
            return "Folder"
    
    def _update_breadcrumbs(self):
        """Update breadcrumb display in toolbar"""
        try:
            if hasattr(self.top_toolbar, 'update_breadcrumbs'):
                collection_name = getattr(self, 'collection_name', 'Collection')
                self.top_toolbar.update_breadcrumbs(collection_name, self.current_path)
        except Exception as e:
            logger.error(f"Failed to update breadcrumbs: {e}")

    async def _load_thumbnails_async(self):
        """Load thumbnails asynchronously in background without blocking UI"""
        try:
            import asyncio
            from pathlib import Path

            if not self.collection_items:
                return

            logger.info(f"🎨 Starting async thumbnail generation for {len(self.collection_items)} items")

            # Generate thumbnails for image files (skip folders and non-images)
            generated_count = 0
            skipped_count = 0
            for idx, item in enumerate(self.collection_items):
                # Skip folders (they already have folder icons)
                if item.get('is_folder', False):
                    logger.debug(f"Skipping folder: {item.get('title', 'unknown')}")
                    skipped_count += 1
                    continue

                # Skip if already has an icon (not None)
                if item.get('icon') is not None:
                    logger.debug(f"Skipping item with existing icon: {item.get('title', 'unknown')}")
                    skipped_count += 1
                    continue

                # Get file path
                file_path = item.get('file_path')
                if not file_path:
                    logger.debug(f"No file_path for: {item.get('title', 'unknown')}")
                    skipped_count += 1
                    continue

                try:
                    # Check if this is a URL item (starts with http:// or https://)
                    if isinstance(file_path, str) and file_path.startswith(('http://', 'https://')):
                        # URL item - use a generic URL icon instead of thumbnail
                        logger.debug(f"URL item detected: {item.get('title', 'unknown')} -> {file_path[:50]}...")

                        # Try to load a URL icon from resources
                        try:
                            import toga
                            url_icon_path = self.app.paths.app / "resources" / "icons" / "url_icon.png"
                            if url_icon_path.exists():
                                icon = toga.Image(str(url_icon_path))
                            else:
                                # Fallback: use link emoji as string (will show as text in DetailedList)
                                icon = "🔗"
                                logger.debug(f"URL icon not found at {url_icon_path}, using emoji")
                        except Exception as e:
                            logger.debug(f"Failed to load URL icon: {e}")
                            icon = "🔗"  # Fallback emoji

                        if icon:
                            item['icon'] = icon
                            generated_count += 1
                            logger.debug(f"✅ Set URL icon for {item.get('title', 'unknown')}")

                            # Update DetailedList
                            if hasattr(self, 'items_list') and self.items_list:
                                self.items_list.data = self.collection_items

                        skipped_count += 1
                        continue

                    # Local file - generate thumbnail
                    path = Path(file_path)

                    # Check if file exists before trying to generate thumbnail
                    if not path.exists():
                        logger.debug(f"File does not exist: {path}")
                        skipped_count += 1
                        continue

                    # Generate thumbnail using library (runs in thread pool via asyncio)
                    icon = await asyncio.to_thread(
                        self.app.library_manager.get_filesystem_icon,
                        path,
                        None,  # size
                        True   # generate=True
                    )

                    if icon:
                        # Update the item with the new icon
                        item['icon'] = icon
                        generated_count += 1
                        logger.info(f"✅ Generated thumbnail {generated_count}/{len(self.collection_items)}: {path.name}")

                        # Update DetailedList data to show the new icon
                        # Toga DetailedList automatically refreshes when data changes
                        if hasattr(self, 'items_list') and self.items_list:
                            self.items_list.data = self.collection_items
                            # Note: Don't reset selection here during thumbnail generation
                            # We only reset when navigating/changing folders
                    else:
                        logger.warning(f"❌ No icon returned for: {path.name}")

                except Exception as e:
                    logger.error(f"Failed to generate thumbnail for {file_path}: {e}")
                    continue

            logger.info(f"✅ Async thumbnail generation completed: {generated_count} generated, {skipped_count} skipped")

        except Exception as e:
            logger.error(f"Failed in async thumbnail loading: {e}")

    def navigate_to_folder(self, folder_path: str):
        """Navigate into a folder using NavigationController"""
        try:
            # Calculate the new full path
            if folder_path == "" or folder_path == ".":
                # Going to root
                new_path = ""
            elif self.current_path:
                # Append folder to current path
                new_path = f"{self.current_path.rstrip('/')}/{folder_path.strip('/')}"
            else:
                # Starting from root
                new_path = folder_path.strip('/')

            # Use NavigationController for path navigation - NO FALLBACKS!
            navigation_controller = self._get_navigation_controller()
            if not navigation_controller:
                logger.error("❌ NavigationController not available - cannot navigate!")
                raise RuntimeError("NavigationController not available")

            logger.info(f"🔙 Collection: Using NavigationController to navigate to path: '{new_path}'")
            success = navigation_controller.navigate_to_path(new_path)
            if not success:
                logger.error(f"❌ NavigationController: Failed to navigate to path: '{new_path}'")
                raise RuntimeError(f"NavigationController failed to navigate to path: '{new_path}'")

            logger.info(f"Navigated to folder: '{folder_path}', current path: '{self.current_path}'")

        except Exception as e:
            logger.error(f"Failed to navigate to folder: {e}")

    def navigate_to_folder_by_id(self, folder_id: str):
        """Navigate to a folder using its ID (builds path by walking parent_id chain)"""
        try:
            # Get all items to build the path
            all_items = self.app.library_manager.storage.get_collection_items(self.collection_id)

            # Build a map of item IDs to items
            id_to_item = {item.id: item for item in all_items}

            # Walk up the parent chain to build the full path
            path_parts = []
            current_id = folder_id

            while current_id:
                if current_id not in id_to_item:
                    logger.error(f"❌ Folder ID {current_id} not found in collection")
                    return

                item = id_to_item[current_id]
                if item.type != "folder":
                    logger.error(f"❌ Item {current_id} is not a folder (type: {item.type})")
                    return

                # Insert folder name at the beginning of path
                path_parts.insert(0, item.name)
                current_id = item.parent_id

            # Build the full path
            new_path = '/'.join(path_parts) if path_parts else ''

            logger.info(f"🔙 Built path from ID {folder_id}: '{new_path}'")

            # Use NavigationController for path navigation
            navigation_controller = self._get_navigation_controller()
            if not navigation_controller:
                logger.error("❌ NavigationController not available")
                return

            # Ensure NavigationController has correct collection context
            if navigation_controller.current_state.collection_id != self.collection_id:
                logger.warning(f"NavigationController collection context mismatch: expected {self.collection_id}, got {navigation_controller.current_state.collection_id}")
                # Re-set collection context
                navigation_controller.navigate_to_collection(self.collection_id, self.collection_name)

            # Navigate to path within current collection
            success = navigation_controller.navigate_to_path(new_path)
            if not success:
                logger.error(f"❌ Failed to navigate to path: '{new_path}'")
            else:
                logger.info(f"✅ Navigated to folder ID {folder_id}, path: '{new_path}'")

        except Exception as e:
            logger.error(f"Failed to navigate to folder by ID: {e}")

    async def _update_inspector_with_folder_async(self, folder_id: str, folder_name: str):
        """Update inspector with folder metadata when navigating to a folder"""
        try:
            if not (hasattr(self.app, 'inspector_window') and self.app.inspector_window):
                return

            # Get folder metadata from database
            item = await self.app.library_manager.get_item(folder_id)
            if not item:
                logger.warning(f"Could not find folder {folder_id} for inspector update")
                return

            # Send metadata as dictionary (direct pass-through from database)
            logger.info(f"📦 Sending folder metadata as dict with {len(item.metadata) if item.metadata else 0} fields")

            # Build metadata dict with all fields
            metadata_dict = {
                'name': folder_name or '(unnamed folder)',
                'type': 'Folder',
                'id': folder_id,
            }

            # Add ALL metadata from database
            if item.metadata:
                metadata_dict.update(item.metadata)

            logger.info(f"📦 Total metadata dict has {len(metadata_dict)} fields: {list(metadata_dict.keys())}")

            # Send dict directly to inspector (no text parsing needed!)
            self.app.inspector_window.update_metadata(metadata_dict, selection_type="FOLDER")
            logger.debug(f"Inspector updated with folder metadata dict for {folder_name}")
            return

            # OLD TEXT-BASED CODE BELOW (keeping for reference, but skipped by return above)
            lines = [
                "=== FOLDER METADATA ===",
                "",
                f"Name: {folder_name or '(unnamed folder)'}",
                f"Type: Folder",
                f"ID: {folder_id}",
            ]

            # Include ALL metadata (just like in _get_current_folder_metadata)
            if item.metadata:
                folder_data = item.metadata

                # IIIF metadata section (check for any IIIF-related fields)
                iiif_fields = ['manifest_url', 'manifest_label', 'manifest_id', 'canvas_id', 'image_url',
                              'attribution', 'license', 'description', 'logo', 'thumbnail', 'page_range',
                              'archive_id', 'collection_label', 'iiif_metadata', 'manifest_metadata']

                if any(k in folder_data for k in iiif_fields):
                    lines.append("")
                    lines.append("=== IIIF METADATA ===")
                    lines.append("")

                    # Manifest information
                    if 'manifest_label' in folder_data:
                        lines.append(f"Manifest Label: {folder_data['manifest_label']}")
                    if 'manifest_id' in folder_data:
                        lines.append(f"Manifest ID: {folder_data['manifest_id']}")
                    if 'manifest_url' in folder_data:
                        lines.append(f"Manifest URL: {folder_data['manifest_url']}")
                    if 'page_range' in folder_data:
                        lines.append(f"Page Range: {folder_data['page_range']}")
                    if 'archive_id' in folder_data:
                        lines.append(f"Archive ID: {folder_data['archive_id']}")

                    # Collection/content information
                    if 'collection_label' in folder_data:
                        lines.append(f"Collection Label: {folder_data['collection_label']}")

                    # Image/canvas information (for folders containing images)
                    if 'canvas_id' in folder_data:
                        lines.append(f"Canvas ID: {folder_data['canvas_id']}")
                    if 'image_url' in folder_data:
                        lines.append(f"Image URL: {folder_data['image_url']}")

                    # Description and attribution
                    if 'description' in folder_data and folder_data['description']:
                        lines.append(f"\nDescription: {folder_data['description']}")
                    if 'attribution' in folder_data and folder_data['attribution']:
                        lines.append(f"\nAttribution: {folder_data['attribution']}")
                    if 'license' in folder_data and folder_data['license']:
                        lines.append(f"License: {folder_data['license']}")

                    # Logo and thumbnail
                    if 'logo' in folder_data and folder_data['logo']:
                        lines.append(f"Logo: {folder_data['logo']}")
                    if 'thumbnail' in folder_data and folder_data['thumbnail']:
                        lines.append(f"Thumbnail: {folder_data['thumbnail']}")

                    # IIIF metadata array (structured metadata from manifest)
                    if 'iiif_metadata' in folder_data and isinstance(folder_data['iiif_metadata'], list):
                        if folder_data['iiif_metadata']:
                            lines.append("")
                            lines.append("IIIF Metadata:")
                            for meta in folder_data['iiif_metadata']:
                                if isinstance(meta, dict):
                                    label = meta.get('label', '')
                                    value = meta.get('value', '')
                                    if label and value:
                                        lines.append(f"  {label}: {value}")

                    # Manifest metadata array
                    if 'manifest_metadata' in folder_data and isinstance(folder_data['manifest_metadata'], list):
                        if folder_data['manifest_metadata']:
                            lines.append("")
                            lines.append("Manifest Metadata:")
                            for meta in folder_data['manifest_metadata']:
                                if isinstance(meta, dict):
                                    label = meta.get('label', '')
                                    value = meta.get('value', '')
                                    if label and value:
                                        lines.append(f"  {label}: {value}")

                # Add any other metadata not covered above
                handled_fields = ['relative_path', 'type'] + iiif_fields
                other_metadata = {k: v for k, v in folder_data.items()
                                 if k not in handled_fields and v}  # Only include non-empty values

                if other_metadata:
                    lines.append("")
                    lines.append("=== ADDITIONAL METADATA ===")
                    lines.append("")
                    for key, value in other_metadata.items():
                        # Format the key nicely (convert snake_case to Title Case)
                        nice_key = key.replace('_', ' ').title()
                        # Handle list/dict values
                        if isinstance(value, (list, dict)):
                            lines.append(f"{nice_key}: {str(value)}")
                        else:
                            lines.append(f"{nice_key}: {value}")

            metadata_text = '\n'.join(lines)
            self.app.inspector_window.update_metadata(metadata_text, selection_type="FOLDER")
            logger.debug(f"Inspector updated with folder metadata for {folder_name}")

        except Exception as e:
            logger.error(f"Failed to update inspector with folder metadata: {e}")



    def refresh(self):
        """Refresh the collection view"""
        try:
            self.refresh_collections()
            super().refresh()
            
        except Exception as e:
            logger.error(f"Failed to refresh collection view: {e}") 

    async def _show_message(self, title: str, message: str):
        """Show a message dialog"""
        try:
            # Create a simple message dialog
            dialog = toga.InfoDialog(
                title=title,
                message=message
            )
            await self.app.dialog(dialog)
        except Exception as e:
            logger.error(f"Failed to show message dialog: {e}")
            # Fallback: just log the message
            logger.info(f"{title}: {message}")
    
    def _get_content_title(self) -> str:
        """Get the title to display above the content list"""
        if self.current_path:
            # In a subfolder - show current folder name
            return self._get_current_folder_display_name()
        else:
            # At collection root - show collection name
            return self.collection_name or "Collection"

    def _update_title(self):
        """Update the collection/folder title label"""
        try:
            if hasattr(self, 'folder_header') and self.folder_header:
                new_title = self._get_content_title()
                self.folder_header.text = new_title
                logger.debug(f"Updated collection title label to: {new_title}")
        except Exception as e:
            logger.error(f"Failed to update title: {e}")

    def _on_collection_selected(self, widget, item):
        """Handle collection selection (placeholder)"""
        try:
            logger.debug("Collection selection handler called")
            # This would typically handle collection selection
            pass
        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")

    # ===== EVENT HANDLERS FOR LIBRARY STATE SYNCHRONIZATION =====

    def _on_collection_deleted_event(self, event):
        """Handle collection_deleted event - navigate away if viewing deleted collection"""
        try:
            deleted_id = event.data.get("collection_id")
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_deleted - {collection_name}")

            # Check if we're viewing the deleted collection
            if self.collection_id == deleted_id:
                logger.info(f"Currently viewing deleted collection - navigating back to library")

                # Navigate back to library view
                nav_controller = self._get_navigation_controller()
                if nav_controller:
                    nav_controller.navigate_back()
                else:
                    logger.warning("NavigationController not available - cannot navigate away from deleted collection")

        except Exception as e:
            logger.error(f"Failed to handle collection_deleted event: {e}")

    def _on_collection_updated_event(self, event):
        """Handle collection_updated event - refresh collection name if this collection was updated"""
        try:
            updated_id = event.data.get("collection_id")
            new_name = event.data.get("collection_name")
            old_name = event.data.get("old_name", "Unknown")
            logger.info(f"📡 Event received: collection_updated - {old_name} -> {new_name}")

            # Check if this is the collection we're viewing
            if self.collection_id == updated_id:
                logger.info(f"Currently viewing updated collection - refreshing name from '{old_name}' to '{new_name}'")

                # Update the collection name
                self.set_collection_name(new_name)

                # Recreate content to update the title label
                self._create_content()

        except Exception as e:
            logger.error(f"Failed to handle collection_updated event: {e}")

    def _on_collection_items_changed_event(self, event):
        """Handle collection_items_changed event - reload items if this collection changed"""
        try:
            changed_id = event.data.get("collection_id")
            added_count = event.data.get("added_count", 0)
            logger.info(f"📡 Event received: collection_items_changed - {added_count} items added")

            # Check if this is our collection
            if self.collection_id == changed_id:
                logger.info(f"Items changed in current collection - reloading collection view")

                # Reload collection items
                # For now, just recreate the content
                self._create_content()

        except Exception as e:
            logger.error(f"Failed to handle collection_items_changed event: {e}")

    def _on_folder_import_started(self, event):
        """Handle folder_import_started event - just log it"""
        try:
            folder_name = event.data.get("folder_name", "folder")
            logger.info(f"📁 Import started: {folder_name}")
        except Exception as e:
            logger.error(f"Failed to handle folder_import_started event: {e}")

    def _on_folder_import_progress(self, event):
        """Handle folder_import_progress event - just log it"""
        try:
            total_processed = event.data.get("total_processed", 0)
            logger.debug(f"📁 Import progress: {total_processed} files processed")
        except Exception as e:
            logger.error(f"Failed to handle folder_import_progress event: {e}")

    def _on_folder_import_completed(self, event):
        """Handle folder_import_completed event - just log it"""
        try:
            added = event.data.get("added", 0)
            folder_name = event.data.get("folder_name", "folder")
            logger.info(f"✅ Import completed: {added} items from {folder_name}")
        except Exception as e:
            logger.error(f"Failed to handle folder_import_completed event: {e}")

    def _on_item_progress_updated(self, event):
        """Handle collection_item_updated event - update progress display for item"""
        try:
            item_id = event.data.get("item_id")
            progress = event.data.get("progress", 0)

            logger.debug(f"📡 Progress update for item {item_id}: {progress}%")

            # Check if this item is in our current collection
            if not self.collection_id:
                return

            # Find the item in our items list
            item_index = None
            for i, item in enumerate(self.collection_items):
                if item.get("id") == item_id:
                    item_index = i
                    break

            if item_index is None:
                return

            # Update the item's progress in our local cache
            self.collection_items[item_index]["progress"] = progress

            # Update the DetailedList display if it exists
            if hasattr(self, 'items_list') and self.items_list:
                try:
                    # Get the updated item data
                    item = self.collection_items[item_index]

                    # Update the subtitle to show progress
                    status = item.get("status", "unknown")
                    if progress < 100:
                        subtitle = f"Processing: {progress}% - {status}"
                    else:
                        subtitle = f"Completed - {status}"

                    # Refresh the item in the list
                    # Note: DetailedList doesn't have a direct update method,
                    # so we need to rebuild the data
                    self._update_items_list()

                except Exception as e:
                    logger.debug(f"Could not update DetailedList for progress: {e}")

        except Exception as e:
            logger.error(f"Failed to handle item progress update: {e}")

    def _on_processing_completed(self, event):
        """Handle processing_completed event - refresh item display"""
        try:
            item_id = event.data.get("item_id")
            task_id = event.data.get("task_id")
            status = event.data.get("status", "unknown")

            logger.info(f"📡 Processing completed for item {item_id}: {status}")

            # Check if this item is in our current collection
            if not self.collection_id:
                return

            # IMPORTANT: Reload collection structure to rebuild item ID map
            # This is critical for external collections where files get library IDs during processing
            logger.info(f"🔄 Reloading collection structure to update item IDs after processing")
            self.collection_items = self.library_service.get_collection_structure_sync(
                self.collection_id,
                self.current_path
            )

            # Find the item in our updated items list
            item_index = None
            for i, item in enumerate(self.collection_items):
                if item.get("id") == item_id:
                    item_index = i
                    break

            if item_index is None:
                logger.debug(f"Item {item_id} not found in collection after reload")
                return

            # Update the item's status
            self.collection_items[item_index]["director_status"] = status
            self.collection_items[item_index]["director_task_id"] = task_id
            self.collection_items[item_index]["progress"] = 100

            # Refresh the display
            if hasattr(self, 'items_list') and self.items_list:
                try:
                    self._update_items_list()
                except Exception as e:
                    logger.debug(f"Could not update DetailedList after completion: {e}")

            # Show completion notification if configured
            # (This could be optional based on settings)
            if status == "success":
                logger.info(f"✅ Item {item_id} processed successfully")
            else:
                logger.warning(f"❌ Item {item_id} processing failed: {status}")

        except Exception as e:
            logger.error(f"Failed to handle processing completion: {e}")

    def get_selection_metadata(self) -> str:
        """Get metadata for the currently selected item"""
        try:
            # Get the currently selected item from the DetailedList
            if not hasattr(self, 'items_list') or not self.items_list or not self.items_list.selection:
                return "No item selected"

            # Get the selected row from DetailedList
            selected_row = self.items_list.selection

            # Try to get full item_data (includes all metadata)
            if hasattr(selected_row, 'item_data'):
                item_data = selected_row.item_data
            else:
                # Fallback: extract basic attributes
                item_data = {
                    'id': getattr(selected_row, 'id', ''),
                    'title': getattr(selected_row, 'title', 'Unknown'),
                    'name': getattr(selected_row, 'name', getattr(selected_row, 'title', 'Unknown')),
                    'type': getattr(selected_row, 'type', 'unknown'),
                    'is_folder': getattr(selected_row, 'is_folder', False),
                    'path': getattr(selected_row, 'path', ''),
                    'file_path': getattr(selected_row, 'file_path', ''),
                    'subtitle': getattr(selected_row, 'subtitle', ''),
                    'description': getattr(selected_row, 'description', '')
                }

            # Format metadata as human-readable text
            lines = [
                "=== ITEM METADATA ===",
                "",
                f"Name: {item_data.get('name', item_data.get('title', 'Unknown'))}",
                f"Type: {'Folder' if item_data.get('is_folder') else item_data.get('type', 'File')}",
            ]

            if item_data.get('id'):
                lines.append(f"ID: {item_data['id']}")

            # Basic paths
            if item_data.get('path'):
                lines.append(f"Path: {item_data['path']}")

            if item_data.get('file_path') and item_data['file_path'] != item_data.get('path'):
                lines.append(f"File Path: {item_data['file_path']}")

            if item_data.get('subtitle'):
                lines.append(f"\nDetails: {item_data['subtitle']}")

            if item_data.get('description'):
                lines.append(f"\nDescription: {item_data['description']}")

            # IIIF/URL metadata section
            if item_data.get('image_url') or item_data.get('manifest_url'):
                lines.append("")
                lines.append("=== IIIF METADATA ===")
                lines.append("")

                if item_data.get('image_url'):
                    lines.append(f"Image URL: {item_data['image_url']}")

                if item_data.get('canvas_label'):
                    lines.append(f"Canvas: {item_data['canvas_label']}")

                if item_data.get('canvas_width') and item_data.get('canvas_height'):
                    lines.append(f"Dimensions: {item_data['canvas_width']} × {item_data['canvas_height']}")

                if item_data.get('manifest_url'):
                    lines.append(f"Manifest: {item_data['manifest_url']}")

                if item_data.get('collection_label'):
                    lines.append(f"Collection: {item_data['collection_label']}")

                if item_data.get('attribution'):
                    lines.append(f"\nAttribution: {item_data['attribution']}")

                if item_data.get('license'):
                    lines.append(f"License: {item_data['license']}")

                # Canvas metadata (if present)
                if item_data.get('canvas_metadata') and isinstance(item_data['canvas_metadata'], list):
                    if item_data['canvas_metadata']:
                        lines.append("")
                        lines.append("Canvas Metadata:")
                        for meta in item_data['canvas_metadata']:
                            if isinstance(meta, dict):
                                label = meta.get('label', '')
                                value = meta.get('value', '')
                                lines.append(f"  {label}: {value}")

                # Manifest metadata (if present)
                if item_data.get('manifest_metadata') and isinstance(item_data['manifest_metadata'], list):
                    if item_data['manifest_metadata']:
                        lines.append("")
                        lines.append("Manifest Metadata:")
                        for meta in item_data['manifest_metadata']:
                            if isinstance(meta, dict):
                                label = meta.get('label', '')
                                value = meta.get('value', '')
                                lines.append(f"  {label}: {value}")

            # Add collection context
            if hasattr(self, 'collection_name') and self.collection_name:
                lines.append(f"\nCollection: {self.collection_name}")

            if hasattr(self, 'current_path') and self.current_path:
                lines.append(f"Current Path: {self.current_path}")

            # Query library for processing steps data (async operation)
            if item_data['id'] and hasattr(self.app, 'library_manager'):
                lines.append("\n=== LIBRARY OUTPUT DATA ===\n")
                lines.append("Querying library_manager.get_item_output_data()...")

                # Run async call synchronously using threading to avoid blocking main UI
                import asyncio
                import threading

                output_data = None
                error = None

                def run_async_query():
                    """Run async query in a new event loop in a separate thread"""
                    nonlocal output_data, error
                    try:
                        # Create new event loop for this thread
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            output_data = loop.run_until_complete(
                                self.app.library_manager.get_item_output_data(item_data['id'])
                            )
                        finally:
                            loop.close()
                    except Exception as e:
                        error = e

                # Run query in thread and wait for result (with timeout)
                thread = threading.Thread(target=run_async_query, daemon=True)
                thread.start()
                thread.join(timeout=3.0)  # Wait up to 3 seconds

                if error:
                    lines.append(f"\n⚠️  Error querying output data: {error}")
                    import traceback
                    lines.append(f"Traceback: {traceback.format_exc()}")
                elif not thread.is_alive() and output_data is not None:
                    # Query completed successfully
                    if output_data:
                        lines.append(f"\n✅ Query completed successfully")
                        lines.append(f"Has Outputs: {output_data.get('has_outputs', False)}")
                        lines.append(f"Workflow: {output_data.get('workflow', 'N/A')}")
                        lines.append(f"Processing Date: {output_data.get('processing_date', 'N/A')}")
                        lines.append(f"Output Root: {output_data.get('output_root', 'N/A')}")

                        processing_steps = output_data.get('processing_steps', [])
                        lines.append(f"\nProcessing Steps: {len(processing_steps)}")

                        for i, step in enumerate(processing_steps, 1):
                            step_name = step.step_name if hasattr(step, 'step_name') else str(step)
                            file_path = step.file_path if hasattr(step, 'file_path') else 'N/A'
                            lines.append(f"  {i}. {step_name}")
                            lines.append(f"     Path: {file_path}")
                    else:
                        lines.append("\n❌ No output data returned from library")
                        lines.append("(Item may not have been processed yet)")
                elif thread.is_alive():
                    lines.append("\n⏱️  Query timed out (>3s)")
                    lines.append("Try refreshing the inspector")
                else:
                    lines.append("\n❌ No output data returned from library")
                    lines.append("(Item may not have been processed yet)")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Failed to get selection metadata: {e}")
            return f"Error loading metadata: {e}"