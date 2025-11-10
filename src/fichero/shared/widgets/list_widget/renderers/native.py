"""
Native renderer using Toga's built-in widgets (Table, Tree, DetailedList).

This renderer adapts to the platform by choosing the appropriate widget:
- Desktop Table: For flat multi-column lists
- Desktop Tree: For hierarchical data
- Mobile DetailedList: For touch-optimized lists
"""

import logging
from typing import List, Dict, Any, Optional

import toga
from toga.sources import ListSource, TreeSource
from . import Renderer


logger = logging.getLogger(__name__)


class NativeRenderer(Renderer):
    """Renderer using native Toga widgets (Table/Tree/DetailedList)."""

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        platform: Optional[str] = None,
        widget_type: Optional[str] = None,
        multiple_select: bool = False,
        on_activate: Optional[callable] = None,
        toga_style: Optional[toga.style.pack.Pack] = None,
    ):
        """
        Initialize native renderer.

        Args:
            headings: Column headings
            on_select: Selection callback
            style: Rendering style (not used for native widgets)
            platform: Platform string (for debugging)
            widget_type: Widget type ('table', 'tree', 'detailedlist')
            multiple_select: Allow multiple selection
            on_activate: Activation callback (double-click, enter)
            toga_style: Toga Pack style for the widget
        """
        super().__init__(headings, on_select, style)
        self.platform = platform
        self.widget_type = widget_type  # 'table', 'tree', 'detailedlist'
        self.widget = None
        self.multiple_select = multiple_select
        self.on_activate = on_activate
        self.toga_style = toga_style

        # Store original callback and wrap it for logging
        self._original_on_select = on_select
        if on_select:
            def wrapped_on_select(widget, **kwargs):
                logger.info(f"🎯 Tree on_select triggered! widget: {type(widget)}, kwargs: {kwargs}")
                return self._original_on_select(widget, **kwargs)
            self.on_select = wrapped_on_select

    def create_widget(self) -> toga.Widget:
        """
        Create the appropriate Toga widget.

        Returns:
            Table, Tree, or DetailedList widget
        """
        if self.widget_type == 'table':
            logger.debug(f"Creating Table widget with headings: {self.headings}")
            self.widget = toga.Table(
                headings=self.headings,
                multiple_select=self.multiple_select,
                on_select=self.on_select,
                on_activate=self.on_activate,
                style=self.toga_style,
            )
        elif self.widget_type == 'tree':
            logger.info(f"🌳 Creating Tree widget with headings: {self.headings}")
            logger.info(f"🌳   on_select callback: {self.on_select}")
            logger.info(f"🌳   on_activate callback: {self.on_activate}")
            self.widget = toga.Tree(
                headings=self.headings,
                multiple_select=self.multiple_select,
                on_select=self.on_select,
                on_activate=self.on_activate,
                style=self.toga_style,
            )
            logger.info(f"🌳 Tree widget created successfully")
        elif self.widget_type == 'detailedlist':
            logger.debug("Creating DetailedList widget")
            # DetailedList doesn't support on_activate in Toga 0.5.2
            self.widget = toga.DetailedList(
                on_select=self.on_select,
                style=self.toga_style,
            )
        else:
            raise ValueError(f"Unknown widget_type: {self.widget_type}")

        return self.widget

    def get_accessors(self, headings: List[str]) -> List[str]:
        """
        Return accessor names for the source.

        Toga converts headings to lowercase for accessors:
        'Collections' → 'collections'

        We also add custom fields for app-specific data.

        Args:
            headings: The column headings

        Returns:
            List of accessor strings
        """
        # Base accessors from headings (lowercase)
        base = [h.lower() for h in headings]

        # Custom fields for app data and DetailedList
        custom = ['title', 'subtitle', 'icon', '_collection_data', '_item_id']

        return base + custom

    def convert_to_source_format(self, data: List[Dict[str, Any]]):
        """
        Convert app data to source-compatible format.

        Input format (from app):
        [
            {
                'text': 'Item name',
                'icon': toga.Icon or None,
                '_collection_data': {...},  # App-specific data
                '_item_id': 'unique_id',
                'children': [...] or None   # For hierarchical data
            },
            ...
        ]

        Output format (for ListSource - Table/DetailedList):
        [
            {
                'collections': 'Item name',   # Heading accessor
                'title': 'Item name',         # For DetailedList
                'subtitle': '',               # For DetailedList
                'icon': toga.Icon or None,
                '_collection_data': {...},
                '_item_id': 'unique_id',
            },
            ...
        ]

        Output format (for TreeSource - Tree):
        [
            (
                {
                    'collections': 'Item name',  # Heading accessor
                    'icon': toga.Icon or None,
                    '_collection_data': {...},
                    '_item_id': 'unique_id',
                },
                None  # or list of child tuples for hierarchical data
            ),
            ...
        ]

        Args:
            data: Application data

        Returns:
            Source-compatible data (list of dicts for ListSource, list of tuples for TreeSource)
        """
        # Get the primary accessor from first heading
        accessor = self.headings[0].lower() if self.headings else 'text'

        if self.widget_type == 'tree':
            # TreeSource format: list of tuples (data_dict, children_list or None)
            logger.info(f"🔄 NativeRenderer: Converting {len(data)} items to TreeSource format")
            result = []
            for item in data:
                text_value = item.get('text', 'Untitled')
                has_children = 'children' in item and item['children']

                node_data = {
                    accessor: text_value,
                    'icon': item.get('icon'),
                    '_collection_data': item.get('_collection_data'),
                    '_item_id': item.get('_item_id'),
                }

                # Handle children recursively if present
                children = item.get('children')
                if children:
                    # Recursively convert children
                    logger.debug(f"🔄   Node '{text_value}' has {len(children)} children - converting recursively")
                    children_tuples = self.convert_to_source_format(children)
                    result.append((node_data, children_tuples))
                else:
                    # No children - leaf node
                    logger.debug(f"🔄   Node '{text_value}' is leaf (no children)")
                    result.append((node_data, None))

            logger.info(f"🔄 NativeRenderer: Converted {len(data)} items to TreeSource tuple format (accessor: '{accessor}')")
            return result
        else:
            # ListSource format: list of dicts
            result = []
            for item in data:
                text_value = item.get('text', 'Untitled')

                source_item = {
                    accessor: text_value,          # For Table
                    'title': text_value,           # For DetailedList
                    'subtitle': item.get('subtitle', ''),  # For DetailedList
                    'icon': item.get('icon'),
                    '_collection_data': item.get('_collection_data'),
                    '_item_id': item.get('_item_id'),
                }
                result.append(source_item)

            logger.debug(f"Converted {len(data)} items to ListSource dict format (accessor: '{accessor}', widget: {self.widget_type})")
            return result

    def attach_source(self, source):
        """
        Attach source to widget.

        For Table and DetailedList, we use ListSource.
        For Tree, we use TreeSource for hierarchical data with icons and multi-column support.

        Args:
            source: ListSource or TreeSource instance
        """
        self.source = source

        if self.widget:
            if self.widget_type in ('table', 'detailedlist', 'tree'):
                source_type = "TreeSource" if self.widget_type == 'tree' else "ListSource"
                logger.debug(f"Attaching {source_type} with {len(source)} items to {self.widget_type}")
                self.widget.data = source
        else:
            logger.warning("Cannot attach source - widget not created yet")


__all__ = ['NativeRenderer']
