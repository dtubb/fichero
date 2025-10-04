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
from fichero.shared.toolbars import ToolbarCoordinator, TopToolbar, BottomToolbar
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead
from fichero.shared.toolbars.color_constants import (
    COLLECTION_ACTIVE, COLLECTION_INACTIVE, VIEW_BACKGROUND
)

logger = logging.getLogger(__name__)


class LibraryView(BaseView):
    """Library view showing all collections using the BaseView system"""
    
    def __init__(self, app, is_mobile: bool = False):
        """Initialize library view"""
        print(f"🔧 LibraryView.__init__ starting with app={app}, is_mobile={is_mobile}")
        logger.debug(f"LibraryView.__init__ called with app={app}, is_mobile={is_mobile}")

        # Initialize collections attribute with empty list
        print("🔧 Setting initial attributes...")
        self.is_edit_mode = False
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None

        # Sort state
        self.current_sort_mode = "name"  # Default sort by name
        self.sort_ascending = True  # True = A-Z, False = Z-A

        print("🔧 Calling super().__init__...")
        super().__init__(app, is_mobile)
        print("✅ BaseView initialization complete")

        # Create toolbars
        print("🔧 Creating toolbars...")

        # Create toolbar coordinator
        self.coordinator = ToolbarCoordinator(app, is_mobile=is_mobile)

        # Set up edit mode callback
        self.coordinator.on_edit_mode_change = self._on_edit_mode_changed

        # No collection management callbacks needed with swipe-only approach

        # Register coordinator with NavigationController
        try:
            if hasattr(app, 'view_integration') and hasattr(app.view_integration, 'navigation_controller'):
                app.view_integration.navigation_controller.register_toolbar_coordinator(self.coordinator)
                logger.debug("Registered toolbar coordinator with navigation controller")
        except Exception as e:
            logger.warning(f"Could not register toolbar coordinator with navigation controller: {e}")

        # Library is root view - use TopToolbar without back navigation + add buttons via composition
        self.top_toolbar = TopToolbar(
            app=app,
            title="",  # Let NavigationController provide dynamic title
            auto_mobile_nav=False,
            is_mobile=is_mobile,
            coordinator=self.coordinator
        )
        self._add_library_toolbar_buttons()

        self.bottom_toolbar = BottomToolbar(
            app=app,
            is_mobile=is_mobile,
            coordinator=self.coordinator
        )
        self._add_library_bottom_toolbar_buttons()
        print("🔧 Setting toolbars...")
        self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
        print("✅ Toolbars created and set")

        # Register callbacks
        print("🔧 Registering toolbar callbacks...")
        self._register_toolbar_callbacks()

        # Initialize callback for collection selection
        print("🔧 Setting collection callback...")
        self.on_collection_selected = None

        # Initialize library manager
        print("🔧 Initializing library system...")
        self._initialize_library_system()

        # Create initial content (will be refreshed when collections load)
        print("🔧 Creating initial content...")
        self._create_content()

        # Schedule collection loading for after initialization (safe for sync context)
        print("🔧 Starting collection loading...")
        try:
            asyncio.create_task(self._load_collections_async())
            print("✅ Async task created")
        except RuntimeError:
            # No event loop running, use thread-safe approach
            print("🔧 Using thread for collection loading...")
            import threading
            threading.Thread(target=self._load_collections_sync, daemon=True).start()
            print("✅ Thread started")

        print("✅ LibraryView initialization complete")
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
        """Create or update detailed list view for collections with selection preservation"""
        try:
            # Store current selection to restore later
            current_selection_id = None
            if (hasattr(self, 'collections_list') and
                self.collections_list and
                self.collections_list.selection):
                try:
                    current_selection_id = self.collections_list.selection.collection_data.get('id')
                    logger.debug(f"Preserving current selection: {current_selection_id}")
                except:
                    pass

            # Format collections for Toga DetailedList (simple, no visual selection indicators)
            collection_data = []
            for collection in self.collections:
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', 'Unknown Collection')

                formatted_item = {
                    'id': collection_id,
                    'title': collection_name,
                    'subtitle': f"{collection.get('item_count', 0)} items • {collection.get('source_type', 'local')}",
                    'icon': "folder",
                    'collection_data': collection  # Store full data for callbacks
                }
                collection_data.append(formatted_item)

            # Always recreate the detailed list - this is the most reliable approach
            # (Skip the problematic in-place update that causes ListSource issues)
            if hasattr(self, 'collections_list') and self.collections_list:
                logger.debug("Recreating DetailedList to avoid ListSource update issues")
                self._recreate_detailed_list(collection_data)
            else:
                # Create new detailed list
                self._recreate_detailed_list(collection_data)

        except Exception as e:
            logger.error(f"Failed to create/update collections detailed list: {e}")

    def _recreate_detailed_list(self, collection_data):
        """Recreate the DetailedList widget (fallback when update fails)"""
        try:
            # Remove existing list if present
            if hasattr(self, 'collections_list') and self.collections_list:
                try:
                    if self.content_container and self.collections_list in self.content_container.children:
                        self.content_container.remove(self.collections_list)
                except:
                    pass

            # Create new detailed list with context-aware swipe actions
            primary_action, secondary_action = self._get_swipe_actions()

            self.collections_list = toga.DetailedList(
                data=collection_data,
                on_select=self._on_collection_selected,  # Re-enable tap to navigate
                primary_action=primary_action["title"],
                on_primary_action=primary_action["handler"],
                secondary_action=secondary_action["title"],
                on_secondary_action=secondary_action["handler"],
                style=Pack(
                    flex=1,
                    margin=0  # Full width - no margins
                )
            )

            if self.content_container:
                self.content_container.add(self.collections_list)

            logger.debug(f"Recreated DetailedList with {len(collection_data)} collections")

        except Exception as e:
            logger.error(f"Failed to recreate detailed list: {e}")

    def _get_swipe_actions(self):
        """Get fixed swipe actions for the library interface"""
        try:
            # Fixed actions - simple and consistent
            primary_action = {
                "title": "Delete",  # Left swipe - destructive (iOS HIG)
                "handler": self._on_swipe_delete_collection
            }
            secondary_action = {
                "title": "Rename",  # Right swipe - edit action
                "handler": self._on_swipe_rename_collection
            }

            return primary_action, secondary_action

        except Exception as e:
            logger.error(f"Failed to get swipe actions: {e}")
            # Fallback
            return (
                {"title": "Delete", "handler": self._on_swipe_delete_collection},
                {"title": "Rename", "handler": self._on_swipe_rename_collection}
            )

    def _on_swipe_delete_collection(self, widget, row):
        """Handle delete collection swipe action"""
        try:
            if hasattr(row, 'collection_data'):
                collection = row.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', 'Unknown Collection')

                logger.info(f"Swipe delete for collection: {collection_name}")
                # Delete immediately without confirmation
                import asyncio
                asyncio.create_task(self._perform_delete_collection(collection_id, collection_name))
            else:
                logger.warning("No collection data found in swipe delete")
        except Exception as e:
            logger.error(f"Failed to handle swipe delete: {e}")

    def _on_swipe_rename_collection(self, widget, row):
        """Handle rename collection swipe action"""
        try:
            if hasattr(row, 'collection_data'):
                collection = row.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', 'Unknown Collection')

                logger.info(f"Swipe rename for collection: {collection_name}")

                # Use NavigationController to navigate to rename view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        success = nav_controller.navigate_to_rename_collection(collection_id, collection_name)
                        if success:
                            logger.info(f"Successfully navigated to rename view for: {collection_name}")
                        else:
                            logger.error(f"Failed to navigate to rename view for: {collection_name}")
                    else:
                        logger.error("NavigationController not available")
                else:
                    logger.error("view_integration not available")
            else:
                logger.warning("No collection data found in swipe rename")
        except Exception as e:
            logger.error(f"Failed to handle swipe rename: {e}")


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
    
    
    def _on_collection_selected(self, widget):
        """Handle collection selection from detailed list"""
        try:
            if widget.selection and hasattr(widget.selection, 'collection_data'):
                collection = widget.selection.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', '')

                logger.info(f"Collection selected: {collection_name}")

                # Always navigate - use fixed swipe actions for editing
                self.selected_collection = collection

                # Navigate to collection if callback is registered
                if self.on_collection_selected:
                    self.on_collection_selected(collection_id, collection_name)

        except Exception as e:
            logger.error(f"Failed to handle collection selection: {e}")


    def _refresh_collections_display(self):
        """Refresh the collections display (simple refresh)"""
        try:
            logger.debug("🔄 Refreshing collections display")

            # Simply recreate the collections list
            self._create_collections_detailed_list()

            logger.debug("✓ Collections display refreshed successfully")
        except Exception as e:
            logger.error(f"Failed to refresh collections display: {e}")

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
            # Edit mode is now handled automatically by smart toolbar system
            # Edit button will trigger coordinator.set_edit_mode() automatically

            # Bottom toolbar callbacks
            self.bottom_toolbar.on_activity_monitor = self._on_activity_monitor
            self.bottom_toolbar.on_library_settings = self._on_library_settings
            self.bottom_toolbar.on_global_inbox = self._on_global_inbox
            self.bottom_toolbar.on_tags = self._on_tags

            # Register sort handler with toolbar coordinator
            if self.coordinator:
                self.coordinator.handle_sort = self._on_toggle_sort

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
            # Create async task for dialog handling
            import asyncio
            task = asyncio.create_task(self._handle_delete_confirmation(collection_id, collection_name))
            logger.debug(f"Created delete confirmation task for collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to create delete confirmation dialog: {e}")

    async def _handle_delete_confirmation(self, collection_id: str, collection_name: str):
        """Handle delete confirmation dialog asynchronously"""
        try:
            # Create QuestionDialog for confirmation
            dialog = toga.QuestionDialog(
                title="Delete Collection",
                message=f"Are you sure you want to delete '{collection_name}'?\n\nThis action cannot be undone."
            )

            # Show dialog and wait for user response
            if await self.app.main_window.dialog(dialog):
                # User confirmed deletion
                logger.info(f"User confirmed deletion of collection: {collection_name}")
                await self._perform_delete_collection(collection_id, collection_name)
            else:
                # User cancelled deletion
                logger.info(f"User cancelled deletion of collection: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to handle delete confirmation: {e}")

    async def _perform_delete_collection(self, collection_id: str, collection_name: str):
        """Actually delete the collection from the library"""
        try:
            # Delete collection through library manager
            if hasattr(self.app, 'library_manager') and self.app.library_manager:
                success = await self.app.library_manager.delete_collection(collection_id)

                if success:
                    logger.info(f"Successfully deleted collection: {collection_name}")
                    # Refresh the collections display
                    self.refresh_collections()
                else:
                    logger.error(f"Failed to delete collection: {collection_name}")
                    error_dialog = toga.ErrorDialog(
                        title="Delete Failed",
                        message=f"Failed to delete collection '{collection_name}'. Please try again."
                    )
                    await self.app.main_window.dialog(error_dialog)
            else:
                logger.error("Library manager not available for collection deletion")
                error_dialog = toga.ErrorDialog(
                    title="Delete Failed",
                    message="Library system not available. Cannot delete collection."
                )
                await self.app.main_window.dialog(error_dialog)

        except Exception as e:
            logger.error(f"Failed to perform collection deletion: {e}")
            error_dialog = toga.ErrorDialog(
                title="Delete Error",
                message=f"An error occurred while deleting the collection: {e}"
            )
            await self.app.main_window.dialog(error_dialog)
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
            # Simply reload collections from database - this is the most reliable approach
            import asyncio
            asyncio.create_task(self._load_collections_async())

            logger.debug("Collections display refresh initiated")

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
                # Determine sort mode based on current state
                # For now, we only support name sorting with A-Z/Z-A toggle
                sort_by = "name"  # Always sort by name

                # Use service layer - it handles all the complexity and returns UI-ready data
                all_collections = await self.library_service.get_collections_for_ui(sort_by=sort_by)

                # Service already provides UI-ready data
                self.collections = all_collections

                # Apply ascending/descending order
                if not self.sort_ascending:
                    # Reverse for Z-A
                    self.collections.reverse()

                logger.debug(f"Loaded {len(self.collections)} collections from library (sort: {sort_by}, {'A-Z' if self.sort_ascending else 'Z-A'}).")

                # Refresh the display to show the loaded collections
                self._create_content()
            else:
                logger.warning("Library service not initialized, cannot load collections.")
                self.collections = []

        except Exception as e:
            logger.error(f"Failed to load collections from library: {e}")
            self.collections = []

    def _load_collections_sync(self):
        """Load collections synchronously (thread-safe version)"""
        try:
            if self.library_service:
                # Use service layer synchronously
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    # Determine sort mode
                    sort_by = "name"  # Always sort by name

                    all_collections = loop.run_until_complete(self.library_service.get_collections_for_ui(sort_by=sort_by))

                    # Service already provides UI-ready data
                    self.collections = all_collections

                    # Apply ascending/descending order
                    if not self.sort_ascending:
                        # Reverse for Z-A
                        self.collections.reverse()

                    logger.debug(f"Loaded {len(self.collections)} collections from library (sync, sort: {sort_by}, {'A-Z' if self.sort_ascending else 'Z-A'}).")

                    # Refresh the display to show the loaded collections (this needs to be on main thread)
                    # We'll skip UI update here and let it happen when the view is shown

                finally:
                    loop.close()
            else:
                logger.warning("Library service not initialized, cannot load collections (sync).")
                self.collections = []

        except Exception as e:
            logger.error(f"Failed to load collections from library (sync): {e}")
            self.collections = []

    def toggle_edit_mode(self, widget=None):
        """Toggle edit mode state"""
        try:
            self.is_edit_mode = not self.is_edit_mode
            self._update_toolbars_for_edit_mode()
            logger.info(f"Edit mode {'enabled' if self.is_edit_mode else 'disabled'}")

        except Exception as e:
            logger.error(f"Failed to toggle edit mode: {e}")

    def _update_toolbars_for_edit_mode(self):
        """Update toolbars based on edit mode state using smart coordinator"""
        try:
            from fichero.shared.toolbars.toolbar_coordinator import EditModeState

            if self.is_edit_mode:
                # Enable edit mode using coordinator (triggers add mode automatically)
                self.coordinator.set_edit_mode(EditModeState.EDIT)
            else:
                # Disable edit mode using coordinator
                self.coordinator.set_edit_mode(EditModeState.NORMAL)

        except Exception as e:
            logger.error(f"Failed to update toolbars for edit mode: {e}")

    def _on_edit_mode_changed(self, state, context: Dict[str, Any]):
        """Handle edit mode changes from coordinator - enables add buttons"""
        try:
            from fichero.shared.toolbars.toolbar_coordinator import EditModeState

            # Swipe actions stay fixed - no need to update them
            # Sort button is now handled by top_edit_actions in toolbar coordinator
            # This callback is for managing the add buttons in edit mode

            if state == EditModeState.EDIT and context.get("edit_type") != "add_items":
                # Only create add context if we don't already have it (prevents infinite loop)
                self._create_add_context_once()
            elif state == EditModeState.NORMAL:
                # Exiting edit mode - clear add context
                self._clear_add_context()

            logger.debug(f"LibraryView edit mode changed to {state.value}")

        except Exception as e:
            logger.error(f"Failed to handle edit mode change: {e}")

    def _create_add_context_once(self):
        """Create add context once when entering edit mode"""
        try:
            # Get platform features
            from fichero.windows.add.platform_features import detect_platform_features
            platform_features = detect_platform_features(self.app)

            # Create library-specific edit context with import buttons
            edit_context = self.coordinator.create_view_edit_context(
                "library",
                platform_features.__dict__
            )

            # Update coordinator context WITHOUT triggering another edit mode change
            self.coordinator._edit_context.update(edit_context)

            # Add import-specific buttons to bottom toolbar
            if self.coordinator.bottom_toolbar:
                # Add export button for selected collection
                self.coordinator.bottom_toolbar.add_edit_mode_button(
                    text="Export",
                    icon="resources/icons/toolbar/download.png",
                    on_press=self._on_export_collection,
                    position="center"
                )

                # Add bulk import button (text file or zip)
                self.coordinator.bottom_toolbar.add_edit_mode_button(
                    text="Bulk",
                    icon="resources/icons/toolbar/document.png",
                    on_press=self._on_import_bulk,
                    position="center"
                )

                # Add URL import button
                self.coordinator.bottom_toolbar.add_edit_mode_button(
                    text="URLs",
                    icon="resources/icons/toolbar/link.png",
                    on_press=self._on_import_urls,
                    position="center"
                )

                # Add file import button (if supported)
                if platform_features.file_import:
                    self.coordinator.bottom_toolbar.add_edit_mode_button(
                        text="Files",
                        icon="resources/icons/toolbar/document.png",
                        on_press=self._on_import_files,
                        position="center"
                    )

                # Add folder import button (if supported)
                if platform_features.folder_import:
                    self.coordinator.bottom_toolbar.add_edit_mode_button(
                        text="Folder",
                        icon="resources/icons/toolbar/folder@10x.png",
                        on_press=self._on_import_folder,
                        position="center"
                    )

                # Notify bottom toolbar (without triggering callbacks)
                self.coordinator.bottom_toolbar.set_edit_mode(
                    self.coordinator._edit_mode_state,
                    self.coordinator._edit_context
                )

            logger.info("Entered add mode with import buttons")

        except Exception as e:
            logger.error(f"Failed to create add context: {e}")

    def _clear_add_context(self):
        """Clear add mode context"""
        try:
            self.coordinator._edit_context = {}
            logger.info("Cleared add mode context")

        except Exception as e:
            logger.error(f"Failed to clear add context: {e}")


    # Add dialog functionality available through edit mode buttons

    def _add_library_toolbar_buttons(self):
        """Add library-specific buttons using smart toolbar system"""
        try:
            # Library root view should NOT show titles on any platform to match mobile behavior
            # Remove contextual title to fix desktop title display issue

            # Add Edit button for edit mode functionality using proper BaseToolbar method
            self.top_toolbar.add_regular_button(
                button_id="edit",
                position="right",
                text="Edit",
                on_press=self.top_toolbar._on_edit_pressed,
                style_class="right_aligned"
            )

            logger.info("Library-specific toolbar buttons added using smart system")

        except Exception as e:
            logger.error(f"Failed to add library toolbar buttons: {e}")


    def _add_library_bottom_toolbar_buttons(self):
        """Add window navigation buttons to BottomToolbar using NavigationController"""
        try:
            from fichero.shared.navigation.navigation_controller import NavigationController

            # Create center-aligned window navigation buttons for normal mode
            # Settings window
            self.bottom_toolbar.add_normal_mode_button(
                text="Settings",
                icon="resources/icons/toolbar/settings.png",
                on_press=self._on_open_settings_window,
                position="center"
            )

            # Processing window
            self.bottom_toolbar.add_normal_mode_button(
                text="Processing",
                icon="resources/icons/toolbar/process.png",
                on_press=self._on_open_processing_window,
                position="center"
            )

            # About window (using help icon)
            self.bottom_toolbar.add_normal_mode_button(
                text="About",
                icon="resources/icons/toolbar/help.png",
                on_press=self._on_open_about_window,
                position="center"
            )

            # Add collection functionality removed - simplified interface"

            # Activity Monitor window
            self.bottom_toolbar.add_normal_mode_button(
                text="Activity",
                icon="resources/icons/toolbar/activity.png",
                on_press=self._on_open_activity_monitor_window,
                position="center"
            )

            # Prompts window
            self.bottom_toolbar.add_normal_mode_button(
                text="Prompts",
                icon="resources/icons/toolbar/prompt.png",
                on_press=self._on_open_prompts_window,
                position="center"
            )

            # Plans window
            self.bottom_toolbar.add_normal_mode_button(
                text="Plans",
                icon="resources/icons/toolbar/plan.png",
                on_press=self._on_open_plans_window,
                position="center"
            )

            # Set up edit mode buttons for library management
            # Platform-specific add buttons are created automatically by the coordinator
            # via _create_add_context_once() when edit mode is entered

            logger.info("Library window navigation buttons configured")

        except Exception as e:
            logger.error(f"Failed to add library toolbar buttons: {e}")


    def _on_toggle_sort(self, widget=None):
        """Toggle sort order (A-Z <-> Z-A)"""
        try:
            # Toggle ascending/descending
            self.sort_ascending = not self.sort_ascending
            new_text = "A-Z" if self.sort_ascending else "Z-A"

            logger.info(f"Sort toggled: {new_text}")

            # Update the button text dynamically
            if self.top_toolbar:
                self.top_toolbar.update_button_text("edit_sort", new_text)

            # Reload collections with new sort order
            import asyncio
            asyncio.create_task(self._load_collections_async())

        except Exception as e:
            logger.error(f"Failed to toggle sort: {e}")

    def _on_library_settings_clicked(self, widget=None):
        """Handle library settings button press"""
        try:
            logger.info("Library settings button pressed")
            # TODO: Open library settings or delegate to app
            if hasattr(self.app, 'show_settings'):
                self.app.show_settings()

        except Exception as e:
            logger.error(f"Failed to handle library settings: {e}")


    # Window navigation button handlers using NavigationController
    def _on_open_settings_window(self, widget=None):
        """Handle settings window navigation"""
        logger.info("Opening settings window")
        self.app.view_integration.navigation_controller.navigate_to_settings()

    def _on_open_processing_window(self, widget=None):
        """Handle processing window navigation"""
        logger.info("Opening processing window")
        self.app.view_integration.navigation_controller.navigate_to_processing()

    def _on_open_about_window(self, widget=None):
        """Handle about window navigation"""
        logger.info("Opening about window")
        self.app.view_integration.navigation_controller.navigate_to_about()

    def _on_open_add_window(self, widget=None):
        """Handle add window button press - simplified interface"""
        try:
            logger.info("Add functionality has been simplified")
            # Add collection functionality removed for simplified interface
            self._show_message("Add Collection", "Add collection functionality has been simplified. Use library management tools instead.")
        except Exception as e:
            logger.error(f"Failed to handle add window request: {e}")

    def _on_open_activity_monitor_window(self, widget=None):
        """Handle activity monitor window navigation"""
        logger.info("Opening activity monitor window")
        self.app.view_integration.navigation_controller.navigate_to_activity_monitor()

    def _on_open_prompts_window(self, widget=None):
        """Handle prompts window navigation"""
        logger.info("Opening prompts window")
        self.app.view_integration.navigation_controller.navigate_to_prompts()

    def _on_open_plans_window(self, widget=None):
        """Handle plans window navigation"""
        logger.info("Opening plans window")
        self.app.view_integration.navigation_controller.navigate_to_plans()

    # Export/Import handlers for Edit mode
    def _on_export_collection(self, widget=None):
        """Handle collection export - save collection to zip file"""
        try:
            # Check if a collection is selected
            if not self.selected_collection:
                self.app.main_window.info_dialog(
                    "No Collection Selected",
                    "Please select a collection to export first."
                )
                return

            collection_id = self.selected_collection.get('id', '')
            collection_name = self.selected_collection.get('name', 'Unknown')

            logger.info(f"Export requested for collection: {collection_name}")

            # Show save file dialog
            from pathlib import Path
            default_filename = f"{collection_name.replace(' ', '_')}_export.zip"

            self.app.main_window.save_file_dialog(
                title=f"Export {collection_name}",
                suggested_filename=default_filename,
                file_types=['zip'],
                on_result=lambda widget, path: asyncio.create_task(
                    self._perform_export_collection(collection_id, collection_name, path)
                )
            )

        except Exception as e:
            logger.error(f"Failed to initiate export: {e}")
            self.app.main_window.error_dialog("Export Error", str(e))

    async def _perform_export_collection(self, collection_id: str, collection_name: str, output_path):
        """Actually perform the export operation"""
        try:
            if not output_path:
                logger.info("Export cancelled by user")
                return

            from pathlib import Path
            output_path = Path(output_path)

            logger.info(f"Exporting collection {collection_name} to {output_path}")

            # Get library service
            if not hasattr(self.app, 'view_integration'):
                self.app.main_window.error_dialog("Error", "Library service not available")
                return

            library_service = self.app.view_integration.library_service

            # Perform export
            success = await library_service.library_manager.export_collection(collection_id, output_path)

            if success:
                # Calculate file size
                file_size = output_path.stat().st_size
                size_mb = file_size / (1024 * 1024)

                self.app.main_window.info_dialog(
                    "Export Successful",
                    f"Collection '{collection_name}' exported successfully.\n\n"
                    f"Location: {output_path}\n"
                    f"Size: {size_mb:.1f} MB"
                )
                logger.info(f"Export completed: {output_path} ({size_mb:.1f} MB)")
            else:
                self.app.main_window.error_dialog(
                    "Export Failed",
                    f"Failed to export collection '{collection_name}'"
                )
                logger.error(f"Export failed for collection: {collection_name}")

        except Exception as e:
            logger.error(f"Export operation failed: {e}")
            self.app.main_window.error_dialog("Export Error", str(e))

    def _on_import_urls(self, widget=None):
        """Handle URL import - navigate to URL add view"""
        try:
            logger.info("Import URLs requested")
            # Use navigation controller to show URL add view
            from fichero.windows.add.views.url_view import URLAddView

            url_view = URLAddView(
                app=self.app,
                on_content_added=self._on_urls_added
            )

            # Navigate to URL view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    # Push URL view onto navigation stack
                    nav_controller.push_view(url_view, "Add URLs")
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open URL import: {e}")

    def _on_import_bulk(self, widget=None):
        """Handle bulk import - navigate to Bulk Import view"""
        try:
            logger.info("Bulk import requested")
            # Use navigation controller to show Bulk Import view
            from fichero.windows.add.views.bulk_import_view import BulkImportView

            bulk_view = BulkImportView(
                app=self.app,
                on_content_added=self._on_bulk_import_added
            )

            # Navigate to Bulk Import view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    # Push Bulk Import view onto navigation stack
                    nav_controller.push_view(bulk_view, "Bulk Import")
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open bulk import: {e}")

    def _on_import_files(self, widget=None):
        """Handle file import - navigate to File add view"""
        try:
            logger.info("Import files requested")
            # Use navigation controller to show File add view
            from fichero.windows.add.views.file_view import FileAddView

            file_view = FileAddView(
                app=self.app,
                on_content_added=self._on_files_added
            )

            # Navigate to File view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    # Push File view onto navigation stack
                    nav_controller.push_view(file_view, "Add Files")
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open file import: {e}")

    def _on_import_folder(self, widget=None):
        """Handle folder import - navigate to Folder add view"""
        try:
            logger.info("Import folder requested")
            # Use navigation controller to show Folder add view
            from fichero.windows.add.views.folder_view import FolderAddView

            folder_view = FolderAddView(
                app=self.app,
                on_content_added=self._on_folders_added
            )

            # Navigate to Folder view
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    # Push Folder view onto navigation stack
                    nav_controller.push_view(folder_view, "Add Folders")
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open folder import: {e}")

    def _on_urls_added(self, data: dict):
        """Callback when URLs are added from URL view

        Args:
            data: Dict with 'urls' list, 'action', and 'option_id'
        """
        try:
            urls = data.get('urls', [])
            logger.info(f"URLs added callback received: {len(urls)} URLs")

            # Create a new collection for the URLs
            import asyncio
            asyncio.create_task(self._create_collection_from_urls(urls))

        except Exception as e:
            logger.error(f"Failed to handle URLs added: {e}")

    async def _create_collection_from_urls(self, urls: List[str]):
        """Create a new collection and add URLs to it"""
        try:
            # Generate collection name
            from datetime import datetime
            collection_name = f"URLs {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type="url",
                description=f"URL collection with {len(urls)} items"
            )

            if collection_id:
                # Add URLs to collection
                for url in urls:
                    # Extract name from URL
                    name = url.split('/')[-1] or url

                    await self.library_service.add_item_to_collection_for_ui(
                        collection_id=collection_id,
                        item_type="url",
                        source=url,
                        name=name,
                        operation="link"  # Don't download, just reference
                    )

                # Refresh collections display
                await self._load_collections_async()

                logger.info(f"Created collection '{collection_name}' with {len(urls)} URLs")

                # Pop back to library view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to create collection for URLs")

        except Exception as e:
            logger.error(f"Failed to create collection from URLs: {e}")

    async def _on_files_added(self, data: dict):
        """Callback when files are added from File view

        Args:
            data: Dict with 'files' list, 'action', and 'option_id'
        """
        try:
            files = data.get('files', [])
            logger.info(f"Files added callback received: {len(files)} files")

            # Create a new collection for the files
            import asyncio
            asyncio.create_task(self._create_collection_from_files(files))

        except Exception as e:
            logger.error(f"Failed to handle files added: {e}")

    async def _create_collection_from_files(self, files: List):
        """Create a new collection and add files to it"""
        try:
            # Generate collection name
            from datetime import datetime
            collection_name = f"Files {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type="local",
                description=f"File collection with {len(files)} items"
            )

            if collection_id:
                # Add files to collection
                for file_path in files:
                    # Extract name from file path
                    name = file_path.name

                    await self.library_service.add_item_to_collection_for_ui(
                        collection_id=collection_id,
                        item_type="file",
                        source=str(file_path),
                        name=name,
                        operation="link"  # Link by default, can be copy/move
                    )

                # Refresh collections display
                await self._load_collections_async()

                logger.info(f"Created collection '{collection_name}' with {len(files)} files")

                # Pop back to library view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to create collection for files")

        except Exception as e:
            logger.error(f"Failed to create collection from files: {e}")

    async def _on_bulk_import_added(self, data: dict):
        """Callback when bulk import is completed

        Args:
            data: Dict with 'collection_id', 'collection_name', 'item_count'
        """
        try:
            collection_id = data.get('collection_id')
            collection_name = data.get('collection_name')
            item_count = data.get('item_count', 0)

            logger.info(f"Bulk import completed: {collection_name} with {item_count} items")

            # Refresh library to show new collection
            await self._refresh_collections()

        except Exception as e:
            logger.error(f"Failed to handle bulk import completion: {e}")

    async def _on_folders_added(self, data: dict):
        """Callback when folders are added from Folder view

        Args:
            data: Dict with 'folders' list, 'action', and 'option_id'
        """
        try:
            folders = data.get('folders', [])
            logger.info(f"Folders added callback received: {len(folders)} folders")

            # Create a new collection for the folders
            import asyncio
            asyncio.create_task(self._create_collection_from_folders(folders))

        except Exception as e:
            logger.error(f"Failed to handle folders added: {e}")

    async def _create_collection_from_folders(self, folders: List):
        """Create a new collection and add folders to it"""
        try:
            # Generate collection name
            from datetime import datetime
            collection_name = f"Folders {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type="local",
                description=f"Folder collection with {len(folders)} items"
            )

            if collection_id:
                # Add folders to collection
                for folder_path in folders:
                    # Extract name from folder path
                    name = folder_path.name

                    await self.library_service.add_item_to_collection_for_ui(
                        collection_id=collection_id,
                        item_type="folder",
                        source=str(folder_path),
                        name=name,
                        operation="link"  # Link by default
                    )

                # Refresh collections display
                await self._load_collections_async()

                logger.info(f"Created collection '{collection_name}' with {len(folders)} folders")

                # Pop back to library view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to create collection for folders")

        except Exception as e:
            logger.error(f"Failed to create collection from folders: {e}")

    async def _on_camera_photo_added(self, data: dict):
        """Callback when photo is added from Camera view

        Args:
            data: Dict with 'photo_path', 'action', and 'option_id'
        """
        try:
            photo_path = data.get('photo_path')
            if not photo_path:
                logger.warning("No photo path provided")
                return

            logger.info(f"Camera photo added callback received: {photo_path}")

            # Create a new collection for the photo
            import asyncio
            asyncio.create_task(self._create_collection_from_photo(photo_path))

        except Exception as e:
            logger.error(f"Failed to handle camera photo added: {e}")

    async def _create_collection_from_photo(self, photo_path):
        """Create a new collection and add camera photo to it"""
        try:
            # Generate collection name
            from datetime import datetime
            from pathlib import Path
            collection_name = f"Photo {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type="local",
                description="Camera photo"
            )

            if collection_id:
                # Add photo to collection
                photo = Path(photo_path)
                await self.library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type="camera",
                    source=str(photo),
                    name=photo.name,
                    operation="copy"  # Copy camera photos
                )

                # Refresh collections display
                await self._load_collections_async()

                logger.info(f"Created collection '{collection_name}' with camera photo")

                # Pop back to library view
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        nav_controller.pop_view()
            else:
                logger.error("Failed to create collection for camera photo")

        except Exception as e:
            logger.error(f"Failed to create collection from camera photo: {e}")


