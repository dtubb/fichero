"""
Shared Collection View Components

Shared navigation logic and components between desktop and mobile collection views.
This file contains the core navigation logic that both platforms can use.
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import asyncio
import logging
from typing import Optional, Callable, List
from pathlib import Path

from fichero.windows.main.services.library_manager import LibraryManager, CollectionInfo
from fichero.windows.main.navigation import HierarchyNavigator, NavigationItem, NavigationLevel

logger = logging.getLogger(__name__)


class IconManager:
    """Manages loading icons from the app resources"""
    
    _icons_cache = {}
    
    @classmethod
    def get_icon(cls, icon_name: str, size: str = "32") -> Optional[toga.Icon]:
        """Load an icon from the app resources with caching"""
        cache_key = f"{icon_name}_{size}"
        
        if cache_key in cls._icons_cache:
            return cls._icons_cache[cache_key]
        
        try:
            app = toga.App.app
            if not app:
                logger.warning("No Toga app instance available for icon loading")
                return None
                
            # Try different icon paths - icons are in src/resources/icons
            icon_paths = [
                f"resources/icons/{icon_name}_{size}.png",
                f"resources/icons/{icon_name}.png", 
                f"resources/icons/{icon_name}/{icon_name}.png"  # For subfolder icons like document/document.png
            ]
            
            for icon_path in icon_paths:
                try:
                    icon_resource = app.paths.app / icon_path
                    logger.debug(f"Trying icon path: {icon_resource}")
                    if icon_resource.exists():
                        icon = toga.Icon(icon_resource)
                        cls._icons_cache[cache_key] = icon
                        logger.info(f"Successfully loaded icon: {icon_path}")
                        return icon
                except Exception as e:
                    logger.debug(f"Failed to load icon {icon_path}: {e}")
                    continue
            
            logger.warning(f"Icon not found: {icon_name} (tried {len(icon_paths)} paths)")
            return None
            
        except Exception as e:
            logger.error(f"Error loading icon {icon_name}: {e}")
            return None


class SharedNavigationLogic:
    """Shared navigation logic for both desktop and mobile"""
    
    def __init__(self, app):
        """Initialize shared navigation components"""
        self.app = app
        
        # Core navigation components
        self.library_manager: Optional[LibraryManager] = None
        self.navigator: Optional[HierarchyNavigator] = None
        
        # Callbacks for UI updates
        self.on_navigation_change: Optional[Callable] = None
        self.on_collections_loaded: Optional[Callable] = None
        
    async def initialize(self):
        """Initialize the shared navigation system"""
        try:
            # Initialize library manager
            self.library_manager = LibraryManager(self.app)
            await self.library_manager.initialize_library()
            
            # Initialize hierarchical navigator
            self.navigator = HierarchyNavigator()
            
            # Set up navigation callbacks
            self.navigator.set_navigation_change_callback(self._on_navigation_change)
            
            # Load collections
            await self.load_collections()
            
            logger.info("Shared navigation logic initialized")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize shared navigation: {e}")
            return False
    
    def _on_navigation_change(self, current_item, breadcrumb_path):
        """Handle navigation changes - notify UI components"""
        try:
            if self.on_navigation_change:
                self.on_navigation_change(current_item, breadcrumb_path)
            logger.info(f"Navigation changed to: {current_item.name if current_item else 'root'}")
        except Exception as e:
            logger.error(f"Failed to handle navigation change: {e}")
    
    async def load_collections(self):
        """Load and return collections for display"""
        try:
            if not self.library_manager:
                return []
            
            collections = self.library_manager.get_collections()
            
            # Notify UI that collections were loaded
            if self.on_collections_loaded:
                self.on_collections_loaded(collections)
                
            logger.info(f"Loaded {len(collections)} collections")
            return collections
            
        except Exception as e:
            logger.error(f"Failed to load collections: {e}")
            return []
    
    async def add_collection_from_folder(self, folder_path: str):
        """Add a new collection from a folder path"""
        try:
            collection_name = Path(folder_path).name
            
            collection = await self.library_manager.add_collection(
                name=collection_name,
                location=folder_path,
                collection_type="external",
                description=f"Collection from {folder_path}"
            )
            
            if collection:
                # Refresh collections
                await self.load_collections()
                logger.info(f"Added collection: {collection.name}")
                return collection
            else:
                logger.error("Failed to add collection")
                return None
                
        except Exception as e:
            logger.error(f"Failed to add collection from folder: {e}")
            return None
    
    def navigate_into_collection(self, collection: CollectionInfo):
        """Navigate into a collection"""
        try:
            if not self.navigator:
                return False
                
            # Build hierarchy for this collection
            collection_path = Path(collection.location)
            collection_item = self.navigator.build_collection_hierarchy(collection_path, collection.name)
            
            # Navigate to the collection using the new method
            return self.navigator.navigate_to_collection(collection_item)
            
        except Exception as e:
            logger.error(f"Failed to navigate into collection: {e}")
            return False
    
    async def navigate_to_collection(self, collection: CollectionInfo):
        """Async version of navigate_into_collection for tree view navigation"""
        try:
            if not self.navigator:
                return False
                
            # Build hierarchy for this collection
            collection_path = Path(collection.location)
            collection_item = self.navigator.build_collection_hierarchy(collection_path, collection.name)
            
            # Navigate to the collection
            result = self.navigator.navigate_to_collection(collection_item)
            
            # Force update navigation to ensure UI refreshes
            if result:
                current_item = self.navigator.get_current_item()
                breadcrumb_path = self.navigator.get_breadcrumb_path()
                if self.on_navigation_change:
                    self.on_navigation_change(current_item, breadcrumb_path)
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to navigate to collection: {e}")
            return False
    
    def navigate_into_folder(self, folder_item: NavigationItem):
        """Navigate into a folder"""
        try:
            if not self.navigator:
                return False
                
            # Use the standard navigate_to method but ensure lazy loading
            self.navigator.navigate_to(folder_item)
            
            # Ensure the folder is scanned for children
            if not folder_item.metadata.get("scanned", False):
                self.navigator.scan_directory_lazy(folder_item)
                
            # Force a navigation change notification after scanning
            current_item = self.navigator.get_current_item()
            breadcrumb_path = self.navigator.get_breadcrumb_path()
            if self.on_navigation_change:
                self.on_navigation_change(current_item, breadcrumb_path)
            
            logger.info(f"Navigated into folder: {folder_item.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to navigate into folder: {e}")
            return False
    
    def navigate_back(self):
        """Navigate back one level"""
        if self.navigator:
            return self.navigator.navigate_up()
        return False
    
    def get_current_items(self):
        """Get items at the current navigation level"""
        if self.navigator:
            return self.navigator.get_items_at_current_level()
        return []
    
    def get_breadcrumb_path(self):
        """Get the current breadcrumb path"""
        if self.navigator:
            return self.navigator.get_breadcrumb_path()
        return []
    
    def get_current_item(self):
        """Get the current navigation item"""
        if self.navigator:
            return self.navigator.get_current_item()
        return None


class SharedItemRenderer:
    """Shared logic for rendering navigation items"""
    
    @staticmethod
    def get_file_icon(extension: str) -> Optional[toga.Icon]:
        """Get appropriate icon for file extension using proper Toga icons"""
        extension = extension.lower()
        
        # Try to get specific icons for different file types
        if extension in {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}:
            return IconManager.get_icon("document")  # Use document icon for images
        elif extension in {'.pdf', '.doc', '.docx', '.txt', '.md'}:
            return IconManager.get_icon("document") 
        else:
            return IconManager.get_icon("document")  # Default to document icon
    
    @staticmethod 
    def get_folder_icon() -> Optional[toga.Icon]:
        """Get the folder icon"""
        return IconManager.get_icon("folder")
    
    @staticmethod
    def get_collection_icon(collection_type: str = "local") -> Optional[toga.Icon]:
        """Get icon for collection based on type"""
        if collection_type == "local":
            return IconManager.get_icon("folder")
        else:
            return IconManager.get_icon("folder")  # Could add link icon later
    
    @staticmethod
    def format_item_for_display(item: NavigationItem, show_subtitle: bool = False) -> dict:
        """Format a navigation item for display in lists"""
        # Clean display: just the name (no emoji icons)
        display_text = item.name
        
        return {
            "title": display_text,
            "subtitle": "" if not show_subtitle else f"{item.level.value}",
            "navigation_item": item,
            "icon": SharedItemRenderer.get_folder_icon() if item.level == NavigationLevel.FOLDER else SharedItemRenderer.get_file_icon(item.get_metadata('extension', ''))
        }
    
    @staticmethod
    def format_collection_for_display(collection: CollectionInfo) -> dict:
        """Format a collection for display in lists"""
        # Clean display: just the name (no emoji icons)
        display_text = collection.name
        
        return {
            "title": display_text,
            "subtitle": "",  # No subtitle for clean display
            "collection": collection,
            "icon": SharedItemRenderer.get_collection_icon(collection.type)
        } 