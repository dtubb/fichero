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

from fichero.shared.views.base_view import BaseView, VIEW_BACKGROUND
from fichero.shared.widgets import ListWidget  # Phase 6: Platform-adaptive widget

# Colors for collection status
COLLECTION_ACTIVE = "#E3F2FD"  # Light blue for active collections
COLLECTION_INACTIVE = "#FFFFFF"  # White for inactive
from .sidebar_data_model import SidebarDataModel  # Phase 6: Hierarchical sidebar organization

# Use native SourceList on macOS desktop (lazy import to avoid Rubicon issues at module load)
import sys
USE_SOURCE_LIST = sys.platform == "darwin"

def _get_source_list_classes():
    """Lazy import of SourceList to avoid Rubicon import issues at module load."""
    from fichero.app.main_window.sidebar import SourceList, SourceListItem
    return SourceList, SourceListItem

logger = logging.getLogger(__name__)


class LibraryView(BaseView):
    """Library view showing all collections using the BaseView system"""

    def __init__(self, app, is_mobile: bool = False):
        """Initialize library view"""
        logger.debug(f" LibraryView.__init__ starting with app={app}, is_mobile={is_mobile}")
        logger.debug(f"LibraryView.__init__ called with app={app}, is_mobile={is_mobile}")

        # Set view_id BEFORE super().__init__
        self.view_id = "library"

        # Initialize collections attribute with empty list
        logger.debug(" Setting initial attributes...")
        self.is_edit_mode = False
        self.collections: List[Dict[str, Any]] = []
        self.selected_collection: Optional[Dict[str, Any]] = None

        # Sort state
        self.current_sort_mode = "name"  # Default sort by name
        self.sort_ascending = True  # True = A-Z, False = Z-A

        # Cache folder icon to prevent repeated loads
        self._folder_icon_cache = None

        # Initialize recursion guard flag
        self._showing = False

        # Track background tasks for cleanup
        self._background_tasks = set()

        # Initialize tree data map for collection lookup (used in _on_tree_select)
        self._tree_data_map = {}

        # Initialize sidebar data model for hierarchical organization
        self.sidebar_model = SidebarDataModel()
        logger.debug(" Sidebar data model initialized")

        logger.debug(" Calling super().__init__...")
        super().__init__(app, is_mobile)
        logger.debug(" BaseView initialization complete")

        # CRITICAL FIX: Library sidebar doesn't need ScrollContainer (NSOutlineView has its own)
        # Remove ScrollContainer and use content_container directly
        if self.scroll_container and self.content_container:
            try:
                # Remove scroll container from main container
                self.container.remove(self.scroll_container)
                # Add content_container directly to main container
                self.container.add(self.content_container)
                # Clear scroll container reference
                self.scroll_container = None
                logger.info("✅ Removed ScrollContainer from LibraryView (using content_container directly)")
            except Exception as e:
                logger.error(f"Failed to remove ScrollContainer: {e}")

        # Commands are now handled by native menu/toolbar (windows/main/menu.py, toolbar.py)
        self.commands = {}  # Empty dict for compatibility

        # Desktop uses native window.toolbar (managed by main_window.py)
        # No custom toolbars needed here
        self.top_toolbar = None
        self.bottom_toolbar = None
        logger.debug(" Desktop mode: Using native window.toolbar only")

        # Initialize callback for collection selection
        logger.debug(" Setting collection callback...")
        self.on_collection_selected = None

        # Initialize folder selection tracking
        self.selected_folder_id = None
        self.selected_folder_path = None

        # Initialize library manager
        logger.debug(" Initializing library system...")
        self._initialize_library_system()

        # Create initial content (will be refreshed when collections load)
        logger.debug(" Creating initial content...")
        self._create_content()

        # Schedule collection loading for after initialization
        logger.debug(" Starting collection loading...")
        self._needs_initial_load = False
        try:
            # Try to create async task - only works if event loop is running
            self._create_task(self._load_collections_async())
            logger.debug(" Async task created")
        except RuntimeError:
            # No event loop yet - defer loading until show() is called
            logger.debug(" No event loop - deferring collection load until show()")
            self._needs_initial_load = True

        # Subscribe to library state events for automatic synchronization
        # Only subscribe once per instance to prevent duplicate event handlers
        if not hasattr(self, '_events_subscribed'):
            logger.debug(" Subscribing to library state events...")
            from fichero.shared.navigation.navigation_event_bus import subscribe_to_navigation
            subscribe_to_navigation("collection_added", self._on_collection_added_event)
            subscribe_to_navigation("collection_deleted", self._on_collection_deleted_event)
            subscribe_to_navigation("collection_updated", self._on_collection_updated_event)
            subscribe_to_navigation("folder_import_started", self._on_folder_import_started_event)
            subscribe_to_navigation("folder_import_progress", self._on_folder_import_progress_event)
            subscribe_to_navigation("folder_import_completed", self._on_folder_import_completed_event)
            self._events_subscribed = True
            logger.debug(f" Event subscriptions registered for LibraryView instance {id(self)}")
        else:
            logger.debug(f"⏭️ Event subscriptions already registered for this instance {id(self)} - skipping")

        # Track imports in progress
        self.importing_collections = {}  # collection_id -> {folder_name, count}

        logger.debug(" LibraryView initialization complete")
        logger.info("Library view created successfully")
    
    def show(self):
        """Called when view becomes active - refresh DetailedList to clear cached selections"""
        import traceback
        # Prevent recursion if show() is called while already showing
        if self._showing:
            logger.warning("⏭️ Recursion detected in LibraryView.show() - preventing recursive call")
            logger.warning(f"Call stack:\n{''.join(traceback.format_stack())}")
            return

        logger.debug("📍 LibraryView.show() called")
        self._showing = True
        try:
            # Tell the coordinator that this view is now active
            if hasattr(self, 'coordinator') and self.coordinator:
                self.coordinator.set_active_view('library')

            # Handle deferred initial load (if event loop wasn't ready during __init__)
            if getattr(self, '_needs_initial_load', False):
                self._needs_initial_load = False
                logger.debug("Performing deferred collection load")
                self._create_task(self._load_collections_async())
                # Note: _load_collections_async() will call _create_content() when done
                # Don't call _create_collections_display() here - would be duplicate
            else:
                # Normal show - just refresh the display
                # Only refresh if we have collections to avoid unnecessary work
                if self.collections:
                    logger.debug("🔄 Refreshing collections display on show()")
                    self._create_collections_display()
                else:
                    logger.debug("📭 No collections to display on show()")

            logger.info("✅ Library view show() completed successfully")
        except Exception as e:
            logger.error(f"❌ Failed in LibraryView.show(): {e}", exc_info=True)
        finally:
            # Always reset the flag, even if an exception occurred
            self._showing = False

    def cleanup(self):
        """Clean up resources and unsubscribe from events to prevent memory leaks"""
        try:
            from fichero.shared.navigation.navigation_event_bus import unsubscribe_from_navigation

            logger.debug("Starting LibraryView cleanup...")

            # Unsubscribe from all navigation events
            unsubscribe_from_navigation("collection_added", self._on_collection_added_event)
            unsubscribe_from_navigation("collection_deleted", self._on_collection_deleted_event)
            unsubscribe_from_navigation("collection_updated", self._on_collection_updated_event)
            unsubscribe_from_navigation("folder_import_started", self._on_folder_import_started_event)
            unsubscribe_from_navigation("folder_import_progress", self._on_folder_import_progress_event)
            unsubscribe_from_navigation("folder_import_completed", self._on_folder_import_completed_event)
            logger.debug("Unsubscribed from navigation events")

            # Cancel all background tasks
            if hasattr(self, '_background_tasks'):
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()
                self._background_tasks.clear()
                logger.debug("Cancelled background tasks")

            # Unregister toolbar coordinator from navigation controller
            if hasattr(self, 'coordinator') and self.coordinator:
                if hasattr(self.app, 'view_integration') and self.app.view_integration:
                    nav = self.app.view_integration.navigation_controller
                    if nav and hasattr(nav, 'unregister_toolbar_coordinator'):
                        nav.unregister_toolbar_coordinator(self.coordinator)
                        logger.debug("Unregistered toolbar coordinator")

            # Clear references
            self.on_collection_selected = None
            self.selected_collection = None

            logger.debug("LibraryView cleanup completed")
        except Exception as e:
            logger.error(f"Failed to cleanup LibraryView: {e}", exc_info=True)

    def _create_task(self, coro):
        """Create and track an async task for proper cleanup"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        # Add error handler to log unhandled exceptions
        def _handle_task_error(t):
            try:
                t.result()  # Raises if task failed
            except asyncio.CancelledError:
                pass  # Normal cancellation, ignore
            except Exception as e:
                logger.error(f"Background task failed: {e}", exc_info=True)

        task.add_done_callback(_handle_task_error)
        return task

    async def _safe_show_error(self, title: str, message: str):
        """Safely show error dialog to user (P0-6 fix)"""
        try:
            if hasattr(self.app, 'main_window') and self.app.main_window:
                await self.app.main_window.dialog(
                    toga.ErrorDialog(title=title, message=message)
                )
            else:
                # Fallback: log only if no window available
                logger.error(f"Cannot show dialog - {title}: {message}")
        except Exception as e:
            logger.error(f"Failed to show error dialog: {e}", exc_info=True)

    def register_collection_callback(self, callback):
        """Register callback for when a collection is selected"""
        try:
            self.on_collection_selected = callback
            logger.debug("Collection selection callback registered")
        except Exception as e:
            logger.error(f"Failed to register collection callback: {e}")
    
    def _create_content(self, widget=None):
        """Update the library view content

        Args:
            widget: Optional widget parameter (ignored, for compatibility with Toga callbacks)
        """
        try:
            logger.info("🔵 _create_content() called - updating collections data")

            # Don't clear! Just update the existing widget
            # ListWidget.set_data() handles all updates properly
            self._create_collections_display()

            logger.info(f"✅ Updated library with {len(self.collections)} collections")

        except Exception as e:
            logger.error(f"Failed to update library content: {e}", exc_info=True)
    
    def _create_collections_display(self):
        """Create display for actual collections"""
        try:
            logger.info("🟢 _create_collections_display() called")
            logger.info(f"🔍 Current collections count: {len(self.collections)}")

            # No title here - titles should only be in top toolbar
            # Create detailed list for collections directly
            logger.info("🟢 Calling _create_collections_detailed_list()...")
            self._create_collections_detailed_list()

            logger.info(f"✅ Created display for {len(self.collections)} collections")

        except Exception as e:
            logger.error(f"Failed to create collections display: {e}", exc_info=True)
    
    def _create_collections_detailed_list(self):
        """Create or update detailed list view for collections with selection preservation"""
        try:
            # Store current selection to restore later
            current_selection_id = None
            if (hasattr(self, 'collections_list') and self.collections_list):
                try:
                    if USE_SOURCE_LIST and hasattr(self, '_source_list'):
                        # SourceList: get selected item directly
                        if self._source_list.selected:
                            data = self._source_list.selected.data or {}
                            current_selection_id = data.get('id')
                    else:
                        # ListWidget: use get_selection()
                        selection = self.collections_list.get_selection()
                        if selection:
                            current_selection_id = selection.collection_data.get('id')
                    if current_selection_id:
                        logger.debug(f"Preserving current selection: {current_selection_id}")
                except:
                    pass

            # Use SourceList on macOS desktop (not mobile)
            if USE_SOURCE_LIST and not self.is_mobile:
                self._create_source_list(current_selection_id)
                return

            # Load folder icon once for all collections (use cache)
            if self._folder_icon_cache is None:
                try:
                    import toga
                    folder_icon_path = self.app.paths.app / "resources" / "icons" / "files_folders" / "folder_small_icon.png"
                    if folder_icon_path.exists():
                        self._folder_icon_cache = toga.Image(str(folder_icon_path))
                        logger.info("Loaded collection folder icon (cached)")
                    else:
                        logger.warning(f"Folder icon not found at: {folder_icon_path}")
                except Exception as e:
                    logger.error(f"Failed to load folder icon: {e}", exc_info=True)

            # Create widget only once on first call
            if not hasattr(self, 'collections_list') or not self.collections_list:
                logger.info("Library: Creating ListWidget for first time")

                self.collections_list = ListWidget(
                    headings=['Collections'],
                    data=[],  # Start empty, will set data below
                    on_select=self._on_tree_select,
                    on_activate=self._on_collection_activate,
                    style=Pack(
                        flex=1,
                        margin_left=2  # Small left margin so focus ring is visible
                    ),
                    renderer='sidebar'  # Custom sidebar renderer for narrow Library column
                )

                # Register get_children callback for hierarchical sidebar (Phase 6)
                if hasattr(self.collections_list, 'set_get_children_callback'):
                    self.collections_list.set_get_children_callback(self._get_children_for_item)
                    logger.debug("Registered get_children callback for hierarchical sidebar")

                # Register drag-and-drop callbacks (Phase 6: drag-and-drop support)
                self._register_drag_and_drop_callbacks()

                # Add to container once
                if self.content_container:
                    self.content_container.add(self.collections_list.widget)
                    logger.info("ListWidget created and added to container")
                else:
                    logger.error("content_container is None - cannot add ListWidget!")
            else:
                # Widget already exists and is in container - just update data below
                logger.debug("ListWidget already exists, will update data")

            # Format and update widget data
            # ListWidget.set_data() handles efficient in-place updates
            formatted_data = self._format_collections_for_widget(self.collections)
            self.collections_list.set_data(formatted_data)
            logger.debug(f"Updated ListWidget with {len(formatted_data)} collections")

            # Restore selection if we had one
            if current_selection_id:
                self._restore_selection(formatted_data, current_selection_id)

        except Exception as e:
            logger.error(f"Failed to create/update collections detailed list: {e}")

    def _create_source_list(self, restore_selection_id: str = None):
        """Create or update SourceList (macOS native NSOutlineView sidebar)."""
        try:
            # Lazy import to avoid Rubicon issues at module load
            SourceList, _ = _get_source_list_classes()

            # Create SourceList only once
            if not hasattr(self, '_source_list') or not self._source_list:
                logger.info("Library: Creating SourceList (native macOS sidebar)")

                self._source_list = SourceList(
                    on_select=self._on_source_list_select,
                    on_reorder=self._on_source_list_reorder,
                    on_file_drop=self._on_source_list_file_drop,
                    on_action=self._on_source_list_action,
                )

                # Add native NSScrollView directly to container's native view
                # This is the Pythonic way to integrate native views with Toga
                if self.content_container and hasattr(self.content_container, '_impl'):
                    native_container = self.content_container._impl.native
                    native_scroll = self._source_list.native

                    # Set autoresizing mask for flexible width/height
                    native_scroll.setAutoresizingMask_(18)  # NSViewWidthSizable | NSViewHeightSizable

                    # Add as subview
                    native_container.addSubview_(native_scroll)

                    # Set a marker so we know SourceList is active
                    self.collections_list = self._source_list

                    logger.info("SourceList created and added to container")
                else:
                    logger.error("content_container is None - cannot add SourceList!")

            # Load data from sidebar model
            self.sidebar_model.load_from_library_data(self.collections)
            items = self.sidebar_model.to_source_list_items()
            self._source_list.items = items
            logger.debug(f"Updated SourceList with {len(items)} sections")

            # Restore selection if we had one
            if restore_selection_id:
                self._source_list.select(restore_selection_id)
                logger.debug(f"Restored selection: {restore_selection_id}")

        except Exception as e:
            logger.error(f"Failed to create/update SourceList: {e}", exc_info=True)

    def _on_source_list_select(self, item: "SourceListItem"):
        """Handle selection from SourceList."""
        try:
            if not item or not item.data:
                return

            data = item.data
            item_type = data.get("type")

            # Ignore section headers
            if item_type == "section":
                logger.debug(f"Section header selected: {item.text} - ignoring")
                return

            # Handle folder selection
            if item_type == "folder":
                folder_data = {
                    "id": data.get("folder_id"),
                    "name": data.get("name"),
                    "collection_id": data.get("collection_id"),
                    "metadata": data.get("metadata", {}),
                }
                logger.info(f"Folder selected: {folder_data['name']}")
                self._handle_folder_selection(folder_data)
                return

            # Handle collection selection
            if item_type == "collection":
                collection_id = data.get("id")
                collection_name = data.get("name")
                logger.info(f"Collection selected: {collection_name} (ID: {collection_id})")

                # Store selected collection (for compatibility with existing code)
                self.selected_collection = data

                # Update SelectionManager
                if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
                    metadata = [{
                        'collection_id': collection_id,
                        'collection_name': collection_name,
                        'item_count': data.get('item_count', 0),
                        'type': data.get('collection_type', 'external'),
                    }]
                    self.app.selection_manager.set_selection(
                        view_id='library',
                        item_ids=[collection_id],
                        metadata=metadata
                    )

                # Update inspector
                if hasattr(self.app, 'inspector_window') and self.app.inspector_window:
                    self.app.inspector_window.update_metadata(data, selection_type="COLLECTION")

                # Enable commands
                if hasattr(self, 'commands'):
                    if 'show_inspector' in self.commands:
                        self.commands['show_inspector'].enable()
                    if 'delete_collection' in self.commands:
                        self.commands['delete_collection'].enable()

                # Navigate to collection
                if self.on_collection_selected:
                    self.on_collection_selected(collection_id, collection_name)

        except Exception as e:
            logger.error(f"Error in _on_source_list_select: {e}", exc_info=True)

    def _on_source_list_reorder(self, src_id: str, tgt_id: str, index: int):
        """Handle item reorder from SourceList drag-drop."""
        try:
            logger.info(f"SourceList reorder: {src_id} -> {tgt_id} at index {index}")

            # Find the source item
            src_item = self._source_list.find(src_id)
            if not src_item or not src_item.data:
                return

            src_type = src_item.data.get("type")

            # Only handle collection reordering for now
            if src_type == "collection":
                # Calculate new position (1-based for library manager)
                new_position = index + 1 if index >= 0 else 1

                async def do_reorder():
                    library_manager = self.app.library_manager
                    if library_manager:
                        success = await library_manager.reorder_collection(src_id, new_position)
                        if success:
                            await self.refresh_collections()
                            logger.info("Collection reordered successfully")

                self._create_task(do_reorder())

        except Exception as e:
            logger.error(f"Error in _on_source_list_reorder: {e}", exc_info=True)

    def _on_source_list_file_drop(self, target_id: str, paths: list):
        """Handle file drop from Finder onto SourceList."""
        try:
            logger.info(f"SourceList file drop: {len(paths)} files onto {target_id}")

            # Find target item
            target_item = self._source_list.find(target_id) if target_id else None
            target_type = target_item.data.get("type") if target_item and target_item.data else None

            async def do_import():
                from pathlib import Path
                library_manager = self.app.library_manager
                if not library_manager:
                    return

                for path_str in paths:
                    path = Path(path_str)
                    if not path.exists():
                        continue

                    if target_type == "collection":
                        # Drop onto collection - add files to that collection
                        collection_id = target_item.data.get("id")
                        if path.is_dir():
                            # Import folder contents
                            await library_manager.import_folder_to_collection(
                                collection_id, str(path)
                            )
                        else:
                            # Import single file
                            await library_manager.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="file",
                                source=str(path),
                                name=path.name,
                                operation="link"
                            )
                    else:
                        # Drop onto sidebar (no target) - create new collection
                        if path.is_dir():
                            await library_manager.add_collection(
                                name=path.name,
                                type="external",
                                source_path=str(path)
                            )
                        else:
                            # Create collection for file
                            collection_id = await library_manager.add_collection(
                                name=path.stem,
                                type="local"
                            )
                            if collection_id:
                                await library_manager.add_item_to_collection(
                                    collection_id=collection_id,
                                    item_type="file",
                                    source=str(path),
                                    name=path.name,
                                    operation="link"
                                )

                await self.refresh_collections()

            self._create_task(do_import())

        except Exception as e:
            logger.error(f"Error in _on_source_list_file_drop: {e}", exc_info=True)

    def _on_source_list_action(self, item: "SourceListItem", action: str):
        """Handle context menu action from SourceList."""
        try:
            logger.info(f"SourceList action: {action} on {item.text}")

            if not item.data:
                return

            data = item.data
            item_type = data.get("type")
            item_id = data.get("id") or item.id

            # Build item_data dict in format expected by existing handlers
            item_data = {
                "id": item_id,
                "text": item.text,
                "_node_type": item_type,
                "_collection_data": data if item_type == "collection" else None,
                "_folder_data": data if item_type == "folder" else None,
            }

            # Map SourceList actions to existing handlers
            if action == "rename":
                self._handle_rename_action(item_id, item.text, item_type)
            elif action == "duplicate":
                self._handle_duplicate_action(item_id, item.text, item_type)
            elif action == "reveal":
                self._handle_reveal_in_finder(item_data)
            elif action == "info":
                self._handle_get_info(item_id, item_data)
            elif action == "delete":
                self._handle_delete_action(item_id, item.text, item_type)
            elif action == "new":
                self._handle_new_collection()
            elif action == "expand":
                # Handled by SourceList internally
                pass
            elif action == "collapse":
                # Handled by SourceList internally
                pass
            else:
                logger.warning(f"Unknown SourceList action: {action}")

        except Exception as e:
            logger.error(f"Error in _on_source_list_action: {e}", exc_info=True)

    def _restore_selection(self, collection_data, selection_id):
        """Restore selection after widget recreation"""
        try:
            if not hasattr(self, 'collections_list') or not self.collections_list:
                return

            # Find the row with matching ID and select it
            for i, item in enumerate(collection_data):
                if item.get('_item_id') == selection_id:  # Use _item_id from formatted data
                    # Use ListWidget's select_row method if available
                    if hasattr(self.collections_list, 'select_row'):
                        self.collections_list.select_row(i)
                        logger.debug(f"Restored selection to collection: {selection_id}")
                    break
        except Exception as e:
            logger.debug(f"Could not restore selection: {e}")

    def _format_collections_for_widget(self, collections):
        """Format collection data for ListWidget using hierarchical sidebar model

        Args:
            collections: List of collection dicts from library_service

        Returns:
            List of dicts formatted for ListWidget with 'icon', 'text', 'subtitle', '_item_id', '_collection_data'
            Includes section headers for hierarchical organization
        """
        # DEBUG: Log entry point
        logger.info(f"🔍 FORMAT ENTRY: {len(collections)} collections to format")

        # Load collections into sidebar model
        self.sidebar_model.load_from_library_data(collections)

        # Convert to widget data with section headers
        formatted = self.sidebar_model.to_widget_data(
            folder_icon_cache=self._folder_icon_cache,
            include_section_headers=True
        )

        # DEBUG: Log the formatted data structure
        logger.info(f"🔍 DEBUG: formatted data has {len(formatted)} root items")
        for i, item in enumerate(formatted):
            is_section = item.get('_is_section_header', False)
            has_children = item.get('_has_children', False)
            children_count = len(item.get('_children', []))
            text = item.get('text', 'NO_TEXT')
            node_type = item.get('_node_type', 'NONE')
            logger.info(f"🔍   [{i}] '{text}' node_type={node_type} is_section={is_section} has_children={has_children} children={children_count}")
            if children_count > 0 and children_count <= 3:
                for j, child in enumerate(item.get('_children', [])):
                    child_text = child.get('text', 'NO_TEXT')
                    child_type = child.get('_node_type', 'NONE')
                    logger.info(f"🔍       child[{j}]: '{child_text}' type={child_type}")

        # Rebuild tree data map for fallback lookup in _on_tree_select
        self._tree_data_map = {}
        for item in formatted:
            # Skip section headers
            if item.get('_is_section_header'):
                continue

            collection_data = item.get('_collection_data')
            if collection_data:
                collection_id = collection_data.get('id')
                if collection_id:
                    self._tree_data_map[collection_id] = {
                        'title': collection_data.get('name', 'Unknown'),
                        'collection_data': collection_data
                    }

        logger.debug(f"Formatted {len(formatted)} items (including section headers) for sidebar")
        return formatted


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
        """Handle delete collection swipe action (P1-10: Now includes confirmation)"""
        try:
            if hasattr(row, 'collection_data'):
                collection = row.collection_data
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', 'Unknown Collection')

                logger.info(f"Swipe delete for collection: {collection_name}")
                # Always confirm destructive actions, even on swipe (iOS HIG compliance)
                self._create_task(self._confirm_and_delete_collection(collection_id, collection_name))
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

    def _on_collection_activate(self, widget, row):
        """Handle double-click on collection to rename (desktop only)"""
        try:
            logger.info(f"🖱️ Collection activated (double-click) - row type: {type(row)}")

            # Extract collection data from row
            collection_data = None
            if hasattr(row, '_collection_data'):
                collection_data = row._collection_data
            elif hasattr(row, 'collection_data'):
                collection_data = row.collection_data
            elif isinstance(row, dict):
                collection_data = row.get('_collection_data')

            if collection_data:
                collection_id = collection_data.get('id', '')
                collection_name = collection_data.get('name', 'Unknown Collection')

                logger.info(f"Double-click rename for collection: {collection_name}")

                # Show rename dialog
                self._create_task(self._show_rename_dialog(collection_id, collection_name))
            else:
                logger.warning("No collection data found in activated row")
        except Exception as e:
            logger.error(f"Failed to handle collection activation: {e}", exc_info=True)

    async def _show_rename_dialog(self, collection_id: str, collection_name: str):
        """Show dialog to rename collection - uses navigation-based rename view"""
        try:
            # Use NavigationController to navigate to rename view
            # This provides a consistent UI pattern across desktop and mobile
            if hasattr(self.app, 'view_integration'):
                nav_controller = self.app.view_integration.get_navigation_controller()
                if nav_controller:
                    success = nav_controller.navigate_to_rename_collection(collection_id, collection_name)
                    if success:
                        logger.info(f"Successfully navigated to rename view for: {collection_name}")
                    else:
                        logger.error(f"Failed to navigate to rename view for: {collection_name}")
                        # Show error to user
                        await self.app.main_window.dialog(
                            toga.ErrorDialog(
                                title=_("Navigation Error"),
                                message=_("Could not open rename dialog. Please try again.")
                            )
                        )
                else:
                    logger.error("NavigationController not available")
                    await self.app.main_window.dialog(
                        toga.ErrorDialog(
                            title=_("Error"),
                            message=_("Navigation system not available.")
                        )
                    )
            else:
                logger.error("view_integration not available")
                await self.app.main_window.dialog(
                    toga.ErrorDialog(
                        title=_("Error"),
                        message=_("Navigation system not initialized.")
                    )
                )

        except Exception as e:
            logger.error(f"Failed to show rename dialog: {e}", exc_info=True)
            await self.app.main_window.dialog(
                toga.ErrorDialog(
                    title=_("Rename Error"),
                    message=f"An error occurred: {str(e)}"
                )
            )

    def _on_delete_collection(self, widget, item=None):
        """Handle delete collection command (Cmd+Backspace) - desktop only"""
        try:
            # Get the currently selected collection
            if not self.selected_collection:
                logger.warning("No collection selected for deletion")
                return

            collection_id = self.selected_collection.get('id', '')
            collection_name = self.selected_collection.get('name', 'Unknown Collection')

            logger.info(f"Delete command triggered for collection: {collection_name}")

            # Show confirmation dialog (async)
            import asyncio
            self._create_task(self._confirm_and_delete_collection(collection_id, collection_name))

        except Exception as e:
            logger.error(f"Failed to handle delete collection command: {e}", exc_info=True)

    async def _confirm_and_delete_collection(self, collection_id: str, collection_name: str):
        """Show confirmation dialog and delete collection if confirmed"""
        try:
            # Create QuestionDialog for confirmation
            dialog = toga.QuestionDialog(
                title=_("Delete Collection"),
                message=_("Are you sure you want to delete '{name}'?\n\nThis action cannot be undone.").format(name=collection_name)
            )

            # Show dialog and wait for user response
            if await self.app.main_window.dialog(dialog):
                # User confirmed deletion
                logger.info(f"User confirmed deletion of collection: {collection_name}")

                # Perform the deletion
                await self._perform_delete_collection(collection_id, collection_name)
            else:
                # User cancelled
                logger.info(f"User cancelled deletion of collection: {collection_name}")

        except Exception as e:
            logger.error(f"Failed to confirm and delete collection: {e}", exc_info=True)
            await self.app.main_window.dialog(
                toga.ErrorDialog(
                    title=_("Delete Error"),
                    message=f"An error occurred: {str(e)}"
                )
            )

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

    def _get_children_for_item(self, item_data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """
        Get children for a hierarchical item (Phase 6: Hierarchical sidebar).

        This callback is used by the NSOutlineView renderer to determine if an item
        has children and what those children are.

        Args:
            item_data: Dict with item metadata (includes '_children' key if item has children)

        Returns:
            List of child item dicts, or None if no children
        """
        try:
            # Check if item has pre-loaded children (from sidebar_model)
            children = item_data.get('_children')
            if children is not None:
                return children

            # No children
            return None

        except Exception as e:
            logger.error(f"Error getting children for item: {e}", exc_info=True)
            return None

    def _on_tree_select(self, selection):
        """
        Wrapper for ListWidget selection (Phase 6).

        Converts ListWidget selection format to the format expected by
        _on_collection_selected. Handles section headers by ignoring them.
        """
        try:
            logger.info(f"🌳 ListWidget selection: {selection}")

            if selection is None:
                # No selection - pass through to clear
                class EmptyWidget:
                    selection = None
                self._on_collection_selected(EmptyWidget())
                return

            # Check if this is a section header
            if selection.get('_is_section_header'):
                logger.debug(f"Section header clicked: {selection.get('_section_id')} - ignoring")
                # Don't trigger collection selection for section headers
                return

            # Phase 6: Check if this is a folder selection (hierarchical sidebar)
            # Folders have _node_type='folder' and store their data in _collection_data
            if selection.get('_node_type') == 'folder' or selection.get('_folder_data'):
                # Folder data is in _collection_data (with is_folder=True) or _folder_data
                folder_data = selection.get('_folder_data') or selection.get('_collection_data', {})
                if folder_data.get('is_folder') or selection.get('_node_type') == 'folder':
                    logger.info(f"📂 Folder selected: {folder_data.get('name')} in collection {folder_data.get('collection_id')}")
                    # Navigate to folder view in collection
                    # Pass both collection_id and folder_id to collection view
                    self._handle_folder_selection(folder_data)
                    return

            # ListWidget returns the underlying widget's selection
            # For Tree/Table/DetailedList, this will be the selected item(s)
            # We need to wrap it to match the expected interface

            # Create a wrapper that mimics the DetailedList selection interface
            class SelectionWrapper:
                def __init__(self, item_data, collection_map):
                    # Get the collection_data we stored earlier
                    self.collection_data = item_data.get('_collection_data')
                    if not self.collection_data and '_item_id' in item_data:
                        # Fallback: lookup from map
                        item_id = item_data['_item_id']
                        if item_id in collection_map:
                            self.collection_data = collection_map[item_id].get('collection_data')

            class WidgetWrapper:
                def __init__(self, selection_wrapper):
                    self.selection = selection_wrapper

            # Get the first selected item (for single selection)
            if isinstance(selection, (list, tuple)):
                if len(selection) > 0:
                    selected_item = selection[0]
                else:
                    # Empty list - no selection
                    logger.info("📭 Empty selection list")
                    class EmptyWidget:
                        selection = None
                    self._on_collection_selected(EmptyWidget())
                    return
            else:
                selected_item = selection

            # Check if selected_item is None or falsy
            if selected_item is None:
                logger.info("📭 Selected item is None")
                class EmptyWidget:
                    selection = None
                self._on_collection_selected(EmptyWidget())
                return

            logger.info(f"🔍 Selected item type: {type(selected_item)}, value: {selected_item}")

            # Extract item data from the selection
            # The format depends on the underlying widget type
            item_data = {}

            # Handle Tree Node objects - they have accessor attributes (e.g., node.collections)
            if hasattr(selected_item, '__class__') and 'Node' in selected_item.__class__.__name__:
                # Tree Node object - extract the text from the accessor
                # The accessor is derived from the heading (e.g., 'Collections' -> 'collections')
                accessor = self.collections_list.headings[0].lower() if hasattr(self, 'collections_list') else 'collections'
                collection_name = getattr(selected_item, accessor, None)
                logger.info(f"🌲 Tree Node selected: {collection_name}")

                # Find the matching collection in _tree_data_map by name
                if collection_name:
                    for coll_id, coll_data in self._tree_data_map.items():
                        if coll_data.get('title') == collection_name:
                            item_data = {'_collection_data': coll_data.get('collection_data'), '_item_id': coll_id}
                            logger.info(f"✅ Found collection data for '{collection_name}': {coll_data.get('collection_data')}")
                            break
                    else:
                        logger.warning(f"⚠️ Could not find collection data for '{collection_name}'")

            # Handle Row objects from Table widget - they have accessors like row.text, row.icon
            elif hasattr(selected_item, '__class__') and 'Row' in selected_item.__class__.__name__:
                # Table Row object - extract data from accessors
                logger.info(f"📊 Table Row selected")
                logger.info(f"📊   Row attributes: {dir(selected_item)}")

                # Row objects have accessors - check if it has our custom data fields
                if hasattr(selected_item, '_collection_data'):
                    item_data = {'_collection_data': selected_item._collection_data}
                    logger.info(f"✅ Found _collection_data on Row: {selected_item._collection_data}")
                elif hasattr(selected_item, '_item_id'):
                    # Lookup in map using _item_id
                    item_id = selected_item._item_id
                    if item_id in self._tree_data_map:
                        item_data = {'_collection_data': self._tree_data_map[item_id].get('collection_data'), '_item_id': item_id}
                        logger.info(f"✅ Found collection data via _item_id: {item_id}")
                    else:
                        logger.warning(f"⚠️ Could not find collection for item_id: {item_id}")
                else:
                    # Fallback: try to match by text
                    row_text = getattr(selected_item, 'text', None)
                    if row_text:
                        for coll_id, coll_data in self._tree_data_map.items():
                            if coll_data.get('title') == row_text:
                                item_data = {'_collection_data': coll_data.get('collection_data'), '_item_id': coll_id}
                                logger.info(f"✅ Found collection data by text match: '{row_text}'")
                                break
                        else:
                            logger.warning(f"⚠️ Could not find collection for text: '{row_text}'")

            # Handle dict (DetailedList or native sidebar)
            elif isinstance(selected_item, dict):
                # Dict may already have _collection_data and _item_id from tree_data
                item_data = selected_item
                logger.info(f"📋 Dict selection: {item_data.keys()}")

                # If dict doesn't have _collection_data, try to look it up
                if '_collection_data' not in item_data and 'text' in item_data:
                    # Try to match by text
                    text = item_data.get('text')
                    if text:
                        for coll_id, coll_data in self._tree_data_map.items():
                            if coll_data.get('title') == text:
                                item_data['_collection_data'] = coll_data.get('collection_data')
                                item_data['_item_id'] = coll_id
                                logger.info(f"✅ Found collection data by text match: '{text}'")
                                break
                        else:
                            logger.warning(f"⚠️ Could not find collection for text: '{text}'")

            # Handle objects with _collection_data attribute
            elif hasattr(selected_item, '_collection_data'):
                item_data = {'_collection_data': selected_item._collection_data}
                logger.info(f"📦 Object with _collection_data")

            wrapper = SelectionWrapper(item_data, self._tree_data_map)
            widget_wrapper = WidgetWrapper(wrapper)

            self._on_collection_selected(widget_wrapper)

        except Exception as e:
            logger.error(f"Error in _on_tree_select: {e}", exc_info=True)

    def select_collection(self, collection_id: str) -> bool:
        """
        Programmatically select a collection in the library sidebar by its ID.

        Args:
            collection_id: ID of the collection to select

        Returns:
            True if collection was found and selected, False otherwise
        """
        if not hasattr(self, 'collections_list') or not self.collections_list:
            logger.warning("Cannot select collection - collections_list not initialized")
            return False

        # Use ListWidget's select_item_by_id method
        return self.collections_list.select_item_by_id(collection_id)

    def _handle_folder_selection(self, folder_data: Dict[str, Any]):
        """
        Handle folder selection in hierarchical sidebar (Phase 6).

        When a user clicks on a folder under a collection, navigate to show the
        folder's contents in the collection view. This uses the same navigation
        pattern as collection selection.

        Args:
            folder_data: Dict with folder information including:
                - id: Folder item ID
                - name: Folder name
                - collection_id: Parent collection ID
                - parent_collection_name: Parent collection name
                - metadata: Dict with relative_path, etc.
        """
        try:
            collection_id = folder_data.get('collection_id')
            folder_id = folder_data.get('id')
            folder_name = folder_data.get('name', 'Unknown')
            collection_name = folder_data.get('parent_collection_name', 'Unknown')
            metadata = folder_data.get('metadata', {})
            relative_path = metadata.get('relative_path', folder_name)

            logger.info(f"📂 Folder selected: '{folder_name}' in collection '{collection_name}'")

            # Store folder selection info for potential use by collection view
            self.selected_folder_id = folder_id
            self.selected_folder_path = relative_path

            # Use the registered collection callback to navigate
            # The collection view will load items filtered by the folder path
            if self.on_collection_selected:
                # Pass the collection_id - the collection view will show the folder's contents
                # We pass folder info via app attributes that CollectionView can check
                if hasattr(self.app, 'main_window_wrapper'):
                    # Store folder context for CollectionView to filter by
                    self.app.main_window_wrapper.current_folder_id = folder_id
                    self.app.main_window_wrapper.current_folder_path = relative_path

                logger.info(f"📂 Navigating to collection '{collection_name}' with folder filter: {relative_path}")
                self.on_collection_selected(collection_id, f"{collection_name}/{folder_name}")
            else:
                logger.warning("No collection selection callback registered for folder navigation")

        except Exception as e:
            logger.error(f"Failed to handle folder selection: {e}", exc_info=True)

    def _on_collection_selected(self, widget):
        """Handle collection selection from detailed list"""
        logger.info(f"🎯 _on_collection_selected CALLED! widget={widget}, has selection={hasattr(widget, 'selection')}")

        # Trigger focus ring when collection is selected
        if self.on_click:
            self.on_click()
            logger.debug("🔵 Focus ring triggered for library view")

        try:
            if widget.selection and hasattr(widget.selection, 'collection_data'):
                collection = widget.selection.collection_data

                # Check if this is a section header (collection_data is None)
                if collection is None:
                    logger.info("Section header selected - ignoring selection")
                    return

                # Check if this item is marked as a section header
                if isinstance(collection, dict) and collection.get('_is_section_header'):
                    logger.info("Section header selected (via flag) - ignoring selection")
                    return

                logger.info("✅ Widget has selection with collection_data")
                collection_id = collection.get('id', '')
                collection_name = collection.get('name', '')

                logger.info(f"Collection selected: {collection_name} (ID: {collection_id})")

                # Store selected collection
                self.selected_collection = collection

                # PHASE 3: Update SelectionManager with collection selection
                if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
                    # Build metadata for status bar display
                    item_count = collection.get('item_count', 0)
                    metadata = [{
                        'collection_id': collection_id,
                        'collection_name': collection_name,
                        'item_count': item_count,
                        'type': collection.get('type', 'external'),
                        'source': collection.get('source', ''),
                    }]

                    # Set selection in manager (single collection)
                    self.app.selection_manager.set_selection(
                        view_id='library',
                        item_ids=[collection_id],
                        metadata=metadata
                    )
                    logger.debug(f"SelectionManager updated: library -> {collection_name}")
                else:
                    logger.warning("SelectionManager not available - selection not tracked")

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

                # Enable delete command on desktop when collection is selected
                if hasattr(self, 'commands') and 'delete_collection' in self.commands:
                    self.commands['delete_collection'].enable()
                    logger.debug("✅ Enabled 'Delete Collection' command (collection selected)")

                # Navigate to collection via callback (called only once)
                if self.on_collection_selected:
                    logger.info(f"🔄 Calling navigation callback for {collection_name}")
                    self.on_collection_selected(collection_id, collection_name)
            else:
                # No selection or selection cleared - clear SelectionManager first
                if hasattr(self.app, 'selection_manager') and self.app.selection_manager:
                    self.app.selection_manager.clear_selection('library')
                    logger.debug("SelectionManager cleared: library")

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

                # Disable delete command on desktop when no selection
                if hasattr(self, 'commands') and 'delete_collection' in self.commands:
                    self.commands['delete_collection'].disable()
                    logger.debug("❌ Disabled 'Delete Collection' command (no selection)")

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
                    color=self.text_color,
                    width=150  # Ensure label has minimum width for visibility
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
                    margin=(20, 20, 20, 20),
                    text_align="center",
                    width=150  # Ensure label has minimum width for visibility
                )
            )
            if self.content_container:
                self.content_container.add(empty_message)

            # Add a helper message for creating first collection
            helper_message = toga.Label(
                "Use the + button in the toolbar to create your first collection",
                style=Pack(
                    font_size=12,
                    color="#8E8E93",
                    margin=(10, 20, 20, 20),
                    text_align="center",
                    width=200  # Wider for longer text
                )
            )
            if self.content_container:
                self.content_container.add(helper_message)

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
                # Note: These callbacks are stub methods - they exist but don't implement functionality yet
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
            self._create_task(self._create_external_collection())
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
    
    def _on_search(self, widget=None):
        """Handle search action from NSSearchToolbarItem"""
        try:
            # Get search query from widget
            search_query = None
            if widget and hasattr(widget, 'stringValue'):
                # macOS NSSearchField
                search_query = str(widget.stringValue())
            elif widget and hasattr(widget, 'value'):
                # Toga search field
                search_query = widget.value

            if not search_query or not search_query.strip():
                logger.debug("Empty search query, clearing search")
                # Clear search filter on collection view
                if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                    collection_view = getattr(self.app.main_window_wrapper, 'cached_collection_view', None)
                    if collection_view and hasattr(collection_view, 'clear_search_filter'):
                        collection_view.clear_search_filter()
                return

            logger.info(f"🔍 Search requested: '{search_query}'")

            # Execute search via SearchService
            asyncio.create_task(self._execute_search(search_query))

        except Exception as e:
            logger.error(f"Failed to handle search: {e}")
            import traceback
            traceback.print_exc()

    async def _execute_search(self, query: str):
        """Execute search and filter CollectionView to show matching items"""
        try:
            # Get library manager
            library_manager = getattr(self.app, 'library_manager', None)
            if not library_manager:
                logger.error("No library manager available for search")
                return

            # Get collection view reference
            collection_view = None
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                collection_view = getattr(self.app.main_window_wrapper, 'cached_collection_view', None)

            # Execute search via library manager (which uses SearchService)
            logger.info(f"Executing search: '{query}'")
            search_response = library_manager.search(
                query=query,
                schema_types=["transcription", "catalogue", "translation"],  # Search all text content
                limit=100,  # Show up to 100 results
                include_snippets=True  # Include highlighted snippets
            )

            logger.info(f"Search found {search_response.total_count} results in {search_response.took_ms:.1f}ms")

            if search_response.total_count == 0:
                logger.info("No search results found")
                # Clear any existing filter to show "no results" state
                if collection_view:
                    collection_view.apply_search_filter(query, set())
                return

            # Collect all matching item IDs, grouped by collection
            results_by_collection = {}
            all_matching_ids = set()

            for result in search_response.results:
                if result.item_id:
                    all_matching_ids.add(result.item_id)
                    if result.collection_id not in results_by_collection:
                        results_by_collection[result.collection_id] = set()
                    results_by_collection[result.collection_id].add(result.item_id)

            logger.info(f"Search results: {len(all_matching_ids)} items across {len(results_by_collection)} collections")

            # Apply filter to collection view
            if collection_view:
                current_collection_id = getattr(collection_view, 'collection_id', None)

                if current_collection_id and current_collection_id in results_by_collection:
                    # Filter current collection to show only matching items
                    matching_ids = results_by_collection[current_collection_id]
                    logger.info(f"Filtering current collection ({current_collection_id}) to {len(matching_ids)} matching items")
                    collection_view.apply_search_filter(query, matching_ids)
                elif results_by_collection:
                    # Navigate to first collection with results, then filter
                    first_collection_id = list(results_by_collection.keys())[0]
                    matching_ids = results_by_collection[first_collection_id]

                    # Get collection details
                    collection = await library_manager.get_collection(first_collection_id)
                    collection_name = collection.name if collection else "Unknown Collection"

                    logger.info(f"Navigating to collection '{collection_name}' with {len(matching_ids)} matching items")

                    # Navigate to collection via callback
                    if hasattr(self, 'on_collection_selected') and self.on_collection_selected:
                        # Build collection data dict for the callback
                        collection_data = {
                            'id': first_collection_id,
                            'name': collection_name,
                            'type': collection.type if collection else 'local'
                        }
                        self.on_collection_selected(collection_data)

                        # Apply filter after navigation (small delay to ensure collection loads)
                        await asyncio.sleep(0.1)
                        collection_view.apply_search_filter(query, matching_ids)
                    else:
                        logger.warning("No collection callback registered - cannot navigate to search result")
            else:
                logger.warning("No collection view available - search results not displayed")

        except Exception as e:
            logger.error(f"Failed to execute search: {e}")
            import traceback
            traceback.print_exc()

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
                self._create_task(self._create_local_collection_with_unique_name())
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
            # Prevent deletion of Inbox collection
            if collection_name == "Inbox":
                logger.warning("Cannot delete Inbox collection")
                # Create async task to show error dialog
                self._create_task(self._show_inbox_delete_error())
                return

            # Create async task for dialog handling
            import asyncio
            task = self._create_task(self._handle_delete_confirmation(collection_id, collection_name))
            logger.debug(f"Created delete confirmation task for collection: {collection_name}")
        except Exception as e:
            logger.error(f"Failed to create delete confirmation dialog: {e}")

    async def _show_inbox_delete_error(self):
        """Show error dialog when trying to delete Inbox"""
        try:
            dialog = toga.InfoDialog(
                title=_("Cannot Delete Inbox"),
                message=_("The Inbox collection cannot be deleted. It's a permanent system collection.")
            )
            await self.app.main_window.dialog(dialog)
        except Exception as e:
            logger.error(f"Failed to show inbox delete error: {e}")

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
            import traceback
            caller = traceback.extract_stack()[-2]
            logger.info(f"🔍 TRACE: _perform_delete_collection called from {caller.filename}:{caller.lineno} in {caller.name}()")

            # Delete collection through library manager
            if hasattr(self.app, 'library_manager') and self.app.library_manager:
                logger.info(f"🔍 TRACE: Calling library_manager.delete_collection({collection_id})")
                success = await self.app.library_manager.delete_collection(collection_id)

                if success:
                    logger.info(f"🔍 TRACE: Successfully deleted collection from database: {collection_name}")

                    # Clear the selected collection if it was the deleted one
                    if self.selected_collection and self.selected_collection.get('id') == collection_id:
                        self.selected_collection = None
                        logger.debug("Cleared selected_collection after deletion")

                    # If we're currently viewing this collection, navigate back to library view
                    if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                        current_view = self.app.main_window_wrapper.center_pane
                        # Check if current view is a collection view showing this collection
                        if hasattr(current_view, 'collection_id') and current_view.collection_id == collection_id:
                            logger.info(f"Navigating away from deleted collection view")
                            # Show library view
                            self.app.main_window_wrapper.show_library_view()

                    # Just refresh - widget handles the UI update
                    await self.refresh_collections()
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
            logger.error(f"Failed to perform collection deletion: {e}", exc_info=True)
            error_dialog = toga.ErrorDialog(
                title=_("Delete Error"),
                message=f"Failed to delete collection: {str(e)}"
            )
            await self.app.main_window.dialog(error_dialog)
    
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
    
    async def _add_collection_to_widget(self, collection_id: str):
        """Add a newly created collection to the widget without full refresh

        Args:
            collection_id: ID of the collection to add

        Returns:
            True if successfully added, False if fallback to refresh needed
        """
        try:
            if not self.library_service:
                return False

            # Get the collection data from the backend
            collection_data = await self.library_service.get_collection_for_ui(collection_id)
            if not collection_data:
                logger.warning(f"Could not fetch collection data for {collection_id}")
                return False

            # Just refresh - no need to manually add to collections or widget
            # refresh_collections() will reload from backend and update widget
            logger.info(f"Collection added, refreshing display: {collection_data.get('name')}")
            return True

        except Exception as e:
            logger.error(f"Failed to add collection to widget: {e}")
            return False

    async def refresh_collections(self):
        """Refresh the collections display"""
        try:
            import traceback
            caller = traceback.extract_stack()[-2]
            logger.info(f"🔍 TRACE: refresh_collections() called from {caller.filename}:{caller.lineno} in {caller.name}()")

            # Reload collections from database and wait for completion
            await self._load_collections_async()
            logger.info(f"🔍 TRACE: refresh_collections() completed")

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
                    show_in_top_toolbar=True,  # Show in desktop toolbar
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

                # ===== FILE MENU - DELETE COLLECTION =====
                'delete_collection': FicheroCommand(
                    id=f'{self.view_id}.delete_collection',
                    label=_("Delete Collection"),
                    action=self._on_delete_collection,
                    shortcut=toga.Key.MOD_1 + toga.Key.BACKSPACE,  # Cmd+Backspace (standard Mac delete)
                    icon='resources/icons/toolbar/trash.png',
                    description=_("Delete the selected collection"),
                    group=toga.Group.FILE,  # File menu on desktop
                    section=1,  # Second section (after New commands, before Close)
                    order=0,  # First item in delete section
                    show_in_menu=True,  # Appear in File menu on desktop
                    show_in_toolbar=False,  # NOT in toolbar (dangerous action, menu only)
                    show_in_bottom_toolbar=False,  # Not on mobile (use swipe instead)
                    desktop_only=True,  # Desktop only - mobile uses swipe
                    context='normal',
                    enabled=False  # Disabled by default, enabled when collection selected
                ),

                # NOTE: Import commands (File, Folder, URL, Link File, Link Folder)
                # have been MOVED to Collection View as of STEP 4.
                # They now add items to the current collection instead of creating new collections.
                # The empty 'import' submenu parent has been removed.

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
                    show_in_top_toolbar=True,  # Show in desktop toolbar
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
                    show_in_top_toolbar=True,  # Show in desktop toolbar and mobile top toolbar
                    show_in_bottom_toolbar=False,  # Not in bottom toolbar
                    mobile_only=False,  # Available on both platforms
                    desktop_only=True,  # Desktop only feature
                    context='normal'
                ),

                # ===== SEARCH TOOLBAR =====
                'search': FicheroCommand(
                    id=f'{self.view_id}.search',
                    label=_("Search"),
                    action=self._on_search,  # Provide action for fallback
                    icon='resources/icons/toolbar/magnifyingglass@10x.png',
                    description=_("Search transcriptions and metadata"),
                    show_in_menu=False,  # Not in menus
                    show_in_top_toolbar=True,  # YES - show in toolbar!
                    show_in_bottom_toolbar=False,
                    desktop_only=True,  # Desktop only (search UI)
                    item_type="search",  # NSSearchToolbarItem
                    search_placeholder=_("Search transcriptions…"),
                    search_action=self._on_search,
                    toolbar_icon="magnifyingglass",  # SF Symbol
                    visibility_priority=600,  # High priority - keep visible when window narrows
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
                    show_in_top_toolbar=True,  # Mobile top toolbar
                    show_in_bottom_toolbar=False,  # Not in bottom toolbar
                    mobile_only=True,  # Only on mobile
                    desktop_only=False,
                    context='normal',
                    enabled=False  # Will be enabled when collection is selected
                )
            }

            logger.debug(f"Defined {len(self.commands)} commands for LibraryView")

        except Exception as e:
            logger.error(f"Failed to define LibraryView commands: {e}")
            self.commands = {}

    # ===== DRAG-AND-DROP SUPPORT (Phase 6) =====

    def _register_drag_and_drop_callbacks(self):
        """Register drag-and-drop callbacks with the sidebar renderer"""
        try:
            # Check if the renderer supports drag-and-drop
            if hasattr(self.collections_list, 'renderer'):
                renderer = self.collections_list.renderer
                if hasattr(renderer, 'set_reorder_callback'):
                    renderer.set_reorder_callback(self._on_collection_reorder)
                    logger.info("✅ Registered reorder callback for drag-and-drop")

                if hasattr(renderer, 'set_import_callback'):
                    renderer.set_import_callback(self._on_external_drop)
                    logger.info("✅ Registered import callback for drag-and-drop")

                # Phase 2: Register new target-aware callbacks
                if hasattr(renderer, 'set_import_to_collection_callback'):
                    renderer.set_import_to_collection_callback(self._on_import_to_collection)
                    logger.info("✅ Registered import-to-collection callback for drag-and-drop")

                if hasattr(renderer, 'set_import_to_section_callback'):
                    renderer.set_import_to_section_callback(self._on_import_to_section)
                    logger.info("✅ Registered import-to-section callback for drag-and-drop")

                # Contextual menu callback for right-click actions
                if hasattr(renderer, 'set_context_menu_callback'):
                    renderer.set_context_menu_callback(self._on_context_menu_action)
                    logger.info("✅ Registered context menu callback for right-click actions")

                # Inline rename callback for Finder-like rename
                if hasattr(renderer, 'set_rename_callback'):
                    renderer.set_rename_callback(self._on_inline_rename)
                    logger.info("✅ Registered inline rename callback")
            else:
                logger.debug("Renderer doesn't support drag-and-drop callbacks")

        except Exception as e:
            logger.error(f"Failed to register drag-and-drop callbacks: {e}", exc_info=True)

    def _on_collection_reorder(self, collection_id: str, new_position: int) -> bool:
        """
        Handle collection reordering via drag-and-drop.

        Args:
            collection_id: ID of collection being moved
            new_position: New position (1-based index)

        Returns:
            True if reorder succeeded, False otherwise
        """
        try:
            logger.info(f"Reordering collection {collection_id} to position {new_position}")

            # Get library manager
            library_manager = self.app.library_manager

            if not library_manager:
                logger.error("Library manager not available")
                return False

            # Call the library manager's reorder method
            # This is async, so we need to run it in an async context
            import asyncio

            async def do_reorder():
                success = await library_manager.reorder_collection(collection_id, new_position)
                if success:
                    # Refresh the sidebar to show new order
                    await self.refresh_collections()
                    logger.info("✅ Collection reordered successfully")
                else:
                    logger.error("❌ Failed to reorder collection")
                return success

            # Create task to run the async operation
            task = self._create_task(do_reorder())
            return True  # Optimistic return - actual result will be handled in callback

        except Exception as e:
            logger.error(f"Error in collection reorder: {e}", exc_info=True)
            return False

    def _on_external_drop(self, file_urls: list) -> bool:
        """
        Handle external file/folder drops from Finder.

        Args:
            file_urls: List of file URLs dropped from Finder (can be NSURL objects or strings)

        Returns:
            True if import succeeded, False otherwise
        """
        try:
            logger.info(f"External drop: {len(file_urls) if isinstance(file_urls, list) else 1} items")
            logger.debug(f"Received file_urls type: {type(file_urls)}, value: {file_urls}")

            # Convert URLs to paths and import to library
            import asyncio
            from pathlib import Path
            import urllib.parse

            async def do_import():
                library_manager = self.app.library_manager
                if not library_manager:
                    logger.error("Library manager not available")
                    return False

                # Track the last created collection to select it after import
                last_collection_id = None

                # Ensure file_urls is a list
                urls_to_process = file_urls if isinstance(file_urls, list) else [file_urls]

                # Process each dropped item
                for file_url in urls_to_process:
                    try:
                        # Convert NSURL to path
                        # file_url could be:
                        # 1. An NSURL object with a 'path' property
                        # 2. A string like "file:///path/to/file"
                        # 3. Already a path string

                        if hasattr(file_url, 'path'):
                            # NSURL object - get path directly
                            path_str = str(file_url.path)
                            logger.debug(f"Extracted path from NSURL: {path_str}")
                        elif isinstance(file_url, str):
                            # String URL - parse it
                            if file_url.startswith("file://"):
                                # URL-decode the path
                                path_str = urllib.parse.unquote(file_url.replace("file://", ""))
                                logger.debug(f"Parsed file:// URL: {path_str}")
                            else:
                                # Already a path
                                path_str = file_url
                                logger.debug(f"Using string as path: {path_str}")
                        else:
                            logger.warning(f"Unknown file_url type: {type(file_url)}, attempting str conversion")
                            path_str = str(file_url)

                        # Create Path object
                        path = Path(path_str)

                        if not path.exists():
                            logger.error(f"Path does not exist: {path_str}")
                            continue

                        if path.is_dir():
                            # Import folder as external collection
                            logger.info(f"Importing folder: {path.name}")
                            new_collection_id = await library_manager.add_collection(
                                name=path.name,
                                type="external",
                                source_path=str(path)
                            )
                            if new_collection_id:
                                logger.info(f"✅ Imported folder as collection: {path.name}")
                                last_collection_id = new_collection_id
                            else:
                                logger.error(f"❌ Failed to import folder: {path.name}")

                        elif path.is_file():
                            # Create a new collection for the file
                            logger.info(f"Importing file: {path.name}")
                            # Create a collection named after the file (without extension)
                            collection_name = path.stem
                            new_collection_id = await library_manager.add_collection(
                                name=collection_name,
                                type="local",
                                source_path=None
                            )
                            if new_collection_id:
                                # Check if this is a PDF - extract pages as images
                                if path.suffix.lower() == '.pdf':
                                    try:
                                        import pymupdf
                                        import tempfile

                                        logger.info(f"📄 Extracting pages from PDF: {path.name}")
                                        doc = pymupdf.open(str(path))

                                        # Extract PDF metadata for the collection
                                        pdf_metadata = doc.metadata or {}
                                        collection_metadata = {
                                            "source_file": str(path),
                                            "source_type": "pdf",
                                            "pdf_title": pdf_metadata.get("title", ""),
                                            "pdf_author": pdf_metadata.get("author", ""),
                                            "pdf_subject": pdf_metadata.get("subject", ""),
                                            "pdf_keywords": pdf_metadata.get("keywords", ""),
                                            "pdf_creator": pdf_metadata.get("creator", ""),
                                            "pdf_producer": pdf_metadata.get("producer", ""),
                                            "pdf_page_count": len(doc),
                                        }
                                        # Update collection with PDF metadata
                                        collection = await library_manager.get_collection(new_collection_id)
                                        if collection:
                                            # Merge with existing metadata
                                            existing_metadata = collection.metadata or {}
                                            existing_metadata.update(collection_metadata)
                                            await library_manager.update_collection(
                                                new_collection_id, metadata=existing_metadata
                                            )

                                        # Get or create collection storage path for extracted images
                                        collection = await library_manager.get_collection(new_collection_id)
                                        if collection and collection.local_path:
                                            base_dir = Path(collection.local_path)
                                        else:
                                            # Create workspace directory in library for this collection
                                            base_dir = library_manager.library_path / "collections" / new_collection_id
                                            # Update collection with local_path
                                            if collection:
                                                await library_manager.update_collection(
                                                    new_collection_id, local_path=str(base_dir)
                                                )

                                        # Create subfolder for PDF pages using PDF name
                                        output_dir = base_dir / path.stem
                                        output_dir.mkdir(parents=True, exist_ok=True)
                                        logger.info(f"📁 PDF pages will be saved to: {output_dir}")

                                        # Import ExtractedMetadata for storing transcription
                                        from fichero.library.models import ExtractedMetadata

                                        # Create a folder item for the PDF (parent for all pages)
                                        pdf_metadata = doc.metadata or {}
                                        folder_metadata = {
                                            "source_type": "pdf",
                                            "source_file": str(path),
                                            "pdf_title": pdf_metadata.get("title", ""),
                                            "pdf_author": pdf_metadata.get("author", ""),
                                            "pdf_page_count": len(doc),
                                        }
                                        folder_id = await library_manager.add_item_to_collection(
                                            collection_id=new_collection_id,
                                            item_type="folder",
                                            source=str(output_dir),
                                            name=path.stem,
                                            operation="link",
                                            metadata=folder_metadata
                                        )
                                        logger.info(f"📁 Created folder item for PDF: {path.stem} (id: {folder_id})")

                                        total_pages = len(doc)
                                        for i, page in enumerate(doc):
                                            # Extract page image
                                            pix = page.get_pixmap(dpi=150)
                                            img = pix.pil_image()
                                            page_filename = f"{path.stem}_{i:03d}.jpg"
                                            page_path = output_dir / page_filename
                                            img.save(str(page_path))

                                            # Extract text from page
                                            page_text = page.get_text()

                                            # Build page metadata
                                            page_metadata = {
                                                "page_number": i + 1,
                                                "total_pages": total_pages,
                                                "source_pdf": path.name,
                                                "width": page.rect.width,
                                                "height": page.rect.height,
                                            }
                                            # Add text if present
                                            if page_text and page_text.strip():
                                                page_metadata["has_text"] = True
                                            else:
                                                page_metadata["has_text"] = False

                                            # Add each page as an item with folder as parent
                                            item_id = await library_manager.add_item_to_collection(
                                                collection_id=new_collection_id,
                                                item_type="file",
                                                source=str(page_path),
                                                name=page_filename,
                                                operation="link",  # Already in library storage
                                                metadata=page_metadata,
                                                parent_id=folder_id  # Set folder as parent
                                            )

                                            # Store extracted text as transcription metadata
                                            if page_text and page_text.strip() and item_id:
                                                transcription_meta = ExtractedMetadata(
                                                    collection_id=new_collection_id,
                                                    item_id=item_id,
                                                    schema_type="transcription",
                                                    source_label="pdf_extract",
                                                    key="text",
                                                    value=page_text.strip(),
                                                    model_name="pymupdf",
                                                    provider_name="pymupdf",
                                                )
                                                library_manager.storage.add_extracted_metadata(transcription_meta)
                                                logger.debug(f"📝 Stored transcription for page {i + 1}")

                                        doc.close()
                                        logger.info(f"✅ Extracted {i + 1} pages from PDF: {collection_name}")
                                        last_collection_id = new_collection_id

                                    except ImportError as ie:
                                        import traceback
                                        logger.warning(f"pymupdf import failed: {ie}")
                                        logger.warning(traceback.format_exc())
                                        # Fall back to importing as single file
                                        await library_manager.add_item_to_collection(
                                            collection_id=new_collection_id,
                                            item_type="file",
                                            source=str(path),
                                            name=path.name,
                                            operation="copy"
                                        )
                                        last_collection_id = new_collection_id
                                    except Exception as pdf_error:
                                        import traceback
                                        logger.error(f"Failed to extract PDF pages: {pdf_error}")
                                        logger.error(traceback.format_exc())
                                        # Fall back to importing as single file
                                        await library_manager.add_item_to_collection(
                                            collection_id=new_collection_id,
                                            item_type="file",
                                            source=str(path),
                                            name=path.name,
                                            operation="copy"
                                        )
                                        last_collection_id = new_collection_id
                                else:
                                    # Non-PDF file - add normally
                                    await library_manager.add_item_to_collection(
                                        collection_id=new_collection_id,
                                        item_type="file",
                                        source=str(path),
                                        name=path.name,
                                        operation="copy"  # Copy the file to library
                                    )
                                    logger.info(f"✅ Imported file as collection: {collection_name}")
                                    last_collection_id = new_collection_id
                            else:
                                logger.error(f"❌ Failed to import file: {path.name}")

                    except Exception as item_error:
                        logger.error(f"Failed to process dropped item: {item_error}", exc_info=True)
                        continue

                # Refresh sidebar
                await self.refresh_collections()

                # Select the last created collection to show its contents
                if last_collection_id:
                    self.select_collection(last_collection_id)

                return True

            # Create task to run the async operation
            task = self._create_task(do_import())
            return True  # Optimistic return

        except Exception as e:
            logger.error(f"Error in external drop: {e}", exc_info=True)
            return False

    def _on_import_to_collection(self, file_urls: list, collection_id: str) -> bool:
        """
        Handle importing files/folders to a specific collection.

        Args:
            file_urls: List of file URLs dropped from Finder
            collection_id: ID of the collection to import into

        Returns:
            True if import succeeded, False otherwise
        """
        try:
            logger.info(f"Import to collection: {len(file_urls)} items to collection {collection_id}")

            import asyncio
            from pathlib import Path
            import urllib.parse

            async def do_import():
                library_manager = self.app.library_manager
                if not library_manager:
                    logger.error("No library manager available")
                    return False

                for file_url in file_urls:
                    try:
                        # Convert NSURL or string to path
                        if hasattr(file_url, 'path'):
                            path_str = str(file_url.path)
                        elif hasattr(file_url, 'absoluteString'):
                            url_str = str(file_url.absoluteString)
                            if url_str.startswith('file://'):
                                path_str = urllib.parse.unquote(url_str[7:])
                            else:
                                path_str = url_str
                        elif isinstance(file_url, str):
                            if file_url.startswith('file://'):
                                path_str = urllib.parse.unquote(file_url[7:])
                            else:
                                path_str = file_url
                        else:
                            path_str = str(file_url)

                        path = Path(path_str)
                        if not path.exists():
                            logger.error(f"Path does not exist: {path_str}")
                            continue

                        if path.is_dir():
                            # Add folder to collection
                            logger.info(f"Adding folder to collection {collection_id}: {path.name}")
                            await library_manager.add_item_to_collection(
                                collection_id=collection_id,
                                item_type="folder",
                                source=str(path),
                                name=path.name,
                                operation="link"  # Link external folders
                            )
                            logger.info(f"✅ Added folder: {path.name}")

                        elif path.is_file():
                            # Check if this is a PDF - extract pages as images
                            if path.suffix.lower() == '.pdf':
                                try:
                                    import pymupdf
                                    import tempfile

                                    logger.info(f"📄 Extracting pages from PDF: {path.name}")
                                    doc = pymupdf.open(str(path))

                                    # Get or create collection storage path for extracted images
                                    collection = await library_manager.get_collection(collection_id)
                                    if collection and collection.local_path:
                                        base_dir = Path(collection.local_path)
                                    else:
                                        # Create workspace directory in library for this collection
                                        base_dir = library_manager.library_path / "collections" / collection_id
                                        # Update collection with local_path
                                        if collection:
                                            await library_manager.update_collection(
                                                collection_id, local_path=str(base_dir)
                                            )

                                    # Create subfolder for PDF pages using PDF name
                                    output_dir = base_dir / path.stem
                                    output_dir.mkdir(parents=True, exist_ok=True)
                                    logger.info(f"📁 PDF pages will be saved to: {output_dir}")

                                    # Import ExtractedMetadata for storing transcription
                                    from fichero.library.models import ExtractedMetadata

                                    # Create a folder item for the PDF (parent for all pages)
                                    pdf_metadata = doc.metadata or {}
                                    folder_metadata = {
                                        "source_type": "pdf",
                                        "source_file": str(path),
                                        "pdf_title": pdf_metadata.get("title", ""),
                                        "pdf_author": pdf_metadata.get("author", ""),
                                        "pdf_page_count": len(doc),
                                    }
                                    folder_id = await library_manager.add_item_to_collection(
                                        collection_id=collection_id,
                                        item_type="folder",
                                        source=str(output_dir),
                                        name=path.stem,
                                        operation="link",
                                        metadata=folder_metadata
                                    )
                                    logger.info(f"📁 Created folder item for PDF: {path.stem} (id: {folder_id})")

                                    page_count = 0
                                    total_pages = len(doc)
                                    for i, page in enumerate(doc):
                                        # Extract page image
                                        pix = page.get_pixmap(dpi=150)
                                        img = pix.pil_image()
                                        page_filename = f"{path.stem}_{i:03d}.jpg"
                                        page_path = output_dir / page_filename
                                        img.save(str(page_path))

                                        # Extract text from page
                                        page_text = page.get_text()

                                        # Build page metadata
                                        page_metadata = {
                                            "page_number": i + 1,
                                            "total_pages": total_pages,
                                            "source_pdf": path.name,
                                            "width": page.rect.width,
                                            "height": page.rect.height,
                                        }
                                        # Add text if present
                                        if page_text and page_text.strip():
                                            page_metadata["has_text"] = True
                                        else:
                                            page_metadata["has_text"] = False

                                        # Add each page as an item with folder as parent
                                        item_id = await library_manager.add_item_to_collection(
                                            collection_id=collection_id,
                                            item_type="file",
                                            source=str(page_path),
                                            name=page_filename,
                                            operation="link",  # Already in library storage
                                            metadata=page_metadata,
                                            parent_id=folder_id  # Set folder as parent
                                        )

                                        # Store extracted text as transcription metadata
                                        if page_text and page_text.strip() and item_id:
                                            transcription_meta = ExtractedMetadata(
                                                collection_id=collection_id,
                                                item_id=item_id,
                                                schema_type="transcription",
                                                source_label="pdf_extract",
                                                key="text",
                                                value=page_text.strip(),
                                                model_name="pymupdf",
                                                provider_name="pymupdf",
                                            )
                                            library_manager.storage.add_extracted_metadata(transcription_meta)
                                            logger.debug(f"📝 Stored transcription for page {i + 1}")

                                        page_count += 1

                                    doc.close()
                                    logger.info(f"✅ Extracted {page_count} pages from PDF: {path.name}")

                                except ImportError as ie:
                                    import traceback
                                    logger.warning(f"pymupdf import failed: {ie}")
                                    logger.warning(traceback.format_exc())
                                    await library_manager.add_item_to_collection(
                                        collection_id=collection_id,
                                        item_type="file",
                                        source=str(path),
                                        name=path.name,
                                        operation="copy"
                                    )
                                except Exception as pdf_error:
                                    import traceback
                                    logger.error(f"Failed to extract PDF pages: {pdf_error}")
                                    logger.error(traceback.format_exc())
                                    await library_manager.add_item_to_collection(
                                        collection_id=collection_id,
                                        item_type="file",
                                        source=str(path),
                                        name=path.name,
                                        operation="copy"
                                    )
                            else:
                                # Non-PDF file - add normally
                                logger.info(f"Adding file to collection {collection_id}: {path.name}")
                                await library_manager.add_item_to_collection(
                                    collection_id=collection_id,
                                    item_type="file",
                                    source=str(path),
                                    name=path.name,
                                    operation="copy"  # Copy files into library
                                )
                                logger.info(f"✅ Added file: {path.name}")

                    except Exception as item_error:
                        logger.error(f"Failed to import item: {item_error}", exc_info=True)
                        continue

                # Refresh sidebar to show updated counts
                await self.refresh_collections()

                # Select the collection to show imported items
                self.select_collection(collection_id)

                return True

            # Create task to run the async operation
            self._create_task(do_import())
            return True  # Optimistic return

        except Exception as e:
            logger.error(f"Error in import to collection: {e}", exc_info=True)
            return False

    def _on_import_to_section(self, file_urls: list, section_id: str) -> bool:
        """
        Handle importing files/folders to a section (creates new collection).

        Args:
            file_urls: List of file URLs dropped from Finder
            section_id: ID of the section ('favorites', 'local', 'external', 'urls')

        Returns:
            True if import succeeded, False otherwise
        """
        try:
            logger.info(f"Import to section: {len(file_urls)} items to section '{section_id}'")

            import asyncio
            from pathlib import Path
            import urllib.parse

            # Map section_id to collection type
            section_to_type = {
                'favorites': 'local',  # Favorites section uses local collections
                'local': 'local',
                'external': 'external',
                'urls': 'url',
            }
            collection_type = section_to_type.get(section_id, 'local')

            async def do_import():
                library_manager = self.app.library_manager
                if not library_manager:
                    logger.error("No library manager available")
                    return False

                for file_url in file_urls:
                    try:
                        # Convert NSURL or string to path
                        if hasattr(file_url, 'path'):
                            path_str = str(file_url.path)
                        elif hasattr(file_url, 'absoluteString'):
                            url_str = str(file_url.absoluteString)
                            if url_str.startswith('file://'):
                                path_str = urllib.parse.unquote(url_str[7:])
                            else:
                                path_str = url_str
                        elif isinstance(file_url, str):
                            if file_url.startswith('file://'):
                                path_str = urllib.parse.unquote(file_url[7:])
                            else:
                                path_str = file_url
                        else:
                            path_str = str(file_url)

                        path = Path(path_str)
                        if not path.exists():
                            logger.error(f"Path does not exist: {path_str}")
                            continue

                        if path.is_dir():
                            # Create new external collection for folder
                            logger.info(f"Creating collection for folder: {path.name}")
                            collection_id = await library_manager.add_collection(
                                name=path.name,
                                type='external',  # Folders are always external
                                source_path=str(path)
                            )
                            if collection_id:
                                logger.info(f"✅ Created external collection: {path.name}")
                            else:
                                logger.error(f"❌ Failed to create collection: {path.name}")

                        elif path.is_file():
                            # Create new local collection for file
                            collection_name = path.stem
                            logger.info(f"Creating collection for file: {collection_name}")
                            collection_id = await library_manager.add_collection(
                                name=collection_name,
                                type=collection_type,
                                source_path=None
                            )
                            if collection_id:
                                # Add the file to the new collection
                                await library_manager.add_item_to_collection(
                                    collection_id=collection_id,
                                    item_type="file",
                                    source=str(path),
                                    name=path.name,
                                    operation="copy"
                                )
                                logger.info(f"✅ Created collection with file: {collection_name}")
                            else:
                                logger.error(f"❌ Failed to create collection: {collection_name}")

                    except Exception as item_error:
                        logger.error(f"Failed to import item: {item_error}", exc_info=True)
                        continue

                # Refresh sidebar to show new collections
                await self.refresh_collections()
                return True

            # Create task to run the async operation
            self._create_task(do_import())
            return True  # Optimistic return

        except Exception as e:
            logger.error(f"Error in import to section: {e}", exc_info=True)
            return False

    def _on_inline_rename(self, item_id: str, new_name: str) -> bool:
        """
        Handle inline rename completion from sidebar.

        Called when user finishes inline editing (Enter, Tab, or click away).
        Updates the collection name in the database and refreshes the sidebar.

        Args:
            item_id: The collection ID being renamed
            new_name: The new name entered by the user

        Returns:
            True if rename succeeded, False otherwise
        """
        try:
            if not new_name or not item_id:
                logger.warning("Invalid rename: empty name or ID")
                return False

            logger.info(f"Inline rename: '{item_id}' -> '{new_name}'")

            library_manager = self.app.library_manager
            if not library_manager:
                logger.error("No library manager available for rename")
                return False

            # Create async task to update database (update_collection is async)
            async def do_rename():
                success = await library_manager.update_collection(item_id, name=new_name)
                if success:
                    # Refresh sidebar to show new name
                    await self.refresh_collections()
                    logger.info(f"Renamed collection to: {new_name}")
                else:
                    logger.error(f"Failed to update collection name in database")
                return success

            self._create_task(do_rename())
            return True  # Optimistic return - actual result handled in async task

        except Exception as e:
            logger.error(f"Error in inline rename: {e}", exc_info=True)
            return False

    def _on_context_menu_action(self, action: str, item_data: dict) -> None:
        """
        Handle context menu actions from sidebar right-click.

        Args:
            action: The action identifier (e.g., 'rename', 'delete', 'reveal_in_finder')
            item_data: The item data dict that was right-clicked
        """
        try:
            logger.info(f"Context menu action: '{action}' on item: {item_data.get('text', 'unknown')}")

            # Get item identifier - check multiple possible keys
            item_id = item_data.get('_item_id') or item_data.get('id') or item_data.get('_id')
            # Also check _collection_data for the ID
            if not item_id and item_data.get('_collection_data'):
                item_id = item_data['_collection_data'].get('id')
            item_text = item_data.get('text', 'Unknown')
            item_type = item_data.get('_node_type', 'unknown')

            if action == 'rename':
                self._handle_rename_action(item_id, item_text, item_type)

            elif action == 'duplicate':
                self._handle_duplicate_action(item_id, item_text, item_type)

            elif action == 'reveal_in_finder':
                self._handle_reveal_in_finder(item_data)

            elif action == 'get_info':
                self._handle_get_info(item_id, item_data)

            elif action == 'export':
                self._handle_export_action(item_id, item_text, item_type)

            elif action == 'delete':
                self._handle_delete_action(item_id, item_text, item_type)

            elif action == 'new_collection':
                self._handle_new_collection()

            elif action == 'expand_all':
                self._handle_expand_all()

            elif action == 'collapse_all':
                self._handle_collapse_all()

            else:
                logger.warning(f"Unknown context menu action: {action}")

        except Exception as e:
            logger.error(f"Error handling context menu action '{action}': {e}", exc_info=True)

    def _handle_rename_action(self, item_id: str, item_text: str, item_type: str):
        """Handle rename context menu action"""
        logger.info(f"Rename requested for {item_type} '{item_text}' (id: {item_id})")

        # Only allow renaming collections (not section headers)
        if item_type == 'section':
            logger.warning("Cannot rename section headers")
            return

        # Start inline editing in the sidebar (like Finder rename)
        # This triggers the NSOutlineView inline edit mode
        if hasattr(self.collections_list, 'renderer'):
            renderer = self.collections_list.renderer
            if hasattr(renderer, 'start_inline_edit'):
                # Find the row for this item and start editing
                renderer.start_inline_edit(item_id)
                return

        # Fallback: show rename dialog if inline edit not available
        self._create_task(self._show_rename_dialog_context_menu(item_id, item_text))

    async def _show_rename_dialog_context_menu(self, item_id: str, current_name: str):
        """Show rename dialog for collection from context menu (fallback).

        Uses a simple text input dialog when inline editing is not available.
        """
        try:
            import toga

            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show text input dialog
            new_name = await window.dialog(
                toga.TextInputDialog(
                    title=_("Rename Collection"),
                    message=_("Enter new name:"),
                    initial_value=current_name
                )
            )

            if new_name and new_name != current_name:
                # Update the collection name
                library_manager = self.app.library_manager
                if library_manager:
                    success = await library_manager.update_collection(item_id, name=new_name)
                    if success:
                        logger.info(f"Collection renamed to: {new_name}")
                        await self.refresh_collections()
                    else:
                        logger.error(f"Failed to rename collection")
                        self._show_message(_("Error"), _("Failed to rename collection"))
                else:
                    logger.error("Library manager not available")
            else:
                logger.info("Rename cancelled or unchanged")
        except Exception as e:
            logger.error(f"Error showing rename dialog: {e}", exc_info=True)

    def _handle_duplicate_action(self, item_id: str, item_text: str, item_type: str):
        """Handle duplicate context menu action"""
        logger.info(f"Duplicate requested for {item_type} '{item_text}' (id: {item_id})")

        # Only allow duplicating collections (not section headers)
        if item_type == 'section':
            logger.warning("Cannot duplicate section headers")
            return

        self._create_task(self._duplicate_collection(item_id, item_text))

    async def _duplicate_collection(self, item_id: str, collection_name: str):
        """Duplicate a collection"""
        try:
            library_manager = self.app.library_manager
            if not library_manager:
                logger.error("Library manager not available")
                return

            logger.info(f"Duplicating collection '{collection_name}'")

            # Get original collection
            original = await library_manager.get_collection(item_id)
            if not original:
                logger.error(f"Could not find collection to duplicate: {item_id}")
                self._show_message(_("Error"), _("Collection not found"))
                return

            # Create new collection with copy suffix
            new_name = f"{original.name} copy"
            new_collection_id = await library_manager.add_collection(
                name=new_name,
                collection_type=original.type,
                source_path=original.source_path,
                description=original.metadata.get('description', '')
            )

            if new_collection_id:
                logger.info(f"Collection duplicated successfully: {new_collection_id}")
                await self.refresh_collections()
                # Select the new collection
                self.select_collection(new_collection_id)
            else:
                logger.error(f"Failed to duplicate collection")
                self._show_message(_("Error"), _("Failed to duplicate collection"))
        except Exception as e:
            logger.error(f"Error duplicating collection: {e}", exc_info=True)

    def _handle_reveal_in_finder(self, item_data: dict):
        """Handle reveal in Finder context menu action"""
        import subprocess
        from pathlib import Path

        # Try to get the path from item data
        source_path = item_data.get('source_path') or item_data.get('path')

        # If no source_path in item_data, try to get from collection data
        if not source_path:
            collection_data = item_data.get('_collection_data', {})
            source_path = collection_data.get('source_path')

        # If still no path, try to fetch from library
        if not source_path:
            item_id = item_data.get('id') or item_data.get('_id')
            if item_id:
                self._create_task(self._reveal_collection_in_finder(item_id))
                return

        if source_path:
            path = Path(source_path)
            if path.exists():
                logger.info(f"Revealing in Finder: {path}")
                subprocess.run(['open', '-R', str(path)])
            else:
                logger.warning(f"Path does not exist: {path}")
                self._show_message(_("Not Found"), _("The file or folder no longer exists."))
        else:
            logger.warning("No path available for reveal in Finder")
            self._show_message(_("No Path"), _("This collection doesn't have an associated file path."))

    async def _reveal_collection_in_finder(self, collection_id: str):
        """Reveal collection in Finder by fetching its source_path"""
        import subprocess
        from pathlib import Path

        try:
            library_manager = self.app.library_manager
            if not library_manager:
                logger.error("Library manager not available")
                return

            collection = await library_manager.get_collection(collection_id)
            if collection and collection.source_path:
                path = Path(collection.source_path)
                if path.exists():
                    logger.info(f"Revealing in Finder: {path}")
                    subprocess.run(['open', '-R', str(path)])
                else:
                    logger.warning(f"Path does not exist: {path}")
                    self._show_message(_("Not Found"), _("The file or folder no longer exists."))
            else:
                logger.warning(f"Collection {collection_id} has no source_path")
                self._show_message(_("No Path"), _("This collection doesn't have an associated file path."))
        except Exception as e:
            logger.error(f"Error revealing in Finder: {e}", exc_info=True)

    def _handle_export_action(self, item_id: str, item_text: str, item_type: str):
        """Handle export collection context menu action"""
        logger.info(f"Export requested for {item_type} '{item_text}' (id: {item_id})")

        # Only allow exporting collections (not section headers)
        if item_type == 'section':
            logger.warning("Cannot export section headers")
            return

        self._create_task(self._show_export_dialog(item_id, item_text))

    async def _show_export_dialog(self, item_id: str, collection_name: str):
        """Show export dialog for collection"""
        try:
            import toga
            from pathlib import Path

            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show save file dialog
            output_path = await window.dialog(
                toga.SaveFileDialog(
                    title=_("Export Collection"),
                    suggested_filename=f"{collection_name}.json",
                    file_types=["json"]
                )
            )

            if output_path:
                logger.info(f"Exporting collection '{collection_name}' to {output_path}")

                # Ask if files should be included
                include_files = await window.dialog(
                    toga.QuestionDialog(
                        title=_("Include Files"),
                        message=_("Include collection files in export?\n\n(This will copy all files to the export location)")
                    )
                )

                # Export via library service
                if self.library_service:
                    success = await self.library_service.export_collection(
                        item_id,
                        Path(output_path),
                        include_files=include_files
                    )
                    if success:
                        logger.info(f"Collection exported successfully to {output_path}")
                        self._show_message(
                            _("Export Complete"),
                            _("Collection exported successfully.")
                        )
                    else:
                        logger.error(f"Failed to export collection")
                        self._show_message(_("Error"), _("Failed to export collection"))
                else:
                    logger.error("Library service not available")
            else:
                logger.info("Export cancelled by user")
        except Exception as e:
            logger.error(f"Error showing export dialog: {e}", exc_info=True)

    def _handle_get_info(self, item_id: str, item_data: dict):
        """Handle get info context menu action - shows inspector panel"""
        logger.info(f"Get Info requested for item: {item_data.get('text', 'unknown')}")

        # First select the collection to update internal state
        collection_id = item_data.get('_item_id') or item_id
        if collection_id:
            # Update selection to ensure inspector shows this collection
            if hasattr(self, 'selection_manager') and self.selection_manager:
                self.selection_manager.select_collection(collection_id)

        # Show the inspector via the existing method
        self._on_show_inspector()

    def _handle_delete_action(self, item_id: str, item_text: str, item_type: str):
        """Handle delete context menu action"""
        logger.info(f"Delete requested for {item_type} '{item_text}' (id: {item_id})")

        # Only allow deleting collections (not section headers)
        if item_type == 'section':
            logger.warning("Cannot delete section headers")
            return

        # Show confirmation dialog
        self._create_task(self._show_delete_confirmation(item_id, item_text))

    async def _show_delete_confirmation(self, item_id: str, collection_name: str):
        """Show delete confirmation dialog"""
        try:
            import toga

            # Get main window
            if not hasattr(self.app, 'main_window_wrapper') or not self.app.main_window_wrapper:
                logger.error("No main window available")
                return

            window = self.app.main_window_wrapper.window

            # Show confirmation dialog
            confirmed = await window.dialog(
                toga.QuestionDialog(
                    title=_("Delete Collection"),
                    message=_(f"Are you sure you want to delete '{collection_name}'?\n\nThis action cannot be undone.")
                )
            )

            if confirmed:
                logger.info(f"Deleting collection '{collection_name}'")

                # Delete via library manager (library_service.delete_collection doesn't exist)
                library_manager = self.app.library_manager
                if library_manager:
                    success = await library_manager.delete_collection(item_id)
                    if success:
                        logger.info(f"Collection deleted successfully")
                        await self.refresh_collections()
                    else:
                        logger.error(f"Failed to delete collection")
                        self._show_message(_("Error"), _("Failed to delete collection"))
                else:
                    logger.error("Library manager not available")
            else:
                logger.info("Delete cancelled by user")
        except Exception as e:
            logger.error(f"Error showing delete confirmation: {e}", exc_info=True)

    def _handle_new_collection(self):
        """Handle new collection context menu action"""
        logger.info("New collection requested from context menu")
        # Trigger the existing new collection command if available
        if hasattr(self, 'commands') and 'library.new_collection' in self.commands:
            command = self.commands['library.new_collection']
            if hasattr(command, 'action') and command.action:
                command.action(None)
        else:
            logger.warning("New collection command not available")

    def _handle_expand_all(self):
        """Handle expand all context menu action"""
        logger.info("Expand all requested from context menu")
        if hasattr(self.collections_list, 'renderer'):
            renderer = self.collections_list.renderer
            if hasattr(renderer, 'expand_all'):
                renderer.expand_all()

    def _handle_collapse_all(self):
        """Handle collapse all context menu action"""
        logger.info("Collapse all requested from context menu")
        if hasattr(self.collections_list, 'renderer'):
            renderer = self.collections_list.renderer
            if hasattr(renderer, 'collapse_all'):
                renderer.collapse_all()

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
            # Create async task to refresh collections
            self._create_task(self.refresh_collections())
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
        """Load collections asynchronously and update UI safely on main thread"""
        try:
            import traceback
            caller = traceback.extract_stack()[-2]
            logger.info(f"🔍 TRACE: _load_collections_async() called from {caller.filename}:{caller.lineno} in {caller.name}()")

            if self.library_service:
                # Note: Inbox creation is handled by LibraryManager.get_or_create_inbox()
                # via get_all_collections() which calls it automatically on first load

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

                # Load folders for hierarchical sidebar (Phase 6)
                # Note: sidebar_model.load_from_library_data() is called in _format_collections_for_widget()
                # Here we just preload the folder data for each collection
                for collection in self.collections:
                    collection_id = collection.get('id')
                    collection_name = collection.get('name', 'Unknown')
                    if collection_id:
                        try:
                            # Load folders into sidebar model cache
                            # This will be available when _format_collections_for_widget() builds the widget data
                            folder_count = await self.sidebar_model.load_collection_folders(
                                collection_id,
                                collection_name,
                                self.library_service.library_manager
                            )
                            if folder_count > 0:
                                logger.debug(f"Loaded {folder_count} folders for collection '{collection_name}'")
                        except Exception as e:
                            logger.error(f"Failed to load folders for collection {collection_name}: {e}")

                # Call UI update directly (we're already async, Toga handles main thread)
                self._create_content()
            else:
                logger.warning("Library service not initialized, cannot load collections.")
                self.collections = []

        except Exception as e:
            logger.error(f"Failed to load collections from library: {e}")
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
            self._create_task(self._load_collections_async())

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
                on_result=lambda widget, path: self._create_task(
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
            self._create_task(self._add_url_to_collection_async(url, collection_id))

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
            self._create_task(self.refresh_collections())
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
                self._create_task(self.refresh_collections())
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
                self._create_task(self.refresh_collections())
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
            self._create_task(self._select_and_add_files_async(collection_id, operation="copy"))

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
            self._create_task(self._select_and_add_folder_async(collection_id, operation="copy"))

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
            self._create_task(self._select_and_add_files_async(collection_id, operation="link"))

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
            self._create_task(self._select_and_add_folder_async(collection_id, operation="link"))

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

    def _on_import_camera(self, widget=None):
        """Import from camera action - opens camera interface"""
        logger.info("Import from camera clicked")
        # Reuse existing camera handler
        self._on_open_camera(widget)

    def _on_import_scanner(self, widget=None):
        """Import from scanner action"""
        logger.info("Import from scanner clicked")
        # TODO: Implement scanner import functionality
        # For now, show a placeholder message
        try:
            if hasattr(self, '_show_message'):
                self._show_message("Scanner Import", "Scanner import feature coming soon")
            else:
                logger.warning("Scanner import not yet implemented")
        except Exception as e:
            logger.error(f"Failed to show scanner import message: {e}")

    # ===== MOBILE TOP TOOLBAR HANDLERS =====

    def _on_show_inspector(self, widget=None):
        """Handle show inspector command - opens inspector window with selected collection"""
        try:
            logger.info("Show inspector requested")

            # Get currently selected collection
            if not hasattr(self, 'collections_list') or not self.collections_list:
                logger.warning("No collections list for inspector")
                return

            selected_row = self.collections_list.get_selection()
            if not selected_row:
                logger.warning("No collection selected for inspector")
                return
            collection_id = getattr(selected_row, 'id', None)

            if not collection_id:
                logger.warning("Selected collection has no ID")
                return

            # Fetch full collection metadata from library service (same for desktop and mobile)
            self._create_task(self._show_inspector_with_full_data(collection_id))

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
            self._create_task(self._create_collection_from_urls(urls))

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

                # Refresh collections to show the new collection
                await self.refresh_collections()

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
            self._create_task(self._create_collection_from_files(files))

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

                # Refresh collections to show the new collection
                await self.refresh_collections()

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
            self._create_task(self._create_collection_from_folders(folders))

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

                # Refresh collections to show the new collection
                await self.refresh_collections()

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
            self._create_task(self._create_collection_from_photo(photo_path))

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

                # Refresh collections to show the new collection
                await self.refresh_collections()

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

            # Just refresh - widget handles diff and incremental updates
            self._create_task(self.refresh_collections())

        except Exception as e:
            logger.error(f"Failed to handle collection_added event: {e}")
            # Show error to user (P0-6 fix)
            self._create_task(self._safe_show_error(
                "Update Failed",
                f"Failed to refresh collections after adding: {str(e)}"
            ))

    def _on_collection_deleted_event(self, event):
        """Handle collection_deleted event from other sources (external deletes)"""
        try:
            collection_id = event.data.get("collection_id")
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_deleted - {collection_name}")

            # Check if collection is still in our cached list
            # If not, we already handled it locally, skip refresh
            collection_exists = any(c.get('id') == collection_id for c in self.collections)

            if collection_exists:
                # External delete - just refresh
                logger.info(f"External delete detected - refreshing library view")
                self._create_task(self.refresh_collections())
            else:
                # Already removed by our own delete handler
                logger.debug(f"Collection {collection_name} already removed (local delete)")

        except Exception as e:
            logger.error(f"Failed to handle collection_deleted event: {e}")

    def _on_collection_updated_event(self, event):
        """Handle collection_updated event - auto-refresh library view"""
        try:
            collection_name = event.data.get("collection_name", "Unknown")
            logger.info(f"📡 Event received: collection_updated - {collection_name}")

            # Just refresh - widget handles diff and incremental updates
            self._create_task(self.refresh_collections())

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
        """Handle folder import completed - clear importing status and refresh sidebar"""
        try:
            collection_id = event.data.get("collection_id")
            added = event.data.get("added", 0)

            # Remove from importing collections
            if collection_id in self.importing_collections:
                del self.importing_collections[collection_id]

            logger.info(f"✅ Import completed: {added} files added")

            # Refresh sidebar to show updated item counts
            self._create_task(self.refresh_collections())

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
