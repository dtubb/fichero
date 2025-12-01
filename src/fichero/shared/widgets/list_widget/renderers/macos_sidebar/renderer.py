"""
Native macOS sidebar renderer using NSOutlineView.

This is the main Python wrapper class that creates and manages the native sidebar.

================================================================================
DRAG-DROP REORDERING: HOW INTERNAL MEMORY IS UPDATED
================================================================================

The sidebar maintains several internal data structures that must stay synchronized
during drag-drop operations:

DATA STRUCTURES:
----------------
1. self._data: List[dict]
   - The authoritative tree of sidebar items
   - Each dict can have '_children' for nested items
   - Example: [{'text': 'SECTION', '_is_section_header': True, '_children': [...]}]

2. self._wrapped_items: List[SidebarItem]
   - ObjC wrapper objects for root-level items only
   - NSOutlineView calls our delegate to get these
   - Children are wrapped dynamically via _get_or_create_wrapper()

3. self._item_cache: Dict[str, SidebarItem]
   - Maps item ID -> wrapper object for quick lookup
   - Used to maintain stable wrapper identity during drag-drop
   - Key is either _collection_data.id or 'text' field

4. self._child_cache: Dict[int, List[SidebarItem]]
   - Maps parent wrapper id() -> list of child wrappers
   - Ensures same wrapper returned for same child (stable identity)
   - Required for insertion lines to appear during drag

DRAG-DROP FLOW:
---------------
1. User drags an item
   -> pasteboardWriterForItem: writes item ID to pasteboard

2. User hovers over drop target
   -> validateDrop: validates and sets visual feedback
   -> Uses setDropItem:dropChildIndex: to control insertion line vs highlight

3. User drops the item
   -> acceptDrop: determines parent_data and insert_index
   -> Calls self.interface.move_item_in_tree(source_id, parent_data, index)

4. move_item_in_tree() updates internal memory:
   a. Validates: no self-drop, no circular reference
   b. Finds source item in self._data tree
   c. Removes from old parent's _children list
   d. Inserts into new parent's _children list
   e. Rebuilds _wrapped_items and _item_cache for root level
   f. Calls reloadData() to refresh NSOutlineView

5. Optionally calls _on_reorder_callback for external updates (e.g., database)

ITEM IDENTIFICATION:
--------------------
Items are identified by ID, checked in this order:
1. _collection_data.id (for library collections)
2. text field (fallback for demo/generic items)

See tree_operations.get_item_id() for implementation.

VISUAL FEEDBACK:
----------------
- index >= 0: Insertion line between items (reordering)
- index == -1: Blue highlight on item (dropping INTO container)

Containers that accept drops:
- Section headers (_is_section_header: True)
- Folders (_can_accept_drops: True)

CALLBACKS FOR EXTERNAL UPDATES:
-------------------------------
- _on_reorder_callback(source_id, new_index): Called after successful reorder
- _on_import_callback(paths, target_data): Called for external file drops

The library_view hooks into these callbacks to update the database.
================================================================================
"""

import logging
from typing import List, Dict, Any, Optional

import toga
from toga.style.pack import Pack

from .. import Renderer
from ..sidebar import SidebarRenderer

from .constants import (
    RUBICON_AVAILABLE,
    load_objc_classes,
    NS_OUTLINE_VIEW_DROP_ON_ITEM_INDEX,
    NS_TABLE_VIEW_DROP_ABOVE,
)
from .objc_classes import create_sidebar_classes
from .tree_operations import (
    clean_item_data,
    get_item_id,
    find_item_by_id,
    find_item_in_tree,
    is_descendant_of,
    remove_item_from_parent,
    insert_item_into_parent,
    flatten_tree,
)

logger = logging.getLogger(__name__)


class NSOutlineViewSidebar(Renderer):
    """
    Native macOS sidebar renderer using NSOutlineView.

    Creates a true native sidebar with:
    - NSOutlineView for the list
    - NSScrollView container
    - macOS Finder-style appearance
    - Native selection highlighting
    - Proper keyboard navigation
    - Accessibility support

    Falls back to Canvas-based SidebarRenderer if Rubicon-ObjC is unavailable.
    """

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        platform: Optional[str] = None,
        toga_style: Optional[toga.style.pack.Pack] = None,
        card_width: int = 200,
        multiple_select: bool = False,
    ):
        """
        Initialize native macOS sidebar renderer.

        Args:
            headings: Column headings (not used for sidebar, kept for compatibility)
            on_select: Selection callback
            style: Rendering style ('default', 'compact')
            platform: Platform string (for debugging)
            toga_style: Toga Pack style for the container
            card_width: Width hint for fallback Canvas renderer only
            multiple_select: Allow selecting multiple items
        """
        if not RUBICON_AVAILABLE:
            logger.warning("Rubicon-ObjC not available, falling back to Canvas renderer")
            self._fallback_mode = True
            self._fallback_args = {
                'headings': headings,
                'on_select': on_select,
                'style': style,
                'platform': platform,
                'toga_style': toga_style,
                'card_width': card_width,
                'multiple_select': multiple_select,
            }
            return

        super().__init__(headings, on_select, style)
        self.uses_native_source = False
        self.platform = platform
        self.toga_style = toga_style
        self.multiple_select = multiple_select
        self.card_width = card_width

        self._data = []
        self._on_select_callback = on_select
        self.widget = None
        self._toga_sidebar = None
        self._scroll_view = None
        self._column = None
        self._actual_column_width = None
        self._current_cell_width = 165

        self._last_container_width = 0
        self._width_check_enabled = True
        self._resize_monitor_task = None

        # Drag-and-drop callbacks
        self._on_reorder_callback = None
        self._on_import_callback = None
        self._on_import_to_collection_callback = None
        self._on_import_to_section_callback = None
        self._get_children_callback = None

        # Item identity cache for stable pointers
        self._item_cache = {}

        # Child cache for stable wrapper identity during drag-drop
        # Maps parent wrapper id() -> list of child wrappers
        self._child_cache = {}

        # Expansion state tracking (item_id -> bool)
        # Used to preserve expansion across reloadData()
        self._expansion_state = {}

        # Pending move for deferred drag-drop processing
        # Stores {source_id, target_parent_data, insert_index} during acceptDrop
        # Processed by processPendingMove_ after acceptDrop returns
        self._pending_move = None

        load_objc_classes()
        self.SidebarItem, self.TogaSidebar, self.MinWidthView = create_sidebar_classes()

        logger.info("NSOutlineViewSidebar initialized with native NSOutlineView")

    def create_widget(self) -> toga.Widget:
        """Create the native sidebar widget."""
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            logger.info("Creating Canvas fallback renderer")
            fallback_renderer = SidebarRenderer(**self._fallback_args)
            return fallback_renderer.create_widget()

        from rubicon.objc import ObjCClass, SEL

        NSScrollView = ObjCClass("NSScrollView")
        NSTableColumn = ObjCClass("NSTableColumn")
        NSColor = ObjCClass("NSColor")
        NSFont = ObjCClass("NSFont")
        NSVisualEffectView = ObjCClass("NSVisualEffectView")
        NSArray = ObjCClass("NSArray")
        NSNotificationCenter = ObjCClass("NSNotificationCenter")

        logger.debug("Creating native macOS sidebar")

        # Create scroll view
        self._scroll_view = NSScrollView.alloc().initWithFrame(((0, 0), (100, 100)))
        self._scroll_view.hasVerticalScroller = True
        self._scroll_view.hasHorizontalScroller = False
        self._scroll_view.borderType = 0
        self._scroll_view.autohidesScrollers = True
        self._scroll_view.horizontalScrollElasticity = 0
        self._scroll_view.contentView.copiesOnScroll = False
        self._scroll_view.scrollsDynamically = True

        # Create outline view
        self._toga_sidebar = self.TogaSidebar.alloc().initWithFrame(
            self._scroll_view.contentView.bounds
        )
        self._toga_sidebar.interface = self

        # Configure appearance
        self._toga_sidebar.headerView = None
        self._toga_sidebar.selectionHighlightStyle = 1
        self._toga_sidebar.rowHeight = 28.0
        # Enable layer backing for proper drop indicator rendering
        self._toga_sidebar.wantsLayer = True
        # drawsBackground=True is required for insertion line visibility
        # The outline view needs to draw its own background for drop feedback
        self._toga_sidebar.drawsBackground = True
        self._toga_sidebar.backgroundColor = NSColor.clearColor

        # Configure indentation
        self._toga_sidebar.indentationPerLevel = 8.0
        self._toga_sidebar.indentationMarkerFollowsCell = True
        self._toga_sidebar.autoresizesOutlineColumn = True
        self._toga_sidebar.allowsMultipleSelection = self.multiple_select
        self._toga_sidebar.allowsEmptySelection = True
        self._toga_sidebar.verticalMotionCanBeginDrag = False

        # Float group rows (section headers)
        # NOTE: Disabled for now - may interfere with drop line visibility inside sections
        try:
            self._toga_sidebar.floatsGroupRows = False
            logger.debug("Disabled floatsGroupRows to test drop line visibility")
        except Exception as e:
            logger.debug(f"Could not set floatsGroupRows: {e}")

        # Set drag feedback style
        # 0 = None, 1 = Regular (blue highlight + line), 2 = SourceList (gap/outline)
        # Regular (1) shows blue highlight on items - confirmed working
        try:
            self._toga_sidebar.draggingDestinationFeedbackStyle = 1
            logger.debug("Set draggingDestinationFeedbackStyle = 1 (Regular)")
        except Exception as e:
            logger.debug(f"Could not set draggingDestinationFeedbackStyle: {e}")

        # Enable spring-loading (auto-expand folders on hover during drag)
        try:
            # NSSpringLoadingEnabled = 1 (NSSpringLoadingEnabledForDrop)
            self._toga_sidebar.springLoadingDestination = True
        except Exception as e:
            logger.debug(f"Could not enable spring-loading: {e}")

        self._toga_sidebar.allowsColumnResizing = False
        self._toga_sidebar.allowsColumnReordering = False

        # Set up vibrancy view
        # NOTE: Testing without vibrancy to check if it affects drop line visibility
        self._vibrancy_view = NSVisualEffectView.alloc().initWithFrame(((0, 0), (100, 100)))
        self._vibrancy_view.material = 3
        self._vibrancy_view.blendingMode = 0
        # state = 0 disables vibrancy effect for testing
        self._vibrancy_view.state = 0
        self._vibrancy_view.wantsLayer = True

        # Add scroll view to vibrancy view
        self._vibrancy_view.addSubview(self._scroll_view)
        self._scroll_view.setTranslatesAutoresizingMaskIntoConstraints(False)

        scroll_constraints = [
            self._scroll_view.leadingAnchor.constraintEqualToAnchor(self._vibrancy_view.leadingAnchor),
            self._scroll_view.trailingAnchor.constraintEqualToAnchor(self._vibrancy_view.trailingAnchor),
            self._scroll_view.topAnchor.constraintEqualToAnchor(self._vibrancy_view.topAnchor),
            self._scroll_view.bottomAnchor.constraintEqualToAnchor(self._vibrancy_view.bottomAnchor),
        ]
        for constraint in scroll_constraints:
            constraint.active = True

        # Set up font
        self.sidebar_font_size = 11.0

        # Create column
        self._column = NSTableColumn.alloc().initWithIdentifier("text")
        self._column.resizingMask = 1
        self._column.editable = False
        self._toga_sidebar.addTableColumn(self._column)
        self._toga_sidebar.outlineTableColumn = self._column
        self._toga_sidebar.columnAutoresizingStyle = 1
        self._toga_sidebar.autoresizesOutlineColumn = True
        self._toga_sidebar.autosaveExpandedItems = False

        # Set data source and delegate
        self._toga_sidebar.usesDataSource = True
        self._toga_sidebar.dataSource = self._toga_sidebar
        self._toga_sidebar.delegate = self._toga_sidebar

        # Register drag types
        drag_types = [
            "com.fichero.collection.id",
            "com.fichero.item.type",
            "com.fichero.sidebar.localreorder",
            "public.file-url",
        ]
        drag_types_array = NSArray.arrayWithArray(drag_types)
        self._toga_sidebar.registerForDraggedTypes(drag_types_array)
        self._toga_sidebar.setDraggingSourceOperationMask_forLocal_(16, True)
        self._toga_sidebar.setDraggingSourceOperationMask_forLocal_(1, False)

        logger.info("Drag-and-drop enabled for sidebar")

        # Add outline view to scroll view
        self._scroll_view.documentView = self._toga_sidebar
        self._scroll_view.backgroundColor = NSColor.clearColor
        self._scroll_view.drawsBackground = False

        # Create Toga Box container
        self.widget = toga.Box(style=self.toga_style or Pack(flex=1))

        try:
            if hasattr(self.widget, '_impl') and hasattr(self.widget._impl, 'native'):
                native_box = self.widget._impl.native
                native_box.addSubview(self._vibrancy_view)
                self._vibrancy_view.setTranslatesAutoresizingMaskIntoConstraints(False)

                constraints = [
                    self._vibrancy_view.leadingAnchor.constraintEqualToAnchor(native_box.leadingAnchor),
                    self._vibrancy_view.trailingAnchor.constraintEqualToAnchor(native_box.trailingAnchor),
                    self._vibrancy_view.topAnchor.constraintEqualToAnchor(native_box.topAnchor),
                    self._vibrancy_view.bottomAnchor.constraintEqualToAnchor(native_box.bottomAnchor),
                ]
                for constraint in constraints:
                    constraint.active = True

                min_width_constraint = native_box.widthAnchor.constraintGreaterThanOrEqualToConstant(275)
                min_width_constraint.active = True

                logger.info("Successfully embedded native NSOutlineView into Toga Box")

                self._toga_sidebar.reloadData()

                notification_center = NSNotificationCenter.defaultCenter
                notification_center.addObserver_selector_name_object_(
                    self._toga_sidebar,
                    SEL('frameDidChange:'),
                    'NSViewFrameDidChangeNotification',
                    self._vibrancy_view
                )
                self._vibrancy_view.postsFrameChangedNotifications = True
            else:
                logger.warning("Could not access Box native impl")
        except Exception as e:
            logger.error(f"Failed to embed native view: {e}")
            fallback_renderer = SidebarRenderer(**self._fallback_args if hasattr(self, '_fallback_args') else {
                'headings': self.headings,
                'on_select': self._on_select_callback,
                'style': self.style,
                'toga_style': self.toga_style,
                'card_width': self.card_width,
                'multiple_select': self.multiple_select,
            })
            return fallback_renderer.create_widget()

        return self.widget

    def _update_column_width_from_container(self) -> bool:
        """Update column width based on container width."""
        if not self.widget or not self._toga_sidebar or not self._column:
            return False

        try:
            if not hasattr(self.widget, '_impl') or not hasattr(self.widget._impl, 'native'):
                return False

            native_box = self.widget._impl.native
            container_width = int(native_box.frame.size.width)

            if container_width <= 0:
                return False

            scrollbar_width = 15
            column_width = max(50, container_width - scrollbar_width)
            current_column_width = int(self._column.width)

            if abs(column_width - current_column_width) > 1:
                logger.info(f"Updating column width: {current_column_width}px -> {column_width}px")
                self._column.width = column_width
                self._column.minWidth = 50
                self._current_cell_width = column_width
                self._update_visible_cells_for_width_change()
                self._toga_sidebar.sizeToFit()
                return True

            return False
        except Exception as e:
            logger.error(f"Failed to update column width: {e}")
            return False

    def _update_visible_cells_for_width_change(self):
        """Update visible cells when column width changes."""
        if not self._toga_sidebar or not self._column:
            return

        try:
            from rubicon.objc import ObjCClass
            NSIndexSet = ObjCClass("NSIndexSet")

            new_width = int(self._column.width)
            self._current_cell_width = new_width

            visible_rect = self._toga_sidebar.visibleRect
            visible_range = self._toga_sidebar.rowsInRect(visible_rect)

            index_set = NSIndexSet.indexSetWithIndexesInRange(visible_range)
            self._toga_sidebar.reloadDataForRowIndexes_columnIndexes_(
                index_set,
                NSIndexSet.indexSetWithIndex(0)
            )
        except Exception as e:
            logger.debug(f"Error updating visible cells: {e}")

    def _get_font_for_item(self, item_data, base_size=13):
        """Get NSFont for item with optional bold/italic styling."""
        from rubicon.objc import ObjCClass
        NSFont = ObjCClass("NSFont")

        font_weight = None
        font_style = None

        if isinstance(item_data, dict):
            font_weight = item_data.get('font_weight')
            font_style = item_data.get('font_style')

        weight_map = {
            'ultralight': -0.8,
            'thin': -0.6,
            'light': -0.4,
            'regular': 0.0,
            'medium': 0.23,
            'semibold': 0.5,
            'bold': 0.8,
            'heavy': 0.56,
            'black': 0.62,
        }

        weight_value = weight_map.get(font_weight, 0.0) if font_weight else 0.0
        font = NSFont.systemFontOfSize_weight_(base_size, weight_value)

        if font_style == 'italic':
            NSFontManager = ObjCClass("NSFontManager")
            font_manager = NSFontManager.sharedFontManager
            font = font_manager.convertFont_toHaveTrait_(font, 1)

        return font

    def get_accessors(self, headings: List[str]) -> List[str]:
        """Return accessor names."""
        return ['text', 'icon', '_collection_data', '_item_id']

    def convert_to_source_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert app data to sidebar-compatible format."""
        return data

    def _get_or_create_wrapper(self, item_data: dict):
        """Get existing wrapper or create new one for stable identity."""
        item_id = get_item_id(item_data)

        if item_id and item_id in self._item_cache:
            wrapper = self._item_cache[item_id]
            wrapper._python_data = item_data
            return wrapper

        wrapper = self.SidebarItem.alloc().init()
        wrapper._python_data = item_data

        if item_id:
            self._item_cache[item_id] = wrapper

        return wrapper

    def find_item_location(self, item_id: str):
        """
        Find an item's location in the tree: (item_data, parent_data, index, parent_wrapper).

        Returns:
            Tuple of (item_data, parent_data, index_in_parent, parent_wrapper)
            parent_wrapper is None for root level items
            Returns (None, None, -1, None) if not found
        """
        # Search root level
        for i, item in enumerate(self._data):
            if get_item_id(item) == item_id:
                return (item, None, i, None)

            # Search children
            children = item.get('_children', [])
            for j, child in enumerate(children):
                if get_item_id(child) == item_id:
                    parent_wrapper = self._item_cache.get(get_item_id(item))
                    return (child, item, j, parent_wrapper)

                # Search grandchildren (3 levels deep)
                grandchildren = child.get('_children', [])
                for k, grandchild in enumerate(grandchildren):
                    if get_item_id(grandchild) == item_id:
                        parent_wrapper = self._item_cache.get(get_item_id(child))
                        return (grandchild, child, k, parent_wrapper)

                    # Search great-grandchildren (4 levels)
                    great_grandchildren = grandchild.get('_children', [])
                    for m, great_grandchild in enumerate(great_grandchildren):
                        if get_item_id(great_grandchild) == item_id:
                            parent_wrapper = self._item_cache.get(get_item_id(grandchild))
                            return (great_grandchild, grandchild, m, parent_wrapper)

        return (None, None, -1, None)

    def get_wrapper_for_parent(self, parent_data):
        """Get the wrapper object for a parent data dict. Returns None for root level."""
        if parent_data is None:
            return None
        parent_id = get_item_id(parent_data)
        return self._item_cache.get(parent_id)

    def update_data_after_move(self, source_id, src_parent_data, target_parent_data, target_index):
        """
        Update internal data structures BEFORE NSOutlineView's native move.

        Per Apple's docs: "Before calling moveItemAtIndex:inParent:toIndex:inParent:,
        you must update the data source to reflect the new structure."

        This method updates self._data so that when NSOutlineView queries data source
        methods during the animated move, they return the correct items.

        IMPORTANT: Do NOT call reloadData() - NSOutlineView handles the visual update.
        """
        try:
            # Find the source item BEFORE modifying _data
            src_item, found_parent, found_index, _ = self.find_item_location(source_id)
            if src_item is None:
                logger.error(f"update_data_after_move: Could not find '{source_id}'")
                return False

            logger.debug(f"Moving '{source_id}' from parent={get_item_id(found_parent) if found_parent else 'root'} "
                        f"index={found_index} to parent={get_item_id(target_parent_data) if target_parent_data else 'root'} "
                        f"index={target_index}")

            # Step 1: Remove from source parent using ID comparison (not identity!)
            # Python's `in` operator uses identity check for objects, which fails
            # when the found item is a different instance than what's in the list.
            if found_parent is None:
                # Remove from root level by ID
                removed = False
                for i, item in enumerate(self._data):
                    if get_item_id(item) == source_id:
                        self._data.pop(i)
                        logger.debug(f"Removed '{source_id}' from root level at index {i}")
                        removed = True
                        # Also remove from _wrapped_items
                        src_wrapper = self._item_cache.get(source_id)
                        if src_wrapper and src_wrapper in self._wrapped_items:
                            self._wrapped_items.remove(src_wrapper)
                        break
                if not removed:
                    logger.error(f"Could not find '{source_id}' in root data to remove!")
            else:
                # Remove from parent's children by ID
                children = found_parent.get('_children', [])
                parent_id = get_item_id(found_parent)
                removed = False
                for i, child in enumerate(children):
                    if get_item_id(child) == source_id:
                        children.pop(i)
                        logger.debug(f"Removed '{source_id}' from parent '{parent_id}' at index {i}")
                        removed = True
                        break
                if not removed:
                    logger.error(f"Could not find '{source_id}' in parent '{parent_id}' children to remove!")

            # Step 2: Insert into target parent
            if target_parent_data is None:
                # Insert at root level
                if target_index >= len(self._data):
                    self._data.append(src_item)
                else:
                    self._data.insert(target_index, src_item)

                # Update _wrapped_items
                src_wrapper = self._item_cache.get(source_id)
                if src_wrapper:
                    if src_wrapper not in self._wrapped_items:
                        if target_index >= len(self._wrapped_items):
                            self._wrapped_items.append(src_wrapper)
                        else:
                            self._wrapped_items.insert(target_index, src_wrapper)
            else:
                # Insert into parent's children
                target_children = target_parent_data.setdefault('_children', [])
                if target_index >= len(target_children):
                    target_children.append(src_item)
                else:
                    target_children.insert(target_index, src_item)

                # Ensure parent knows it has children
                target_parent_data['_has_children'] = True

            # Step 3: Clear child cache (will be rebuilt lazily)
            self._child_cache.clear()

            logger.info(f"Data updated: '{source_id}' moved to index {target_index}")
            return True

        except Exception as e:
            logger.error(f"Error in update_data_after_move: {e}", exc_info=True)
            return False

    def attach_source(self, source):
        """Attach data to native sidebar renderer."""
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            return

        if not self.widget or not self._toga_sidebar:
            logger.warning("Cannot attach source - widget not created yet")
            return

        if isinstance(source, list):
            self._data = source
        else:
            self._data = list(source)

        new_cache = {}
        self._wrapped_items = []

        for item in self._data:
            clean_dict = clean_item_data(item)
            wrapper = self._get_or_create_wrapper(clean_dict)
            self._wrapped_items.append(wrapper)

            item_id = get_item_id(clean_dict)
            if item_id:
                new_cache[item_id] = wrapper

        self._item_cache = new_cache

        # Clear child cache - wrappers will be recreated on demand
        self._child_cache = {}

        self._toga_sidebar.reloadData()
        logger.info(f"Reloaded NSOutlineView with {len(self._data)} items")

        # Use deferred expand to avoid segfault from stale wrappers
        self._expand_all_deferred()

        width_updated = self._update_column_width_from_container()
        if not width_updated:
            self._schedule_deferred_reload()

    def _schedule_deferred_reload(self):
        """Schedule a deferred check after layout completes."""
        async def _try_reload_once():
            import asyncio
            await asyncio.sleep(0.3)
            if self._data and self._wrapped_items:
                width_updated = self._update_column_width_from_container()
                if not width_updated:
                    self._toga_sidebar.reloadData()

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_try_reload_once())
        except RuntimeError:
            self._toga_sidebar.reloadData()

    def move_item_in_tree(self, source_id: str, target_parent_data: dict, insert_index: int) -> bool:
        """
        Move an item from its current location to a new location in the tree.

        This is the core method for drag-drop reordering. It updates the internal
        data structures (self._data, self._wrapped_items, self._item_cache) and
        then refreshes the NSOutlineView to reflect the changes.

        INTERNAL MEMORY UPDATE SEQUENCE:
        ================================

        1. VALIDATION
           - Prevent self-drop (item onto itself)
           - Prevent circular reference (parent into child)

        2. FIND SOURCE
           - Search self._data tree recursively
           - Returns: (item_dict, parent_dict, index_in_parent)

        3. REMOVE FROM OLD LOCATION
           - If parent is None: remove from self._data (root level)
           - If parent exists: remove from parent['_children']

        4. INSERT AT NEW LOCATION
           - Adjust index if moving within same parent (source before target)
           - If parent is None: insert into self._data
           - If parent exists: insert into parent['_children']
           - Set parent['_has_children'] = True

        5. UPDATE WRAPPER CACHES
           - Rebuild self._wrapped_items for root items
           - Rebuild self._item_cache for quick ID lookup
           - Uses _get_or_create_wrapper() to maintain stable identity

        6. REFRESH VIEW
           - Call reloadData() to update NSOutlineView
           - Re-expand all items to maintain visual state

        Args:
            source_id: ID of item to move (from get_item_id: collection ID or text)
            target_parent_data: Parent dict to move into:
                - None: Move to root level (not typically used)
                - Section header dict: Move into section's _children
                - Folder dict: Move into folder's _children
            insert_index: Position within target's children (0 = first, -1 = end)

        Returns:
            True if move succeeded, False otherwise (with logging)

        Example:
            # Move "My Collection" to be first child of "COLLECTIONS" section
            success = sidebar.move_item_in_tree(
                source_id="my-collection-uuid",
                target_parent_data={'text': 'COLLECTIONS', '_is_section_header': True, ...},
                insert_index=0
            )
        """
        try:
            target_name = target_parent_data.get('text') if target_parent_data else 'root'
            logger.info(f"move_item_in_tree: source='{source_id}', target='{target_name}', index={insert_index}")

            # ================================================================
            # STEP 1: VALIDATION - Prevent invalid moves
            # ================================================================
            if target_parent_data:
                target_id = get_item_id(target_parent_data)

                # Can't drop item onto itself
                if target_id and target_id == source_id:
                    logger.warning(f"Cannot move item '{source_id}' into itself")
                    return False

                # Can't drop parent into its own child (circular reference)
                # Need to find source item and check if it CONTAINS target
                # If source contains target, moving source INTO target creates a cycle
                source_item_for_check = find_item_by_id(self._data, source_id)
                if source_item_for_check and target_id:
                    if is_descendant_of(source_item_for_check, target_id):
                        logger.warning(f"Cannot move item '{source_id}' into its own descendant '{target_id}'")
                        return False

            # ================================================================
            # STEP 2: FIND SOURCE - Locate item in self._data tree
            # ================================================================
            # Returns: (item_dict, parent_dict_or_None, index_in_parent)
            source_item, source_parent, source_index = find_item_in_tree(self._data, source_id)

            if source_item is None:
                logger.error(f"Source item '{source_id}' not found in self._data")
                return False

            # No-op detection: moving to same position does nothing
            if source_parent == target_parent_data:
                if insert_index == source_index or insert_index == source_index + 1:
                    logger.debug("No-op move detected, skipping")
                    return True

            # ================================================================
            # STEP 3: REMOVE FROM OLD LOCATION
            # ================================================================
            # Modifies: source_parent['_children'] or self._data
            if not remove_item_from_parent(source_item, source_parent, self._data):
                logger.error("Failed to remove item from old parent")
                return False

            # ================================================================
            # STEP 4: INSERT AT NEW LOCATION
            # ================================================================
            # Adjust index if moving within same parent and source was before target
            # Example: [A, B, C] move A to index 2 -> after removing A, list is [B, C]
            # so index 2 becomes 1 to insert after B
            adjusted_index = insert_index
            if source_parent == target_parent_data and source_index < insert_index:
                adjusted_index = insert_index - 1

            # Modifies: target_parent_data['_children'] or self._data
            if not insert_item_into_parent(source_item, target_parent_data, adjusted_index, self._data):
                logger.error("Failed to insert item into new parent")
                # Rollback: restore original position
                insert_item_into_parent(source_item, source_parent, source_index, self._data)
                return False

            # ================================================================
            # STEP 5: CLEAR CHILD CACHE
            # ================================================================
            # Children need rewrapping after the tree structure changed
            self._child_cache = {}

            # ================================================================
            # STEP 6: REBUILD ROOT WRAPPERS
            # ================================================================
            # Rebuild _wrapped_items for root items using cached wrappers
            # _get_or_create_wrapper() returns existing cached wrappers to maintain
            # stable pointer identity where possible
            self._wrapped_items = []
            for root_item in self._data:
                wrapper = self._get_or_create_wrapper(root_item)
                self._wrapped_items.append(wrapper)

            # ================================================================
            # STEP 7: RELOAD DATA
            # ================================================================
            # This is now safe because move_item_in_tree is called from
            # processPendingMove_, which runs AFTER acceptDrop has returned.
            # NSOutlineView has finished its post-drop processing by now.
            self._toga_sidebar.reloadData()

            # NOTE: Don't call _expand_all_deferred() here - it can cause crashes
            # by trying to access wrappers while NSOutlineView is still processing
            # the reloadData(). Users can expand items manually if needed.

            logger.info(f"Move completed: '{source_id}' moved to '{target_name}' at index {adjusted_index}")
            return True

        except Exception as e:
            logger.error(f"Error in move_item_in_tree: {e}", exc_info=True)
            return False

    def supports_incremental_updates(self) -> bool:
        """Return True - native NSOutlineView supports incremental operations."""
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            return False
        return True

    def remove_item_at_index(self, index: int) -> bool:
        """Remove a row from NSOutlineView."""
        try:
            if not self._toga_sidebar or not self._wrapped_items:
                return False

            if index < 0 or index >= len(self._wrapped_items):
                return False

            removed_item = self._wrapped_items.pop(index)
            removed_data = self._data.pop(index)

            try:
                self._toga_sidebar.reloadData()
                return True
            except Exception as e:
                self._wrapped_items.insert(index, removed_item)
                self._data.insert(index, removed_data)
                return False
        except Exception as e:
            logger.error(f"Error in remove_item_at_index: {e}")
            return False

    def add_item_at_index(self, item: Dict[str, Any], index: int) -> bool:
        """Add a row to NSOutlineView."""
        try:
            if not self._toga_sidebar:
                return False

            if index < 0 or index > len(self._wrapped_items):
                return False

            clean_dict = clean_item_data(item)
            wrapper = self.SidebarItem.alloc().init()
            wrapper._python_data = clean_dict

            self._wrapped_items.insert(index, wrapper)
            self._data.insert(index, item)

            try:
                self._toga_sidebar.reloadData()
                return True
            except Exception as e:
                self._wrapped_items.pop(index)
                self._data.pop(index)
                return False
        except Exception as e:
            logger.error(f"Error in add_item_at_index: {e}")
            return False

    # =========================================================================
    # CALLBACK SETTERS
    # =========================================================================

    def set_reorder_callback(self, callback: callable):
        """Set callback for collection reordering via drag-and-drop."""
        self._on_reorder_callback = callback

    def set_import_callback(self, callback: callable):
        """Set callback for external file/folder drops from Finder."""
        self._on_import_callback = callback

    def set_import_to_collection_callback(self, callback: callable):
        """Set callback for importing files/folders to a specific collection."""
        self._on_import_to_collection_callback = callback

    def set_import_to_section_callback(self, callback: callable):
        """Set callback for importing files/folders to a section."""
        self._on_import_to_section_callback = callback

    def set_get_children_callback(self, callback: callable):
        """Set callback for getting children of a hierarchical item."""
        self._get_children_callback = callback

    # =========================================================================
    # EXPANSION STATE MANAGEMENT
    # =========================================================================

    def _save_expansion_state(self):
        """
        Save the current expansion state of all items.

        Called BEFORE reloadData() to preserve which items were expanded.
        Stores item_id -> expanded (bool) in self._expansion_state.
        """
        if not self._toga_sidebar or not hasattr(self, '_wrapped_items'):
            return

        self._expansion_state = {}

        def _save_item_state(wrapper):
            """Save expansion state for one item and its children."""
            if not wrapper or not hasattr(wrapper, '_python_data'):
                return

            item_data = wrapper._python_data
            if not isinstance(item_data, dict):
                return

            item_id = get_item_id(item_data)
            if item_id:
                try:
                    expanded = bool(self._toga_sidebar.isItemExpanded_(wrapper))
                    self._expansion_state[item_id] = expanded
                except Exception:
                    pass

        # Save state for all root items
        for wrapper in self._wrapped_items:
            _save_item_state(wrapper)

        # Also save state for cached children
        for parent_id, children in self._child_cache.items():
            for child_wrapper in children:
                _save_item_state(child_wrapper)

        logger.debug(f"Saved expansion state for {len(self._expansion_state)} items")

    def _restore_expansion_state(self):
        """
        Restore expansion state after reloadData().

        Called AFTER reloadData() and after new wrappers are created.
        Uses saved self._expansion_state to expand previously-expanded items.
        """
        if not self._toga_sidebar or not self._expansion_state:
            return

        def _expand_item_recursively(item_data, wrapper):
            """Restore expansion for one item and recurse to children."""
            if not isinstance(item_data, dict):
                return

            item_id = get_item_id(item_data)
            if item_id and self._expansion_state.get(item_id, False):
                try:
                    self._toga_sidebar.expandItem_(wrapper)
                except Exception as e:
                    logger.debug(f"Could not expand {item_id}: {e}")

        # Expand root items
        for wrapper in self._wrapped_items:
            if hasattr(wrapper, '_python_data'):
                _expand_item_recursively(wrapper._python_data, wrapper)

        logger.debug(f"Restored expansion state")

    def _expand_all_deferred(self):
        """
        Expand all items after a short delay.

        This is used after reloadData() to let NSOutlineView finish
        processing before we try to expand items. Prevents segfaults.
        """
        import asyncio

        async def _do_expand():
            await asyncio.sleep(0.05)  # Small delay for NSOutlineView to settle
            if self._toga_sidebar and hasattr(self, '_wrapped_items'):
                try:
                    # If we have saved expansion state, restore it
                    if self._expansion_state:
                        self._restore_expansion_state()
                    else:
                        # Default: expand all section headers
                        for wrapper in self._wrapped_items:
                            if hasattr(wrapper, '_python_data'):
                                item_data = wrapper._python_data
                                if isinstance(item_data, dict) and item_data.get('_is_section_header'):
                                    try:
                                        self._toga_sidebar.expandItem_(wrapper)
                                    except Exception:
                                        pass
                except Exception as e:
                    logger.error(f"Error in deferred expand: {e}")

        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_do_expand())
        except RuntimeError:
            # No event loop - try sync expand of just root items
            if self._expansion_state:
                self._restore_expansion_state()

    # =========================================================================
    # EXPAND/COLLAPSE API
    # =========================================================================

    def _find_wrapped_item(self, item_data: dict):
        """Find the wrapped SidebarItem for given item_data."""
        if not hasattr(self, '_wrapped_items') or not self._wrapped_items:
            return None

        for wrapped_item in self._wrapped_items:
            if hasattr(wrapped_item, '_python_data') and wrapped_item._python_data == item_data:
                return wrapped_item
        return None

    def expand_item(self, item_data: dict):
        """Expand an item programmatically."""
        if not self._toga_sidebar:
            return

        wrapped_item = self._find_wrapped_item(item_data)
        if wrapped_item:
            self._toga_sidebar.expandItem_(wrapped_item)

    def collapse_item(self, item_data: dict):
        """Collapse an item programmatically."""
        if not self._toga_sidebar:
            return

        wrapped_item = self._find_wrapped_item(item_data)
        if wrapped_item:
            self._toga_sidebar.collapseItem_(wrapped_item)

    def expand_all(self):
        """Expand all expandable items in the sidebar."""
        if not self._toga_sidebar:
            return

        if not hasattr(self, '_wrapped_items') or not self._wrapped_items:
            return

        for wrapped_item in self._wrapped_items:
            if hasattr(wrapped_item, '_python_data'):
                item_data = wrapped_item._python_data
                if isinstance(item_data, dict) and item_data.get('_has_children'):
                    self._toga_sidebar.expandItem_expandChildren_(wrapped_item, True)

    def collapse_all(self):
        """Collapse all expandable items in the sidebar."""
        if not self._toga_sidebar:
            return

        if not hasattr(self, '_wrapped_items') or not self._wrapped_items:
            return

        for wrapped_item in self._wrapped_items:
            if hasattr(wrapped_item, '_python_data'):
                item_data = wrapped_item._python_data
                if isinstance(item_data, dict) and item_data.get('_has_children'):
                    self._toga_sidebar.collapseItem_(wrapped_item)

    def is_item_expanded(self, item_data: dict) -> bool:
        """Check if an item is currently expanded."""
        if not self._toga_sidebar:
            return False

        wrapped_item = self._find_wrapped_item(item_data)
        if wrapped_item:
            return bool(self._toga_sidebar.isItemExpanded_(wrapped_item))
        return False


__all__ = ['NSOutlineViewSidebar']
