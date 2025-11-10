"""
Platform-agnostic tree/list widget that adapts to the target platform.

- macOS/Linux: toga.Tree (hierarchical tree view)
- Windows: toga.Table (table with expandable rows - Tree not well supported)
- iOS/Android: toga.DetailedList (mobile-optimized list)
"""

import logging
import sys
from typing import Any, Callable, Optional, List, Dict
from enum import Enum

import toga
from toga.style.pack import Pack


logger = logging.getLogger(__name__)


class Platform(Enum):
    """Platform types for widget selection."""
    MACOS = "macOS"
    LINUX = "Linux"
    WINDOWS = "Windows"
    IOS = "iOS"
    ANDROID = "Android"


class AbstractTreeList:
    """
    Platform-agnostic tree/list widget.

    Automatically selects the appropriate widget based on platform:
    - Desktop (macOS/Linux): toga.Tree
    - Desktop (Windows): toga.Table (Tree support is limited on Windows)
    - Mobile (iOS/Android): toga.DetailedList

    Provides unified interface for data binding and event handling.
    """

    def __init__(
        self,
        headings: List[str],
        data: Optional[List[Dict[str, Any]]] = None,
        on_select: Optional[Callable] = None,
        on_activate: Optional[Callable] = None,
        multiple_select: bool = False,
        style: Optional[Pack] = None,
    ):
        """
        Initialize the abstract tree/list widget.

        Args:
            headings: Column headings for the widget
            data: Initial data (list of dicts with 'icon', 'text', 'children' keys)
            on_select: Callback when item is selected (receives selected item)
            on_activate: Callback when item is activated/double-clicked
            multiple_select: Whether to allow multiple selection
            style: Toga Pack style for the widget
        """
        self.headings = headings
        self._data = data or []
        self._on_select = on_select
        self._on_activate = on_activate
        self.multiple_select = multiple_select
        self.style = style or Pack(flex=1)

        self.platform = self._detect_platform()
        self.widget = self._create_widget()

        logger.debug(f"AbstractTreeList created for platform: {self.platform.value}")

    def _detect_platform(self) -> Platform:
        """Detect the current platform."""
        platform_str = sys.platform

        if platform_str == "darwin":
            # Check if iOS (via toga backend detection)
            try:
                import toga
                backend_name = toga.platform.current_platform
                if "ios" in backend_name.lower():
                    return Platform.IOS
            except:
                pass
            return Platform.MACOS
        elif platform_str == "win32":
            return Platform.WINDOWS
        elif platform_str == "linux":
            return Platform.LINUX
        elif "android" in platform_str.lower():
            return Platform.ANDROID
        else:
            # Default to Linux for unknown platforms
            logger.warning(f"Unknown platform '{platform_str}', defaulting to Linux")
            return Platform.LINUX

    def _create_widget(self) -> toga.Widget:
        """Create the appropriate widget for the detected platform."""
        if self.platform in (Platform.MACOS, Platform.LINUX):
            return self._create_tree()
        elif self.platform == Platform.WINDOWS:
            return self._create_table()
        else:  # iOS, Android
            return self._create_detailed_list()

    def _create_tree(self) -> toga.Tree:
        """Create a Tree widget for macOS/Linux."""
        tree = toga.Tree(
            headings=self.headings,
            multiple_select=self.multiple_select,
            on_select=self._handle_select if self._on_select else None,
            on_activate=self._handle_activate if self._on_activate else None,
            style=self.style,
        )

        # Populate with initial data
        if self._data:
            tree.data = self._convert_to_tree_data(self._data)

        return tree

    def _create_table(self) -> toga.Table:
        """Create a Table widget for Windows (Tree support is limited)."""
        # Note: Windows doesn't have great Tree support in Toga 0.5.2
        # We use Table as a fallback, but it won't have hierarchy
        table = toga.Table(
            headings=self.headings,
            multiple_select=self.multiple_select,
            on_select=self._handle_select if self._on_select else None,
            on_activate=self._handle_activate if self._on_activate else None,
            style=self.style,
        )

        # Populate with initial data (flattened)
        if self._data:
            table.data = self._flatten_tree_data(self._data)

        return table

    def _create_detailed_list(self) -> toga.DetailedList:
        """Create a DetailedList widget for mobile platforms."""
        detailed_list = toga.DetailedList(
            data=self._convert_to_detailed_list_data(self._data) if self._data else [],
            on_select=self._handle_select if self._on_select else None,
            on_activate=self._handle_activate if self._on_activate else None,
            style=self.style,
        )

        return detailed_list

    def _convert_to_tree_data(self, data: List[Dict[str, Any]]) -> List[tuple]:
        """
        Convert generic data format to Tree-compatible format.

        Toga TreeSource expects data as list of tuples: (data_dict, children_list)

        Expected input format:
        [
            {
                'icon': toga.Icon or None,
                'text': 'Item text',
                'children': [...] or None
            },
            ...
        ]

        Output format:
        [
            ({'icon': None, 'text': 'Item'}, [...children as tuples...]),
            ...
        ]
        """
        tree_data = []
        for item in data:
            tree_item = {
                'icon': item.get('icon'),
                'text': item.get('text', 'Untitled'),
            }

            # Recursively convert children
            if item.get('children'):
                children = self._convert_to_tree_data(item['children'])
                tree_data.append((tree_item, children))
            else:
                tree_data.append((tree_item, []))

        return tree_data

    def _flatten_tree_data(self, data: List[Dict[str, Any]], level: int = 0) -> List[Dict[str, Any]]:
        """
        Flatten hierarchical data for Table widget (Windows).

        Adds indentation to simulate hierarchy visually.
        """
        flattened = []
        indent = "  " * level  # Two spaces per level

        for item in data:
            table_item = {
                'icon': item.get('icon'),
                'text': f"{indent}{item.get('text', 'Untitled')}",
            }
            flattened.append(table_item)

            # Recursively flatten children
            if item.get('children'):
                flattened.extend(self._flatten_tree_data(item['children'], level + 1))

        return flattened

    def _convert_to_detailed_list_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert generic data format to DetailedList-compatible format.

        DetailedList expects: {'icon': ..., 'title': ..., 'subtitle': ...}
        """
        detailed_data = []

        for item in data:
            detailed_item = {
                'icon': item.get('icon'),
                'title': item.get('text', 'Untitled'),
                'subtitle': item.get('subtitle', ''),
            }
            detailed_data.append(detailed_item)

            # Note: DetailedList doesn't support hierarchy, so children are ignored
            # In the future, we could add subtitle text like "3 items" for folders

        return detailed_data

    def _handle_select(self, widget: toga.Widget) -> None:
        """Handle selection event and normalize across platforms."""
        if not self._on_select:
            return

        try:
            if isinstance(widget, toga.Tree):
                selected = widget.selection
            elif isinstance(widget, toga.Table):
                selected = widget.selection
            elif isinstance(widget, toga.DetailedList):
                selected = widget.selection
            else:
                logger.warning(f"Unknown widget type for selection: {type(widget)}")
                selected = None

            self._on_select(selected)
        except Exception as e:
            logger.error(f"Error in selection handler: {e}", exc_info=True)

    def _handle_activate(self, widget: toga.Widget) -> None:
        """Handle activation event (double-click, enter key, etc.)."""
        if not self._on_activate:
            return

        try:
            if isinstance(widget, toga.Tree):
                selected = widget.selection
            elif isinstance(widget, toga.Table):
                selected = widget.selection
            elif isinstance(widget, toga.DetailedList):
                selected = widget.selection
            else:
                logger.warning(f"Unknown widget type for activation: {type(widget)}")
                selected = None

            self._on_activate(selected)
        except Exception as e:
            logger.error(f"Error in activation handler: {e}", exc_info=True)

    def set_data(self, data: List[Dict[str, Any]]) -> None:
        """
        Update the widget's data.

        Args:
            data: New data in generic format (see _convert_to_tree_data)
        """
        self._data = data

        if isinstance(self.widget, toga.Tree):
            self.widget.data = self._convert_to_tree_data(data)
        elif isinstance(self.widget, toga.Table):
            self.widget.data = self._flatten_tree_data(data)
        elif isinstance(self.widget, toga.DetailedList):
            self.widget.data = self._convert_to_detailed_list_data(data)

    def get_selection(self) -> Any:
        """Get the currently selected item(s)."""
        if isinstance(self.widget, (toga.Tree, toga.Table, toga.DetailedList)):
            return self.widget.selection
        return None

    def clear(self) -> None:
        """Clear all data from the widget."""
        self.set_data([])

    @property
    def impl(self) -> toga.Widget:
        """Get the underlying Toga widget implementation."""
        return self.widget
