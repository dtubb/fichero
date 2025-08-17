"""
Collection Presenter

Core business logic and state management for collection views.
All UI components delegate to this presenter for data operations.
"""

import asyncio
import logging
from typing import Optional, Callable, List
from pathlib import Path

from fichero.windows.main.services.library_manager import LibraryManager, CollectionInfo
from fichero.windows.main.navigation import HierarchyNavigator, NavigationItem, NavigationLevel
from fichero.windows.main.views.collection_view_shared import SharedNavigationLogic
from .shared_preview import ImagePreviewHelper

logger = logging.getLogger(__name__)


class CollectionPresenter:
    """
    Single source of truth for all collection view behavior.
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
            import toga
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
                        # Handle single file selection
                        self._handle_file_selection(navigation_item)
                    
        except Exception as e:
            logger.error(f"Failed to handle item selection: {e}")
    
    def _handle_file_selection(self, navigation_item):
        """Handle selection of a single file"""
        try:
            # Use the preview manager to handle all file types
            logger.info(f"Opening preview for: {navigation_item.name}")
            for ui_display in self.ui_displays:
                if hasattr(ui_display, 'preview_manager'):
                    # Use the new preview manager
                    ui_display.preview_manager.preview_file(navigation_item.path)
                elif hasattr(ui_display, 'show_image_preview'):
                    # Fallback to old image preview for backward compatibility
                    ui_display.show_image_preview(navigation_item.path, navigation_item.name)
                
        except Exception as e:
            logger.error(f"Failed to handle file selection: {e}")
    
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