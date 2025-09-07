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

from fichero.windows.main.views.base_view import BaseView
from fichero.library.library_manager import LibraryManager
from fichero.windows.main.toolbars.collection_top_toolbar import CollectionTopToolbar
from fichero.windows.main.toolbars.collection_bottom_toolbar import CollectionBottomToolbar
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead

logger = logging.getLogger(__name__)


class CollectionView(BaseView):
    """Collection view using the new BaseView system"""
    
    def __init__(self, app, collection_name: str = "", is_mobile: bool = False):
        """Initialize refactored collection view"""
        logger.debug(f"CollectionView.__init__ called with app={app}, collection_name='{collection_name}', is_mobile={is_mobile}")
        super().__init__(app, is_mobile)
        
        # Collection-specific data
        self.collection_name = collection_name
        self.collections: List[Dict[str, Any]] = []
        self.current_collection: Optional[Dict[str, Any]] = None
        self.collection_id: Optional[str] = None
        self.collection_items: List[Dict[str, Any]] = []
        
        # Preview callback for showing files in right pane
        self.on_file_preview_requested: Optional[Callable] = None
        
        # Hierarchical navigation state
        self.current_path: str = ""  # Current path within collection (empty = root)
        self.path_history: List[str] = []  # For back navigation
        self.breadcrumb_path: List[str] = []  # For breadcrumb display
        
        # Initialize library manager
        self._initialize_library_manager()
        
        # Create separate top and bottom toolbars
        self.top_toolbar = CollectionTopToolbar(app, collection_name, is_mobile)
        self.bottom_toolbar = CollectionBottomToolbar(app, is_mobile)
        
        # Set both toolbars
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Note: scroll container is handled by BaseView
        
        # Register callbacks
        self._register_toolbar_callbacks()
        
        # Create content
        self._create_content()
        
        # Set up scroll container integration
        self._setup_scroll_integration()
        
        logger.info("Refactored collection view created successfully")
    
    def _create_content(self):
        """Create the collection view content"""
        try:
            # Clear any existing content first to prevent duplicates
            if self.content_container:
                self.content_container.clear()
            
            # No header here - titles should only be in top toolbar
            # Show collection items if we have them, otherwise show placeholder
            if hasattr(self, 'collection_items') and self.collection_items:
                logger.debug(f"Displaying {len(self.collection_items)} collection items")
                self._create_collection_items_list(self.collection_items)
            else:
                # Show placeholder message
                if hasattr(self, 'collection_id') and self.collection_id:
                    placeholder = toga.Label(
                        f"Collection is empty.\n\nUse the toolbar to add files and folders to this collection.",
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
        """Setup navigation callbacks with the collection toolbar"""
        if hasattr(toolbar, 'register_navigation_callbacks'):
            toolbar.register_navigation_callbacks(
                on_back_to_library=self._on_back_to_library,
                on_navigate_back=self._on_navigate_back,
                on_navigate_to_path=self._on_navigate_to_path,
                on_add_folder=self._on_add_folder,
                on_add_file=self._on_add_file
            )
    
    def _on_back_to_library(self):
        """Handle back to library navigation from toolbar"""
        try:
            # Navigate back to library view
            if hasattr(self.app, 'main_window') and hasattr(self.app.main_window, 'pane_manager'):
                self.app.main_window.pane_manager.switch_to_view('collection_management')
            logger.info("Navigated back to library")
        except Exception as e:
            logger.error(f"Failed to navigate back to library: {e}")
    
    def _on_navigate_back(self):
        """Handle hierarchical back navigation from toolbar"""
        try:
            self._go_back()
        except Exception as e:
            logger.error(f"Failed to navigate back: {e}")
    
    def _on_navigate_to_path(self, path: str):
        """Handle navigation to specific path from toolbar breadcrumb"""
        try:
            logger.info(f"Navigating to breadcrumb path: {path}")
            
            # Update navigation state
            self.current_path = path
            
            # Update path history - remove any entries after this path
            if path == "":
                # Going to root
                self.path_history.clear()
            else:
                # Find this path in history and truncate after it
                path_parts = path.split("/")
                self.path_history = path_parts[:-1]  # All parts except the last one
            
            # Update breadcrumbs
            self._update_breadcrumbs()
            
            # Reload items for the new path
            self._load_collection_items()
            
            # Update toolbar
            self._update_toolbar_navigation()
            
        except Exception as e:
            logger.error(f"Failed to navigate to path {path}: {e}")
    
    def _on_add_folder(self):
        """Handle add folder action from toolbar"""
        try:
            # TODO: Implement add folder functionality
            logger.info("Add folder requested from toolbar")
        except Exception as e:
            logger.error(f"Failed to handle add folder: {e}")
    
    def _on_add_file(self):
        """Handle add file action from toolbar"""
        try:
            # TODO: Implement add file functionality
            logger.info("Add file requested from toolbar")
        except Exception as e:
            logger.error(f"Failed to handle add file: {e}")
    
    def _update_toolbar_navigation(self):
        """Update toolbar navigation state"""
        try:
            if hasattr(self.top_toolbar, 'update_navigation_state'):
                self.top_toolbar.update_navigation_state(self.current_path, self.path_history)
        except Exception as e:
            logger.error(f"Failed to update toolbar navigation: {e}")
    
    def _create_collection_items_list(self, items: List[Dict[str, Any]]):
        """Create a detailed list view for collection items"""
        try:
            if not items:
                logger.debug("No items to display in collection")
                return
            
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
                
                # Handle item navigation
                self._handle_item_navigation(item_data)
            else:
                logger.debug("No selection in widget")
                
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
                if self.on_file_preview_requested:
                    self.on_file_preview_requested(file_path, item_data)
                    logger.info(f"File preview requested via callback: {file_path}")
                else:
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
                folder_path = item_data.get('path', item_data.get('name', ''))
                logger.info(f"FOLDER NAVIGATION: Navigating to folder path: '{folder_path}'")
                self.navigate_to_folder(folder_path)
            else:
                # Handle file - check if we have a file path
                file_path = item_data.get('file_path')
                if file_path:
                    logger.info(f"FILE NAVIGATION: Opening preview for file: {file_path}")
                    # Use the preview callback to show in right pane
                    if self.on_file_preview_requested:
                        self.on_file_preview_requested(file_path, item_data)
                        logger.info(f"File preview requested via callback: {file_path}")
                    else:
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
    
    def _register_toolbar_callbacks(self):
        """Register callbacks for both toolbars"""
        try:
            # Top toolbar navigation callbacks
            if hasattr(self.top_toolbar, 'register_navigation_callbacks'):
                self.top_toolbar.register_navigation_callbacks(
                    on_back_to_library=self._on_back_to_library,
                    on_navigate_back=self._go_back,  # Use _go_back directly
                    on_navigate_to_path=self._on_navigate_to_path,
                    on_add_folder=self._on_add_folder,
                    on_add_file=self._on_add_file
                )
            else:
                # Fallback to old registration method
                self.top_toolbar.register_callbacks(
                on_back_to_library=self._on_back_to_library,
                on_navigate_back=self._go_back,  # Use _go_back directly
                on_add_folder=self._on_add_folder,
                on_add_file=self._on_add_file
            )

            # Bottom toolbar callbacks
            if hasattr(self.bottom_toolbar, 'register_callbacks'):
                self.bottom_toolbar.register_callbacks(
                    on_collection_settings=self._on_collection_settings
                )

            logger.info("Toolbar callbacks registered successfully")
            
        except Exception as e:
            logger.error(f"Failed to register toolbar callbacks: {e}")
    
    def _on_collection_settings(self):
        """Handle collection settings action"""
        logger.debug("Collection settings requested")
        # This would typically open a settings dialog
        if hasattr(self, 'on_collection_settings') and self.on_collection_settings:
            self.on_collection_settings()
    
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
        
        logger.debug("Collection view callbacks registered")
    
    def register_preview_callback(self, callback: Callable):
        """Register callback for file preview requests"""
        self.on_file_preview_requested = callback
        logger.debug("Preview callback registered")
    
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
            else:
                logger.warning("Library service not initialized or no collection ID set")
                self._create_content() # This now handles the placeholder
                
        except Exception as e:
            logger.error(f"Failed to load collection items: {e}")
    
    def _update_breadcrumbs(self):
        """Update breadcrumb display in toolbar"""
        try:
            if hasattr(self.top_toolbar, 'update_breadcrumbs'):
                collection_name = getattr(self, 'collection_name', 'Collection')
                self.top_toolbar.update_breadcrumbs(collection_name, self.current_path)
        except Exception as e:
            logger.error(f"Failed to update breadcrumbs: {e}")
    
    def navigate_to_folder(self, folder_path: str):
        """Navigate into a folder"""
        try:
            # Add current path to history for back navigation
            self.path_history.append(self.current_path)
            
            # Update current path
            if self.current_path:
                self.current_path = f"{self.current_path}/{folder_path}"
            else:
                self.current_path = folder_path
            
            # Update breadcrumbs
            self._update_breadcrumbs()
            
            # Update toolbar navigation state
            if hasattr(self.top_toolbar, 'set_current_path'):
                self.top_toolbar.set_current_path(self.current_path)
            
            # Reload items for new path
            self._load_collection_items()
            
            logger.info(f"Navigated to folder: {folder_path}, current path: {self.current_path}")
            
        except Exception as e:
            logger.error(f"Failed to navigate to folder: {e}")
    
    def _go_back(self):
        """Go back one level in the hierarchy"""
        try:
            if self.path_history:
                # Go back to previous path
                self.current_path = self.path_history.pop()
                logger.info(f"Going back to: {self.current_path}")
            else:
                # At root level, clear current path
                self.current_path = ""
                logger.info("Going back to collection root")
            
            # Update breadcrumbs
            self._update_breadcrumbs()
            
            # Update toolbar navigation state
            if hasattr(self.top_toolbar, 'set_current_path'):
                self.top_toolbar.set_current_path(self.current_path)
            
            # Reload items for new path
            self._load_collection_items()
            
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
    
    def navigate_to_breadcrumb(self, breadcrumb_index: int):
        """Navigate to a specific breadcrumb level"""
        try:
            if breadcrumb_index == 0:
                # Navigate to root
                self.path_history.append(self.current_path)
                self.current_path = ""
            else:
                # Navigate to specific level
                path_parts = self.current_path.split('/') if self.current_path else []
                if breadcrumb_index - 1 < len(path_parts):
                    self.path_history.append(self.current_path)
                    self.current_path = '/'.join(path_parts[:breadcrumb_index])
            
            # Update breadcrumbs
            self._update_breadcrumbs()
            
            # Reload items for new path
            self._load_collection_items()
            
            # Update toolbar navigation state
            self._update_toolbar_navigation()
            
            logger.info(f"Navigated to breadcrumb level {breadcrumb_index}: {self.current_path or 'root'}")
        except Exception as e:
            logger.error(f"Failed to navigate to breadcrumb {breadcrumb_index}: {e}")
    
    def reset_navigation(self):
        """Reset navigation to root level"""
        try:
            self.current_path = ""
            self.path_history = []
            self.breadcrumb_path = []
            self._load_collection_items()
            
            # Update toolbar navigation state
            self._update_toolbar_navigation()
            
            logger.info("Navigation reset to root level")
        except Exception as e:
            logger.error(f"Failed to reset navigation: {e}")

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
    
    def _on_collection_selected(self, widget, item):
        """Handle collection selection (placeholder)"""
        try:
            logger.debug("Collection selection handler called")
            # This would typically handle collection selection
            pass
        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}") 