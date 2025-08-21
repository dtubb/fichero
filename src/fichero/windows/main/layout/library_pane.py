"""
Library Pane for Fichero

Manages the left pane content for library navigation with:
- Global sections (Inbox, Tags, Trash)
- Collections list
- External links
- Navigation state
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN, ROW
import logging
from typing import Optional, List, Dict, Any, Callable

from ..views.base_view import BaseView
from ..containers.scroll_container import ScrollableContainer

logger = logging.getLogger(__name__)


class LibraryPane:
    """Manages the left pane content for library navigation"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize library pane"""
        self.app = app
        self.is_mobile = is_mobile
        
        # Pane container
        self.container: Optional[toga.Box] = None
        
        # Navigation sections
        self.global_sections: Dict[str, Dict[str, Any]] = {}
        self.collections: List[Dict[str, Any]] = []
        self.external_links: List[Dict[str, Any]] = []
        
        # Navigation state
        self.current_section: Optional[str] = None
        self.current_collection: Optional[str] = None
        
        # Callbacks
        self.on_section_selected: Optional[Callable] = None
        self.on_collection_selected: Optional[Callable] = None
        self.on_external_link_selected: Optional[Callable] = None
        
        # Create pane
        self._create_pane()
        
        logger.info("Library pane initialized successfully")
    
    def _create_pane(self):
        """Create the library pane structure"""
        try:
            # Create main container
            self.container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    flex=1,
                    background_color="#F0F0F0"
                )
            )
            
            # Create scrollable container for content
            self.scroll_container = ScrollableContainer(self.app, self.is_mobile)
            
            # Add scroll container to main container
            self.container.add(self.scroll_container.get_container())
            
            # Create initial content
            self._create_initial_content()
            
        except Exception as e:
            logger.error(f"Failed to create library pane: {e}")
    
    def _create_initial_content(self):
        """Create the initial library pane content"""
        try:
            # Create global sections
            self._create_global_sections()
            
            # Create collections section
            self._create_collections_section()
            
            # Create external links section
            self._create_external_links_section()
            
        except Exception as e:
            logger.error(f"Failed to create initial content: {e}")
    
    def _create_global_sections(self):
        """Create the global sections (Inbox, Tags, Trash)"""
        try:
            # Global sections header
            global_header = toga.Label(
                "🌐 Global",
                style=Pack(
                    font_size=14,
                    font_weight="bold",
                    margin=(15, 10, 5, 10),
                    color="#333333"
                )
            )
            self.scroll_container.add_content(global_header)
            
            # Global Inbox
            inbox_item = self._create_navigation_item(
                "📥 Global Inbox",
                "global_inbox",
                "global",
                description="System-wide inbox for all documents"
            )
            self.scroll_container.add_content(inbox_item)
            self.global_sections["global_inbox"] = {"type": "global", "name": "Global Inbox"}
            
            # Tags
            tags_item = self._create_navigation_item(
                "🏷️ Tags",
                "tags",
                "global",
                description="Document tags and categories"
            )
            self.scroll_container.add_content(tags_item)
            self.global_sections["tags"] = {"type": "global", "name": "Tags"}
            
            # Trash
            trash_item = self._create_navigation_item(
                "🗑️ Trash",
                "trash",
                "global",
                description="Deleted documents and collections"
            )
            self.scroll_container.add_content(trash_item)
            self.global_sections["trash"] = {"type": "global", "name": "Trash"}
            
            # Add separator
            separator = toga.Box(
                style=Pack(
                    height=1,
                    background_color="#D0D0D0",
                    margin=(10, 15)
                )
            )
            self.scroll_container.add_content(separator)
            
        except Exception as e:
            logger.error(f"Failed to create global sections: {e}")
    
    def _create_collections_section(self):
        """Create the collections section"""
        try:
            # Collections header
            collections_header = toga.Label(
                "📁 Collections",
                style=Pack(
                    font_size=14,
                    font_weight="bold",
                    margin=(15, 10, 5, 10),
                    color="#333333"
                )
            )
            self.scroll_container.add_content(collections_header)
            
            # Add placeholder for collections
            placeholder = toga.Label(
                "No collections available",
                style=Pack(
                    margin=(5, 20),
                    font_size=12,
                    color="#666666"
                )
            )
            self.scroll_container.add_content(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to create collections section: {e}")
    
    def _create_external_links_section(self):
        """Create the external links section"""
        try:
            # External links header
            external_header = toga.Label(
                "🔗 External Links",
                style=Pack(
                    font_size=14,
                    font_weight="bold",
                    margin=(15, 10, 5, 10),
                    color="#333333"
                )
            )
            self.scroll_container.add_content(external_header)
            
            # Add placeholder for external links
            placeholder = toga.Label(
                "No external links configured",
                style=Pack(
                    margin=(5, 20),
                    font_size=12,
                    color="#666666"
                )
            )
            self.scroll_container.add_content(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to create external links section: {e}")
    
    def _create_navigation_item(self, text: str, item_id: str, section: str, description: str = "") -> toga.Widget:
        """Create a navigation item widget"""
        try:
            # Create item container
            item_container = toga.Box(
                style=Pack(
                    direction=COLUMN,
                    margin=(8, 12),
                    background_color="#FFFFFF",
                    border_color="#E0E0E0",
                    border_width=1
                )
            )
            
            # Item text
            text_label = toga.Label(
                text,
                style=Pack(
                    font_size=13,
                    color="#333333"
                )
            )
            item_container.add(text_label)
            
            # Item description (if provided)
            if description:
                desc_label = toga.Label(
                    description,
                    style=Pack(
                        margin=(2, 0, 0, 0),
                        font_size=11,
                        color="#666666"
                    )
                )
                item_container.add(desc_label)
            
            # Make item clickable
            item_container.on_press = lambda widget: self._on_item_selected(item_id, section)
            
            return item_container
            
        except Exception as e:
            logger.error(f"Failed to create navigation item: {e}")
            # Return fallback widget
            return toga.Label(f"Error creating item: {e}")
    
    def _on_item_selected(self, item_id: str, section: str):
        """Handle navigation item selection"""
        try:
            logger.debug(f"Navigation item selected: {item_id} in section {section}")
            
            # Update current section
            self.current_section = section
            
            # Handle different section types
            if section == "global":
                self.current_collection = None
                if self.on_section_selected:
                    self.on_section_selected(item_id, section)
            elif section == "collections":
                self.current_collection = item_id
                if self.on_collection_selected:
                    self.on_collection_selected(item_id)
            elif section == "external":
                if self.on_external_link_selected:
                    self.on_external_link_selected(item_id)
            
            # Update visual state
            self._update_selection_state()
            
        except Exception as e:
            logger.error(f"Failed to handle item selection: {e}")
    
    def _update_selection_state(self):
        """Update the visual state of selected items"""
        try:
            # This would update the visual appearance of selected items
            # For now, just log the current state
            logger.debug(f"Selection state updated: section={self.current_section}, collection={self.current_collection}")
            
        except Exception as e:
            logger.error(f"Failed to update selection state: {e}")
    
    def add_collection(self, collection_data: Dict[str, Any]):
        """Add a collection to the library pane"""
        try:
            # Add to collections list
            self.collections.append(collection_data)
            
            # Create collection navigation item
            collection_item = self._create_navigation_item(
                f"📁 {collection_data.get('name', 'Unknown')}",
                collection_data.get('id', ''),
                "collections",
                f"Type: {collection_data.get('type', 'Unknown')} | Items: {collection_data.get('item_count', 0)}"
            )
            
            # Add to scroll container (after collections header)
            # Find the collections section and insert after it
            self._insert_collection_item(collection_item)
            
            logger.debug(f"Collection added to library pane: {collection_data.get('name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to add collection to library pane: {e}")
    
    def _insert_collection_item(self, collection_item: toga.Widget):
        """Insert a collection item in the correct position"""
        try:
            # Find the collections section and insert after it
            # This is a simplified approach - in a real implementation,
            # you'd want to track the exact position
            self.scroll_container.add_content(collection_item)
            
        except Exception as e:
            logger.error(f"Failed to insert collection item: {e}")
    
    def remove_collection(self, collection_id: str):
        """Remove a collection from the library pane"""
        try:
            # Find and remove from collections list
            for i, collection in enumerate(self.collections):
                if collection.get('id') == collection_id:
                    self.collections.pop(i)
                    
                    # Remove from scroll container
                    # This would need more sophisticated logic to find the exact widget
                    logger.debug(f"Collection removed from library pane: {collection_id}")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to remove collection from library pane: {e}")
    
    def add_external_link(self, link_data: Dict[str, Any]):
        """Add an external link to the library pane"""
        try:
            # Add to external links list
            self.external_links.append(link_data)
            
            # Create external link navigation item
            link_item = self._create_navigation_item(
                f"🔗 {link_data.get('name', 'Unknown')}",
                link_data.get('id', ''),
                "external",
                link_data.get('description', 'No description')
            )
            
            # Add to scroll container
            self.scroll_container.add_content(link_item)
            
            logger.debug(f"External link added to library pane: {link_data.get('name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to add external link to library pane: {e}")
    
    def set_current_section(self, section: str):
        """Set the current active section"""
        try:
            self.current_section = section
            self._update_selection_state()
            logger.debug(f"Current section set to: {section}")
            
        except Exception as e:
            logger.error(f"Failed to set current section: {e}")
    
    def set_current_collection(self, collection_id: str):
        """Set the current active collection"""
        try:
            self.current_collection = collection_id
            self._update_selection_state()
            logger.debug(f"Current collection set to: {collection_id}")
            
        except Exception as e:
            logger.error(f"Failed to set current collection: {e}")
    
    def get_current_section(self) -> Optional[str]:
        """Get the current active section"""
        return self.current_section
    
    def get_current_collection(self) -> Optional[str]:
        """Get the current active collection"""
        return self.current_collection
    
    def get_collections(self) -> List[Dict[str, Any]]:
        """Get all collections"""
        return self.collections.copy()
    
    def get_external_links(self) -> List[Dict[str, Any]]:
        """Get all external links"""
        return self.external_links.copy()
    
    def clear_collections(self):
        """Clear all collections from the library pane"""
        try:
            self.collections.clear()
            
            # Recreate collections section
            self._recreate_collections_section()
            
            logger.debug("All collections cleared from library pane")
            
        except Exception as e:
            logger.error(f"Failed to clear collections from library pane: {e}")
    
    def _recreate_collections_section(self):
        """Recreate the collections section"""
        try:
            # This would remove the old collections section and recreate it
            # For now, just log the intention
            logger.debug("Collections section recreation requested")
            
        except Exception as e:
            logger.error(f"Failed to recreate collections section: {e}")
    
    def refresh(self):
        """Refresh the library pane"""
        try:
            # Refresh all content
            self.scroll_container.refresh()
            logger.debug("Library pane refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh library pane: {e}")
    
    def register_callbacks(self, 
                         on_section_selected: Optional[Callable] = None,
                         on_collection_selected: Optional[Callable] = None,
                         on_external_link_selected: Optional[Callable] = None):
        """Register callbacks for library pane actions"""
        self.on_section_selected = on_section_selected
        self.on_collection_selected = on_collection_selected
        self.on_external_link_selected = on_external_link_selected
        
        logger.debug("Library pane callbacks registered")
    
    def get_container(self) -> toga.Box:
        """Get the library pane container"""
        return self.container
    
    def get_navigation_info(self) -> Dict[str, Any]:
        """Get information about the current navigation state"""
        return {
            'current_section': self.current_section,
            'current_collection': self.current_collection,
            'collections_count': len(self.collections),
            'external_links_count': len(self.external_links),
            'global_sections': list(self.global_sections.keys())
        } 