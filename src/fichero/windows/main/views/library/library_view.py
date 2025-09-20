"""
Library View for Fichero

Shows all collections in the library. Uses the BaseView system with toolbar integration.
"""

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN
import logging
import asyncio
from typing import Optional, List, Dict, Any

from fichero.shared.views.base_view import BaseView
from fichero.windows.main.views.library.library_top_toolbar import LibraryTopToolbar
from fichero.windows.main.views.library.library_bottom_toolbar import LibraryBottomToolbar
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead
from fichero.shared.toolbars.color_constants import (
    COLLECTION_ACTIVE, COLLECTION_INACTIVE, VIEW_BACKGROUND
)

logger = logging.getLogger(__name__)


class LibraryView(BaseView):
    """Library view showing all collections using the BaseView system"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize library view"""
        logger.debug(f"LibraryView.__init__ called with app={app}, is_mobile={is_mobile}")
        
        # Initialize collections attribute with empty list
        self.is_edit_mode = False
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None
        
        super().__init__(app, is_mobile)
        
        # Create toolbars
        self.top_toolbar = LibraryTopToolbar(app, is_mobile)
        self.bottom_toolbar = LibraryBottomToolbar(app, is_mobile)
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        
        # Register callbacks
        self._register_toolbar_callbacks()
        
        # Initialize callback for collection selection
        self.on_collection_selected = None
        
        # Initialize library manager
        self._initialize_library_system()
        
        # Create initial content (will be refreshed when collections load)
        self._create_content()
        
        # Schedule collection loading for after initialization
        asyncio.create_task(self._load_collections_async())
        
        logger.info("Library view created successfully")
    
    def show(self):
        """Called when view becomes active - refresh DetailedList to clear cached selections"""
        try:
            # Refresh the collections display to clear any cached DetailedList selection state
            self._create_collections_display()
            logger.info("🔄 Library view refreshed on show() to clear cached selections")
        except Exception as e:
            logger.error(f"Failed to refresh library view on show: {e}")
    
    def register_collection_callback(self, callback):
        """Register callback for when a collection is selected"""
        try:
            self.on_collection_selected = callback
            logger.debug("Collection selection callback registered")
        except Exception as e:
            logger.error(f"Failed to register collection callback: {e}")
    
    def _create_content(self):
        """Create the library view content"""
        try:
            # Clear any existing content first to prevent duplicates
            if self.content_container:
                self.content_container.clear()
            
            # Check if we have collections to display
            if self.collections:
                self._create_collections_display()
            else:
                self._create_placeholder_content()
            
        except Exception as e:
            logger.error(f"Failed to create library content: {e}")
    
    def _create_collections_display(self):
        """Create display for actual collections"""
        try:
            # No title here - titles should only be in top toolbar
            # Create detailed list for collections directly
            self._create_collections_detailed_list()
            
            logger.debug(f"Created display for {len(self.collections)} collections")
            
        except Exception as e:
            logger.error(f"Failed to create collections display: {e}")
    
    def _create_collections_detailed_list(self):
        """Create a detailed list view for collections with swipe actions"""
        try:
            # Always clear any existing DetailedList to reset selection state
            if hasattr(self, 'collections_list') and self.collections_list:
                try:
                    # Remove from container if it exists
                    if self.content_container and self.collections_list in self.content_container.children:
                        self.content_container.remove(self.collections_list)
                    logger.info("🔄 Cleared existing collections DetailedList to reset selection")
                except Exception as e:
                    logger.debug(f"Note: Could not remove existing collections DetailedList: {e}")
            
            # Format collections for Toga DetailedList
            collection_data = []
            for collection in self.collections:
                formatted_item = {
                    'id': collection.get('id', ''),
                    'title': collection.get('name', 'Unknown Collection'),
                    'subtitle': f"{collection.get('item_count', 0)} items • {collection.get('source_type', 'local')}",
                    'icon': "folder",
                    'collection_data': collection  # Store full data for callbacks
                }
                collection_data.append(formatted_item)
            
            # Create detailed list with full width (no margins)
            self.collections_list = toga.DetailedList(
                data=collection_data,
                on_select=self._on_collection_selected,
                primary_action="Open",
                on_primary_action=self._on_open_collection,
                secondary_action="Info",
                on_secondary_action=self._on_collection_info,
                style=Pack(
                    flex=1,
                    margin=0  # Full width - no margins
                )
            )
            
            if self.content_container:
                self.content_container.add(self.collections_list)
                
            logger.debug(f"Created DetailedList with {len(collection_data)} collections")
            
        except Exception as e:
            logger.error(f"Failed to create collections detailed list: {e}")
    
    def _get_collection_icon(self, collection: Dict[str, Any]) -> Optional[str]:
        """Get appropriate icon for collection type"""
        collection_type = collection.get('type', 'local')
        if collection_type == 'local':
            return '📁'
        elif collection_type == 'external':
            return '💾'
        elif collection_type == 'url':
            return '🌐'
        else:
            return '��'
    
    def _on_open_collection(self, widget, row):
        """Handle opening a collection (primary action)"""
        try:
            if row and hasattr(row, 'collection_data'):
                collection = row.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', '')
                logger.info(f"Opening collection: {collection_name}")
                
                if self.on_collection_selected:
                    self.on_collection_selected(collection_id, collection_name)
            
        except Exception as e:
            logger.error(f"Failed to open collection: {e}")
    
    def _on_collection_info(self, widget, row):
        """Handle collection info (secondary action)"""
        try:
            if row and hasattr(row, 'collection_data'):
                collection = row.collection_data
                collection_name = collection.get('name', 'Unknown')
                logger.info(f"Showing info for collection: {collection_name}")
                # TODO: Implement collection info dialog
            
        except Exception as e:
            logger.error(f"Failed to show collection info: {e}")
    
    def _on_collection_selected(self, widget):
        """Handle collection selection from detailed list"""
        try:
            if widget.selection and hasattr(widget.selection, 'collection_data'):
                collection = widget.selection.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', '')
                
                logger.info(f"Collection selected: {collection_name}")
                
                # Store selected collection
                self.selected_collection = collection
                
                # Navigate to collection if callback is registered
                if self.on_collection_selected:
                    self.on_collection_selected(collection_id, collection_name)
                    
        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")
    
    def _on_collection_selected_fallback(self, widget):
        """Fallback handler for collection selection (when called without item)"""
        try:
            logger.debug("Collection selection fallback handler called")
            # This is a fallback - could show a message or handle differently
            pass
        except Exception as e:
            logger.error(f"Failed to handle collection selection fallback: {e}")
    
    def _on_collection_selected_simple(self, widget):
        """Simple handler for collection selection (compatible with Toga's DetailedList)"""
        try:
            logger.debug("Collection selection simple handler called")
            # This handles the case where Toga calls the handler without the item parameter
            # We'll need to get the selected item from the detailed list
            if hasattr(self, 'collections_list') and self.collections_list:
                # Try to get the selected item from the detailed list
                # Toga's DetailedList selection might be a Row object or index
                selection = getattr(self.collections_list, 'selection', None)
                logger.debug(f"Selection object: {selection}, type: {type(selection)}")
                
                if selection is not None:
                    # If selection is a Row object, try to get its data
                    if hasattr(selection, 'data'):
                        collection_data = selection.data
                        self._handle_collection_navigation(collection_data)
                        return
                    # If selection is an index, use it to get data from collections
                    elif isinstance(selection, int) and selection >= 0:
                        if selection < len(self.collections):
                            collection_data = self.collections[selection]
                            self._handle_collection_navigation(collection_data)
                            return
            
            # If we can't get the selected item, show a message
            self._show_message("Selection", "Please select a collection from the list.")
            
        except Exception as e:
            logger.error(f"Failed to handle collection selection simple: {e}")
            # Show error message
            self._show_message("Selection Error", f"Error selecting collection: {str(e)}")
    
    def _handle_collection_navigation(self, collection_data: Dict[str, Any]):
        """Handle navigation to a selected collection"""
        try:
            collection_name = collection_data.get('name', 'Unknown')
            collection_id = collection_data.get('id', '')
            logger.info(f"Navigating to collection: {collection_name}")
            
            # Store selected collection
            self.selected_collection = collection_data
            
            # Use the registered callback (set by main window)
            if hasattr(self, 'on_collection_selected') and self.on_collection_selected:
                # Call the parent callback to handle navigation
                self.on_collection_selected(collection_id, collection_name)
                logger.debug(f"Called navigation callback for collection: {collection_name}")
            else:
                logger.warning("No collection selection callback registered")
                # Show fallback message
                self._show_message("Navigation", f"Selected: {collection_name}\n\nNavigation callback not registered.")
            
        except Exception as e:
            logger.error(f"Failed to handle collection navigation: {e}")
    
    def _navigate_to_collection_view(self, collection_id: str, collection_name: str):
        """Navigate to collection view by finding the main window"""
        try:
            # This method is now deprecated - navigation should go through the callback
            logger.warning("_navigate_to_collection_view called - this should use the callback instead")
            self._handle_collection_navigation({'id': collection_id, 'name': collection_name})
            
        except Exception as e:
            logger.error(f"Failed to navigate to collection view: {e}")
    
    def _create_placeholder_content(self):
        """Create simple placeholder content for empty collections"""
        try:
            # Simple "Library" title
            title = toga.Label(
                "Library",
                style=Pack(
                    # Use default font size (no font_size specified)
                    font_weight="bold",
                    margin=(20, 20, 15, 20),
                    color=self.text_color
                )
            )
            if self.content_container:
                self.content_container.add(title)
            
            # Simple empty state message
            empty_message = toga.Label(
                "No collections yet",
                style=Pack(
                    font_size=14,
                    color="#8E8E93",  # iOS-style secondary text color
                    margin=(20, 20, 0, 20),
                    text_align="center"
                )
            )
            if self.content_container:
                self.content_container.add(empty_message)
                
            logger.debug("Created simple collections view with empty state")
            
        except Exception as e:
            logger.error(f"Failed to create placeholder content: {e}")
    
    def _register_toolbar_callbacks(self):
        """Register callbacks for toolbar actions"""
        try:
            # Top toolbar callbacks - register edit callback using the proper method
            self.top_toolbar.register_edit_callback(self.toggle_edit_mode)
            
            # Bottom toolbar callbacks
            self.bottom_toolbar.on_add_clicked = self._on_add_dialog_requested
            self.bottom_toolbar.on_activity_monitor = self._on_activity_monitor
            self.bottom_toolbar.on_library_settings = self._on_library_settings
            self.bottom_toolbar.on_global_inbox = self._on_global_inbox
            self.bottom_toolbar.on_tags = self._on_tags
            
            logger.debug("Library view toolbar callbacks registered")
            
        except Exception as e:
            logger.error(f"Failed to register toolbar callbacks: {e}")
    
    def _on_add_collection(self, widget=None):
        """Handle add collection action"""
        logger.debug("Add collection requested")
        try:
            # Try to integrate with library system
            self._add_collection_with_library()
        except Exception as e:
            logger.error(f"Failed to add collection with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_add_collection') and self.on_add_collection:
                self.on_add_collection()
    
    def _on_edit_collection(self, widget=None):
        """Handle edit collection action"""
        logger.debug("Edit collection requested")
        try:
            # Try to integrate with library system
            self._edit_collection_with_library()
        except Exception as e:
            logger.error(f"Failed to edit collection with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_edit_collection') and self.on_edit_collection:
                self.on_edit_collection()
    
    def _on_share_collections(self, widget=None):
        """Handle share collections action"""
        logger.debug("Share collections requested")
        try:
            # Try to integrate with library system
            self._share_collections_with_library()
        except Exception as e:
            logger.error(f"Failed to share collections with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_share_collections') and self.on_share_collections:
                self.on_share_collections()
    
    def _share_collections_with_library(self):
        """Share collections using the library system"""
        try:
            # For now, just show a message - in real implementation, this would open a share dialog
            self._show_message("Share Collections", "Share/export functionality will be implemented here")
            
        except Exception as e:
            logger.error(f"Library system share collections failed: {e}")
            # Fall back to basic functionality
            self._show_basic_share_dialog()
    
    def _show_basic_share_dialog(self):
        """Show basic share collections dialog as fallback"""
        logger.debug("Showing basic share collections dialog")
        # This would show a simple dialog for sharing collections
        pass
    
    def _on_manage_collections(self):
        """Handle manage collections action"""
        logger.debug("Manage collections requested")
        try:
            # Try to integrate with library system
            self._manage_collections_with_library()
        except Exception as e:
            logger.error(f"Failed to manage collections with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_manage_collections') and self.on_manage_collections:
                self.on_manage_collections()
    
    def _manage_collections_with_library(self):
        """Manage collections using the library system"""
        try:
            # For now, just show a message - in real implementation, this would open a collections manager
            self._show_message("Manage Collections", "Collections manager will show Local vs External collections")
            
        except Exception as e:
            logger.error(f"Library system manage collections failed: {e}")
            # Fall back to basic functionality
            self._show_basic_manage_dialog()
    
    def _show_basic_manage_dialog(self):
        """Show basic manage collections dialog as fallback"""
        logger.debug("Showing basic manage collections dialog")
        # This would show a simple dialog for managing collections
        pass
    
    def _edit_collection_with_library(self):
        """Edit collection using the library system"""
        try:
            # For now, just show a message - in real implementation, this would open an edit dialog
            if self.selected_collection:
                self._show_message("Edit Collection", f"Editing collection: {self.selected_collection.get('name', 'Unknown')}")
            else:
                self._show_message("Edit Collection", "Please select a collection to edit first.")
                
        except Exception as e:
            logger.error(f"Library system edit failed: {e}")
            # Fall back to basic functionality
            self._show_basic_edit_dialog()
    
    def _show_basic_edit_dialog(self):
        """Show basic edit dialog as fallback"""
        logger.debug("Showing basic edit dialog")
        # This would show a simple dialog for editing collections
        pass
    
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
    
    def _on_import_collection(self):
        """Handle import collection action"""
        logger.debug("Import collection requested")
        try:
            # Try to integrate with library system
            self._import_collection_with_library()
        except Exception as e:
            logger.error(f"Failed to import collection with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_import_collection') and self.on_import_collection:
                self.on_import_collection()
    
    def _on_export_collection(self):
        """Handle export collection action"""
        logger.debug("Export collection requested")
        try:
            # Try to integrate with library system
            self._export_collection_with_library()
        except Exception as e:
            logger.error(f"Failed to export collection with library system: {e}")
            # Fallback to basic functionality
            if hasattr(self, 'on_export_collection') and self.on_export_collection:
                self.on_export_collection()
    
    def _add_collection_with_library(self):
        """Add collection using the library system"""
        try:
            # Create a new collection with a simple name
            collection_name = f"Collection {len(self.collections) + 1}"
            
            # Create collection using the library system
            if self.library_service:
                # Create a new collection model
                from fichero.library.models import Collection
                
                new_collection = Collection(
                    name=collection_name,
                    type="local",
                    metadata={"description": "New collection created via UI"}
                )
                
                # Add to library storage
                success = self.library_manager.storage.add_collection(new_collection)
                if success:
                    logger.info(f"Collection '{collection_name}' added via library system")
                    
                    # Add to local collections list for UI
                    collection_data = {
                        'id': new_collection.id,
                        'name': new_collection.name,
                        'type': new_collection.type,
                        'description': new_collection.metadata.get('description', ''),
                        'item_count': 0,
                        'active': True,
                        'created_at': new_collection.created_at,
                        'updated_at': new_collection.updated_at,
                        'source_path': new_collection.source_path,
                        'local_path': new_collection.local_path
                    }
                    self.collections.append(collection_data)
                    
                    # Sort collections by name
                    self.collections.sort(key=lambda x: x['name'])
                    
                    # Update the UI
                    self._refresh_collections_display()
                    
                    # Show success message
                    self._show_message("Success", f"Collection '{collection_name}' has been created.")
                    
                else:
                    logger.error("Failed to add collection via library system")
                    self._show_message("Error", "Failed to create collection. Please try again.")
                    
            else:
                logger.error("Library manager not available")
                self._show_message("Error", "Library system not available. Please restart the application.")
                
        except Exception as e:
            logger.error(f"Library system integration failed: {e}")
            self._show_message("Error", f"Failed to create collection: {str(e)}")
    
    def _import_collection_with_library(self):
        """Import collection using the library system"""
        try:
            # Try to import and use the library system
            import sys
            from pathlib import Path
            
            # Add library path to sys.path
            library_path = Path(__file__).parent.parent.parent.parent.parent.parent / "library"
            if str(library_path) not in sys.path:
                sys.path.insert(0, str(library_path))
            
            # Import library components
            import import_export
            import library_manager
            
            # Create library manager
            manager = library_manager.LibraryManager(self.app)
            
            # Create importer
            importer = import_export.CollectionImporter(manager.storage)
            
            # For now, just show a message - in real implementation, this would open a file picker
            self._show_message("Import Collection", "Import functionality will be implemented with file picker")
            
        except Exception as e:
            logger.error(f"Library system import failed: {e}")
            # Fall back to basic functionality
            self._show_basic_import_dialog()
    
    def _export_collection_with_library(self):
        """Export collection using the library system"""
        try:
            # Try to import and use the library system
            import sys
            from pathlib import Path
            
            # Add library path to sys.path
            library_path = Path(__file__).parent.parent.parent.parent.parent.parent / "library"
            if str(library_path) not in sys.path:
                sys.path.insert(0, str(library_path))
            
            # Import library components
            import import_export
            import library_manager
            
            # Create library manager
            manager = library_manager.LibraryManager(self.app)
            
            # Create exporter
            exporter = import_export.CollectionExporter(manager.storage)
            
            # For now, just show a message - in real implementation, this would open a save dialog
            self._show_message("Export Collection", "Export functionality will be implemented with save dialog")
            
        except Exception as e:
            logger.error(f"Library system export failed: {e}")
            # Fall back to basic functionality
            self._show_basic_export_dialog()
    
    def _show_message(self, title: str, message: str):
        """Show a simple message dialog"""
        try:
            # Create a simple message box
            message_box = toga.Box(style=Pack(direction=COLUMN, margin=20))
            
            title_label = toga.Label(title, style=Pack(font_size=16, font_weight="bold", margin=(0, 0, 10, 0)))
            message_label = toga.Label(message, style=Pack(margin=(0, 0, 20, 0)))
            
            ok_button = toga.Button("OK", on_press=lambda widget: self._close_message_dialog())
            
            message_box.add(title_label)
            message_box.add(message_label)
            message_box.add(ok_button)
            
            # Create a simple window for the message
            self.message_window = toga.Window(title=title, content=message_box, size=(400, 200))
            self.message_window.show()
            
        except Exception as e:
            logger.error(f"Failed to show message dialog: {e}")
    
    def _close_message_dialog(self):
        """Close the message dialog"""
        try:
            if hasattr(self, 'message_window') and self.message_window:
                self.message_window.close()
                self.message_window = None
        except Exception as e:
            logger.error(f"Failed to close message dialog: {e}")
    
    def _refresh_collections_display(self):
        """Refresh the collections display"""
        try:
            if self.content_container:
                self.content_container.clear()
            self._create_content()
            logger.debug(f"Collections display refreshed with {len(self.collections)} collections")
        except Exception as e:
            logger.error(f"Failed to refresh collections display: {e}")
    
    def add_collection(self, collection_data: Dict[str, Any]):
        """Add a collection to the management view"""
        try:
            # Add to collections list
            self.collections.append(collection_data)
            
            # Refresh the display
            self._refresh_collections_display()
            
            logger.debug(f"Collection added to management view: {collection_data.get('name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Failed to add collection to management view: {e}")
    
    def _create_collection_management_item(self, collection: Dict[str, Any]) -> toga.Widget:
        """Create a collection management item widget (fallback if detailed list fails)"""
        try:
            # Create a simple box container for the collection
            collection_box = toga.Box(
                style=Pack(
                    direction=ROW,
                    margin=(10, 15),
                    background_color=COLLECTION_ACTIVE if collection.get('active', False) else COLLECTION_INACTIVE
                )
            )
            
            # Collection icon
            icon_label = toga.Label(
                self._get_collection_icon(collection),
                style=Pack(
                    font_size=24,
                    margin=(0, 10, 0, 0)
                )
            )
            collection_box.add(icon_label)
            
            # Collection info
            info_box = toga.Box(style=Pack(direction=COLUMN, flex=1))
            
            # Collection name
            name_label = toga.Label(
                collection.get('name', 'Unknown Collection'),
                style=Pack(
                    font_size=16,
                    font_weight="bold",
                    color=self.text_color
                )
            )
            info_box.add(name_label)
            
            # Collection details
            details_label = toga.Label(
                f"Type: {collection.get('type', 'Unknown')} | Items: {collection.get('item_count', 0)}",
                style=Pack(
                    font_size=12,
                    color=self.text_color
                )
            )
            info_box.add(details_label)
            
            collection_box.add(info_box)
            
            # Add click handler
            collection_box.on_press = lambda widget: self._on_collection_selected(widget, type('MockItem', (), {'data': collection})())
            
            return collection_box
            
        except Exception as e:
            logger.error(f"Failed to create collection management item: {e}")
            # Return a simple label as fallback
            return toga.Label(
                f"Error displaying collection: {collection.get('name', 'Unknown')}",
                style=Pack(color="red")
            )
    
    def _on_open_collection(self, widget, row):
        """Handle opening a collection"""
        logger.debug(f"Opening collection: {row.collection_data.get('name', 'Unknown')}")
        # This would typically navigate to the collection view
        if hasattr(self, 'on_open_collection') and self.on_open_collection:
            self.on_open_collection(row.collection_data)
    
    def _on_delete_collection(self, widget, item):
        """Handle delete action from swipe gesture"""
        try:
            if item:
                collection_name = item.get('title', 'Unknown')
                collection_id = item.get('id', '')
                logger.info(f"Delete requested for collection: {collection_name}")
                
                # TODO: Implement delete confirmation dialog
                # For now, just log the action
                logger.warning(f"Delete action not implemented yet for collection {collection_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle collection deletion: {e}")
    
    def _on_edit_collection(self, widget, item):
        """Handle edit action from swipe gesture"""
        try:
            if item:
                collection_name = item.get('title', 'Unknown')
                collection_id = item.get('id', '')
                logger.info(f"Edit requested for collection: {collection_name}")
                
                # TODO: Implement edit dialog
                # For now, just log the action
                logger.warning(f"Edit action not implemented yet for collection {collection_id}")
                
        except Exception as e:
            logger.error(f"Failed to handle collection editing: {e}")
    
    def _confirm_delete_collection(self, collection_id: str, collection_name: str):
        """Show confirmation dialog for collection deletion"""
        try:
            # Create confirmation dialog
            dialog = toga.AlertDialog(
                title="Delete Collection",
                message=f"Are you sure you want to delete '{collection_name}'?\n\nThis action cannot be undone.",
                buttons=["Cancel", "Delete"]
            )
            
            # Show dialog and handle response
            dialog.show()
            
            # Note: Toga's AlertDialog doesn't have a callback, so we'll need to handle this differently
            # For now, we'll use a simple approach
            self._perform_delete_collection(collection_id, collection_name)
            
        except Exception as e:
            logger.error(f"Failed to show delete confirmation: {e}")
            # Fallback: delete directly
            self._perform_delete_collection(collection_id, collection_name)
    
    def _perform_delete_collection(self, collection_id: str, collection_name: str):
        """Actually delete the collection from the library and UI"""
        try:
            # Delete from library system
            if self.library_service:
                success = self.library_manager.storage.delete_collection(collection_id)
                if success:
                    logger.info(f"Collection '{collection_name}' deleted from library")
                else:
                    logger.error(f"Failed to delete collection '{collection_name}' from library")
                    return
            
            # Remove from local collections list
            self.collections = [c for c in self.collections if c.get('id') != collection_id]
            
            # Refresh the display
            self._refresh_collections_display()
            
            # Show success message
            self._show_message("Success", f"Collection '{collection_name}' has been deleted.")
            
        except Exception as e:
            logger.error(f"Failed to perform collection deletion: {e}")
            self._show_message("Error", f"Failed to delete collection: {str(e)}")
    
    def _edit_collection(self, collection_id: str, collection_name: str):
        """Open edit dialog for collection"""
        try:
            # Find the collection data
            collection = next((c for c in self.collections if c.get('id') == collection_id), None)
            if not collection:
                logger.error(f"Collection not found for editing: {collection_id}")
                return
            
            # Create edit dialog
            dialog = toga.AlertDialog(
                title="Edit Collection",
                message=f"Editing: {collection_name}\n\nThis feature will be implemented in the next iteration.",
                buttons=["OK"]
            )
            
            # Show dialog
            dialog.show()
            
            logger.info(f"Edit dialog shown for collection: {collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to show edit dialog: {e}")
            self._show_message("Error", f"Failed to open edit dialog: {str(e)}")
    
    def remove_collection(self, collection_id: str):
        """Remove a collection from the management view"""
        try:
            # Find and remove collection
            self.collections = [c for c in self.collections if c.get('id') != collection_id]
            
            # Clear selection if it was the selected collection
            if (self.selected_collection and 
                self.selected_collection.get('id') == collection_id):
                self.selected_collection = None
            
            # Refresh the display
            self._refresh_collections_display()
            
            logger.debug(f"Collection removed from management view: {collection_id}")
            
        except Exception as e:
            logger.error(f"Failed to remove collection from management view: {e}")
    
    def update_collection(self, collection_id: str, updates: Dict[str, Any]):
        """Update a collection in the management view"""
        try:
            # Find and update collection
            for collection in self.collections:
                if collection.get('id') == collection_id:
                    collection.update(updates)
                    break
            
            # Refresh the display
            self._refresh_collections_display()
            
            logger.debug(f"Collection updated in management view: {collection_id}")
            
        except Exception as e:
            logger.error(f"Failed to update collection in management view: {e}")
    
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

    def _initialize_library_system(self):
        """Initialize the library system and its components."""
        try:
            # Import library components using proper relative imports
            from fichero.library.models import Collection
            from fichero.library.library_manager import LibraryManager
            
            # Create library manager
            self.library_service = self.app.library_service
            logger.debug("Library system initialized successfully.")
            
        except ImportError as e:
            logger.error(f"Failed to import library components: {e}")
            # Fallback: try direct import
            try:
                import sys
                from pathlib import Path
                
                # Add library path to sys.path
                library_path = Path(__file__).parent.parent.parent.parent.parent.parent / "library"
                if str(library_path) not in sys.path:
                    sys.path.insert(0, str(library_path))
                
                # Import library components
                import models
                import library_manager
                
                # Create library manager
                self.library_service = self.app.library_service
                logger.debug("Library system initialized successfully via fallback import.")
                
            except Exception as fallback_e:
                logger.error(f"Failed to initialize library system via fallback: {fallback_e}")
                self.library_service = None
        except Exception as e:
            logger.error(f"Failed to initialize library system: {e}")
            self.library_service = None
    
    async def _load_collections_async(self):
        """Load collections asynchronously and update UI"""
        try:
            if self.library_service:
                # Use service layer - it handles all the complexity and returns UI-ready data
                all_collections = await self.library_service.get_collections_for_ui()
                
                # Service already provides UI-ready data, so we can use it directly
                self.collections = all_collections
                
                # Sort collections by name
                self.collections.sort(key=lambda x: x.get('name', ''))
                
                logger.debug(f"Loaded {len(self.collections)} collections from library.")
                
                # Refresh the display to show the loaded collections
                self._create_content()
            else:
                logger.warning("Library service not initialized, cannot load collections.")
                self.collections = []
                
        except Exception as e:
            logger.error(f"Failed to load collections from library: {e}")
            self.collections = [] 
    def toggle_edit_mode(self):
        """Toggle edit mode state"""
        try:
            self.is_edit_mode = not self.is_edit_mode
            self._update_toolbars_for_edit_mode()
            logger.info(f"Edit mode {'enabled' if self.is_edit_mode else 'disabled'}")
            
        except Exception as e:
            logger.error(f"Failed to toggle edit mode: {e}")
    
    def _update_toolbars_for_edit_mode(self):
        """Update toolbars based on edit mode state"""
        try:
            if self.is_edit_mode:
                # Edit mode: Show "Done" in top toolbar, "Add" in bottom toolbar
                self.top_toolbar.set_edit_mode(True)
                self.bottom_toolbar.set_edit_mode(True)
            else:
                # Normal mode: Show "Edit" in top toolbar, normal buttons in bottom toolbar
                self.top_toolbar.set_edit_mode(False)
                self.bottom_toolbar.set_edit_mode(False)
                
        except Exception as e:
            logger.error(f"Failed to update toolbars for edit mode: {e}")
    
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
