"""
StatusBar component for displaying status information.

Similar to macOS Finder's status bar, shows item counts and selection info.
"""

import toga
from toga.style import Pack
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class StatusBar:
    """
    A Finder-style status bar component.

    Displays status information (item counts, selection, etc.) with a grey background.
    Height: 52 retina pixels (26pt)
    Font: 10pt San Francisco
    """

    # HIG specifications for status bar height
    HEIGHT_DESKTOP = 26  # 52 retina pixels
    HEIGHT_MOBILE = 26
    FONT_SIZE = 8  # Match sidebar font size

    def __init__(self, platform='desktop'):
        """
        Initialize the StatusBar.

        Args:
            platform: 'desktop' or 'mobile'
        """
        self.platform = platform
        self.height = self.HEIGHT_DESKTOP if platform == 'desktop' else self.HEIGHT_MOBILE

        # Create left label (selection info - left-aligned)
        self.left_label = toga.Label(
            '',
            style=Pack(
                margin_left=10,
                margin_right=10,
                font_size=self.FONT_SIZE,
                flex=1,
                text_align='left'
            )
        )

        # Create right label (focus info - right-aligned)
        self.right_label = toga.Label(
            '',
            style=Pack(
                margin_left=10,
                margin_right=10,
                font_size=self.FONT_SIZE,
                flex=0,
                text_align='right'
            )
        )

        # Keep reference to old status_label for backward compatibility
        self.status_label = self.left_label

        # Create the container with grey background (match sidebar color)
        self.container = toga.Box(
            children=[self.left_label, self.right_label],
            style=Pack(
                direction='row',
                align_items='center',
                height=self.height,
                flex=0,  # Don't expand - fixed height only
                background_color='#F1F0F7',  # macOS sidebar background (0xF1, 0xF0, 0xF7)
                margin=0
            )
        )

        # Track current focused pane
        self.focused_pane = None

        logger.debug(f"StatusBar created for {platform}")

    def set_status(self, text):
        """
        Set the status text to display (left side).

        Args:
            text: String status text to display
        """
        if text:
            self.left_label.text = str(text)
            logger.debug(f"StatusBar status set to: {text}")
        else:
            self.left_label.text = ''
            logger.debug("StatusBar status cleared")

    def set_focused_pane(self, pane_name: str):
        """
        Set the focused pane name (right side).

        Args:
            pane_name: Name of the focused pane (e.g., "Collection View", "Preview Pane")
        """
        self.focused_pane = pane_name
        if pane_name:
            self.right_label.text = pane_name
            logger.debug(f"StatusBar focused pane set to: {pane_name}")
        else:
            self.right_label.text = ''
            logger.debug("StatusBar focused pane cleared")

    def clear(self):
        """Clear the status display."""
        self.left_label.text = ''
        self.right_label.text = ''
        self.focused_pane = None
        logger.debug("StatusBar cleared")

    # Phase 2: Selection count integration methods

    def update_status_from_selection(
        self,
        context: str,
        selected_count: int,
        metadata: Dict = None
    ) -> None:
        """
        Update status bar based on selection context and count.

        This is the main entry point called by MainWindow when selection changes.
        It formats the appropriate message based on context and selection state.

        Args:
            context: SelectionContext value ('library', 'collection', 'steps', etc.)
            selected_count: Number of selected items (0 = no selection)
            metadata: Optional dict with total_items and folder_count
                     Example: {'total_items': 127, 'folder_count': 5}

        Example:
            # Collection view with 127 items, 3 selected
            status_bar.update_status_from_selection(
                'collection',
                selected_count=3,
                metadata={'total_items': 127, 'folder_count': 5}
            )
            # Shows: "3 items selected"

            # Library view with 10 collections, none selected
            status_bar.update_status_from_selection(
                'library',
                selected_count=0,
                metadata={'total_items': 10}
            )
            # Shows: "10 collections"
        """
        metadata = metadata or {}
        total_items = metadata.get('total_items', 0)
        folder_count = metadata.get('folder_count', 0)

        # If items are selected, show selection count
        if selected_count > 0:
            message = self._format_selection_message(selected_count)
        else:
            # No selection - show total counts based on context
            if context == 'library':
                message = self._format_library_status(total_items, selected_count)
            elif context == 'collection':
                message = self._format_collection_status(total_items, folder_count, selected_count, metadata)
            elif context == 'steps':
                message = self._format_steps_status(total_items, selected_count)
            else:
                # Unknown context - generic message
                message = self._format_generic_status(total_items)

        self.set_status(message)
        logger.debug(f"StatusBar updated: {message}")

    def _format_selection_message(self, count: int) -> str:
        """
        Format selection count message.

        Args:
            count: Number of selected items

        Returns:
            "1 item selected" or "X items selected"
        """
        return self._pluralize(count, "item", suffix=" selected")

    def _format_library_status(self, total_count: int, selected_count: int) -> str:
        """
        Format library view status (collections).

        Args:
            total_count: Total number of collections
            selected_count: Number of selected collections

        Returns:
            "No collections", "1 collection", or "X collections"
        """
        return self._pluralize(total_count, "collection")

    def _format_collection_status(
        self,
        total_items: int,
        folder_count: int,
        selected_count: int,
        metadata: Dict
    ) -> str:
        """
        Format collection view status (items and folders).

        Shows item count and folder count if folders exist.

        Args:
            total_items: Total number of items
            folder_count: Number of folders
            selected_count: Number of selected items
            metadata: Additional metadata (may contain items list)

        Returns:
            "No items", "1 item", "127 items", or "127 items, 5 folders"
        """
        if total_items == 0:
            return "No items"

        # Format item count
        item_text = self._pluralize(total_items, "item", no_prefix=True)

        # Add folder count if folders exist
        if folder_count > 0:
            folder_text = self._pluralize(folder_count, "folder", no_prefix=True)
            return f"{item_text}, {folder_text}"

        return item_text

    def _format_steps_status(self, total_count: int, selected_count: int) -> str:
        """
        Format steps view status.

        Args:
            total_count: Total number of steps
            selected_count: Number of selected steps

        Returns:
            "No steps", "1 step", or "X steps"
        """
        return self._pluralize(total_count, "step")

    def _format_generic_status(self, total_count: int) -> str:
        """
        Format generic status for unknown contexts.

        Args:
            total_count: Total number of items

        Returns:
            "No items", "1 item", or "X items"
        """
        return self._pluralize(total_count, "item")

    def _count_folders_and_items(self, items: list) -> tuple:
        """
        Count folders and total items from a list of collection items.

        CRITICAL FIX #1: Uses item.get() for dictionaries, not getattr().

        Args:
            items: List of collection item dictionaries

        Returns:
            Tuple of (folder_count, total_count)
        """
        if not items:
            return (0, 0)

        total_count = len(items)
        # FIXED: Use item.get() for dictionaries (not getattr)
        folder_count = sum(
            1 for item in items
            if isinstance(item, dict) and item.get('is_folder', False)
        )

        return (folder_count, total_count)

    def _pluralize(
        self,
        count: int,
        singular: str,
        plural: str = None,
        suffix: str = "",
        no_prefix: bool = False
    ) -> str:
        """
        Helper for pluralization with proper grammar.

        Args:
            count: Number of items
            singular: Singular form (e.g., "item")
            plural: Plural form (defaults to singular + "s")
            suffix: Text to append (e.g., " selected")
            no_prefix: If True, don't add "No" prefix for count=0

        Returns:
            Properly pluralized string

        Examples:
            _pluralize(0, "item") → "No items"
            _pluralize(1, "item") → "1 item"
            _pluralize(5, "item") → "5 items"
            _pluralize(3, "item", suffix=" selected") → "3 items selected"
            _pluralize(0, "item", no_prefix=True) → "0 items"
        """
        if plural is None:
            plural = singular + "s"

        if count == 0:
            if no_prefix:
                return f"0 {plural}{suffix}"
            else:
                return f"No {plural}{suffix}"
        elif count == 1:
            return f"1 {singular}{suffix}"
        else:
            return f"{count} {plural}{suffix}"
