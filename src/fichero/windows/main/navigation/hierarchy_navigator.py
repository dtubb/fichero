"""
Hierarchical Navigator

Manages navigation through the library hierarchy:
Library > Collection > Folder > File > Page
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from enum import Enum

logger = logging.getLogger(__name__)


class NavigationLevel(Enum):
    """Navigation levels in the hierarchy"""
    LIBRARY = "library"
    COLLECTION = "collection"
    FOLDER = "folder"
    FILE = "file"
    PAGE = "page"


class NavigationItem:
    """Represents an item in the navigation hierarchy"""
    
    def __init__(self, 
                 name: str,
                 path: Path,
                 level: NavigationLevel,
                 metadata: Optional[Dict[str, Any]] = None,
                 children: Optional[List['NavigationItem']] = None):
        self.name = name
        self.path = path
        self.level = level
        self.metadata = metadata or {}
        self.children = children or []
        self.parent: Optional[NavigationItem] = None
        
        # Set parent references for children
        for child in self.children:
            child.parent = self
    
    def add_child(self, child: 'NavigationItem'):
        """Add a child item"""
        child.parent = self
        self.children.append(child)
    
    def has_children(self) -> bool:
        """Check if this item has children"""
        return len(self.children) > 0
    
    def get_children(self) -> List['NavigationItem']:
        """Get all children"""
        return self.children.copy()
    
    def find_child(self, name: str) -> Optional['NavigationItem']:
        """Find a child by name"""
        for child in self.children:
            if child.name == name:
                return child
        return None
    
    def get_path_string(self) -> str:
        """Get the full path as a string"""
        return str(self.path)
    
    def get_metadata(self, key: str, default=None):
        """Get metadata value"""
        return self.metadata.get(key, default)
    
    def set_metadata(self, key: str, value: Any):
        """Set metadata value"""
        self.metadata[key] = value


class HierarchyNavigator:
    """Manages hierarchical navigation through the library"""
    
    def __init__(self):
        """Initialize the navigator"""
        self.current_path: List[NavigationItem] = []
        self.root: Optional[NavigationItem] = None
        
        # Callbacks
        self.on_navigation_change: Optional[Callable] = None
        self.on_item_select: Optional[Callable] = None
        
        logger.info("HierarchyNavigator initialized")
    
    def set_root(self, root_item: NavigationItem):
        """Set the root item (Library level)"""
        self.root = root_item
        self.current_path = [root_item]
        logger.info(f"Set root: {root_item.name}")
    
    def get_current_item(self) -> Optional[NavigationItem]:
        """Get the currently selected item"""
        return self.current_path[-1] if self.current_path else None
    
    def get_current_level(self) -> NavigationLevel:
        """Get the current navigation level"""
        current = self.get_current_item()
        return current.level if current else NavigationLevel.LIBRARY
    
    def get_breadcrumb_path(self) -> List[NavigationItem]:
        """Get the current breadcrumb path"""
        return self.current_path.copy()
    
    def navigate_to(self, item: NavigationItem):
        """Navigate to a specific item"""
        try:
            # Check if we have a root and the item is connected to it
            if self.root:
                path = self._find_path_to_item(item)
                if path:
                    self.current_path = path
                    self._notify_navigation_change()
                    logger.info(f"Navigated to: {item.name} ({item.level.value})")
                    return
            
            # If no root or item not connected, treat this item as a new root/start point
            if item.level == NavigationLevel.COLLECTION:
                # Set this collection as the starting point
                self.current_path = [item]
                self._notify_navigation_change()
                logger.info(f"Started navigation at collection: {item.name}")
            else:
                # For non-collection items, add to current path to maintain breadcrumb
                if self.current_path and item.level == NavigationLevel.FOLDER:
                    # Add folder to existing path for breadcrumb navigation
                    self.current_path.append(item)
                else:
                    # For other items or if no current path, start fresh
                    self.current_path = [item]
                self._notify_navigation_change()
                logger.info(f"Navigation to: {item.name} ({item.level.value})")
                
        except Exception as e:
            logger.error(f"Failed to navigate to {item.name}: {e}")
    
    def navigate_to_collection(self, collection_item: NavigationItem):
        """Navigate to a collection and set it as the current context"""
        try:
            if collection_item.level != NavigationLevel.COLLECTION:
                logger.error(f"Item {collection_item.name} is not a collection")
                return False
                
            # Set this collection as the current root context
            self.current_path = [collection_item]
            
            # Ensure the collection is scanned for children
            if not collection_item.metadata.get("scanned", False):
                self.scan_directory_lazy(collection_item)
            
            self._notify_navigation_change()
            logger.info(f"Navigated to collection: {collection_item.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to navigate to collection {collection_item.name}: {e}")
            return False
    
    def navigate_up(self) -> bool:
        """Navigate up one level"""
        if len(self.current_path) > 1:
            # Navigate up within the hierarchy (folder to parent folder, or folder to collection)
            self.current_path.pop()
            self._notify_navigation_change()
            current = self.get_current_item()
            logger.info(f"Navigated up to: {current.name if current else 'root'}")
            return True
        elif len(self.current_path) == 1:
            # Navigate from collection back to collections list
            self.current_path = []
            self._notify_navigation_change()
            logger.info("Navigated back to collections list")
            return True
        return False
    
    def navigate_to_root(self):
        """Navigate back to root"""
        if self.root:
            self.current_path = [self.root]
            self._notify_navigation_change()
            logger.info("Navigated to root")
    
    def get_items_at_current_level(self) -> List[NavigationItem]:
        """Get items at the current navigation level"""
        current = self.get_current_item()
        if current:
            return current.get_children()
        return []
    
    def _find_path_to_item(self, target_item: NavigationItem) -> Optional[List[NavigationItem]]:
        """Find the path from root to a specific item"""
        if not self.root:
            return None
        
        def find_path_recursive(current: NavigationItem, target: NavigationItem, path: List[NavigationItem]) -> Optional[List[NavigationItem]]:
            current_path = path + [current]
            
            if current == target:
                return current_path
            
            for child in current.children:
                result = find_path_recursive(child, target, current_path)
                if result:
                    return result
            
            return None
        
        return find_path_recursive(self.root, target_item, [])
    
    def _notify_navigation_change(self):
        """Notify listeners of navigation change"""
        if self.on_navigation_change:
            try:
                self.on_navigation_change(self.get_current_item(), self.get_breadcrumb_path())
            except Exception as e:
                logger.error(f"Error in navigation change callback: {e}")
    
    def _is_hidden_file(self, path: Path) -> bool:
        """Check if a file should be hidden from display"""
        name = path.name
        
        # Hidden files starting with dot
        if name.startswith('.'):
            return True
            
        # System files we don't want to show
        hidden_names = {
            'Thumbs.db',      # Windows thumbnails
            'desktop.ini',    # Windows folder config
            '__pycache__',    # Python cache
            '.git',           # Git repository
            '.svn',           # SVN repository
            '.idea',          # IntelliJ IDE
            '.vscode',        # VS Code settings
            'node_modules',   # Node.js packages
        }
        
        return name in hidden_names
    
    def build_collection_hierarchy(self, collection_path: Path, collection_name: str) -> NavigationItem:
        """Build a hierarchy for a collection (lazy loading)"""
        try:
            collection_item = NavigationItem(
                name=collection_name,
                path=collection_path,
                level=NavigationLevel.COLLECTION,
                metadata={
                    "type": "collection",
                    "description": f"Collection: {collection_name}",
                    "scanned": False  # Mark as not yet scanned
                }
            )
            
            logger.info(f"Created collection hierarchy for: {collection_name}")
            return collection_item
            
        except Exception as e:
            logger.error(f"Failed to build hierarchy for {collection_name}: {e}")
            return NavigationItem(
                name=collection_name,
                path=collection_path,
                level=NavigationLevel.COLLECTION,
                metadata={"error": str(e)}
            )
    
    def scan_directory_lazy(self, item: NavigationItem):
        """Scan a directory only when accessed (lazy loading)"""
        try:
            if item.metadata.get("scanned", False):
                return  # Already scanned
            
            if not item.path.exists() or not item.path.is_dir():
                return
            
            # Scan only the immediate children
            children = []
            for item_path in sorted(item.path.iterdir()):
                # Skip hidden files and system files
                if self._is_hidden_file(item_path):
                    continue
                    
                if item_path.is_dir():
                    # Create folder item (not scanned yet)
                    folder_item = NavigationItem(
                        name=item_path.name,
                        path=item_path,
                        level=NavigationLevel.FOLDER,
                        metadata={
                            "type": "folder",
                            "scanned": False  # Will be scanned when accessed
                        }
                    )
                    children.append(folder_item)
                    
                elif item_path.is_file():
                    # Create file item
                    try:
                        file_item = NavigationItem(
                            name=item_path.name,
                            path=item_path,
                            level=NavigationLevel.FILE,
                            metadata={
                                "type": "file",
                                "size": item_path.stat().st_size,
                                "extension": item_path.suffix.lower(),
                                "can_navigate": False  # Single files can't be navigated into
                            }
                        )
                        children.append(file_item)
                    except OSError:
                        # Skip files we can't access
                        continue
                else:
                    # Handle special cases like symbolic links, device files, etc.
                    # For now, treat as files but mark appropriately
                    try:
                        special_item = NavigationItem(
                            name=item_path.name,
                            path=item_path,
                            level=NavigationLevel.FILE,
                            metadata={
                                "type": "special",
                                "can_navigate": item_path.is_dir(),  # Can navigate if it's effectively a directory
                                "extension": item_path.suffix.lower() if item_path.suffix else ""
                            }
                        )
                        children.append(special_item)
                    except OSError:
                        # Skip items we can't access
                        continue
            
            # Add all children to the item
            for child in children:
                item.add_child(child)
            
            # Mark as scanned
            item.metadata["scanned"] = True
            item.metadata["item_count"] = len(children)
            
            logger.info(f"Scanned directory: {item.name} ({len(children)} items)")
            
        except Exception as e:
            logger.error(f"Failed to scan directory {item.name}: {e}")
            item.metadata["error"] = str(e)
    
    def set_navigation_change_callback(self, callback: Callable):
        """Set callback for navigation changes"""
        self.on_navigation_change = callback
    
    def set_item_select_callback(self, callback: Callable):
        """Set callback for item selection"""
        self.on_item_select = callback 