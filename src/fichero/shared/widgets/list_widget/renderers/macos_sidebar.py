"""
Native macOS sidebar renderer using NSOutlineView via Rubicon-ObjC.

This renderer creates a true native macOS sidebar using NSOutlineView, following
Toga's established pattern for wrapping native widgets.

Based on Toga's Tree widget implementation in toga-cocoa, adapted for sidebar usage.
"""

import sys
import logging
from typing import List, Dict, Any, Optional

import toga
from toga.style.pack import Pack

# Check if Rubicon is available on macOS
RUBICON_AVAILABLE = False
_objc_classes_loaded = False

if sys.platform == 'darwin':
    try:
        from rubicon.objc import ObjCClass, objc_method, objc_property
        from rubicon.objc.runtime import objc_id

        RUBICON_AVAILABLE = True
        logging.info("Rubicon-ObjC available - native macOS sidebar support enabled")
    except ImportError as e:
        logging.warning(f"Rubicon-ObjC not available - using Canvas fallback: {e}")


def _load_objc_classes():
    """Lazy-load ObjC classes to avoid import-time issues."""
    global _objc_classes_loaded, NSOutlineView, NSScrollView, NSTableColumn, NSColor, NSFont, NSImage, NSImageView, NSObject

    if _objc_classes_loaded:
        return

    if not RUBICON_AVAILABLE:
        return

    try:
        from rubicon.objc import ObjCClass, NSObject as RubiconNSObject

        # Load AppKit classes
        NSOutlineView = ObjCClass("NSOutlineView")
        NSScrollView = ObjCClass("NSScrollView")
        NSTableColumn = ObjCClass("NSTableColumn")
        NSColor = ObjCClass("NSColor")
        NSFont = ObjCClass("NSFont")
        NSImage = ObjCClass("NSImage")
        NSImageView = ObjCClass("NSImageView")
        NSObject = RubiconNSObject

        _objc_classes_loaded = True
        logging.debug("ObjC classes loaded successfully")
    except Exception as e:
        logging.error(f"Failed to load ObjC classes: {e}")
        raise

# Always import the Canvas-based fallback
from .sidebar import SidebarRenderer
from ..renderers import Renderer

logger = logging.getLogger(__name__)

# Cache for sidebar classes (created once, reused)
_sidebar_classes_cache = None


def _create_sidebar_classes():
    """Create sidebar classes after ObjC classes are loaded (cached after first call)."""
    global _sidebar_classes_cache

    # Return cached classes if already created
    if _sidebar_classes_cache is not None:
        return _sidebar_classes_cache

    if not RUBICON_AVAILABLE:
        _sidebar_classes_cache = (None, None)
        return None, None

    _load_objc_classes()

    class SidebarItem(NSObject):
        """Wrapper for sidebar item data to avoid NSOutlineView introspection issues."""

        def __init__(self):
            super().__init__()
            # Store Python dict directly, not as ObjC property
            self._python_data = {}

        @objc_method
        def get_data(self):
            """Get the stored Python dict."""
            return self._python_data

        @objc_method
        def set_data_(self, value):
            """Set the stored Python dict."""
            self._python_data = value

        def __repr__(self):
            """String representation for debugging."""
            if self._python_data and isinstance(self._python_data, dict):
                text = self._python_data.get('text', '<no text>')
                return f"<SidebarItem: {text}>"
            return "<SidebarItem: no data>"

    class TogaSidebar(NSOutlineView):
        """
        NSOutlineView subclass that serves as both data source and delegate.

        Follows Toga's pattern from TogaTree implementation.
        """

        # Weak reference to Python interface to prevent retain cycles
        interface = objc_property(object, weak=True)

        @objc_method
        def outlineView_numberOfChildrenOfItem_(self, outline_view, item) -> int:
            """
            Return number of children for item (None = root).

            NSOutlineViewDataSource protocol method.
            """
            if item is None:
                # Root level - return number of data items
                if self.interface and hasattr(self.interface, '_data') and self.interface._data:
                    return len(self.interface._data)
                return 0
            # Flat list - no children
            return 0

        @objc_method
        def outlineView_child_ofItem_(self, outline_view, index: int, item):
            """
            Return child at index for item (None = root).

            NSOutlineViewDataSource protocol method.
            """
            if item is None:
                # Root level - return wrapped item
                if self.interface and hasattr(self.interface, '_wrapped_items'):
                    if 0 <= index < len(self.interface._wrapped_items):
                        return self.interface._wrapped_items[index]
            return None

        @objc_method
        def outlineView_isItemExpandable_(self, outline_view, item) -> bool:
            """
            Return True if item has children.

            NSOutlineViewDataSource protocol method.
            For sidebar (flat list), always False.
            """
            return False

        @objc_method
        def outlineView_objectValueForTableColumn_byItem_(self, outline_view, table_column, item):
            """
            Return value for table column and item.

            NSOutlineViewDataSource protocol method (cell-based - not used in view-based mode).
            """
            # Not called in view-based mode, but required for protocol compliance
            if item is None:
                return ""

            # For view-based rendering, see outlineView_viewForTableColumn_item_
            return ""

        @objc_method
        def outlineView_viewForTableColumn_item_(self, outline_view, table_column, item):
            """
            Return view for table column and item.

            NSOutlineViewDelegate protocol method (view-based - modern API).
            """
            if item is None:
                return None

            # Try to get text and icon from wrapped item
            try:
                # Item is a SidebarItem wrapper - access Python attribute directly
                has_python_data = hasattr(item, '_python_data')
                data_value = item._python_data if has_python_data else None
                is_dict = isinstance(data_value, dict)

                if has_python_data and is_dict:
                    text = data_value.get('text', '')
                    icon_name = data_value.get('icon', None)
                    logger.debug(f"[VIEW] Extracted from data dict - text: '{text}', icon: {icon_name}")
                else:
                    text = str(item)
                    icon_name = None
                    logger.warning(f"[VIEW] Fallback to str(item) - has_python_data={has_python_data}, is_dict={is_dict}, item={item}, text='{text}'")

                # Try to reuse existing view
                NSTableCellView = ObjCClass("NSTableCellView")
                NSTextField = ObjCClass("NSTextField")

                identifier = "IconTextCell"
                view = outline_view.makeViewWithIdentifier(identifier, owner=outline_view)

                if view is None:
                    # Check if container width changed and update column if needed
                    if hasattr(self.interface, 'widget') and self.interface.widget:
                        try:
                            if hasattr(self.interface.widget, '_impl') and hasattr(self.interface.widget._impl, 'native'):
                                current_container_width = self.interface.widget._impl.native.frame.size.width
                                if current_container_width > 0:
                                    expected_column_width = int(current_container_width - 15)
                                    current_column_width = int(outline_view.tableColumns[0].width) if len(outline_view.tableColumns) > 0 else 165

                                    # Update column if container resized
                                    if abs(expected_column_width - current_column_width) > 1:  # Allow 1px tolerance
                                        logger.debug(f"📏 Container resized to {current_container_width}px, updating column: {current_column_width}px → {expected_column_width}px")
                                        outline_view.tableColumns[0].width = expected_column_width
                                        outline_view.tableColumns[0].minWidth = expected_column_width
                                        outline_view.tableColumns[0].maxWidth = expected_column_width
                        except Exception as e:
                            logger.debug(f"Could not check container width: {e}")

                    # Get column width from the NSTableColumn
                    column_width = outline_view.tableColumns[0].width if len(outline_view.tableColumns) > 0 else 165

                    # Cell fills the column
                    CELL_WIDTH = int(column_width)
                    # Text width = column - left margin - icon - spacing - right margin
                    # 4px left margin + 16px icon + 6px spacing + 4px right margin = 30px
                    TEXT_WIDTH = int(column_width - 30)

                    logger.debug(f"Creating NEW cell: column={column_width}px, text={TEXT_WIDTH}px")

                    view = NSTableCellView.alloc().initWithFrame(((0, 0), (CELL_WIDTH, 24)))
                    view.identifier = identifier

                    # Create image view for icon (16x16 like Finder sidebar)
                    image_view = NSImageView.alloc().initWithFrame(((4, 6), (16, 16)))
                    image_view.imageScaling = 1  # NSImageScaleProportionallyUpOrDown
                    view.imageView = image_view
                    view.addSubview(image_view)

                    # Create text field (offset by icon width, vertically centered)
                    # Width calculated from column width
                    text_field = NSTextField.alloc().initWithFrame(((24, 6), (TEXT_WIDTH, 16)))
                    text_field.editable = False
                    text_field.bordered = False
                    text_field.drawsBackground = False
                    text_field.font = NSFont.systemFontOfSize(self.interface.sidebar_font_size)

                    # Make sure text field doesn't expand beyond its frame - NO AUTO LAYOUT
                    text_field.autoresizingMask = 0  # Don't auto-resize

                    # Use single line mode for proper truncation
                    text_field.cell.usesSingleLineMode = True
                    text_field.cell.scrollable = False  # Don't scroll horizontally

                    # Truncate in middle like Finder sidebar (NSLineBreakByTruncatingMiddle = 5)
                    text_field.cell.lineBreakMode = 5
                    text_field.cell.truncatesLastVisibleLine = True
                    text_field.cell.wraps = False  # Don't wrap text

                    view.textField = text_field
                    view.addSubview(text_field)

                # Set text
                if view.textField:
                    view.textField.stringValue = text
                    # Ensure truncation is applied (set every time in case it was reset)
                    view.textField.cell.lineBreakMode = 5  # NSLineBreakByTruncatingMiddle
                    view.textField.cell.truncatesLastVisibleLine = True

                # Set icon (system icon or custom)
                if view.imageView:
                    if icon_name:
                        # Try to load system icon
                        icon = NSImage.imageNamed(icon_name)
                        if icon:
                            view.imageView.image = icon
                        else:
                            # Use generic folder icon as fallback
                            view.imageView.image = NSImage.imageNamed("NSFolder")
                    else:
                        # Use generic folder icon
                        view.imageView.image = NSImage.imageNamed("NSFolder")

                return view

            except Exception as e:
                logger.error(f"Error creating view: {e}", exc_info=True)
                return None

        @objc_method
        def outlineViewSelectionDidChange_(self, notification):
            """
            Handle selection change.

            NSOutlineViewDelegate protocol method.
            """
            if self.interface and self.interface._on_select_callback:
                # Get selected items
                selected_row = self.selectedRow
                if selected_row >= 0:
                    item = self.itemAtRow(selected_row)
                    if item:
                        try:
                            # Extract the data dict from the SidebarItem wrapper
                            if hasattr(item, '_python_data'):
                                data_item = item._python_data
                            else:
                                data_item = item
                            # Call with just the data item (not widget, item)
                            self.interface._on_select_callback(data_item)
                        except Exception as e:
                            logger.error(f"Error in selection callback: {e}")

    # Cache the classes for reuse
    _sidebar_classes_cache = (SidebarItem, TogaSidebar)
    return SidebarItem, TogaSidebar


class MacOSSidebarRenderer(Renderer):
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
        card_width: int = 200,  # Only used for fallback renderer
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
            card_width: Width hint for fallback Canvas renderer only (ignored for native)
            multiple_select: Allow selecting multiple items
        """
        if not RUBICON_AVAILABLE:
            # Log warning and create fallback
            logger.warning("Rubicon-ObjC not available, falling back to Canvas renderer")
            # We can't call super().__init__ here because we're not Renderer
            # Instead we'll store these for create_widget to handle fallback
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
        self.platform = platform
        self.toga_style = toga_style
        self.multiple_select = multiple_select

        self._data = []
        self._on_select_callback = on_select
        self.widget = None
        self._toga_sidebar = None  # Strong reference to prevent GC
        self._scroll_view = None  # Strong reference to scroll view
        self._column = None  # Reference to NSTableColumn
        self._actual_column_width = None  # Actual column width after layout

        # Lazy-load ObjC classes
        _load_objc_classes()

        # Create sidebar classes
        self.SidebarItem, self.TogaSidebar = _create_sidebar_classes()

        logger.info("MacOSSidebarRenderer initialized with native NSOutlineView")

    def create_widget(self) -> toga.Widget:
        """
        Create the native sidebar widget.

        Returns:
            Toga Box containing the native NSOutlineView (wrapped in NSScrollView)
        """
        # Fallback to Canvas renderer if Rubicon not available
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            logger.info("Creating Canvas fallback renderer")
            fallback_renderer = SidebarRenderer(**self._fallback_args)
            return fallback_renderer.create_widget()

        logger.debug("Creating native macOS sidebar (width determined by container)")

        # Create scroll view with minimal frame (will be sized by AutoLayout)
        self._scroll_view = NSScrollView.alloc().initWithFrame(
            ((0, 0), (100, 100))  # Minimal initial size
        )
        self._scroll_view.hasVerticalScroller = True
        self._scroll_view.hasHorizontalScroller = False  # CRITICAL: Disable horizontal scrolling
        self._scroll_view.borderType = 0  # No border

        # Ensure scroll view content doesn't expand beyond bounds
        self._scroll_view.autohidesScrollers = True
        self._scroll_view.horizontalScrollElasticity = 0  # NSScrollElasticityNone

        # Create outline view
        self._toga_sidebar = self.TogaSidebar.alloc().initWithFrame(
            self._scroll_view.contentView.bounds
        )
        self._toga_sidebar.interface = self

        # Configure appearance - macOS Finder sidebar style
        self._toga_sidebar.headerView = None  # Hide header
        self._toga_sidebar.selectionHighlightStyle = 1  # NSTableViewSelectionHighlightStyleSourceList
        self._toga_sidebar.rowHeight = 28.0  # Increased for larger font
        self._toga_sidebar.indentationPerLevel = 0.0  # Flat list, no indentation
        self._toga_sidebar.allowsMultipleSelection = self.multiple_select
        self._toga_sidebar.allowsEmptySelection = True

        # Use transparent background (sidebar style)
        self._toga_sidebar.backgroundColor = NSColor.clearColor

        # Set the scroll view to have transparent background
        self._scroll_view.backgroundColor = NSColor.clearColor
        self._scroll_view.drawsBackground = False

        # Wrap in vibrancy view for translucent sidebar background
        NSVisualEffectView = ObjCClass("NSVisualEffectView")
        self._vibrancy_view = NSVisualEffectView.alloc().initWithFrame(
            ((0, 0), (100, 100))  # Minimal initial size
        )
        self._vibrancy_view.material = 3  # NSVisualEffectMaterialSidebar
        self._vibrancy_view.blendingMode = 0  # NSVisualEffectBlendingModeBehindWindow
        self._vibrancy_view.state = 1  # NSVisualEffectStateActive
        self._vibrancy_view.wantsLayer = True

        # Add scroll view to vibrancy view
        self._vibrancy_view.addSubview(self._scroll_view)
        self._scroll_view.setTranslatesAutoresizingMaskIntoConstraints(False)

        # Make scroll view fill vibrancy view
        scroll_constraints = [
            self._scroll_view.leadingAnchor.constraintEqualToAnchor(self._vibrancy_view.leadingAnchor),
            self._scroll_view.trailingAnchor.constraintEqualToAnchor(self._vibrancy_view.trailingAnchor),
            self._scroll_view.topAnchor.constraintEqualToAnchor(self._vibrancy_view.topAnchor),
            self._scroll_view.bottomAnchor.constraintEqualToAnchor(self._vibrancy_view.bottomAnchor),
        ]
        for constraint in scroll_constraints:
            constraint.active = True

        # Use default macOS sidebar font size (11pt system font)
        self.sidebar_font_size = 11.0
        system_font = NSFont.systemFontOfSize(self.sidebar_font_size)

        # Create single column for text
        # Width will be set dynamically after layout based on container
        self._column = NSTableColumn.alloc().initWithIdentifier("text")

        # Start with minimal width - will be updated after layout
        initial_column_width = 100
        self._column.width = initial_column_width
        self._column.minWidth = 50  # Allow narrow widths
        self._column.maxWidth = 1000  # Allow wide widths

        # Disable resizing
        self._column.resizingMask = 0  # NSTableColumnNoResizing

        # Make column editable = False
        self._column.editable = False

        self._toga_sidebar.addTableColumn(self._column)
        self._toga_sidebar.outlineTableColumn = self._column

        # Prevent column from auto-resizing
        self._toga_sidebar.columnAutoresizingStyle = 0  # NSTableViewNoColumnAutoresizing
        self._toga_sidebar.autoresizesOutlineColumn = False  # Don't auto-resize the outline column

        logger.debug(f"Created NSOutlineView column (width will be set from container)")

        # Force outline view to use the data source for values
        self._toga_sidebar.usesDataSource = True

        # Set self as data source and delegate
        self._toga_sidebar.dataSource = self._toga_sidebar
        self._toga_sidebar.delegate = self._toga_sidebar

        # Add outline view to scroll view
        self._scroll_view.documentView = self._toga_sidebar

        # Create Toga Box container
        self.widget = toga.Box(
            style=self.toga_style or Pack(flex=1)
        )

        # Try to embed the native NSScrollView into the Toga Box
        # Access the native impl of the Box widget
        try:
            # Get the native NSView from the Box's impl
            if hasattr(self.widget, '_impl') and hasattr(self.widget._impl, 'native'):
                native_box = self.widget._impl.native

                # Add vibrancy view (which contains scroll view)
                native_box.addSubview(self._vibrancy_view)
                self._vibrancy_view.setTranslatesAutoresizingMaskIntoConstraints(False)

                # Add constraints to fill parent
                constraints = [
                    self._vibrancy_view.leadingAnchor.constraintEqualToAnchor(native_box.leadingAnchor),
                    self._vibrancy_view.trailingAnchor.constraintEqualToAnchor(native_box.trailingAnchor),
                    self._vibrancy_view.topAnchor.constraintEqualToAnchor(native_box.topAnchor),
                    self._vibrancy_view.bottomAnchor.constraintEqualToAnchor(native_box.bottomAnchor),
                ]
                for constraint in constraints:
                    constraint.active = True

                logger.info("Successfully embedded native NSOutlineView with vibrancy into Toga Box")
            else:
                logger.warning("Could not access Box native impl - native view not embedded")
        except Exception as e:
            logger.error(f"Failed to embed native view: {e}")
            logger.info("Falling back to Canvas renderer")
            # Fall back to Canvas renderer
            fallback_renderer = SidebarRenderer(**self._fallback_args if hasattr(self, '_fallback_args') else {
                'headings': self.headings,
                'on_select': self._on_select_callback,
                'style': self.style,
                'toga_style': self.toga_style,
                'card_width': self.card_width,
                'multiple_select': self.multiple_select,
            })
            return fallback_renderer.create_widget()

        logger.debug("Native macOS sidebar created")
        return self.widget

    def _update_column_width_from_container(self):
        """
        Update the NSOutlineView column width based on actual container width.

        This should be called after the widget is laid out and has its final size.
        """
        if not self.widget or not self._toga_sidebar or not self._column:
            return

        try:
            # Get actual width of the native Box
            if hasattr(self.widget, '_impl') and hasattr(self.widget._impl, 'native'):
                native_box = self.widget._impl.native
                actual_width = native_box.frame.size.width

                logger.info(f"📏 Container actual width: {actual_width}px")

                # If width is 0, the layout hasn't happened yet - skip update
                if actual_width <= 0:
                    logger.debug(f"📏 Container width is {actual_width}px - layout not ready, skipping update")
                    return

                # Get scroll view width
                if self._scroll_view:
                    scroll_width = self._scroll_view.frame.size.width
                    logger.info(f"📏 Scroll view width: {scroll_width}px")

                # Get outline view width
                outline_width = self._toga_sidebar.frame.size.width
                logger.info(f"📏 Outline view width: {outline_width}px")

                # Calculate column width (container width - scrollbar)
                scrollbar_width = 15  # macOS scrollbar width
                column_width = int(actual_width - scrollbar_width)

                # Ensure minimum width
                if column_width < 50:
                    logger.warning(f"📏 Calculated column width {column_width}px is too small, using minimum 50px")
                    column_width = 50

                # Update column width if it changed
                current_column_width = int(self._column.width)
                if column_width != current_column_width:
                    logger.info(f"📏 Updating column width: {current_column_width}px → {column_width}px")

                    self._column.width = column_width
                    self._column.minWidth = column_width
                    self._column.maxWidth = column_width

                    # Store the column width for cell rendering
                    self._actual_column_width = column_width

                    # Reload to apply new width
                    self._toga_sidebar.reloadData()
                else:
                    logger.debug(f"📏 Column width unchanged: {column_width}px")
                    self._actual_column_width = column_width

        except Exception as e:
            logger.error(f"Failed to update column width: {e}")

    def get_accessors(self, headings: List[str]) -> List[str]:
        """
        Return accessor names.

        For sidebar, we use: text, icon, _collection_data, _item_id

        Args:
            headings: The column headings (ignored for sidebar)

        Returns:
            List of accessor strings
        """
        return ['text', 'icon', '_collection_data', '_item_id']

    def convert_to_source_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert app data to sidebar-compatible format.

        Args:
            data: Application data

        Returns:
            Data in sidebar format (same as input for native renderer)
        """
        logger.debug(f"Converting {len(data)} items to native sidebar format")
        return data

    def attach_source(self, source):
        """
        Attach data to native sidebar renderer.

        Args:
            source: Data (list of dicts) to display as sidebar rows
        """
        # Fallback mode
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            return

        if not self.widget or not self._toga_sidebar:
            logger.warning("Cannot attach source - widget not created yet")
            return

        # Update column width based on actual container size
        self._update_column_width_from_container()

        # Store data
        if isinstance(source, list):
            self._data = source
        else:
            # If source is a ListSource or TreeSource, convert to list
            self._data = list(source)

        # Wrap items in SidebarItem objects to avoid NSOutlineView introspection issues
        self._wrapped_items = []
        for item in self._data:
            # Convert Row objects to plain dicts
            if hasattr(item, '__dict__'):
                data_dict = {k: v for k, v in item.__dict__.items() if not k.startswith('_')}
            elif hasattr(item, '_asdict'):
                data_dict = item._asdict()
            elif isinstance(item, dict):
                data_dict = item
            else:
                data_dict = {'text': str(item)}

            # Filter out non-serializable objects (toga.Image, etc) - keep only primitives
            clean_dict = {}
            for k, v in data_dict.items():
                # Only keep strings, numbers, bools, None
                if isinstance(v, (str, int, float, bool, type(None))):
                    clean_dict[k] = v
                elif v is None:
                    clean_dict[k] = None
                else:
                    # Skip complex objects like toga.Image
                    logger.debug(f"Skipping non-primitive field '{k}' of type {type(v)}")

            wrapper = self.SidebarItem.alloc().init()
            # Store dict directly in Python attribute (don't pass to ObjC)
            wrapper._python_data = clean_dict
            self._wrapped_items.append(wrapper)

        # Reload data in outline view
        self._toga_sidebar.reloadData()

        logger.debug(f"Attached {len(self._data)} items to native sidebar")

    def supports_incremental_updates(self) -> bool:
        """
        Native NSOutlineView supports incremental row operations.

        Returns:
            True - we can add/remove individual rows without full rebuild
        """
        # Fallback mode doesn't support incremental
        if hasattr(self, '_fallback_mode') and self._fallback_mode:
            return False
        return True

    def remove_item_at_index(self, index: int) -> bool:
        """
        Remove a row from NSOutlineView incrementally using native API.

        Args:
            index: Index of item to remove

        Returns:
            True if removed successfully
        """
        try:
            if not self._toga_sidebar or not self._wrapped_items:
                logger.error(f"❌ Remove failed: _toga_sidebar={self._toga_sidebar is not None}, _wrapped_items={len(self._wrapped_items) if self._wrapped_items else 0}")
                return False

            if index < 0 or index >= len(self._wrapped_items):
                logger.error(f"❌ Invalid index {index} for remove (have {len(self._wrapped_items)} items)")
                return False

            logger.info(f"🔍 TRACE: remove_item_at_index(index={index}, total_items={len(self._wrapped_items)})")

            # Remove from data structures
            removed_item = self._wrapped_items.pop(index)
            removed_data = self._data.pop(index)

            logger.info(f"🔍 TRACE: Removed from data - text='{removed_data.get('text', 'N/A')}', remaining={len(self._data)}")

            # For flat lists (no tree hierarchy), reloadData() is the simplest and most reliable
            # It's fast enough for <100 items (~2ms) and avoids complex animation API issues
            # removeItemsAtIndexes is for parent-child hierarchies in NSOutlineView
            try:
                self._toga_sidebar.reloadData()
                logger.info(f"✅ NSOutlineView reloadData after remove: index {index}")
                return True
            except Exception as e:
                logger.error(f"❌ reloadData failed: {e}")
                # Restore data
                self._wrapped_items.insert(index, removed_item)
                self._data.insert(index, removed_data)
                return False

        except Exception as e:
            logger.error(f"❌ Exception in remove_item_at_index({index}): {type(e).__name__}: {e}", exc_info=True)
            # Try to restore data if we removed it
            if 'removed_item' in locals() and 'removed_data' in locals():
                logger.warning(f"⚠️ Restoring data after exception")
                try:
                    self._wrapped_items.insert(index, removed_item)
                    self._data.insert(index, removed_data)
                except Exception as restore_error:
                    logger.error(f"Failed to restore data: {restore_error}")
            return False

    def add_item_at_index(self, item: Dict[str, Any], index: int) -> bool:
        """
        Add a row to NSOutlineView incrementally using native API.

        Args:
            item: Item data to add
            index: Index where to insert

        Returns:
            True if added successfully
        """
        try:
            if not self._toga_sidebar:
                return False

            if index < 0 or index > len(self._wrapped_items):
                logger.error(f"Invalid index {index} for add (have {len(self._wrapped_items)} items)")
                return False

            # Clean and wrap the item (same logic as attach_source)
            clean_dict = {}
            for k, v in item.items():
                if isinstance(v, (str, int, float, bool, type(None))):
                    clean_dict[k] = v
                elif v is None:
                    clean_dict[k] = None
                else:
                    logger.debug(f"Skipping non-primitive field '{k}' of type {type(v)}")

            wrapper = self.SidebarItem.alloc().init()
            wrapper._python_data = clean_dict

            # Insert into wrapped items and data
            self._wrapped_items.insert(index, wrapper)
            self._data.insert(index, item)

            # Use reloadData for simplicity and reliability (same as remove)
            try:
                self._toga_sidebar.reloadData()
                logger.info(f"✅ NSOutlineView reloadData after add: index {index}")
                return True
            except Exception as e:
                logger.error(f"❌ reloadData failed: {e}")
                # Restore data
                self._wrapped_items.pop(index)
                self._data.pop(index)
                return False

        except Exception as e:
            logger.error(f"Failed to add item at index {index}: {e}")
            return False


__all__ = ['MacOSSidebarRenderer', 'RUBICON_AVAILABLE']
