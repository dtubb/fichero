"""
Refactored Collection View for Fichero

Uses the new BaseView system with toolbar integration and proper styling.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
from typing import Optional, List, Dict, Any

from .base_view import BaseView
from ..toolbars.collection_top_toolbar import CollectionTopToolbar
from ..toolbars.collection_bottom_toolbar import CollectionBottomToolbar
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
            # Create initial placeholder content directly in the content container
            self._create_placeholder_content()
            
        except Exception as e:
            logger.error(f"Failed to create collection content: {e}")
    
    def _create_placeholder_content(self):
        """Create placeholder content for the collection view"""
        try:
            # Create header
            header = toga.Label(
                f"📁 Collections",
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
            # Top toolbar callbacks
            self.top_toolbar.register_callbacks(
                on_back_to_library=self._on_back_to_library,
                on_add_folder=self._on_add_folder,
                on_add_file=self._on_add_file
            )
            
            # Bottom toolbar callbacks
            self.bottom_toolbar.register_callbacks(
                on_collection_settings=self._on_collection_settings,
                on_process_collection=self._on_process_collection,
                on_export_collection=self._on_export_collection
            )
            
        except Exception as e:
            logger.error(f"Failed to register toolbar callbacks: {e}")
    
    def _on_back_to_library(self):
        """Handle back to library action"""
        logger.debug("Back to library requested")
        # This would typically be handled by the main window
        if hasattr(self, 'on_back_to_library') and self.on_back_to_library:
            self.on_back_to_library()
    
    def _on_add_folder(self):
        """Handle add folder action"""
        logger.debug("Add folder requested")
        # This would typically open a folder picker
        if hasattr(self, 'on_add_folder') and self.on_add_folder:
            self.on_add_folder()
    
    def _on_add_file(self):
        """Handle add file action"""
        logger.debug("Add file requested")
        # This would typically open a file picker
        if hasattr(self, 'on_add_file') and self.on_add_file:
            self.on_add_file()
    
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
                    margin=(5, 10),
                    padding=(10, 15),
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
                    margin=(2, 0),
                    padding=(8, 12),
                    background_color=self.accent_color
                )
            )
            actions_container.add(open_button)
            
            # Settings button
            settings_button = toga.Button(
                "⚙️",
                on_press=lambda widget: self._on_collection_settings(),
                style=Pack(
                    margin=(2, 0),
                    padding=(8, 12),
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
            self._create_placeholder_content()
            
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
                # Set up scroll behavior
                self.scroll_container.set_scroll_enabled(True)
                
                # Configure scroll margins to account for toolbars
                self.scroll_container.set_scroll_margins(top=10, bottom=10)
                
                logger.debug("Scroll container integration set up successfully")
                
        except Exception as e:
            logger.error(f"Failed to set up scroll integration: {e}")
    
    def refresh(self):
        """Refresh the collection view"""
        try:
            self.refresh_collections()
            super().refresh()
            
        except Exception as e:
            logger.error(f"Failed to refresh collection view: {e}") 