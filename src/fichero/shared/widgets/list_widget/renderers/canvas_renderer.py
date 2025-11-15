"""
Canvas-based interactive renderer - base class for renderers that use Canvas with click handling.

This base class provides common functionality for renderers that display items
using Canvas widgets with click/selection support. Both CardRenderer and SidebarRenderer
inherit from this class.
"""

import logging
from typing import List, Dict, Any, Optional, Set
from abc import abstractmethod

import toga
from toga.style.pack import Pack
from . import Renderer


logger = logging.getLogger(__name__)


class CanvasRenderer(Renderer):
    """
    Base class for renderers that use Canvas widgets with interactive click handling.

    This class provides:
    - Selection state management (selected_items set)
    - Click event handling (canvas.on_press)
    - Visual feedback updates (re-rendering selected/unselected items)
    - Multiple selection support
    - Common helper methods

    Subclasses must implement:
    - _render_item_canvas(): Create the Canvas widget for an item
    - create_widget(): Create the container widget
    - Other abstract Renderer methods
    """

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        multiple_select: bool = False,
    ):
        """
        Initialize canvas renderer.

        Args:
            headings: Column headings
            on_select: Selection callback
            style: Rendering style
            multiple_select: Allow selecting multiple items
        """
        super().__init__(headings, on_select, style)
        self.uses_native_source = False  # Canvas renderers handle raw data
        self.multiple_select = multiple_select

        # Selection state
        self.selected_items: Set[int] = set()  # Set of selected item indices

        # Item storage
        self.items: List[toga.Canvas] = []  # List of Canvas widgets
        self.item_data: List[Any] = []  # Data for each item

    def _get_item_value(self, item: Any, key: str, default: Any = None) -> Any:
        """
        Safely get a value from an item (dict or Toga Row object).

        Args:
            item: Item (dict or Row object)
            key: Key to retrieve
            default: Default value if key not found

        Returns:
            Value for the key, or default if not found
        """
        try:
            if isinstance(item, dict):
                return item.get(key, default)
            else:
                # Try to access as attribute (for Toga Row objects)
                return getattr(item, key, default)
        except AttributeError:
            return default

    @abstractmethod
    def _render_item_canvas(self, item: Any, item_index: int, is_selected: bool = False) -> toga.Canvas:
        """
        Render an item as a Canvas widget.

        Subclasses must implement this to define how items are rendered.

        Args:
            item: Item data
            item_index: Index of this item
            is_selected: Whether this item is selected

        Returns:
            Canvas widget with item rendered on it
        """
        pass

    def _create_item_widget(self, item: Any, item_index: int) -> toga.Canvas:
        """
        Create a Canvas widget for an item with click handling.

        Args:
            item: Item data
            item_index: Index of this item

        Returns:
            Canvas widget with click handler attached
        """
        # Render the item as a canvas
        is_selected = item_index in self.selected_items
        canvas = self._render_item_canvas(item, item_index, is_selected)

        # Add click handler to canvas
        def on_item_press(widget, x, y, idx=item_index):
            logger.debug(f"Item {idx} clicked at ({x}, {y})")
            self._handle_item_select(idx)

        canvas.on_press = on_item_press

        return canvas

    def _handle_item_select(self, item_index: int):
        """
        Handle item selection with visual feedback by re-rendering canvas.

        Args:
            item_index: Index of the selected item
        """
        logger.debug(f"_handle_item_select called: index={item_index}, multiple_select={self.multiple_select}")

        # Track which items need updating
        items_to_update = set()

        if self.multiple_select:
            # Toggle selection
            if item_index in self.selected_items:
                self.selected_items.remove(item_index)
            else:
                self.selected_items.add(item_index)
            items_to_update.add(item_index)
        else:
            # Single selection - toggle if clicking same item, otherwise select new one
            old_selected = self.selected_items.copy()

            # If clicking the already selected item, deselect it
            if item_index in self.selected_items:
                self.selected_items.clear()
            else:
                # Otherwise select the new item
                self.selected_items.clear()
                self.selected_items.add(item_index)

            # Update both old and new selections
            items_to_update.update(old_selected)
            items_to_update.add(item_index)

        # Re-render affected items
        for idx in items_to_update:
            if idx < len(self.items) and idx < len(self.item_data):
                is_selected = idx in self.selected_items
                new_canvas = self._render_item_canvas(self.item_data[idx], idx, is_selected)

                # Replace old canvas
                old_canvas = self.items[idx]
                parent = old_canvas.parent

                if parent:
                    children = list(parent.children)
                    try:
                        position = children.index(old_canvas)
                        parent.remove(old_canvas)
                        parent.insert(position, new_canvas)

                        # Update click handler
                        def on_item_press(widget, x, y, item_idx=idx):
                            logger.debug(f"Item {item_idx} clicked")
                            self._handle_item_select(item_idx)

                        new_canvas.on_press = on_item_press
                        self.items[idx] = new_canvas
                    except (ValueError, IndexError) as e:
                        logger.error(f"Could not replace item {idx} in parent: {e}")

        # Call selection callback
        if self.on_select:
            if self.multiple_select:
                selected_data = [self.item_data[idx] for idx in sorted(self.selected_items) if idx < len(self.item_data)]
                self.on_select(selected_data)
            else:
                if item_index < len(self.item_data):
                    self.on_select(self.item_data[item_index])


__all__ = ['CanvasRenderer']
