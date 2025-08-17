"""
Minimal Collection View

Maximally shared code approach - the view is just a thin UI wrapper around shared logic.
All business logic, navigation, and data handling is shared between platforms.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import asyncio
import logging
from typing import Optional, Dict, Any
from pathlib import Path

from fichero.windows.main.views.collection_view_shared import SharedNavigationLogic, SharedItemRenderer

logger = logging.getLogger(__name__)


class CollectionViewPresenter:
    """
    Presenter that handles ALL logic and coordinates with multiple UI displays.
    
    This is the single source of truth for all collection view behavior.
    UI components are just dumb displays that delegate everything here.
    """
    
    def __init__(self, app):
        """Initialize the presenter with shared navigation logic"""
        self.app = app
        self.nav_logic = SharedNavigationLogic(app)
        
        # UI displays (can have multiple for same data)
        self.ui_displays: list = []
        
        # Set up callbacks
        self.nav_logic.on_navigation_change = self._on_navigation_change
        self.nav_logic.on_collections_loaded = self._on_collections_loaded
    
    def register_ui_display(self, ui_display):
        """Register a UI display that will be updated when data changes"""
        self.ui_displays.append(ui_display)
        
    async def initialize(self):
        """Initialize the presenter and shared logic"""
        result = await self.nav_logic.initialize()
        logger.info(f"Presenter initialized: {result}")
        return result
    
    # ===== SHARED EVENT HANDLERS (called by any UI) =====
    
    async def handle_add_collection(self):
        """Handle add collection request from any UI"""
        try:
            # Show folder selection dialog
            dialog = toga.SelectFolderDialog(title="Select Collection Folder")
            window = self.app.main_window
            selected_folder = await window.dialog(dialog)
            
            if selected_folder:
                result = await self.nav_logic.add_collection_from_folder(selected_folder)
                logger.info(f"Added collection result: {result}")
                
        except Exception as e:
            logger.error(f"Failed to add collection: {e}")
    
    def handle_item_selection(self, selected_data):
        """Handle item selection from any UI"""
        try:
            if hasattr(selected_data, 'collection'):
                # Collection selected
                collection = selected_data.collection
                logger.info(f"Navigating to collection: {collection.name}")
                self.nav_logic.navigate_into_collection(collection)
                
            elif hasattr(selected_data, 'navigation_item'):
                # File or folder selected
                navigation_item = selected_data.navigation_item
                logger.info(f"Item selected: {navigation_item.name} (level: {navigation_item.level.value})")
                
                if navigation_item.level.value == "folder":
                    # Navigate into folder
                    self.nav_logic.navigate_into_folder(navigation_item)
                elif navigation_item.level.value == "file":
                    # Check if file is a directory (folder of images, etc.)
                    if navigation_item.path.is_dir():
                        # Navigate into file directory (e.g., folder of images)
                        logger.info(f"File is directory, navigating into: {navigation_item.path}")
                        self.nav_logic.navigate_into_folder(navigation_item)
                    else:
                        # Handle single file selection - could expand to show pages
                        logger.info(f"Single file selected: {navigation_item.name}")
                        # Future: navigate into file to show pages/metadata
                    
        except Exception as e:
            logger.error(f"Failed to handle item selection: {e}")
    
    def handle_back_navigation(self):
        """Handle back navigation from any UI"""
        try:
            result = self.nav_logic.navigate_back()
            logger.info(f"Back navigation result: {result}")
        except Exception as e:
            logger.error(f"Failed to navigate back: {e}")
    
    async def handle_collection_navigation(self, collection_name: str):
        """Handle navigation to a collection from tree view"""
        try:
            # Find the collection by name
            collections = self.nav_logic.library_manager.get_collections()
            target_collection = None
            for collection in collections:
                if collection.name == collection_name:
                    target_collection = collection
                    break
            
            if target_collection:
                logger.info(f"Navigating to collection from tree: {collection_name}")
                result = await self.nav_logic.navigate_to_collection(target_collection)
                return result
            else:
                logger.warning(f"Collection not found: {collection_name}")
                return False
        except Exception as e:
            logger.error(f"Failed to navigate to collection {collection_name}: {e}")
            return False
    
    async def handle_tree_folder_navigation(self, collection_name: str, folder_path: list):
        """Handle navigation to a specific folder from tree view"""
        try:
            # First navigate to the collection
            await self.handle_collection_navigation(collection_name)
            
            # Then navigate through the folder path
            for folder_name in folder_path:
                # Find the folder in current items
                current_items = self.nav_logic.get_current_items()
                target_folder = None
                for item in current_items:
                    if item.name == folder_name and item.level.value == "folder":
                        target_folder = item
                        break
                
                if target_folder:
                    logger.info(f"Navigating to folder from tree: {folder_name}")
                    self.nav_logic.navigate_into_folder(target_folder)
                else:
                    logger.warning(f"Folder not found in path: {folder_name}")
                    return False
            
            return True
        except Exception as e:
            logger.error(f"Failed to navigate to folder path {folder_path}: {e}")
            return False
    
    # ===== DATA CHANGE NOTIFICATIONS =====
    
    def _on_navigation_change(self, current_item, breadcrumb_path):
        """Navigation changed - notify all UI displays"""
        logger.info(f"Navigation change: {current_item.name if current_item else 'None'}, breadcrumb: {[i.name for i in breadcrumb_path]}")
        for ui_display in self.ui_displays:
            if hasattr(ui_display, 'update_navigation'):
                ui_display.update_navigation(current_item, breadcrumb_path)
    
    def _on_collections_loaded(self, collections):
        """Collections loaded - notify all UI displays"""
        logger.info(f"Collections loaded: {len(collections)} collections")
        for ui_display in self.ui_displays:
            if hasattr(ui_display, 'update_collections'):
                ui_display.update_collections(collections)
    
    # ===== SHARED DATA ACCESS =====
    
    def get_current_items(self):
        """Get current navigation items for display"""
        items = self.nav_logic.get_current_items()
        logger.info(f"Current items: {len(items)} items")
        return items
    
    def get_breadcrumb_path(self):
        """Get current breadcrumb path for display"""  
        return self.nav_logic.get_breadcrumb_path()
    
    def get_current_item(self):
        """Get current navigation item for display"""
        return self.nav_logic.get_current_item()


class SharedDisplayMethods:
    """Shared methods for both mobile and desktop displays"""
    
    def __init__(self, presenter: CollectionViewPresenter):
        self.presenter = presenter
        self.presenter.register_ui_display(self)
    
    def update_collections(self, collections):
        """Update display when collections are loaded"""
        try:
            list_items = [
                SharedItemRenderer.format_collection_for_display(collection)
                for collection in collections
            ]
            self._update_collection_list(list_items)
        except Exception as e:
            logger.error(f"Failed to update collections: {e}")
    
    def update_navigation_items(self):
        """Update navigation items from current state"""
        try:
            items = self.presenter.get_current_items()
            list_items = [
                SharedItemRenderer.format_item_for_display(item)
                for item in items
            ]
            self._update_navigation_list(list_items)
        except Exception as e:
            logger.error(f"Failed to update navigation items: {e}")
    
    def _update_collection_list(self, list_items):
        """Override in subclasses"""
        pass
    
    def _update_navigation_list(self, list_items):
        """Override in subclasses"""
        pass
    
    # ===== SHARED UI HELPERS =====
    
    def create_add_button(self):
        """Create standardized Add button"""
        return toga.Button(
            "Add", 
            on_press=lambda w: asyncio.create_task(self.presenter.handle_add_collection())
        )
    
    def format_breadcrumb_text(self, breadcrumb_path):
        """Generate breadcrumb text from path - shows just the parent level"""
        if len(breadcrumb_path) > 1:
            # Show just the parent (previous level)
            return breadcrumb_path[-2].name  # Second to last item is the parent
        elif len(breadcrumb_path) == 1:
            # At collection level, parent is "Collections"
            return "Collections"
        else:
            return "Collections"
    
    def should_show_back_button(self, breadcrumb_path, current_item):
        """Determine if back button should be visible"""
        return len(breadcrumb_path) >= 1 or current_item is not None
    
    def handle_item_selection(self, widget, **kwargs):
        """Unified item selection handler"""
        if widget.selection:
            self.presenter.handle_item_selection(widget.selection)
    
    def should_load_collections(self, breadcrumb_path, current_item):
        """Determine if we should load collections (at root level)"""
        return len(breadcrumb_path) == 0 and not current_item


class MobileCollectionDisplay(SharedDisplayMethods):
    """Mobile UI display - pure presentation, no logic"""
    
    def __init__(self, presenter: CollectionViewPresenter):
        super().__init__(presenter)
        
        # UI components
        self.container = None
        self.title_label = None
        self.back_button = None
        self.navigation_list = None
        
        self._create_ui()
    
    # Mobile doesn't have tree view - these methods are no-ops
    def _populate_tree_with_collections(self, collection_items):
        """No-op for mobile - no tree view"""
        pass
    
    def _update_tree_view(self, breadcrumb_path):
        """No-op for mobile - no tree view"""
        pass
    
    def _create_ui(self):
        """Create mobile UI - just widgets, no logic"""
        # Main container
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=1))
        
        # Header with breadcrumb navigation
        header = toga.Box(style=Pack(direction=ROW, margin=10))
        
        # Back button (initially hidden)
        self.back_button = toga.Button(
            "← Back", 
            on_press=lambda w: self.presenter.handle_back_navigation(),
            style=Pack(margin_right=10)
        )
        self.back_button.style.visibility = "hidden"
        header.add(self.back_button)
        
        # Breadcrumb title (dynamic)
        self.title_label = toga.Label(
            "Collections", 
            style=Pack(font_size=10, flex=1)
        )
        header.add(self.title_label)
        
        # Add collection button
        add_btn = self.create_add_button()
        add_btn.style.margin_left = 10
        header.add(add_btn)
        
        self.container.add(header)
        
        # Navigation list
        self.navigation_list = toga.DetailedList(
            data=[],
            on_select=self._on_item_select,
            style=Pack(flex=1)
        )
        
        self.container.add(self.navigation_list)
    
    def _on_item_select(self, widget, **kwargs):
        """Delegate item selection to presenter"""
        self.handle_item_selection(widget, **kwargs)
    
    def update_navigation(self, current_item, breadcrumb_path):
        """Update display when navigation changes"""
        try:
            # Update breadcrumb title using shared helper
            self.title_label.text = self.format_breadcrumb_text(breadcrumb_path)
            
            # Show/hide back button using shared helper
            if self.should_show_back_button(breadcrumb_path, current_item):
                self.back_button.style.visibility = "visible"
            else:
                self.back_button.style.visibility = "hidden"
            
            # Update navigation items
            if self.should_load_collections(breadcrumb_path, current_item):
                # We're at collections list - need to load collections
                asyncio.create_task(self.presenter.nav_logic.load_collections())
            else:
                # We're in a hierarchy - show current items
                self.update_navigation_items()
            
        except Exception as e:
            logger.error(f"Failed to update mobile navigation: {e}")
    
    def _update_collection_list(self, list_items):
        """Update the navigation list with collections"""
        self.navigation_list.data = list_items
    
    def _update_navigation_list(self, list_items):
        """Update the navigation list with current items"""
        self.navigation_list.data = list_items


class DesktopCollectionDisplay(SharedDisplayMethods):
    """Desktop UI display - pure presentation, no logic"""
    
    def __init__(self, presenter: CollectionViewPresenter):
        super().__init__(presenter)
        
        # UI components
        self.container = None
        self.collection_list = None
        self.folder_tree = None
        self.content_view = None
        self.breadcrumb_label = None  # NEW: Breadcrumb above folder tree
        
        self._create_ui()
    
    def _create_ui(self):
        """Create desktop UI - Tree + iOS-style + Preview"""
        # Main container (3 columns)
        self.container = toga.Box(style=Pack(direction=ROW, flex=1))
        
        # Left panel - Collections Tree
        left_panel = toga.Box(style=Pack(direction=COLUMN, width=250, margin=10))
        
        # Tree header with Add button
        tree_header = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        add_btn = self.create_add_button()
        tree_header.add(add_btn)
        left_panel.add(tree_header)
        
        # Collections tree (hierarchical view) 
        from toga.sources import TreeSource
        self.tree_source = TreeSource(accessors=["name", "tree_data"], data=[])
        self.collection_tree = toga.Tree(
            data=self.tree_source,
            accessors=["name"],
            on_select=self._on_tree_select,
            style=Pack(flex=1)
        )
        left_panel.add(self.collection_tree)
        
        # Center panel - iOS-style Current Level View
        center_panel = toga.Box(style=Pack(direction=COLUMN, width=400, margin=10))
        
        # iOS-style header with back button, breadcrumb, and actions
        header = toga.Box(style=Pack(direction=ROW, margin_bottom=10))
        
        # Back button (iOS-style)
        self.back_button = toga.Button(
            "← Back",
            on_press=lambda w: self.presenter.handle_back_navigation(),
            style=Pack(margin_right=10)
        )
        self.back_button.style.visibility = "hidden"
        header.add(self.back_button)
        
        # Breadcrumb (iOS-style)
        self.breadcrumb_label = toga.Label(
            "Collections", 
            style=Pack(font_size=10, flex=1)
        )
        header.add(self.breadcrumb_label)
        
        center_panel.add(header)
        
        # Current level list (iOS-style)
        self.current_level_list = toga.DetailedList(
            data=[],
            on_select=self._on_current_level_select,
            style=Pack(flex=1)
        )
        center_panel.add(self.current_level_list)
        
        # Right panel - Preview (Always Visible)
        from fichero.windows.main.views.collection.preview import PreviewManager
        self.preview_manager = PreviewManager(self.presenter, width=None, is_mobile=False)
        right_panel = self.preview_manager.container
        
        # Add all panels to main container
        self.container.add(left_panel)
        self.container.add(center_panel)
        self.container.add(right_panel)
    
    def _populate_tree_with_collections(self, collection_items):
        """Populate the tree with collections using proper lazy loading"""
        try:
            # Clear existing tree data
            self.tree_source.clear()
            
            # Add collections to tree root - NO pre-loading
            for item in collection_items:
                collection_data = item.get("collection", None)
                if collection_data:
                    # Create collection node - add empty children list to show disclosure triangle
                    node_data = {
                        "name": collection_data.name,
                        "tree_data": {
                            "collection": collection_data.name,
                            "type": "collection",
                            "loaded": False  # Mark as not loaded yet
                        }
                    }
                    
                    # Add with empty children array to show disclosure triangle
                    collection_node = self.tree_source.append(node_data, children=[])
                    logger.info(f"Added collection to tree: {collection_data.name}")
                    
        except Exception as e:
            logger.error(f"Failed to populate tree with collections: {e}")

    def _on_tree_select(self, widget, **kwargs):
        """Handle tree node selection - navigate and lazy load if needed"""
        try:
            # Get the selected node from the tree widget
            if not widget.selection:
                return
                
            node = widget.selection
            logger.info(f"Tree node selected: {node.name}")
            
            # Get tree metadata
            tree_data = node.tree_data
            node_type = tree_data.get("type", "unknown")
            
            if node_type == "collection":
                # Navigate to collection and lazy load if needed
                collection_name = tree_data.get("collection")
                if collection_name:
                    # Lazy load children if not loaded
                    if not tree_data.get("loaded", False):
                        self._lazy_load_collection_folders(node, collection_name)
                    
                    # Navigate to collection
                    asyncio.create_task(self.handle_collection_navigation(collection_name))
                    
            elif node_type == "folder":
                # Navigate to folder and lazy load if needed
                collection_name = tree_data.get("collection")
                folder_path = tree_data.get("folder_path", [])
                
                if collection_name and folder_path:
                    # Lazy load subfolders if not loaded
                    if not tree_data.get("loaded", False):
                        self._lazy_load_subfolder(node, collection_name, folder_path)
                    
                    # Navigate to folder
                    asyncio.create_task(self.handle_folder_navigation(collection_name, folder_path))
                    
        except Exception as e:
            logger.error(f"Failed to handle tree selection: {e}")

    def _lazy_load_collection_folders(self, collection_node, collection_name: str):
        """Lazy load folders for a collection - only when needed"""
        try:
            logger.info(f"Lazy loading folders for collection: {collection_name}")
            
            # Get collection data
            collections = self.presenter.nav_logic.library_manager.get_collections()
            target_collection = None
            for collection in collections:
                if collection.name == collection_name:
                    target_collection = collection
                    break
            
            if not target_collection:
                logger.warning(f"Collection not found for lazy loading: {collection_name}")
                return
            
            # Navigate to collection to get its structure
            collection_path = Path(target_collection.location)
            collection_item = self.presenter.nav_logic.navigator.build_collection_hierarchy(collection_path, collection_name)
            
            # Add immediate child folders only
            if hasattr(collection_item, 'children') and collection_item.children:
                for child in collection_item.children:
                    if child.item_type == "folder":
                        folder_data = {
                            "name": child.name,
                            "tree_data": {
                                "collection": collection_name,
                                "type": "folder",
                                "folder_path": [child.name],
                                "loaded": False  # Will lazy load subfolders if needed
                            }
                        }
                        
                        # Add with empty children to show disclosure triangle if it has subfolders
                        folder_node = collection_node.append(folder_data, children=[])
                        logger.debug(f"Added folder to tree: {child.name}")
            
            # Mark collection as loaded
            collection_node.tree_data["loaded"] = True
            logger.info(f"Lazy loaded {len(collection_node)} folders for collection: {collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to lazy load collection folders {collection_name}: {e}")

    def _lazy_load_subfolder(self, folder_node, collection_name: str, folder_path: list):
        """Lazy load subfolders for a folder - only when needed"""
        try:
            logger.info(f"Lazy loading subfolders for: {'/'.join(folder_path)}")
            
            # Get collection data
            collections = self.presenter.nav_logic.library_manager.get_collections()
            target_collection = None
            for collection in collections:
                if collection.name == collection_name:
                    target_collection = collection
                    break
            
            if not target_collection:
                logger.warning(f"Collection not found for lazy loading: {collection_name}")
                return
            
            # Build path to the folder
            collection_path = Path(target_collection.location)
            folder_full_path = collection_path
            for folder_name in folder_path:
                folder_full_path = folder_full_path / folder_name
            
            # Scan folder for subfolders
            if folder_full_path.exists() and folder_full_path.is_dir():
                for item in folder_full_path.iterdir():
                    if item.is_dir():
                        subfolder_path = folder_path + [item.name]
                        subfolder_data = {
                            "name": item.name,
                            "tree_data": {
                                "collection": collection_name,
                                "type": "folder",
                                "folder_path": subfolder_path,
                                "loaded": False
                            }
                        }
                        
                        # Add with empty children to show disclosure triangle
                        subfolder_node = folder_node.append(subfolder_data, children=[])
                        logger.debug(f"Added subfolder to tree: {item.name}")
            
            # Mark folder as loaded
            folder_node.tree_data["loaded"] = True
            logger.info(f"Lazy loaded subfolders for: {'/'.join(folder_path)}")
            
        except Exception as e:
            logger.error(f"Failed to lazy load subfolders {folder_path}: {e}")

    async def handle_folder_navigation(self, collection_name: str, folder_path: list):
        """Handle navigation to a folder from tree view"""
        try:
            logger.info(f"Navigating to folder from tree: {collection_name}/{'/'.join(folder_path)}")
            
            # Get collection
            collections = self.presenter.nav_logic.library_manager.get_collections()
            target_collection = None
            for collection in collections:
                if collection.name == collection_name:
                    target_collection = collection
                    break
            
            if not target_collection:
                logger.warning(f"Collection not found: {collection_name}")
                return False
            
            # Navigate to collection first
            collection_path = Path(target_collection.location)
            collection_item = self.presenter.nav_logic.navigator.build_collection_hierarchy(collection_path, collection_name)
            
            # Navigate through folder path
            current_item = collection_item
            for folder_name in folder_path:
                if hasattr(current_item, 'children') and current_item.children:
                    for child in current_item.children:
                        if child.name == folder_name and child.item_type == "folder":
                            current_item = child
                            break
                    else:
                        logger.warning(f"Folder not found in path: {folder_name}")
                        return False
                else:
                    logger.warning(f"No children found for folder: {current_item.name}")
                    return False
            
            # Navigate to the final folder
            if current_item:
                result = self.presenter.nav_logic.navigator.navigate_to_item(current_item)
                logger.info(f"Navigation result: {result}")
                return result
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to navigate to folder: {e}")
            return False

    def _update_tree_view(self, breadcrumb_path):
        """Update tree view to reflect current navigation - minimal since tree is lazy"""
        try:
            # Tree is lazy loaded, so just log the current path
            if breadcrumb_path:
                path_names = [item.name for item in breadcrumb_path]
                logger.info(f"Tree view updated for path: {'/'.join(path_names)}")
        except Exception as e:
            logger.error(f"Failed to update tree view: {e}")

    def _find_tree_node_by_collection(self, collection_name: str):
        """Find a collection node in the tree by name"""
        try:
            for i in range(len(self.tree_source)):
                node = self.tree_source[i]
                if node.name == collection_name:
                    return node
            return None
        except Exception as e:
            logger.error(f"Failed to find tree node for collection {collection_name}: {e}")
            return None
    
    def _on_current_level_select(self, widget, **kwargs):
        """Handle current level list selection - same as iOS"""
        self.handle_item_selection(widget, **kwargs)
    
    def update_navigation(self, current_item, breadcrumb_path):
        """Update display when navigation changes"""
        try:
            # Update breadcrumb (iOS-style)
            if breadcrumb_path:
                self.breadcrumb_label.text = self.format_breadcrumb_text(breadcrumb_path)
            else:
                self.breadcrumb_label.text = "Collections"
            
            # Show/hide back button (iOS-style)
            if self.should_show_back_button(breadcrumb_path, current_item):
                self.back_button.style.visibility = "visible"
            else:
                self.back_button.style.visibility = "hidden"
            
            # Update current level list (iOS-style center column)
            if self.should_load_collections(breadcrumb_path, current_item):
                # We're at collections list - clear current level and reload collections
                self.current_level_list.data = []
                asyncio.create_task(self.presenter.nav_logic.load_collections())
            else:
                # We're in a hierarchy - show current items
                self.update_navigation_items()
                
            # Update tree view (always show full hierarchy) - THIS IS KEY!
            self._update_tree_view(breadcrumb_path)
            
            # Update preview
            self._update_preview(current_item, breadcrumb_path)
            
        except Exception as e:
            logger.error(f"Failed to update desktop navigation: {e}")
    
    def _update_collection_list(self, list_items):
        """Update the current level list with collections"""
        self.current_level_list.data = list_items
        # Also update tree with collections
        self._populate_tree_with_collections(list_items)
    
    def _update_navigation_list(self, list_items):
        """Update the current level list with current items"""
        self.current_level_list.data = list_items
    
    def _update_preview(self, current_item, breadcrumb_path):
        """Update the preview panel with current context"""
        try:
            # Clear the preview manager
            self.preview_manager.clear()
            
            # Show navigation context in the preview manager
            if current_item:
                # If it's a file, try to preview it
                if hasattr(current_item, 'path') and current_item.path.is_file():
                    self.preview_manager.preview_file(current_item.path)
                else:
                    # Show item info
                    self.preview_manager.header.text = f"Item: {current_item.name}"
                    self.preview_manager.content_container.add(toga.Label(f"Type: {current_item.level.value}"))
                    
                    # Show current level summary
                    items = self.presenter.get_current_items()
                    folders = sum(1 for item in items if item.level.value == "folder")
                    files = sum(1 for item in items if item.level.value == "file")
                    
                    self.preview_manager.content_container.add(toga.Label(""))  # Spacer
                    self.preview_manager.content_container.add(toga.Label("Current Level:"))
                    self.preview_manager.content_container.add(toga.Label(f"• {folders} folders"))
                    self.preview_manager.content_container.add(toga.Label(f"• {files} files"))
                    
            elif breadcrumb_path:
                # Show breadcrumb context
                self.preview_manager.header.text = "Navigation"
                self.preview_manager.content_container.add(toga.Label(f"Level: {breadcrumb_path[-1].name if breadcrumb_path else 'Collections'}"))
                
                items = self.presenter.get_current_items()
                self.preview_manager.content_container.add(toga.Label(f"Items: {len(items)}"))
            else:
                self.preview_manager.header.text = "Collections Library"
                self.preview_manager.content_container.add(toga.Label("Select a collection to begin browsing"))
                
        except Exception as e:
            logger.error(f"Failed to update preview: {e}")


class CollectionView:
    """
    Minimal collection view that maximizes code sharing.
    
    This is just a thin coordinator - all logic is in the presenter,
    UI is just dumb displays that delegate everything to the presenter.
    """
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize minimal collection view"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Single presenter handles all logic
        self.presenter = CollectionViewPresenter(app)
        
        # Platform-appropriate display
        if is_mobile:
            self.display = MobileCollectionDisplay(self.presenter)
        else:
            self.display = DesktopCollectionDisplay(self.presenter)
        
        logger.info(f"Created minimal collection view (mobile: {is_mobile})")
    
    def create(self) -> toga.Widget:
        """Create method for view manager compatibility"""
        return self.display.container
    
    def get_container(self) -> toga.Widget:
        """Get container method for backward compatibility"""
        return self.display.container
    
    async def initialize(self):
        """Initialize the view"""
        logger.info("Initializing minimal collection view...")
        result = await self.presenter.initialize()
        logger.info(f"Minimal collection view initialized: {result}")
        return result
    
    async def refresh(self):
        """Refresh the view"""
        try:
            await self.presenter.nav_logic.load_collections()
        except Exception as e:
            logger.error(f"Failed to refresh: {e}") 