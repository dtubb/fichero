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
from fichero.shared.commands import FicheroCommand, ViewCommandMixin
# from ..containers.scroll_container import ScrollableContainer  # Using BaseView's scroll container instead
from fichero.shared.toolbars.color_constants import (
    COLLECTION_ACTIVE, COLLECTION_INACTIVE, VIEW_BACKGROUND
)

logger = logging.getLogger(__name__)


class LibraryView(BaseView, ViewCommandMixin):
    """Library view showing all collections using the BaseView system"""

    def __init__(self, app, is_mobile: bool = False):
        """Initialize library view"""
        print(f"🔧 LibraryView.__init__ starting with app={app}, is_mobile={is_mobile}")
        logger.debug(f"LibraryView.__init__ called with app={app}, is_mobile={is_mobile}")

        # Set view_id BEFORE super().__init__
        self.view_id = "library"

        # Initialize collections attribute with empty list
        print("🔧 Setting initial attributes...")
        self.is_edit_mode = False
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None

        # Sort state
        self.current_sort_mode = "name"  # Default sort by name
        self.sort_ascending = True  # True = A-Z, False = Z-A

        # Cache folder icon to prevent repeated loads
        self._folder_icon_cache = None

        print("🔧 Calling super().__init__...")
        super().__init__(app, is_mobile)
        ViewCommandMixin.__init__(self)
        print("✅ BaseView initialization complete")

        # Define and register commands
        print("🔧 Defining commands...")
        self.define_commands()
        self.register_commands()
        print("✅ Commands defined and registered")

        # Note: Native toolbar will be built by MainWindow after this view is created
        # and app.main_window is set. Don't build it here - app.main_window doesn't exist yet!

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

        # MOBILE ONLY: Create custom Toga toolbars
        # Desktop uses ONLY native window.toolbar (no custom TopToolbar/BottomToolbar widgets)
        if is_mobile:
            # Library is root view - use TopToolbar without back navigation + add buttons via composition
            self.top_toolbar = TopToolbar(
                app=app,
                title="",  # Let NavigationController provide dynamic title
                auto_mobile_nav=False,
                is_mobile=is_mobile,
                coordinator=self.coordinator
            )

            self.bottom_toolbar = BottomToolbar(
                app=app,
                is_mobile=is_mobile,
                coordinator=self.coordinator
            )
            # Toolbars will be populated automatically by set_toolbars() from command definitions
            print("🔧 Setting mobile toolbars...")
            self.set_toolbars(self.top_toolbar, self.bottom_toolbar)
            print("✅ Mobile toolbars created and set")
        else:
            # Desktop: No custom toolbars - use native window.toolbar exclusively
            self.top_toolbar = None
            self.bottom_toolbar = None
            print("✅ Desktop mode: Using native window.toolbar only")

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

        # Subscribe to library state events for automatic synchronization
        print("🔧 Subscribing to library state events...")
        from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
        subscribe_to_navigation("collection_added", self._on_collection_added_event)
        subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
        subscribe_to_navigation("collection_updated", self._on_collection_updated_event)
        subscribe_to_navigation("folder_import_started", self._on_folder_import_started_event)
        subscribe_to_navigation("folder_import_progress", self._on_folder_import_progress_event)
        subscribe_to_navigation("folder_import_completed", self._on_folder_import_completed_event)
        print("✅ Event subscriptions registered")

        # Track imports in progress
        self.importing_collections = {}  # collection_id -> {folder_name, count}

        print("✅ LibraryView initialization complete")
        logger.info("Library view created successfully")
    
    def show(self):
        """Called when view becomes active - refresh DetailedList to clear cached selections"""
        try:
            # Tell the coordinator that this view is now active
            if hasattr(self, 'coordinator') and self.coordinator:
                self.coordinator.set_active_view('library')

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

            # Load folder icon once for all collections (use cache)
            folder_icon = None
            if self._folder_icon_cache is not None:
                folder_icon = self._folder_icon_cache
            else:
                try:
                    import toga
                    folder_icon_path = self.app.paths.app / "resources" / "icons" / "files_folders" / "folder_small_icon.png"
                    if folder_icon_path.exists():
                        folder_icon = toga.Image(str(folder_icon_path))
                        self._folder_icon_cache = folder_icon  # Cache for future use
                        logger.info(f"✅ Loaded collection folder icon (cached)")
                    else:
                        logger.warning(f"❌ Folder icon not found at: {folder_icon_path}")
                except Exception as e:
                    logger.error(f"Failed to load folder icon: {e}", exc_info=True)

            for collection in self.collections:
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', 'Unknown Collection')

                # Format subtitle with storage stats
                item_count = collection.get('item_count', 0)
                # Simple item count - no storage type breakdown
                subtitle = f"{item_count} items"

                formatted_item = {
                    'id': collection_id,
                    'title': collection_name,
                    'subtitle': subtitle,
                    'icon': folder_icon,  # toga.Image or None
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
        logger.info(f"🎯 _on_collection_selected CALLED! widget={widget}, has selection={hasattr(widget, 'selection')}")
        try:
            if widget.selection and hasattr(widget.selection, 'collection_data'):
                logger.info("✅ Widget has selection with collection_data")
                collection = widget.selection.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', '')

                logger.info(f"Collection selected: {collection_name} (ID: {collection_id})")

                # Store selected collection
                self.selected_collection = collection

                # Update inspector with collection metadata (as dict)
                logger.info(f"📋 Collection selected, checking inspector: has_attr={hasattr(self.app, 'inspector_window')}, exists={getattr(self.app, 'inspector_window', None) is not None}")
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    logger.info("📋 Updating inspector with collection dict...")
                    # Use collection dict directly (already contains all needed fields)
                    logger.info(f"📋 Calling inspector.update_metadata with {len(collection)} fields")
                    self.app.inspector_window.update_metadata(collection, selection_type="COLLECTION")
                    logger.info("📋 Inspector updated with collection metadata")
                else:
                    logger.warning("📋 Inspector window not available!")

                # Enable inspector button on mobile when collection is selected
                if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                    self.commands['show_inspector'].enable()
                    logger.debug("✅ Enabled 'Show Inspector' button (collection selected)")

                # Navigate to collection via callback (called only once)
                if self.on_collection_selected:
                    logger.info(f"🔄 Calling navigation callback for {collection_name}")
                    self.on_collection_selected(collection_id, collection_name)
            else:
                # No selection or selection cleared - clear the center pane
                logger.info("❌ No collection selected - clearing center pane")
                if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                    if hasattr(self.app.main_window_wrapper, 'center_pane') and self.app.main_window_wrapper.center_pane:
                        self.app.main_window_wrapper.center_pane.clear()
                        logger.info("📭 Center pane cleared")

                # Disable inspector button on mobile when no selection
                if hasattr(self, 'commands') and 'show_inspector' in self.commands:
                    self.commands['show_inspector'].disable()
                    logger.debug("❌ Disabled 'Show Inspector' button (no selection)")

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

            # Bottom toolbar callbacks (mobile only - desktop uses native menus)
            if self.bottom_toolbar:
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

    def _on_new_collection(self, widget=None):
        """Handle new collection command (Cmd+N) - creates empty local collection"""
        logger.debug("New local collection requested")
        try:
            # Create a new empty collection in library folder with default name
            self._add_collection_with_library()
        except Exception as e:
            logger.error(f"Failed to create new collection: {e}")
            # Show error message to user
            try:
                self._show_message("Error", f"Failed to create new collection: {str(e)}")
            except:
                logger.error("Could not show error dialog")

    def _on_new_collection_from_folder(self, widget=None):
        """Handle new collection from folder command - creates external collection at chosen location"""
        logger.debug("New external collection requested")
        try:
            # Show save dialog to choose location and name
            import asyncio
            asyncio.create_task(self._create_external_collection())
        except Exception as e:
            logger.error(f"Failed to create external collection: {e}")
            try:
                self._show_message("Error", f"Failed to create external collection: {str(e)}")
            except:
                logger.error("Could not show error dialog")

    async def _create_external_collection(self):
        """Show save dialog and create external collection at chosen location"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show folder selection dialog (user picks location)
            # Note: Toga doesn't have a "save as" dialog, so we use folder picker
            # User will need to type the folder name in the OS dialog
            import toga
            selected_path = await window.dialog(
                toga.SelectFolderDialog(
                    title=_("Choose Location and Name for New Collection"),
                    initial_directory=None
                )
            )

            if selected_path:
                from pathlib import Path
                collection_path = Path(selected_path)
                collection_name = collection_path.name

                logger.info(f"📝 Creating external collection: {collection_name} at {collection_path}")

                # Create collection using the library service
                if self.library_service:
                    logger.debug(f"🔧 Calling library_service.add_collection_for_ui with:")
                    logger.debug(f"   name={collection_name}")
                    logger.debug(f"   collection_type=external")
                    logger.debug(f"   source_path={collection_path}")

                    # Add collection via library service
                    collection_id = await self.library_service.add_collection_for_ui(
                        name=collection_name,
                        collection_type="external",
                        source_path=str(collection_path),
                        description=""
                    )

                    if collection_id:
                        logger.info(f"✅ External collection '{collection_name}' created with ID: {collection_id}")
                        logger.debug(f"🔄 Refreshing collections view...")

                        # Refresh the collections view
                        await self.refresh_collections()

                        logger.debug(f"📂 Opening newly created collection: {collection_id}")

                        # Automatically open the newly created collection
                        if self.on_collection_selected:
                            logger.debug(f"🎯 Calling on_collection_selected({collection_id}, {collection_name})")
                            self.on_collection_selected(collection_id, collection_name)
                    else:
                        logger.error("Failed to create external collection")
                        self._show_message("Error", "Failed to create collection. Please try again.")
                else:
                    logger.error("Library service not available")
                    self._show_message("Error", "Library system not available.")
            else:
                logger.info("Collection creation cancelled")

        except Exception as e:
            logger.error(f"Failed to create external collection: {e}")
            self._show_message("Error", f"Failed to create collection: {str(e)}")

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
    
    async def _get_unique_collection_name(self, base_name: str = "Untitled Collection") -> str:
        """Get a unique collection name by adding numbers if needed (macOS style)"""
        try:
            # Get all existing collections
            collections = await self.library_service.get_collections_for_ui()
            existing_names = {c['name'] for c in collections}

            # If base name is available, use it
            if base_name not in existing_names:
                return base_name

            # Otherwise, find the next available number
            counter = 2
            while f"{base_name} {counter}" in existing_names:
                counter += 1

            return f"{base_name} {counter}"

        except Exception as e:
            logger.error(f"Failed to generate unique name: {e}")
            # Fallback to base name
            return base_name

    def _add_collection_with_library(self):
        """Add local collection using the library system - creates 'Untitled Collection'"""
        try:
            # Create collection using the library service
            if self.library_service:
                import asyncio
                asyncio.create_task(self._create_local_collection_with_unique_name())
            else:
                logger.error("Library service not available")
                self._show_message("Error", "Library system not available. Please restart the application.")

        except Exception as e:
            logger.error(f"Library system integration failed: {e}")
            self._show_message("Error", f"Failed to create collection: {str(e)}")

    async def _create_local_collection_with_unique_name(self):
        """Create local collection with auto-incremented name if needed"""
        try:
            # Get unique name
            collection_name = await self._get_unique_collection_name("Untitled Collection")

            # Create collection
            await self._create_local_collection(collection_name)

        except Exception as e:
            logger.error(f"Failed to create local collection with unique name: {e}")
            self._show_message("Error", f"Failed to create collection: {str(e)}")

    async def _create_local_collection(self, collection_name: str):
        """Create local collection via library service"""
        try:
            # Add collection via library service
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type="local",
                source_path=None,
                description=""
            )

            if collection_id:
                logger.info(f"Local collection '{collection_name}' created with ID: {collection_id}")
                # Refresh the collections view
                await self.refresh_collections()

                # Automatically open the newly created collection
                if self.on_collection_selected:
                    self.on_collection_selected(collection_id, collection_name)
            else:
                logger.error("Failed to create local collection")
                self._show_message("Error", "Failed to create collection. Please try again.")

        except Exception as e:
            logger.error(f"Failed to create local collection: {e}")
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
                title=_("Delete Collection"),
                message=_("delete_collection_confirm").format(name=collection_name)
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

                    # If we're currently viewing this collection, navigate back to library view
                    if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                        current_view = self.app.main_window_wrapper.center_pane
                        # Check if current view is a collection view showing this collection
                        if hasattr(current_view, 'collection_id') and current_view.collection_id == collection_id:
                            logger.info(f"Navigating away from deleted collection view")
                            # Show library view
                            self.app.main_window_wrapper.show_library_view()

                    # Refresh the collections display
                    self.refresh_collections()
                else:
                    logger.error(f"Failed to delete collection: {collection_name}")
                    error_dialog = toga.ErrorDialog(
                        title=_("Delete Failed"),
                        message=_("delete_failed_message").format(name=collection_name)
                    )
                    await self.app.main_window.dialog(error_dialog)
            else:
                logger.error("Library manager not available for collection deletion")
                error_dialog = toga.ErrorDialog(
                    title=_("Delete Failed"),
                    message=_("delete_failed_no_service")
                )
                await self.app.main_window.dialog(error_dialog)

        except Exception as e:
            logger.error(f"Failed to perform collection deletion: {e}")
            error_dialog = toga.ErrorDialog(
                title=_("Delete Error"),
                message=_("delete_error_message").format(error=str(e))
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
                title=_("Edit Collection"),
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
    
    async def refresh_collections(self):
        """Refresh the collections display"""
        try:
            # Reload collections from database and wait for completion
            await self._load_collections_async()
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
    
    def define_commands(self):
        """Define all commands for LibraryView"""
        try:
            # Create custom menu groups (following OutputView pattern)
            tools_group = toga.Group("Tools", order=50)  # After View (30), before Window (90)

            # Note: _() is available globally via gettext.install() in app.py
            self.commands = {
                # ===== FILE MENU - NEW COLLECTION =====
                'new_collection': FicheroCommand(
                    id=f'{self.view_id}.new_collection',
                    label=_("New Collection"),
                    action=self._on_new_collection,
                    shortcut=toga.Key.MOD_1 + 'n',  # Cmd+N (standard Mac shortcut for New)
                    icon='resources/icons/toolbar/folder@10x.png',  # Folder icon for new collection
                    description=_("Create a new collection in library folder"),
                    group=toga.Group.FILE,  # File menu on desktop
                    section=0,  # First section of File menu
                    order=0,  # First item in section
                    show_in_menu=True,  # Appear in File menu on desktop
                    show_in_toolbar=True,  # Show in desktop toolbar
                    show_in_bottom_toolbar=False,  # Not on mobile bottom toolbar
                    desktop_only=True,  # Only show on desktop
                    context='normal'  # Always visible on desktop
                ),

                'new_collection_from_folder': FicheroCommand(
                    id=f'{self.view_id}.new_collection_from_folder',
                    label=_("New External Collection…"),
                    action=self._on_new_collection_from_folder,
                    icon='resources/icons/toolbar/folder@10x.png',
                    description=_("Create a new collection at external location"),
                    group=toga.Group.FILE,  # File menu on desktop
                    section=0,  # Same section as New Collection
                    order=1,  # Second item in section (after New Collection)
                    show_in_menu=True,  # Appear in File menu on desktop
                    show_in_toolbar=False,  # NOT in toolbar (menu only)
                    show_in_bottom_toolbar=False,  # Not on mobile bottom toolbar
                    desktop_only=True,  # Only show on desktop
                    context='normal'  # Always visible on desktop
                ),

                # ===== FILE MENU - IMPORT SUBMENU PARENT =====
                'import': FicheroCommand(
                    id=f'{self.view_id}.import',
                    label=_("Import"),
                    action=None,  # Submenu parent has no action
                    description=_("Import items into collection"),
                    group=toga.Group.FILE,  # File menu on desktop
                    section=1,  # Second section of File menu (with divider after New Collection)
                    order=0,  # First item in this section
                    show_in_menu=True,  # Appear in File menu on desktop
                    show_in_toolbar=False,  # Not in toolbar
                    show_in_bottom_toolbar=False,  # Not on mobile bottom toolbar
                    desktop_only=True,  # Only show on desktop
                    context='normal'  # Always visible on desktop
                ),

                # NOTE: Import commands (File, Folder, URL, Link File, Link Folder)
                # have been MOVED to Collection View as of STEP 4.
                # They now add items to the current collection instead of creating new collections.

                # ===== WINDOW NAVIGATION COMMANDS =====
                # Desktop: Application/Window menus | Mobile: Bottom toolbar
                'settings': FicheroCommand(
                    id=f'{self.view_id}.settings',
                    label=_("Settings…"),
                    action=self._on_open_settings_window,
                    shortcut=toga.Key.MOD_1 + ',',  # Standard macOS: Cmd+, (Command+Comma)
                    icon='resources/icons/toolbar/settings.png',
                    description=_("Open settings window"),
                    group=toga.Group.APP,  # Application menu on desktop (Fichero menu on macOS)
                    section=0,  # First section - before Plans/Prompts
                    order=0,  # First item in section
                    show_in_menu=True,  # Appear in App menu
                    show_in_toolbar=True,  # Show in desktop toolbar ONLY (not mobile top toolbar)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'processing': FicheroCommand(
                    id=f'{self.view_id}.processing',
                    label=_("Processing"),
                    action=self._on_open_processing_window,
                    icon='resources/icons/toolbar/process.png',
                    description=_("Open processing window"),
                    group=toga.Group.WINDOW,  # Window menu on desktop
                    show_in_menu=True,  # Appear in Window menu on desktop
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'about': FicheroCommand(
                    id=f'{self.view_id}.about',
                    label=_("About"),
                    action=self._on_open_about_window,
                    icon='resources/icons/toolbar/help.png',
                    description=_("Open about window"),
                    group=toga.Group.APP,  # Application menu on desktop (Fichero menu on macOS)
                    show_in_menu=False,  # Don't add to App menu (Toga/system may provide About automatically)
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'activity': FicheroCommand(
                    id=f'{self.view_id}.activity',
                    label=_("Activity"),
                    action=self._on_open_activity_monitor_window,
                    icon='resources/icons/toolbar/activity.png',
                    description=_("Open activity monitor"),
                    group=toga.Group.WINDOW,  # Window menu on desktop
                    show_in_menu=True,  # Appear in Window menu on desktop
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'inspector': FicheroCommand(
                    id=f'{self.view_id}.inspector',
                    label=_("Show Inspector…"),
                    action=self._on_toggle_inspector,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 'i',  # Cmd+Shift+I
                    icon='resources/icons/toolbar/info.circle@10x.png',  # Info circle icon
                    description=_("Toggle inspector window"),
                    group=tools_group,  # Tools menu on desktop (custom group)
                    section=-1,  # BEFORE all other Tools menu items (separator after)
                    order=0,  # First item in section
                    show_in_menu=True,  # Appear in Tools menu on desktop
                    show_in_toolbar=True,  # Show in desktop toolbar (top left)
                    show_in_top_toolbar=True,  # Show in mobile top toolbar (top right after Edit)
                    show_in_bottom_toolbar=False,  # Not in bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=True,  # Desktop only feature
                    context='normal'
                ),

                'plans': FicheroCommand(
                    id=f'{self.view_id}.plans',
                    label=_("Plans…"),
                    action=self._on_open_plans_window,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 'l',  # Cmd+Shift+L
                    icon='resources/icons/toolbar/plan.png',
                    description=_("Open plans window"),
                    group=toga.Group.APP,  # Application menu on desktop (Fichero menu on macOS)
                    section=1,  # Second section - Settings/Plans/Prompts grouped
                    order=1,  # Second item after Settings
                    show_in_menu=True,  # Appear in App menu
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'prompts': FicheroCommand(
                    id=f'{self.view_id}.prompts',
                    label=_("Prompts…"),
                    action=self._on_open_prompts_window,
                    shortcut=toga.Key.MOD_1 + toga.Key.SHIFT + 'p',  # Cmd+Shift+P
                    icon='resources/icons/toolbar/prompt.png',
                    description=_("Open prompts window"),
                    group=toga.Group.APP,  # Application menu on desktop (Fichero menu on macOS)
                    section=1,  # Second section - Settings/Plans/Prompts grouped
                    order=2,  # Third item after Settings and Plans
                    show_in_menu=True,  # Appear in App menu
                    show_in_toolbar=False,  # NOT in desktop toolbar (menu only)
                    show_in_bottom_toolbar=True,  # Mobile bottom toolbar
                    toolbar_position='center',  # Center on mobile bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                'output': FicheroCommand(
                    id=f'{self.view_id}.output',
                    label=_("Output"),
                    action=self._on_open_output_window,
                    icon='resources/icons/toolbar/document.png',
                    description=_("Open output window"),
                    group=toga.Group.WINDOW,  # Window menu on desktop
                    show_in_menu=True,  # Appear in Window menu on desktop
                    show_in_toolbar=False,  # Not in desktop toolbar (not needed)
                    show_in_bottom_toolbar=False,  # Not in mobile toolbar
                    toolbar_position='center',
                    mobile_only=False,  # Available on both platforms
                    desktop_only=False,
                    context='normal'
                ),

                # ===== EDIT MODE COMMANDS =====
                # Add Collection button for edit mode (mobile bottom toolbar)
                'edit_add_collection': FicheroCommand(
                    id=f'{self.view_id}.edit_add_collection',
                    label=_("Add\nCollection"),
                    action=self._on_new_collection,
                    icon='resources/icons/toolbar/folder@10x.png',
                    description=_("Create a new collection"),
                    show_in_menu=False,
                    show_in_bottom_toolbar=True,
                    toolbar_position='center',
                    mobile_only=True,  # Mobile only - mobile edit mode
                    desktop_only=False,
                    context='edit'
                ),

                # ===== MOBILE TOP TOOLBAR - INSPECTOR BUTTON =====
                'show_inspector': FicheroCommand(
                    id=f'{self.view_id}.show_inspector',
                    label=_("Info"),
                    action=self._on_show_inspector,
                    icon='resources/icons/toolbar/info.circle@10x.png',
                    description=_("Show inspector for selected collection"),
                    show_in_menu=False,  # Not in menus
                    show_in_toolbar=False,  # Not in desktop toolbar
                    show_in_top_toolbar=True,  # Mobile top toolbar
                    toolbar_position='right',  # Right side of toolbar
                    show_in_bottom_toolbar=False,  # Not in bottom toolbar
                    mobile_only=True,  # Only on mobile
                    desktop_only=False,
                    context='normal',
                    order=99,  # Last on right side (rightmost)
                    enabled=False  # Will be enabled when collection is selected
                ),
            }

            logger.debug(f"Defined {len(self.commands)} commands for LibraryView")

        except Exception as e:
            logger.error(f"Failed to define LibraryView commands: {e}")
            self.commands = {}

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
        """Update toolbars based on edit mode state using pure declarative system"""
        try:
            from fichero.shared.toolbars.toolbar_coordinator import EditModeState

            if self.is_edit_mode:
                # Enable edit mode - pass view_id so toolbar can query declarative commands
                self.coordinator.set_edit_mode(
                    EditModeState.EDIT,
                    context={'view_id': 'library'}
                )
            else:
                # Disable edit mode - pass view_id for consistency
                self.coordinator.set_edit_mode(
                    EditModeState.NORMAL,
                    context={'view_id': 'library'}
                )

        except Exception as e:
            logger.error(f"Failed to update toolbars for edit mode: {e}")

    def _on_edit_mode_changed(self, state, context: Dict[str, Any]):
        """Handle edit mode changes from coordinator - pure declarative system"""
        try:
            from fichero.shared.toolbars.toolbar_coordinator import EditModeState

            # Pure declarative system: Bottom toolbar will query CommandRegistry automatically
            # for commands matching view_id='library', context='edit', show_in_bottom_toolbar=True
            #
            # No need to create action dicts or inject context - commands are already declared
            # in define_commands() with proper metadata

            logger.debug(f"LibraryView edit mode changed to {state.value} (pure declarative)")

        except Exception as e:
            logger.error(f"Failed to handle edit mode change: {e}")

    # REMOVED: Parallel non-declarative system methods
    # - _create_add_context_once() - Created action dicts instead of using declared commands
    # - _clear_add_context() - Cleared parallel system context
    #
    # Edit mode buttons are now declared as FicheroCommands in define_commands() above:
    # - edit_import_urls, edit_import_files, edit_import_folder, export, bulk_import
    # - All marked with context='edit', show_in_bottom_toolbar=True, mobile_only=True
    #
    # Bottom toolbar queries CommandRegistry.get_commands_for_view() to populate buttons automatically


    # Add dialog functionality available through edit mode buttons

    def _on_edit_pressed(self, widget=None):
        """Handle Edit button press - wrapper for top toolbar handler"""
        try:
            if hasattr(self.top_toolbar, '_on_edit_pressed'):
                self.top_toolbar._on_edit_pressed(widget)
            else:
                # Fallback: toggle edit mode directly
                self.toggle_edit_mode()
        except Exception as e:
            logger.error(f"Failed to handle edit press: {e}")

    # REMOVED: Manual toolbar button creation methods
    # Toolbars are now populated automatically from command definitions via BaseView.set_toolbars()
    # Commands are defined in define_commands() with show_in_toolbar flags


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

    def _on_toggle_inspector(self, widget=None):
        """Handle inspector window toggle"""
        logger.info("Toggling inspector window")
        self.app.toggle_inspector()

    def _on_open_prompts_window(self, widget=None):
        """Handle prompts window navigation"""
        logger.info("Opening prompts window")
        self.app.view_integration.navigation_controller.navigate_to_prompts()

    def _on_open_plans_window(self, widget=None):
        """Handle plans window navigation"""
        logger.info("Opening plans window")
        self.app.view_integration.navigation_controller.navigate_to_plans()

    def _on_open_output_window(self, widget=None):
        """Handle output window navigation"""
        logger.info("Opening output window")
        self.app.view_integration.navigation_controller.navigate_to_output()

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
                title=_("Export") + f" {collection_name}",
                suggested_filename=default_filename,
                file_types=['zip'],
                on_result=lambda widget, path: asyncio.create_task(
                    self._perform_export_collection(collection_id, collection_name, path)
                )
            )

        except Exception as e:
            logger.error(f"Failed to initiate export: {e}")
            self.app.main_window.error_dialog(_("Export Error"), str(e))

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
                self.app.main_window.error_dialog(_("Error"), _("library_service_unavailable"))
                return

            library_service = self.app.view_integration.library_service

            # Perform export
            success = await library_service.library_manager.export_collection(collection_id, output_path)

            if success:
                # Calculate file size
                file_size = output_path.stat().st_size
                size_mb = file_size / (1024 * 1024)

                self.app.main_window.info_dialog(
                    _("Export Successful"),
                    _("export_successful_message").format(path=output_path, size=f"{size_mb:.1f}")
                )
                logger.info(f"Export completed: {output_path} ({size_mb:.1f} MB)")
            else:
                self.app.main_window.error_dialog(
                    _("Export Failed"),
                    _("export_failed_message").format(error=collection_name)
                )
                logger.error(f"Export failed for collection: {collection_name}")

        except Exception as e:
            logger.error(f"Export operation failed: {e}")
            self.app.main_window.error_dialog(_("Export Error"), str(e))

    def _on_import_urls(self, widget=None):
        """Handle URL import - opens URL add view with selected collection context"""
        try:
            logger.info("Import URLs requested from library view")

            # Check if a collection is selected
            if not self.selected_collection:
                logger.warning("No collection selected - cannot import URL")
                return

            collection_id = self.selected_collection.get('id')
            logger.info(f"Importing URL to selected collection: {collection_id}")

            # Import URLAddView and create window (same pattern as collection_view)
            from fichero.windows.add.views.url_view import URLAddView
            import toga

            # Create callback that uses the selected collection_id
            def on_url_added_with_context(data):
                return self._on_url_added_with_collection(data, collection_id)

            url_view = URLAddView(
                app=self.app,
                on_content_added=on_url_added_with_context
            )

            # Desktop: create new window
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                add_window = toga.Window(
                    title="Import URL",
                    size=(600, 400),
                    resizable=True
                )
                add_window.content = url_view.container
                url_view.window = add_window
                add_window.show()
                logger.info("URL add window shown")
            else:
                logger.error("main_window_wrapper not available")

        except Exception as e:
            logger.error(f"Failed to open URL import: {e}")

    def _on_url_added_with_collection(self, data: dict, collection_id: str):
        """Callback when URL is added - uses specified collection_id"""
        try:
            url = data.get('url', '')
            logger.info(f"URL added callback received: {url}, collection_id={collection_id}")

            # Add URL to the specified collection using library service
            import asyncio
            asyncio.create_task(self._add_url_to_collection_async(url, collection_id))

        except Exception as e:
            logger.error(f"Failed to handle URL add callback: {e}")

    async def _add_url_to_collection_async(self, url: str, collection_id: str):
        """Add URL to collection asynchronously"""
        try:
            logger.info(f"Adding URL '{url}' to collection {collection_id}")

            # Use library service to import URL
            await self.app.library_service.import_urls_for_ui(
                collection_id=collection_id,
                urls=[url]
            )

            # Refresh the library view to show updated collection
            self._load_collections()
            logger.info(f"✅ URL added to collection successfully")

        except Exception as e:
            logger.error(f"Failed to add URL to collection: {e}")

    async def _select_and_add_files_async(self, collection_id: str, operation: str = "link"):
        """Show file selection dialog and add selected files to collection"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show file selection dialog (can select multiple files)
            # Support all common image formats plus documents
            import toga
            selected_paths = await window.dialog(
                toga.OpenFileDialog(
                    title=_("Select Files to Add"),
                    initial_directory=None,
                    multiple_select=True,
                    file_types=['tif', 'tiff', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'jxl',
                               'pdf', 'heic', 'heif', 'raw', 'cr2', 'nef', 'arw', 'dng']
                )
            )

            if selected_paths:
                logger.info(f"{len(selected_paths)} file(s) selected, operation={operation}")
                # Add files to collection using library service
                for file_path in selected_paths:
                    await self.app.library_service.add_item_to_collection_for_ui(
                        collection_id=collection_id,
                        item_type="file",
                        source=str(file_path),
                        operation=operation
                    )

                # Refresh the library view
                self._load_collections()
                logger.info(f"✅ Files added to collection successfully")
            else:
                logger.info("File selection cancelled")

        except Exception as e:
            logger.error(f"Failed to select and add files: {e}")

    async def _select_and_add_folder_async(self, collection_id: str, operation: str = "link"):
        """Show folder selection dialog and add selected folder to collection"""
        try:
            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show folder selection dialog
            import toga
            selected_path = await window.dialog(
                toga.SelectFolderDialog(
                    title=_("Select Folder to Add"),
                    initial_directory=None
                )
            )

            if selected_path:
                logger.info(f"Folder selected: {selected_path}, operation={operation}")
                # Add folder to collection using library service
                await self.app.library_service.add_item_to_collection_for_ui(
                    collection_id=collection_id,
                    item_type="folder",
                    source=str(selected_path),
                    operation=operation
                )

                # Refresh the library view
                self._load_collections()
                logger.info(f"✅ Folder added to collection successfully")
            else:
                logger.info("Folder selection cancelled")

        except Exception as e:
            logger.error(f"Failed to select and add folder: {e}")

    def _on_import_bulk(self, widget=None):
        """Handle bulk import - not yet implemented in NavigationController"""
        try:
            logger.info("Bulk import requested")
            # TODO: Add navigate_to_bulk_import() to NavigationController
            logger.warning("Bulk import navigation not yet implemented")
            self._show_message("Bulk Import", "Bulk import feature coming soon")

        except Exception as e:
            logger.error(f"Failed to open bulk import: {e}")

    def _on_import_files(self, widget=None):
        """Handle file import - opens native dialog and copies files to collection"""
        try:
            logger.info("Import files requested (copy operation)")

            # Check if a collection is selected
            if not self.selected_collection:
                logger.warning("No collection selected - cannot import files")
                return

            collection_id = self.selected_collection.get('id')
            logger.info(f"Importing files to selected collection: {collection_id}")

            # Open native file dialog and add files
            import asyncio
            asyncio.create_task(self._select_and_add_files_async(collection_id, operation="copy"))

        except Exception as e:
            logger.error(f"Failed to open file import: {e}")

    def _on_import_folder(self, widget=None):
        """Handle folder import - opens native dialog and copies folder to collection"""
        try:
            logger.info("Import folder requested (copy operation)")

            # Check if a collection is selected
            if not self.selected_collection:
                logger.warning("No collection selected - cannot import folder")
                return

            collection_id = self.selected_collection.get('id')
            logger.info(f"Importing folder to selected collection: {collection_id}")

            # Open native folder dialog and add folder
            import asyncio
            asyncio.create_task(self._select_and_add_folder_async(collection_id, operation="copy"))

        except Exception as e:
            logger.error(f"Failed to open folder import: {e}")

    def _on_link_file(self, widget=None):
        """Handle link file - opens native dialog and links (not copies) selected files"""
        try:
            logger.info("Link file requested (link operation)")

            # Check if a collection is selected
            if not self.selected_collection:
                logger.warning("No collection selected - cannot link files")
                return

            collection_id = self.selected_collection.get('id')
            logger.info(f"Linking files to selected collection: {collection_id}")

            # Open native file dialog and link files
            import asyncio
            asyncio.create_task(self._select_and_add_files_async(collection_id, operation="link"))

        except Exception as e:
            logger.error(f"Failed to open link file: {e}")

    def _on_link_folder(self, widget=None):
        """Handle link folder - opens native dialog and links (not copies) selected folder"""
        try:
            logger.info("Link folder requested (link operation)")

            # Check if a collection is selected
            if not self.selected_collection:
                logger.warning("No collection selected - cannot link folder")
                return

            collection_id = self.selected_collection.get('id')
            logger.info(f"Linking folder to selected collection: {collection_id}")

            # Open native folder dialog and link folder
            import asyncio
            asyncio.create_task(self._select_and_add_folder_async(collection_id, operation="link"))

        except Exception as e:
            logger.error(f"Failed to open link folder: {e}")

    def _on_open_camera(self, widget=None):
        """Handle camera - navigate to Camera add view"""
        try:
            logger.info("Camera requested")
            # Use NavigationController to navigate to camera view (mobile only)
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    nav_controller.navigate_to_add_camera()
                else:
                    logger.error("NavigationController not available")
            else:
                logger.error("view_integration not available")

        except Exception as e:
            logger.error(f"Failed to open camera: {e}")

    # ===== MOBILE TOP TOOLBAR HANDLERS =====

    def _on_show_inspector(self, widget=None):
        """Handle show inspector command - opens inspector window with selected collection"""
        try:
            logger.info("Show inspector requested")

            # Get currently selected collection
            if not hasattr(self, 'collections_list') or not self.collections_list or not self.collections_list.selection:
                logger.warning("No collection selected for inspector")
                return

            selected_row = self.collections_list.selection
            collection_id = getattr(selected_row, 'id', None)

            if not collection_id:
                logger.warning("Selected collection has no ID")
                return

            # Fetch full collection metadata from library service (same for desktop and mobile)
            asyncio.create_task(self._show_inspector_with_full_data(collection_id))

        except Exception as e:
            logger.error(f"Failed to show inspector: {e}")

    async def _show_inspector_with_full_data(self, collection_id: str):
        """Fetch full collection data and show inspector (unified for desktop and mobile)"""
        try:
            # Fetch full collection from library
            collection_data = None
            if self.library_service and hasattr(self.library_service, 'library_manager'):
                collection = await self.library_service.library_manager.get_collection(collection_id)
                if collection:
                    # Pass dictionary directly - inspector supports it
                    collection_data = collection.to_dict()
                    logger.info(f"Fetched full collection from database: {len(collection_data)} fields")
                else:
                    logger.warning(f"Collection not found in database: {collection_id}")
            else:
                logger.warning("Library service not available")

            # Fallback to minimal data if fetch failed
            if not collection_data:
                collection_data = {'name': 'Unknown', 'id': collection_id}

            # Mobile: Use NavigationController to navigate to inspector
            if self.is_mobile:
                if hasattr(self.app, 'view_integration'):
                    nav_controller = self.app.view_integration.get_navigation_controller()
                    if nav_controller:
                        # Pass dictionary directly with COLLECTION selection type
                        nav_controller.navigate_to_inspector(
                            item_id=collection_id,
                            item_data=collection_data,
                            selection_type='COLLECTION'
                        )
                        logger.info(f"Navigated to inspector for collection: {collection_id}")
                    else:
                        logger.error("NavigationController not available")
                else:
                    logger.error("view_integration not available")
            # Desktop: Show inspector window directly
            else:
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    # Update inspector with dictionary
                    self.app.inspector_window.update_metadata(collection_data, selection_type='COLLECTION')
                    self.app.inspector_window.show()
                    logger.info(f"Inspector window shown for collection: {collection_id}")
                else:
                    logger.warning("Inspector window not available")

        except Exception as e:
            logger.error(f"Failed to show inspector with full data: {e}")
            import traceback
            traceback.print_exc()

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
            # Check if this is a link operation
            operation = getattr(self, '_pending_operation', 'copy')
            # Clear the pending operation
            if hasattr(self, '_pending_operation'):
                delattr(self, '_pending_operation')

            # Generate collection name
            from datetime import datetime
            op_label = "Linked " if operation == 'link' else ""
            collection_name = f"{op_label}Files {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_type = "external" if operation == 'link' else "local"
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type=collection_type,
                description=f"File collection with {len(files)} items ({'linked' if operation == 'link' else 'copied'})"
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
                        operation=operation  # Use determined operation (copy or link)
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
            # Check if this is a link operation
            operation = getattr(self, '_pending_operation', 'copy')
            # Clear the pending operation
            if hasattr(self, '_pending_operation'):
                delattr(self, '_pending_operation')

            # Generate collection name
            from datetime import datetime
            op_label = "Linked " if operation == 'link' else ""
            collection_name = f"{op_label}Folders {datetime.now().strftime('%Y-%m-%d %H:%M')}"

            # Create collection
            collection_type = "external" if operation == 'link' else "local"
            collection_id = await self.library_service.add_collection_for_ui(
                name=collection_name,
                collection_type=collection_type,
                description=f"Folder collection with {len(folders)} items ({'linked' if operation == 'link' else 'copied'})"
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
                        operation=operation  # Use determined operation (copy or link)
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

    # ===== EVENT HANDLERS FOR LIBRARY STATE SYNCHRONIZATION =====

    def _on_collection_added_event(self, event):
        """Handle collection_added event - auto-refresh library view"""
        try:
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_added - {collection_name}")

            # Reload collections to show the new one
            asyncio.create_task(self._load_collections_async())

        except Exception as e:
            logger.error(f"Failed to handle collection_added event: {e}")

    def _on_collection_deleted_event(self, event):
        """Handle collection_deleted event - auto-refresh library view"""
        try:
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_deleted - {collection_name}")

            # Reload collections to remove the deleted one
            asyncio.create_task(self._load_collections_async())

        except Exception as e:
            logger.error(f"Failed to handle collection_deleted event: {e}")

    def _on_collection_updated_event(self, event):
        """Handle collection_updated event - auto-refresh library view"""
        try:
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_updated - {collection_name}")

            # Reload collections to show updates
            asyncio.create_task(self._load_collections_async())

        except Exception as e:
            logger.error(f"Failed to handle collection_updated event: {e}")

    def _on_folder_import_started_event(self, event):
        """Handle folder import started - update collection subtitle"""
        try:
            collection_id = event.data.get("collection_id")
            folder_name = event.data.get("folder_name", "folder")

            # Track this import
            self.importing_collections[collection_id] = {
                "folder_name": folder_name,
                "count": 0
            }

            # Update the collection's subtitle in the DetailedList
            self._update_collection_subtitle(collection_id, f"Importing {folder_name}...")

            logger.info(f"📁 Started importing {folder_name} to collection {collection_id}")

        except Exception as e:
            logger.error(f"Failed to handle folder_import_started event: {e}")

    def _on_folder_import_progress_event(self, event):
        """Handle folder import progress - update count in subtitle"""
        try:
            collection_id = event.data.get("collection_id")
            total_processed = event.data.get("total_processed", 0)

            if collection_id in self.importing_collections:
                self.importing_collections[collection_id]["count"] = total_processed
                folder_name = self.importing_collections[collection_id]["folder_name"]

                # Update subtitle with count
                self._update_collection_subtitle(collection_id, f"Importing {folder_name}... ({total_processed} files)")

                logger.debug(f"📁 Import progress: {total_processed} files")

        except Exception as e:
            logger.error(f"Failed to handle folder_import_progress event: {e}")

    def _on_folder_import_completed_event(self, event):
        """Handle folder import completed - clear importing status"""
        try:
            collection_id = event.data.get("collection_id")
            added = event.data.get("added", 0)

            # Remove from importing collections
            if collection_id in self.importing_collections:
                del self.importing_collections[collection_id]

            # Subtitle will be updated when collection_items_changed event fires
            logger.info(f"✅ Import completed: {added} files added")

        except Exception as e:
            logger.error(f"Failed to handle folder_import_completed event: {e}")

    def _update_collection_subtitle(self, collection_id: str, subtitle: str):
        """Update the subtitle for a collection in the DetailedList"""
        try:
            # DISABLED: Updating subtitles during import causes hundreds of full refreshes
            # and freezes the app. Toga's DetailedList doesn't support partial updates.
            # The subtitle will be correct when the user refreshes or navigates back.

            # Find the collection in our list and update the data (but don't refresh UI)
            for collection in self.collections:
                if collection.get("id") == collection_id:
                    # Update the subtitle in memory only
                    collection["subtitle"] = subtitle
                    logger.debug(f"Updated subtitle for collection {collection_id}: {subtitle}")
                    break

            # DO NOT call self._create_content() here - it causes app freeze during large imports

        except Exception as e:
            logger.error(f"Failed to update collection subtitle: {e}")
