"""
Navigation State Manager

Tracks the current position in the library hierarchy and manages
drill-down navigation state for both desktop and mobile.
"""

import logging
from enum import Enum
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class NavigationLevel(Enum):
    """Navigation hierarchy levels"""
    COLLECTIONS = "collections"
    FOLDERS = "folders" 
    DOCUMENTS = "documents"
    PAGES = "pages"


@dataclass
class NavigationItem:
    """Represents an item at any navigation level"""
    id: str
    name: str
    level: NavigationLevel
    path: str
    metadata: Dict[str, Any]
    has_children: bool = False
    children_count: int = 0
    
    def __str__(self):
        return f"{self.name} ({self.level.value})"


class NavigationState:
    """
    Manages navigation state for library hierarchy.
    
    Tracks current path: Collection → Folder → Document → Page
    Provides drill-down and back navigation functionality.
    """
    
    def __init__(self):
        """Initialize navigation state"""
        # Current navigation path
        self.path: List[NavigationItem] = []
        
        # Current level being displayed
        self.current_level: NavigationLevel = NavigationLevel.COLLECTIONS
        
        # Current items at the current level
        self.current_items: List[NavigationItem] = []
        
        # Selected item at current level
        self.selected_item: Optional[NavigationItem] = None
        
        # Callbacks for navigation events
        self.on_level_change: Optional[Callable[[NavigationLevel, List[NavigationItem]], None]] = None
        self.on_selection_change: Optional[Callable[[Optional[NavigationItem]], None]] = None
        self.on_items_load: Optional[Callable[[NavigationLevel, str], List[NavigationItem]]] = None
        
    def get_current_path_string(self) -> str:
        """Get human-readable current path"""
        if not self.path:
            return "Library"
        
        path_names = [item.name for item in self.path]
        return " > ".join(path_names)
    
    def get_current_level(self) -> NavigationLevel:
        """Get current navigation level"""
        return self.current_level
    
    def can_go_back(self) -> bool:
        """Check if we can navigate back"""
        return len(self.path) > 0
    
    def get_back_level(self) -> Optional[NavigationLevel]:
        """Get the level we would go back to"""
        if not self.can_go_back():
            return None
            
        if len(self.path) == 1:
            return NavigationLevel.COLLECTIONS
        elif len(self.path) == 2:
            return NavigationLevel.FOLDERS
        elif len(self.path) == 3:
            return NavigationLevel.DOCUMENTS
        else:
            return NavigationLevel.PAGES
    
    def navigate_to_level(self, level: NavigationLevel, parent_path: str = ""):
        """Navigate to a specific level"""
        try:
            self.current_level = level
            
            # Load items for this level
            if self.on_items_load:
                self.current_items = self.on_items_load(level, parent_path)
            else:
                self.current_items = []
            
            # Clear selection
            self.selected_item = None
            
            # Notify level change
            if self.on_level_change:
                self.on_level_change(level, self.current_items)
                
            logger.info(f"Navigated to level: {level.value} with {len(self.current_items)} items")
            
        except Exception as e:
            logger.error(f"Failed to navigate to level {level.value}: {e}")
    
    def drill_down(self, item: NavigationItem):
        """Drill down into a selected item"""
        try:
            # Add item to path
            self.path.append(item)
            self.selected_item = item
            
            # Determine next level
            next_level = self._get_next_level(item.level)
            if next_level:
                self.navigate_to_level(next_level, item.path)
            
            logger.info(f"Drilled down into: {item.name} at level {item.level.value}")
            
        except Exception as e:
            logger.error(f"Failed to drill down into {item.name}: {e}")
    
    def go_back(self):
        """Navigate back to previous level"""
        try:
            if not self.can_go_back():
                logger.warning("Cannot go back - already at root level")
                return
            
            # Remove last item from path
            removed_item = self.path.pop()
            
            # Determine current level
            if not self.path:
                # Back to collections
                self.navigate_to_level(NavigationLevel.COLLECTIONS)
            else:
                # Back to parent level
                parent_item = self.path[-1]
                parent_level = parent_item.level
                next_level = self._get_next_level(parent_level)
                if next_level:
                    self.navigate_to_level(next_level, parent_item.path)
            
            logger.info(f"Navigated back from: {removed_item.name}")
            
        except Exception as e:
            logger.error(f"Failed to go back: {e}")
    
    def select_item(self, item: NavigationItem):
        """Select an item at the current level"""
        self.selected_item = item
        
        # Notify selection change
        if self.on_selection_change:
            self.on_selection_change(item)
            
        logger.info(f"Selected item: {item.name}")
    
    def get_current_items(self) -> List[NavigationItem]:
        """Get items at current level"""
        return self.current_items
    
    def get_selected_item(self) -> Optional[NavigationItem]:
        """Get currently selected item"""
        return self.selected_item
    
    def refresh_current_level(self):
        """Refresh items at current level"""
        parent_path = ""
        if self.path:
            parent_path = self.path[-1].path
            
        self.navigate_to_level(self.current_level, parent_path)
    
    def reset(self):
        """Reset navigation to root level"""
        self.path.clear()
        self.selected_item = None
        self.navigate_to_level(NavigationLevel.COLLECTIONS)
        logger.info("Navigation state reset to root")
    
    def _get_next_level(self, current_level: NavigationLevel) -> Optional[NavigationLevel]:
        """Get the next level in hierarchy"""
        level_order = [
            NavigationLevel.COLLECTIONS,
            NavigationLevel.FOLDERS, 
            NavigationLevel.DOCUMENTS,
            NavigationLevel.PAGES
        ]
        
        try:
            current_index = level_order.index(current_level)
            if current_index < len(level_order) - 1:
                return level_order[current_index + 1]
        except ValueError:
            pass
            
        return None
    
    # Helper methods for building navigation items
    
    @staticmethod
    def create_collection_item(name: str, path: str, metadata: Dict[str, Any] = None) -> NavigationItem:
        """Create a collection navigation item"""
        return NavigationItem(
            id=f"collection_{name}",
            name=name,
            level=NavigationLevel.COLLECTIONS,
            path=path,
            metadata=metadata or {},
            has_children=True
        )
    
    @staticmethod
    def create_folder_item(name: str, path: str, metadata: Dict[str, Any] = None) -> NavigationItem:
        """Create a folder navigation item"""
        return NavigationItem(
            id=f"folder_{name}",
            name=name,
            level=NavigationLevel.FOLDERS,
            path=path,
            metadata=metadata or {},
            has_children=True
        )
    
    @staticmethod
    def create_document_item(name: str, path: str, metadata: Dict[str, Any] = None) -> NavigationItem:
        """Create a document navigation item"""
        return NavigationItem(
            id=f"document_{name}",
            name=name,
            level=NavigationLevel.DOCUMENTS,
            path=path,
            metadata=metadata or {},
            has_children=True
        )
    
    @staticmethod
    def create_page_item(name: str, path: str, metadata: Dict[str, Any] = None) -> NavigationItem:
        """Create a page navigation item"""
        return NavigationItem(
            id=f"page_{name}",
            name=name,
            level=NavigationLevel.PAGES,
            path=path,
            metadata=metadata or {},
            has_children=False
        ) 