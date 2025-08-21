"""
Refactored Collection Management View for Fichero

Uses the new BaseView system with toolbar integration and proper styling.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, List, Dict, Any

from .base_view import BaseView
from ..toolbars.library_top_toolbar import LibraryTopToolbar
from ..toolbars.library_bottom_toolbar import LibraryBottomToolbar
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead
from fichero.windows.main.styling.color_constants import (
    COLLECTION_ACTIVE, COLLECTION_INACTIVE, VIEW_BACKGROUND
)

logger = logging.getLogger(__name__)


class CollectionManagementView(BaseView):
    """Collection management view using the new BaseView system"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize refactored collection management view"""
        logger.debug(f"CollectionManagementView.__init__ called with app={app}, is_mobile={is_mobile}")
        super().__init__(app, is_mobile)
        
        # Collection management data
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None
        
        # Create separate top and bottom toolbars
        self.top_toolbar = LibraryTopToolbar(app, is_mobile)
        self.bottom_toolbar = LibraryBottomToolbar(app, is_mobile)
        
        # Set both toolbars
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Note: scroll container is handled by BaseView
        
        # Register callbacks
        self._register_toolbar_callbacks()
        
        # Create content
        self._create_content()
        
        logger.info("Refactored collection management view created successfully")
    
    def _create_content(self):
        """Create the collection management view content"""
        try:
            # Clear any existing content first to prevent duplicates
            if self.content_container:
                self.content_container.clear()
            
            # Create initial placeholder content directly in the content container
            self._create_placeholder_content()
            
        except Exception as e:
            logger.error(f"Failed to create collection management content: {e}")
    
    def _create_placeholder_content(self):
        """Create placeholder content for the collection management view"""
        try:
            # Create header
            header = toga.Label(
                "📚 Library Management",
                style=Pack(
                    font_size=20,
                    font_weight="bold",
                    margin=(20, 10),
                    color=self.text_color
                )
            )
            if self.content_container:
                self.content_container.add(header)
            
            # Create placeholder for collections
            placeholder = toga.Label(
                "No collections available. Use the toolbar to add collections.",
                style=Pack(
                    margin=(10, 20),
                    color=self.text_color
                )
            )
            if self.content_container:
                self.content_container.add(placeholder)
            
        except Exception as e:
            logger.error(f"Failed to create placeholder content: {e}")
    
    def _register_toolbar_callbacks(self):
        """Register callbacks for both toolbars"""
        try:
            # Top toolbar callbacks - pass all required parameters
            self.top_toolbar.register_callbacks(
                on_back=None,  # No back button needed
                on_settings=None,  # No settings button needed
                on_about=None,  # No about button needed
                on_help=None,  # No help button needed
                on_add_collection=self._on_add_collection,
                on_activity_monitor=self._on_activity_monitor
            )
            
            # Bottom toolbar callbacks
            self.bottom_toolbar.register_callbacks(
                on_library_settings=self._on_library_settings,
                on_global_inbox=self._on_global_inbox,
                on_tags=self._on_tags
            )
            
        except Exception as e:
            logger.error(f"Failed to register toolbar callbacks: {e}")
    
    def _on_add_collection(self):
        """Handle add collection action"""
        logger.debug("Add collection requested")
        # This would typically open a folder picker
        if hasattr(self, 'on_add_collection') and self.on_add_collection:
            self.on_add_collection()
    
    def _on_activity_monitor(self):
        """Handle activity monitor action"""
        logger.debug("Activity monitor requested")
        # This would typically open the activity monitor
        if hasattr(self, 'on_activity_monitor') and self.on_activity_monitor:
            self.on_activity_monitor()
    
    def _on_library_settings(self):
        """Handle library settings action"""
        logger.debug("Library settings requested")
        # This would typically open a settings dialog
        if hasattr(self, 'on_library_settings') and self.on_library_settings:
            self.on_library_settings()
    
    def _on_global_inbox(self):
        """Handle global inbox action"""
        logger.debug("Global inbox requested")
        # This would typically navigate to global inbox
        if hasattr(self, 'on_global_inbox') and self.on_global_inbox:
            self.on_global_inbox()
    
    def _on_tags(self):
        """Handle tags action"""
        logger.debug("Tags requested")
        # This would typically open the tags manager
        if hasattr(self, 'on_tags') and self.on_tags:
            self.on_tags()
    
    def add_collection(self, collection_data: Dict[str, Any]):
        """Add a collection to management"""
        try:
            # Add to collections list
            self.collections.append(collection_data)
            
            # Update toolbar collection count
            if self.top_toolbar:
                # Could add collection count to top toolbar if needed
                pass
            
            logger.debug(f"Collection added to management: {collection_data.get('name', 'Unknown')}")
            
            # Notify content changed
            if self.on_content_changed:
                self.on_content_changed()
                
        except Exception as e:
            logger.error(f"Failed to add collection to management: {e}")
    
    def _create_collection_management_item(self, collection_data: Dict[str, Any]) -> toga.Widget:
        """Create a collection management item widget"""
        try:
            # Create collection item container
            item_container = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(10, 5)
                )
            )
            
            # Collection name
            name_label = toga.Label(
                collection_data.get('name', 'Unknown'),
                style=Pack(
                    flex=1,
                    color=self.text_color
                )
            )
            item_container.add(name_label)
            
            # Collection status indicator
            status_label = toga.Label(
                "●",
                style=Pack(
                    color=COLLECTION_ACTIVE if collection_data.get('active') else COLLECTION_INACTIVE,
                    margin=(5, 0)
                )
            )
            item_container.add(status_label)
            
            return item_container
            
        except Exception as e:
            logger.error(f"Failed to create collection management item: {e}")
            return toga.Label("Error creating collection item")
    
    def _on_open_collection(self, collection_data: Dict[str, Any]):
        """Handle opening a collection"""
        logger.debug(f"Opening collection: {collection_data.get('name', 'Unknown')}")
        # This would typically navigate to the collection view
        if hasattr(self, 'on_open_collection') and self.on_open_collection:
            self.on_open_collection(collection_data)
    
    def _on_edit_collection(self, collection_data: Dict[str, Any]):
        """Handle editing a collection"""
        logger.debug(f"Editing collection: {collection_data.get('name', 'Unknown')}")
        # This would typically open an edit dialog
        if hasattr(self, 'on_edit_collection') and self.on_edit_collection:
            self.on_edit_collection(collection_data)
    
    def _on_delete_collection(self, collection_data: Dict[str, Any]):
        """Handle deleting a collection"""
        logger.debug(f"Deleting collection: {collection_data.get('name', 'Unknown')}")
        # This would typically show a confirmation dialog
        if hasattr(self, 'on_delete_collection') and self.on_delete_collection:
            self.on_delete_collection(collection_data)
    
    def remove_collection(self, collection_id: str):
        """Remove a collection from the management view"""
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
                    
                    # Update toolbar collection count
                    if self.top_toolbar:
                        # Could add collection count to top toolbar if needed
                        pass
                    
                    logger.debug(f"Collection removed from management: {collection_id}")
                    break
                    
        except Exception as e:
            logger.error(f"Failed to remove collection from management: {e}")
    
    def clear_collections(self):
        """Clear all collections from the management view"""
        try:
            self.collections.clear()
            self.scroll_container.clear_content()
            
            # Recreate placeholder content
            self._create_placeholder_content()
            
            # Update toolbar collection count
            if self.top_toolbar:
                # Could add collection count to top toolbar if needed
                pass
            
            logger.debug("All collections cleared from management")
            
        except Exception as e:
            logger.error(f"Failed to clear collections from management: {e}")
    
    def refresh_collections(self):
        """Refresh the collections display"""
        try:
            # Clear current content
            self.scroll_container.clear_content()
            
            # Recreate content
            self._create_content()
            
            logger.debug("Collections display refreshed")
            
        except Exception as e:
            logger.error(f"Failed to refresh collections: {e}")
    
    def set_global_section_active(self, active: bool):
        """Set global section as active/inactive"""
        if self.bottom_toolbar:
            # Could add global section active state to bottom toolbar if needed
            pass
    
    def set_collections_section_active(self, active: bool):
        """Set collections section as active/inactive"""
        if self.bottom_toolbar:
            # Could add collections section active state to bottom toolbar if needed
            pass
    
    def register_callbacks(self, 
                         on_add_collection: Optional[Any] = None,
                         on_library_settings: Optional[Any] = None,
                         on_global_inbox: Optional[Any] = None,
                         on_activity_monitor: Optional[Any] = None,
                         on_tags: Optional[Any] = None,
                         on_open_collection: Optional[Any] = None,
                         on_edit_collection: Optional[Any] = None,
                         on_delete_collection: Optional[Any] = None):
        """Register callbacks for collection management actions"""
        self.on_add_collection = on_add_collection
        self.on_library_settings = on_library_settings
        self.on_global_inbox = on_global_inbox
        self.on_activity_monitor = on_activity_monitor
        self.on_tags = on_tags
        self.on_open_collection = on_open_collection
        self.on_edit_collection = on_edit_collection
        self.on_delete_collection = on_delete_collection
        
        logger.debug("Collection management view callbacks registered")
    
    def _on_initialize(self):
        """Called when view is initialized"""
        try:
            # Set up collection management-specific features
            logger.debug("Collection management view initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize collection management view: {e}")
    
    def refresh(self):
        """Refresh the collection management view"""
        try:
            self.refresh_collections()
            super().refresh()
            
        except Exception as e:
            logger.error(f"Failed to refresh collection management view: {e}") 