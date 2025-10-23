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
        logger.debug(f"CollectionView.__init__ called with app={app}, collection_name='{collection_name}', is_mobile={is_mobile}, collection_id={collection_id}")

        # Initialize attributes BEFORE calling super().__init__ to prevent AttributeError
        # during _create_content() which gets called by BaseView's constructor

        # Collection-specific data
        self.collection_name = collection_name
        self.collections: List[Dict[str, Any]] = []
        self.current_collection: Optional[Dict[str, Any]] = None
        self.collection_id: Optional[str] = collection_id  # Set from parameter
        self.collection_items: List[Dict[str, Any]] = []

        # Preview callback for showing files in right pane
        self.on_file_preview_requested: Optional[Callable] = None

        # Hierarchical navigation state
        self.current_path: str = ""  # Current path within collection (empty = root)
        self.breadcrumb_path: List[str] = []  # For breadcrumb display

        # Navigation loop protection
        self._updating_from_navigation_callback = False

        # Set view_id BEFORE initializing ViewCommandMixin
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
        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
        subscribe_to_navigation("collection_items_changed", self._on_collection_items_changed_event)
        subscribe_to_navigation("collection_item_updated", self._on_item_progress_updated)
        subscribe_to_navigation("processing_completed", self._on_processing_completed)
        logger.debug("Event subscriptions registered for collection view (including progress updates)")

        # Load collection items if collection_id was provided during initialization
        if self.collection_id:
            logger.debug(f"Loading items for collection {self.collection_id} provided during initialization")
            self._load_collection_items()

        logger.info("Refactored collection view created successfully")

    def define_commands(self):
        """Define all commands for CollectionView"""
        try:
            # Create custom menu groups (following OutputView/LibraryView pattern)
            tools_group = toga.Group("Tools", order=50)  # After View (30), before Window (90)

            # Note: _() is available globally via gettext.install() in app.py
            self.commands = {
                # ===== TOOLS MENU - PROCESS SELECTED COMMAND =====
                'process_selected': FicheroCommand(
                    id='collection.process_selected',
                    label=_("Process Selected"),
                    action=self._on_process_selected_requested,
                    shortcut=toga.Key.MOD_1 + toga.Key.ENTER,  # Cmd+Enter
                    icon='resources/icons/toolbar/sparkle@10x.png',  # Single sparkle for selected item
                    description=_("Process selected item with Fichero Director"),
                    group=tools_group,  # Tools menu on desktop
                    section=1,  # Section 1 = separator after Inspector (section=-1), before OutputView (section=0)
                    order=0,  # First item in this section
                    show_in_menu=True,  # Appear in Tools menu on desktop
                    show_in_toolbar=True,  # Show in desktop toolbar
                    show_in_top_toolbar=False,  # Not in mobile top toolbar
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal',
                    enabled=False  # Will be enabled when item is selected
                ),

                # ===== TOOLS MENU - PROCESS ALL COMMAND =====
                'process_all': FicheroCommand(
                    id='collection.process_all',
                    label=_("Process All"),
                    action=self._on_process_all_requested,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + toga.Key.ENTER,  # Cmd+Shift+Enter
                    icon='resources/icons/toolbar/sparkles@10x.png',  # Multiple sparkles for all items
                    description=_("Process all items in current folder with Fichero Director"),
                    group=tools_group,  # Tools menu on desktop
                    section=1,  # Same section as Process Selected
                    order=1,  # Second item in this section (after Process Selected)
                    show_in_menu=True,  # Appear in Tools menu on desktop
                    show_in_toolbar=True,  # Show in desktop toolbar
                    show_in_top_toolbar=False,  # Not in mobile top toolbar
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
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
            # Show on both mobile and desktop, always show current location
            content_title = self._get_content_title()
            if content_title:
                folder_header = toga.Label(
                    content_title,
                    style=Pack(
                        margin=(15, 20, 10, 20),
                        # Use default font size (no font_size specified)
                        font_weight="bold",
                        color=self.text_color
                    )
                )
                self.content_container.add(folder_header)
            
            # Show collection items if we have them, otherwise show placeholder
            if hasattr(self, 'collection_items') and self.collection_items:
                logger.debug(f"Displaying {len(self.collection_items)} collection items")
                self._create_collection_items_list(self.collection_items)
            else:
                # Show placeholder message
                if hasattr(self, 'collection_id') and self.collection_id:
                    placeholder = toga.Label(
                        f"This folder is empty.\n\nUse the toolbar to add files and folders.",
                        style=Pack(
                            margin=(10, 20),
                            color=self.text_color
                        )
                    )
                else:
                    placeholder = toga.Label(
                        "Select a collection from the left pane to view its items",
                        style=Pack(
                            margin=(10, 20),
                            color=self.text_color
                        )
                    )
                if self.content_container:
                    self.content_container.add(placeholder)
            
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
            if hasattr(self.app, 'view_integration') and self.app.view_integration:
                navigation_controller = self.app.view_integration.get_navigation_controller()
                if navigation_controller:
                    navigation_controller.navigate_back()

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

    async def _select_and_add_folder(self):
        """Show folder selection dialog and add selected folder to collection"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show folder selection dialog
            selected_path = await window.select_folder_dialog(
                title=_("Select Folder to Add"),
                initial_directory=None
            )

            if selected_path:
                logger.info(f"Folder selected: {selected_path}")
                # Add folder to current collection
                await self._add_folder_to_collection(str(selected_path))
            else:
                logger.info("Folder selection cancelled")

        except Exception as e:
            logger.error(f"Failed to select and add folder: {e}")

    def _on_add_file(self):
        """Handle add file action from toolbar"""
        try:
            logger.info("Add file requested from toolbar")
            # Use navigation controller to show file add view
            from fichero.windows.add.views.file_view import FileAddView

            file_view = FileAddView(
                app=self.app,
                on_content_added=self._on_file_added
            )

            # Navigate to file view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    nav_controller.push_view(file_view, "Add File")
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

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

    async def _add_folder_to_collection(self, folder_path: str):
        """Add a folder to the current collection"""
        try:
            if not self.collection_id:
                logger.error("No collection ID available")
                return

            # Get folder name
            from pathlib import Path
            folder_name = Path(folder_path).name

            # Add to collection via library service
            item_id = await self.app.library_service.add_item_to_collection_for_ui(
                collection_id=self.collection_id,
                item_type="folder",
                source=folder_path,
                name=folder_name,
                operation="link"  # Link to folder, don't copy
            )

            if item_id:
                # Refresh collection display
                await self._load_collection_items()
                logger.info(f"Added folder '{folder_name}' to collection")

                # Pop back to collection view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to add folder to collection")

        except Exception as e:
            logger.error(f"Failed to add folder to collection: {e}")

    async def _add_file_to_collection(self, file_path: str):
        """Add a file to the current collection"""
        try:
            if not self.collection_id:
                logger.error("No collection ID available")
                return

            # Get file name
            from pathlib import Path
            file_name = Path(file_path).name

            # Add to collection via library service
            item_id = await self.app.library_service.add_item_to_collection_for_ui(
                collection_id=self.collection_id,
                item_type="file",
                source=file_path,
                name=file_name,
                operation="link"  # Link to file, don't copy
            )

            if item_id:
                # Refresh collection display
                await self._load_collection_items()
                logger.info(f"Added file '{file_name}' to collection")

                # Pop back to collection view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to add file to collection")

        except Exception as e:
            logger.error(f"Failed to add file to collection: {e}")
    
    def _update_toolbar_navigation(self):
        """Update toolbar navigation state"""
        try:
            if hasattr(self.top_toolbar, 'update_navigation_state'):
                self.top_toolbar.update_navigation_state(self.current_path)
        except Exception as e:
            logger.error(f"Failed to update toolbar navigation: {e}")
    
    def _create_collection_items_list(self, items: List[Dict[str, Any]]):
        """Create a detailed list view for collection items"""
        try:
            if not items:
                logger.debug("No items to display in collection")
                return
            
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
            self.items_list = toga.DetailedList(
                data=items,  # Direct use of Toga-compatible format
                on_select=self._on_item_selected,
                primary_action="Open",
                on_primary_action=self._on_open_item,
                secondary_action="Info", 
                on_secondary_action=self._on_item_info,
                style=Pack(
                    flex=1,
                    margin=0  # Full width - no margins
                )
            )
            
            if self.content_container:
                self.content_container.add(self.items_list)
                
            logger.debug(f"Created DetailedList with {len(items)} items in native Toga format")

        except Exception as e:
            logger.error(f"Failed to create collection items list: {e}")

    def _update_items_list(self):
        """Update the DetailedList with current collection_items data"""
        try:
            if hasattr(self, 'items_list') and self.items_list:
                # Update the data property to refresh the list
                self.items_list.data = self.collection_items
                logger.debug(f"Updated DetailedList with {len(self.collection_items)} items")
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

                logger.info(f"Item selected: {item_data['title']}")
                logger.debug(f"Full item_data extracted: {item_data}")

                # Enable "Process Selected" command now that an item is selected
                logger.info(f"🔍 DEBUG: hasattr(self, 'commands') = {hasattr(self, 'commands')}")
                if hasattr(self, 'commands'):
                    logger.info(f"🔍 DEBUG: self.commands.keys() = {list(self.commands.keys())}")
                    logger.info(f"🔍 DEBUG: 'process_selected' in self.commands = {'process_selected' in self.commands}")

                if hasattr(self, 'commands') and 'process_selected' in self.commands:
                    self.commands['process_selected'].enable()
                    logger.info("✅ Enabled 'Process Selected' command (item selected)")

                # Update inspector with item metadata
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    metadata = self.get_selection_metadata()
                    self.app.inspector_window.update_metadata(metadata, selection_type="ITEM")
                    logger.debug("Inspector updated with item metadata")

                # Navigate to show preview
                self._handle_item_navigation(item_data)
            else:
                logger.debug("No selection in widget")

                # Disable "Process Selected" command when no selection
                if hasattr(self, 'commands') and 'process_selected' in self.commands:
                    self.commands['process_selected'].disable()
                    logger.debug("❌ Disabled 'Process Selected' command (no selection)")

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
                    if hasattr(self.app, 'view_integration') and self.app.view_integration:
                        navigation_controller = self.app.view_integration.get_navigation_controller()
                        if navigation_controller:
                            navigation_controller.navigate_back()
                else:
                    # Regular folder navigation
                    folder_path = item_data.get('path', item_data.get('name', ''))
                    logger.info(f"FOLDER NAVIGATION: Navigating to folder path: '{folder_path}'")
                    
                    # Check if this is an absolute path or relative path
                    if folder_path and self.current_path and folder_path.startswith(self.current_path):
                        # It's an absolute path, extract the relative part
                        relative_path = folder_path[len(self.current_path):].lstrip('/')
                        logger.info(f"FOLDER NAVIGATION: Converted absolute path '{folder_path}' to relative '{relative_path}'")
                        self.navigate_to_folder(relative_path)
                    else:
                        # It's already a relative path or we're at root
                        self.navigate_to_folder(folder_path)
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
                auto_mobile_nav=True,
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

    async def _on_process_selected_requested(self, widget):
        """Handle Process Selected button click - process only selected item"""
        try:
            logger.info(f"Process Selected clicked - collection_id={self.collection_id}, collection_name={self.collection_name}")

            # Check if we have a collection
            if not self.collection_id:
                logger.error(f"NO COLLECTION ID! collection_id = {self.collection_id}")
                # Skip dialog - just log error and return (dialogs cause NSTableView crash)
                return

            # Get currently selected item (REQUIRED for this command)
            selected_item_id = None
            selected_item_name = None
            if hasattr(self, 'items_list') and self.items_list and self.items_list.selection:
                try:
                    # Get the selected item's ID and name from the row data
                    selected_row = self.items_list.selection
                    if hasattr(selected_row, 'item_id'):
                        selected_item_id = selected_row.item_id
                    elif hasattr(selected_row, 'id'):
                        selected_item_id = selected_row.id

                    # Get the display name from the row
                    if hasattr(selected_row, 'title'):
                        selected_item_name = selected_row.title
                    elif hasattr(selected_row, 'name'):
                        selected_item_name = selected_row.name

                    logger.info(f"Selected item: id={selected_item_id}, name={selected_item_name}")
                except Exception as e:
                    logger.debug(f"Could not get selected item: {e}")

            # If no selection, just log and return (skip dialog to avoid crash)
            if not selected_item_id:
                logger.warning("No item selected - cannot process")
                return

            # Show processing dialog with selected item
            await self._show_process_dialog(selected_item_id, selected_item_name)

        except Exception as e:
            logger.error(f"Error handling process selected request: {e}")
            # Skip error dialog - just log (dialogs cause NSTableView crash)
            import traceback
            traceback.print_exc()

    async def _on_process_all_requested(self, widget):
        """Handle Process All button click - process all items in current folder"""
        try:
            logger.info(f"Process All clicked - collection_id={self.collection_id}, collection_name={self.collection_name}")

            # Check if we have a collection
            if not self.collection_id:
                logger.error(f"NO COLLECTION ID! collection_id = {self.collection_id}")
                # Skip dialog - just log error and return (dialogs cause NSTableView crash)
                return

            # Show processing dialog with NO selected item (process all)
            await self._show_process_dialog(selected_item_id=None)

        except Exception as e:
            logger.error(f"Error handling process all request: {e}")
            # Skip error dialog - just log (dialogs cause NSTableView crash)
            import traceback
            traceback.print_exc()

    async def _show_process_dialog(self, selected_item_id: Optional[str] = None, selected_item_name: Optional[str] = None):
        """Show simple confirmation and process directly"""
        try:
            # Get collection first
            collection = await self.app.library_manager.get_collection(self.collection_id)
            if not collection:
                logger.error("Collection not found")
                # Skip dialog - just return (dialogs cause NSTableView crash)
                return

            # Check if we have items in the database
            all_items = await self.app.library_manager.get_collection_items(self.collection_id)

            # Determine processing approach based on what we have
            if all_items:
                # We have items in database - use DirectorIntegrationService
                await self._process_via_items(collection, all_items, selected_item_id, selected_item_name)
            else:
                # No items in database
                if selected_item_id:
                    # "Process Selected" was clicked but no items in database - show error
                    logger.error("Cannot process selected item: Collection has no items in database. Please index the collection first.")
                    logger.error("Use a 'Scan' or 'Reindex' command to populate the collection with files from the filesystem.")
                    return
                else:
                    # "Process All" was clicked - process folder directly
                    await self._process_via_folder(collection)

        except Exception as e:
            logger.error(f"Error in process dialog: {e}")
            # Skip error dialog - just log (dialogs cause NSTableView crash)
            import traceback
            traceback.print_exc()

    async def _process_via_items(self, collection, all_items, selected_item_id: Optional[str] = None, selected_item_name: Optional[str] = None):
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
            scope_text = f"All {len(all_items)} items"
            item_ids = [item.id for item in all_items]

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
        logger.info(f"Collection ID: {self.collection_id}")

        # Process items
        # Use first workflow from the plan (typically "Catalogue")
        try:
            logger.info("Calling director_integration.process_items()...")
            task_ids = await self.app.director_integration.process_items(
                collection_id=self.collection_id,
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

    async def _process_via_folder(self, collection):
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
        """Unregister NavigationController callbacks to prevent duplicate events"""
        try:
            if hasattr(self, '_nav_callback_ref'):
                navigation_controller = self._get_navigation_controller()
                if navigation_controller:
                    navigation_controller.remove_callback('state_changed', self._nav_callback_ref)
                    logger.debug("Collection view unregistered NavigationController callback")
                    delattr(self, '_nav_callback_ref')
        except Exception as e:
            logger.error(f"Failed to cleanup NavigationController callbacks: {e}")

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

                # Only update UI if we're in a collection context and it's our collection
                if navigation_state.context == NavigationContext.COLLECTION:
                    if navigation_state.collection_id == self.collection_id:
                        # Check if this is actually a new path to prevent unnecessary reloads
                        new_path = navigation_state.current_path or ""

                        if new_path != self.current_path:
                            logger.info(f"🔄 Path changed from '{self.current_path}' to '{new_path}' - updating UI")

                            # Update our local state to match NavigationController
                            self.current_path = new_path

                            # Update UI elements
                            self._update_breadcrumbs()

                            # Update toolbar navigation state
                            if hasattr(self.top_toolbar, 'set_current_path'):
                                self.top_toolbar.set_current_path(self.current_path)

                            # Reload items for new path - use silent version to avoid navigation events
                            self._load_collection_items_silent()

                            logger.info(f"✅ UI updated for path: '{self.current_path}'")
                        else:
                            logger.debug(f"🔄 Path unchanged ('{self.current_path}') - skipping reload to prevent event storm")
                    else:
                        logger.debug(f"State change for different collection: {navigation_state.collection_id}")
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
            if self.library_service and hasattr(self, 'collection_id') and self.collection_id:
                # Use hierarchical structure method for folder navigation
                logger.info(f"Loading hierarchical structure for collection {self.collection_id}, path: '{self.current_path}'")
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

                # Refresh the display with items
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

                # Refresh the display with items - NO breadcrumb updates to prevent events
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

            # Extract item data from row attributes
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
                f"Name: {item_data['name']}",
                f"Type: {'Folder' if item_data['is_folder'] else 'File'}",
            ]

            if item_data['id']:
                lines.append(f"ID: {item_data['id']}")

            if item_data['path']:
                lines.append(f"Path: {item_data['path']}")

            if item_data['file_path'] and item_data['file_path'] != item_data['path']:
                lines.append(f"File Path: {item_data['file_path']}")

            if item_data['subtitle']:
                lines.append(f"\nDetails: {item_data['subtitle']}")

            if item_data['description']:
                lines.append(f"\nDescription: {item_data['description']}")

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