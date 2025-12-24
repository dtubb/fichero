"""
Sidebar renderer - displays items as compact rows in a narrow vertical sidebar.

This renderer creates a sidebar-style layout optimized for narrow columns (140px).
Each item is displayed as a compact row with icon and title only.
Designed to match macOS Finder sidebar appearance using Canvas-based rendering.
"""

import logging
from typing import List, Dict, Any, Optional

import toga
from toga.style.pack import Pack, COLUMN, ROW, NORMAL
from toga.fonts import Font, SYSTEM
from .canvas_renderer import CanvasRenderer
from ..helpers.smart_label import SmartLabel, TruncationMode


logger = logging.getLogger(__name__)


# Sidebar appearance settings - macOS Finder sidebar style
SIDEBAR_SETTINGS = {
    'title_font_size': 8,  # macOS sidebar font size (8pt - very small)
    'row_height': 24,  # Taller rows (increased from 20)
    'row_spacing': 0,  # No space between rows - squircle provides spacing
    'first_row_margin_top': 8,  # Top margin before first row
    'card_background': '#F1F0F7',  # macOS sidebar background (0xF1, 0xF0, 0xF7)
    'card_selected_background': '#d0d1d5',  # Light gray selection background
    'text_color': '#484848',  # Dark gray text for unselected items (0x48, 0x48, 0x48)
    'selected_text_color': '#000000',  # Black text for selected items (not white)
    'selection_corner_radius': 8,  # More rounded corners (increased from 6)
}


class SidebarRenderer(CanvasRenderer):
    """Renderer that displays items as compact sidebar rows using Canvas."""

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        platform: Optional[str] = None,
        toga_style: Optional[toga.style.pack.Pack] = None,
        card_width: int = 200,  # Fixed width for sidebar
        multiple_select: bool = False,  # Allow multiple card selection
    ):
        """
        Initialize sidebar renderer.

        Args:
            headings: Column headings (not used for sidebar, but kept for compatibility)
            on_select: Selection callback
            style: Rendering style ('default', 'compact')
            platform: Platform string (for debugging)
            toga_style: Toga Pack style for the container
            card_width: Width of sidebar in pixels (default 140px)
            multiple_select: Allow selecting multiple cards
        """
        super().__init__(headings, on_select, style, multiple_select)
        self.platform = platform
        self.toga_style = toga_style
        self.card_width = card_width

        self.widget = None
        self.rows_box = None  # Container for all rows

        # Initialize SmartLabel helper for accurate text truncation
        self.smart_label = SmartLabel(
            font_family='SYSTEM',
            font_size=SIDEBAR_SETTINGS['title_font_size'],
            font_weight='NORMAL'
        )

    def _truncate_text_with_ellipsis(self, text: str, width: float, font_size: int = None) -> str:
        """
        Truncate text to fit within a given width, adding ellipsis if needed.

        Now uses SmartLabel helper for accurate truncation with proper font metrics.

        Args:
            text: Text to truncate
            width: Available width in pixels
            font_size: Font size in points (optional, uses SIDEBAR_SETTINGS if not provided)

        Returns:
            Truncated text with ellipsis (…) if needed
        """
        if not text:
            return ""

        # Use SmartLabel for accurate truncation
        truncated = self.smart_label.truncate(
            text,
            max_width=width,
            mode=TruncationMode.END
        )

        if truncated != text:
            logger.debug(f"Truncated '{text}' to '{truncated}' (width={width}px)")

        return truncated

    def _render_item_canvas(self, item: Any, item_index: int, is_selected: bool = False) -> toga.Canvas:
        """
        Render a compact sidebar row as a Canvas widget - macOS Finder style.

        Args:
            item: Item data
            item_index: Index of this item
            is_selected: Whether this item is selected

        Returns:
            Canvas widget with row rendered on it
        """
        # Get item values
        text = self._get_item_value(item, 'text', 'Untitled')

        logger.debug(f"Rendering sidebar row {item_index}: text='{text[:30]}...'")

        # Calculate dimensions (no icons, just text with margins)
        selection_margin_left = 5
        selection_margin_right = 5
        text_padding_left = 8  # Internal padding inside selection box
        text_padding_right = 8  # Internal padding on right side
        # Calculate available width for text - truncate aggressively (e.g., "1700" becomes "17…")
        text_width = self.card_width - selection_margin_left - selection_margin_right - text_padding_left - text_padding_right - 15  # More aggressive truncation

        # Truncate text with ellipsis (…)
        truncated_text = self._truncate_text_with_ellipsis(text, text_width, SIDEBAR_SETTINGS['title_font_size'])

        # Determine colors based on selection
        bg_color = SIDEBAR_SETTINGS['card_selected_background'] if is_selected else SIDEBAR_SETTINGS['card_background']
        text_color = SIDEBAR_SETTINGS['selected_text_color'] if is_selected else SIDEBAR_SETTINGS['text_color']

        # Row dimensions
        row_width = self.card_width - 15  # Subtract scrollbar
        row_height = SIDEBAR_SETTINGS['row_height']

        # Create canvas - calculate total height including spacing
        total_height = row_height + SIDEBAR_SETTINGS['row_spacing']
        canvas = toga.Canvas(
            style=Pack(
                height=total_height,
                flex=1,  # Fill available width
            )
        )

        # Draw squircle background - fills full row height with margins on sides only
        selection_margin_left = 5
        selection_margin_right = 5

        # Squircle fills the full row height (no vertical margins)
        rect_x = selection_margin_left
        rect_y = 0  # Start at top of canvas
        rect_width = self.card_width - selection_margin_left - selection_margin_right - 3
        rect_height = row_height  # Full row height

        if is_selected:
            # Rounded rectangle (squircle) for selection using bezier curves
            r = SIDEBAR_SETTINGS['selection_corner_radius']

            with canvas.Fill(color=bg_color) as fill:
                # Use bezier_curve_to for smoother rounded corners
                # Start at top-left, after the rounded corner
                fill.move_to(rect_x + r, rect_y)

                # Top edge
                fill.line_to(rect_x + rect_width - r, rect_y)
                # Top-right corner using quadratic bezier
                fill.bezier_curve_to(
                    rect_x + rect_width, rect_y,
                    rect_x + rect_width, rect_y,
                    rect_x + rect_width, rect_y + r
                )

                # Right edge
                fill.line_to(rect_x + rect_width, rect_y + rect_height - r)
                # Bottom-right corner
                fill.bezier_curve_to(
                    rect_x + rect_width, rect_y + rect_height,
                    rect_x + rect_width, rect_y + rect_height,
                    rect_x + rect_width - r, rect_y + rect_height
                )

                # Bottom edge
                fill.line_to(rect_x + r, rect_y + rect_height)
                # Bottom-left corner
                fill.bezier_curve_to(
                    rect_x, rect_y + rect_height,
                    rect_x, rect_y + rect_height,
                    rect_x, rect_y + rect_height - r
                )

                # Left edge
                fill.line_to(rect_x, rect_y + r)
                # Top-left corner
                fill.bezier_curve_to(
                    rect_x, rect_y,
                    rect_x, rect_y,
                    rect_x + r, rect_y
                )
        else:
            # Regular rectangle for unselected (background color) - no margins needed
            with canvas.Fill(color=bg_color) as fill:
                fill.rect(0, 0, row_width, row_height)

        # Calculate text baseline offset with vertical margin inside squircle
        text_margin_top = 8  # Top margin inside squircle (increased from 6 to center better)
        text_baseline_offset = SIDEBAR_SETTINGS['title_font_size'] + text_margin_top

        # Draw text with padding inside the selection box
        text_padding_left = 8  # Horizontal padding inside the box
        text_x = selection_margin_left + text_padding_left
        text_y = text_baseline_offset
        text_font = Font(SYSTEM, SIDEBAR_SETTINGS['title_font_size'], weight=NORMAL)

        with canvas.Fill(color=text_color) as fill:
            fill.write_text(truncated_text, x=text_x, y=text_y, font=text_font)

        return canvas

    def create_widget(self) -> toga.Widget:
        """
        Create the sidebar container widget.

        Returns:
            ScrollContainer with rows arranged vertically
        """
        logger.debug(f"Creating Sidebar renderer container (width={self.card_width}px)")

        # Create a box to hold all rows with gray background (full width, no margins)
        self.rows_box = toga.Box(
            style=Pack(
                direction=COLUMN,
                background_color=SIDEBAR_SETTINGS['card_background'],  # Gray background for whole sidebar
                margin=0  # No margins on container - margins will be on individual rows
            )
        )

        # Wrap rows in scroll container (vertical scrolling only)
        rows_scroll = toga.ScrollContainer(
            content=self.rows_box,
            style=Pack(flex=1),
        )

        # Wrap container in outer widget with user's style
        self.widget = toga.Box(
            children=[rows_scroll],
            style=self.toga_style or Pack(flex=1),
        )

        return self.widget

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

        For sidebar, we keep the data as-is since we're not using a Toga source.

        Args:
            data: Application data

        Returns:
            Data in sidebar format (same as input)
        """
        logger.debug(f"Converting {len(data)} items to sidebar format")
        return data

    def attach_source(self, source):
        """
        Attach data to sidebar renderer.

        Unlike native widgets, sidebar doesn't use a Toga source - we directly
        create Canvas-based row widgets from the data.

        Args:
            source: Data (list of dicts) to display as sidebar rows
        """
        if not self.widget:
            logger.warning("Cannot attach source - widget not created yet")
            return

        # Clear existing items
        self.rows_box.clear()
        self.items.clear()
        self.item_data.clear()
        self.selected_items.clear()

        # Create row widgets from data
        if isinstance(source, list):
            data = source
        else:
            # If source is a ListSource or TreeSource, convert to list
            data = list(source)

        # Create Canvas-based rows with click handling
        for i, item in enumerate(data):
            # Add top margin spacer before first row
            if i == 0:
                spacer = toga.Box(style=Pack(
                    height=SIDEBAR_SETTINGS['first_row_margin_top'],
                    background_color=SIDEBAR_SETTINGS['card_background']
                ))
                self.rows_box.add(spacer)

            canvas = self._create_item_widget(item, i)
            self.rows_box.add(canvas)
            self.items.append(canvas)
            self.item_data.append(item)

        logger.debug(f"Created {len(self.items)} sidebar row widgets")


__all__ = ['SidebarRenderer']
