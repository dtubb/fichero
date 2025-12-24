"""
Base renderer class for ListWidget.

All renderers (Native, HTML, Card, etc.) inherit from this base class
and implement the required abstract methods.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import toga


class Renderer(ABC):
    """Base class for all list renderers."""

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default'
    ):
        """
        Initialize renderer.

        Args:
            headings: Column headings for the list
            on_select: Callback when item is selected
            style: Rendering style ('default', 'compact', 'detailed')
        """
        self.headings = headings
        self.on_select = on_select
        self.style = style
        self.source = None
        # Flag to indicate if renderer uses Toga's native source (ListSource/TreeSource)
        # or handles raw data directly (Card, HTML renderers)
        self.uses_native_source = True

    @abstractmethod
    def create_widget(self) -> toga.Widget:
        """
        Create and return the Toga widget.

        Returns:
            The widget instance (Table, Tree, DetailedList, WebView, etc.)
        """
        pass

    @abstractmethod
    def get_accessors(self, headings: List[str]) -> List[str]:
        """
        Return list of accessor names for the source.

        Args:
            headings: The column headings

        Returns:
            List of accessor strings (e.g., ['collections', 'icon', '_item_id'])
        """
        pass

    @abstractmethod
    def convert_to_source_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert application data to source-compatible format.

        Args:
            data: Application data (list of dicts)

        Returns:
            Source-compatible data (list of dicts with accessor keys)
        """
        pass

    def attach_source(self, source):
        """
        Attach source to widget.

        Args:
            source: ListSource or TreeSource instance
        """
        self.source = source

    def supports_incremental_updates(self) -> bool:
        """
        Check if this renderer supports incremental add/remove operations.

        Returns:
            True if incremental updates are supported (e.g., native NSOutlineView),
            False if only full rebuild is supported (e.g., Toga widgets)
        """
        return False  # Default: most renderers don't support it

    def remove_item_at_index(self, index: int) -> bool:
        """
        Remove an item at a specific index incrementally (without full rebuild).

        Only called if supports_incremental_updates() returns True.

        Args:
            index: Index of item to remove

        Returns:
            True if removed successfully, False if not supported or failed
        """
        return False  # Default: not supported

    def add_item_at_index(self, item: Dict[str, Any], index: int) -> bool:
        """
        Add an item at a specific index incrementally (without full rebuild).

        Only called if supports_incremental_updates() returns True.

        Args:
            item: Item data to add
            index: Index where to insert

        Returns:
            True if added successfully, False if not supported or failed
        """
        return False  # Default: not supported


__all__ = ['Renderer']
