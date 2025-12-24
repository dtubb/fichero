"""Table Viewer - Display tabular data.

Usage:
    from fichero.app.main_window.views.library.viewers import TableViewer

    viewer = TableViewer(columns=["Name", "Type", "Status"])
    viewer.load(documents)  # list of Document or dicts
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from rubicon.objc import ObjCClass, objc_method, objc_property

from fichero.app.main_window.views.library.viewers.base import EditorProtocol

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

_AUTORESIZE_FLEX = 18  # NSViewWidthSizable | NSViewHeightSizable
_BORDER_NONE = 0

# Table defaults
DEFAULT_ROW_HEIGHT = 24
DEFAULT_COLUMN_WIDTH = 150

# =============================================================================
# Column Definition
# =============================================================================


@dataclass(frozen=True)
class TableColumn:
    """Definition for a table column.

    Attributes:
        id: Column identifier (used for data lookup)
        title: Display title in header
        width: Column width in pixels
        getter: Optional function to extract value from item
    """
    id: str
    title: str
    width: int = DEFAULT_COLUMN_WIDTH
    getter: Callable[[Any], str] | None = None


# Default columns for Document display
DEFAULT_COLUMNS = (
    TableColumn("name", "Name", 200, lambda d: getattr(d, 'name', str(d))),
    TableColumn("doc_type", "Type", 100, lambda d: getattr(d, 'doc_type', {}).value if hasattr(getattr(d, 'doc_type', None), 'value') else ""),
    TableColumn("status", "Status", 100, lambda d: getattr(d, 'status', {}).value if hasattr(getattr(d, 'status', None), 'value') else ""),
)

# =============================================================================
# Cocoa Classes
# =============================================================================

NSObject = ObjCClass("NSObject")
NSScrollView = ObjCClass("NSScrollView")
NSTableView = ObjCClass("NSTableView")
NSTableColumn = ObjCClass("NSTableColumn")


# =============================================================================
# Table Data Source (NSObject subclass)
# =============================================================================

class _TableDataSource(NSObject):
    """Data source for NSTableView."""

    _viewer = objc_property(object, weak=True)

    @objc_method
    def numberOfRowsInTableView_(self, tv) -> int:
        if self._viewer:
            return len(self._viewer._items)
        return 0

    @objc_method
    def tableView_objectValueForTableColumn_row_(self, tv, col, row: int):
        if not self._viewer:
            return ""

        items = self._viewer._items
        if row >= len(items):
            return ""

        item = items[row]
        col_id = str(col.identifier)

        # Find column definition
        for col_def in self._viewer._columns:
            if col_def.id == col_id:
                if col_def.getter:
                    return col_def.getter(item)
                # Default: try attribute access
                return str(getattr(item, col_id, ""))

        return ""


# =============================================================================
# Table Viewer
# =============================================================================

class TableViewer(EditorProtocol):
    """Table view for displaying lists of data.

    Displays documents, search results, or other tabular data.
    """

    def __init__(self, columns: tuple[TableColumn, ...] | None = None):
        self._items: list = []
        self._columns = columns or DEFAULT_COLUMNS

        # Scroll view
        self._scroll = NSScrollView.alloc().initWithFrame_(((0, 0), (400, 400)))
        self._scroll.hasVerticalScroller = True
        self._scroll.autohidesScrollers = True
        self._scroll.borderType = _BORDER_NONE
        self._scroll.setAutoresizingMask_(_AUTORESIZE_FLEX)

        # Table view
        self._table = NSTableView.alloc().initWithFrame_(((0, 0), (400, 400)))
        self._table.rowHeight = DEFAULT_ROW_HEIGHT
        self._table.usesAlternatingRowBackgroundColors = True

        # Data source
        self._data_source = _TableDataSource.alloc().init()
        self._data_source._viewer = self
        self._table.dataSource = self._data_source

        # Add columns
        for col_def in self._columns:
            col = NSTableColumn.alloc().initWithIdentifier_(col_def.id)
            col.headerCell.stringValue = col_def.title
            col.width = col_def.width
            self._table.addTableColumn_(col)

        self._scroll.documentView = self._table

        logger.info(f"TableViewer created with {len(self._columns)} columns")

    @property
    def native(self) -> Any:
        """The native NSScrollView."""
        return self._scroll

    @property
    def items(self) -> list:
        """Current items in the table."""
        return self._items

    @property
    def selected_items(self) -> list:
        """Currently selected items."""
        result = []
        row = self._table.selectedRow
        if row >= 0 and row < len(self._items):
            result.append(self._items[row])
        return result

    def load(self, items: Any) -> None:
        """Load items into table.

        Args:
            items: List of Document models, dicts, or any objects
        """
        if items is None:
            self._items = []
        elif isinstance(items, list):
            self._items = items
        else:
            # Single item - wrap in list
            self._items = [items]

        self._table.reloadData()
        logger.debug(f"TableViewer loaded {len(self._items)} items")

    def clear(self) -> None:
        """Clear the table."""
        self._items = []
        self._table.reloadData()

    def select_row(self, index: int):
        """Select a specific row.

        Args:
            index: Row index to select
        """
        if 0 <= index < len(self._items):
            self._table.selectRowIndexes_byExtendingSelection_(
                {index}, False
            )

    def reload(self):
        """Reload table data."""
        self._table.reloadData()
