"""
Card renderer - displays items as visual cards in a scrollable container.

This renderer creates a card-based layout where each item is displayed
as a card with icon, title, and subtitle. Cards are arranged in a grid
or vertical list depending on available space.
"""

import logging
from typing import List, Dict, Any, Optional, Callable

import toga
from toga.style.pack import Pack, COLUMN, ROW, BOLD, NORMAL
from toga.fonts import Font, SYSTEM
from . import Renderer


logger = logging.getLogger(__name__)


# Card appearance settings
CARD_SETTINGS = {
    'title_font_size': 10,  # Reduced from 11
    'subtitle_font_size': 9,
    'card_padding': 10,
    'card_background': '#ffffff',
    'card_selected_background': '#E3F2FD',
    'subtitle_color': '#666666',
}


class CardRenderer(Renderer):
    """Renderer that displays items as visual cards."""

    def __init__(
        self,
        headings: List[str],
        on_select: Optional[callable] = None,
        style: str = 'default',
        platform: Optional[str] = None,
        toga_style: Optional[toga.style.pack.Pack] = None,
        card_width: int = 200,
        card_height: int = 150,
        layout: str = 'vertical',  # 'vertical', 'horizontal', 'grid', 'spatial'
        scroll_direction: str = 'vertical',  # 'vertical', 'horizontal', 'both'
        grid_columns: int = 3,  # Number of columns for grid layout
        zoom_level: float = 1.0,  # Zoom factor (0.5 = 50%, 2.0 = 200%)
        card_spacing: int = 10,  # Space between cards
        multiple_select: bool = False,  # Allow multiple card selection
        on_navigate_back: Optional[Callable] = None,  # Callback for back button
    ):
        """
        Initialize card renderer.

        Args:
            headings: Column headings (not used for cards, but kept for compatibility)
            on_select: Selection callback
            style: Rendering style ('default', 'compact', 'detailed')
            platform: Platform string (for debugging)
            toga_style: Toga Pack style for the container
            card_width: Width of each card in pixels
            card_height: Height of each card in pixels
            layout: Card layout ('vertical', 'horizontal', 'grid', 'spatial')
            scroll_direction: Scroll direction ('vertical', 'horizontal', 'both')
            grid_columns: Number of columns for grid layout
            zoom_level: Zoom factor for cards (affects card_width and card_height)
            card_spacing: Space between cards in pixels
            multiple_select: Allow selecting multiple cards
        """
        super().__init__(headings, on_select, style)
        self.uses_native_source = False  # CardRenderer handles raw data, not ListSource
        self.platform = platform
        self.toga_style = toga_style
        self.base_card_width = card_width
        self.base_card_height = card_height
        self.layout = layout
        self.scroll_direction = scroll_direction
        self.grid_columns = grid_columns
        self.zoom_level = zoom_level
        self.card_spacing = card_spacing
        self.multiple_select = multiple_select

        # Apply zoom to card dimensions
        self.card_width = int(card_width * zoom_level)
        self.card_height = int(card_height * zoom_level)

        self.widget = None
        self.cards = []  # List of card widgets (Box objects)
        self.card_data = []  # Data for each card
        self.selected_cards = set()  # Set of selected card indices
        self.grid_rows = []  # For grid layout: list of row boxes

        # Navigation support (like HTML renderer)
        self.current_path = ""  # Current folder path for navigation
        self.on_navigate_back = on_navigate_back  # Callback for back button
        self.items = []  # Store all items for filtering
        self.header_is_selected = False  # Track if header folder is selected

        # Width tracking for automatic resize detection
        self._last_container_width = 0  # Track last known container width
        self._width_check_enabled = True  # Enable automatic width checking
        self._resize_monitor_task = None  # Asyncio task for monitoring width changes

    def _update_header(self):
        """Update the navigation header with folder name and back button."""
        # Clear existing header
        self.header_box.clear()

        if not self.current_path:
            # At root - no header needed
            return

        # Find the current folder item to get its icon
        current_folder_item = None
        for item in self.items:
            item_path = self._get_item_value(item, 'path', '')
            if item_path == self.current_path:
                current_folder_item = item
                break

        # Extract folder name from path
        folder_name = self.current_path.split('/')[-1] if '/' in self.current_path else self.current_path

        # Store current folder item for selection
        self.current_folder_item = current_folder_item

        # Create header as a Canvas so it can be clickable and support text wrapping
        header_canvas = self._create_header_canvas(folder_name, current_folder_item, self.header_is_selected)
        self.header_box.add(header_canvas)

    def _create_header_canvas(self, folder_name: str, folder_item: Any, is_selected: bool = False) -> toga.Canvas:
        """Create a clickable header canvas with back button and wrapped folder name."""
        # Calculate header dimensions - use dynamic card width
        header_width = self.card_width  # Use actual container width
        padding = 8
        back_button_width = 30
        icon_width = 20 if folder_item else 0

        # Text area width (subtract back button, icon, and padding)
        text_width = header_width - back_button_width - icon_width - (padding * 4)

        # Wrap folder name
        folder_lines = self._wrap_text(folder_name, text_width, 10)
        line_height = 10 * 1.4
        text_baseline_offset = 10 + 3  # Same as cards
        text_height = len(folder_lines) * line_height

        # Header height based on text (include baseline offset)
        header_height = int(max(40, text_baseline_offset + text_height + (padding * 2)))

        # Create canvas
        canvas = toga.Canvas(
            style=Pack(
                height=header_height,
                flex=1,
            )
        )

        # Determine background color based on selection
        bg_color = CARD_SETTINGS['card_selected_background'] if is_selected else '#f8f8f8'

        # Draw background
        with canvas.Fill(color=bg_color) as fill:
            fill.rect(0, 0, header_width, header_height)

        # Draw back button (clickable area on left)
        with canvas.Fill(color='#333333') as fill:
            back_font = Font(SYSTEM, 16, weight=NORMAL)
            fill.write_text("‹", x=padding, y=padding + 16, font=back_font)

        # Draw folder name with wrapping
        x_offset = back_button_width + padding

        # Draw icon if available (would need to convert to canvas drawing - skip for now)
        if folder_item and icon_width > 0:
            x_offset += icon_width + padding

        # Draw folder name lines
        y_offset = padding + 10
        folder_font = Font(SYSTEM, 10, weight=NORMAL)
        with canvas.Fill(color='#333333') as fill:
            for line in folder_lines:
                fill.write_text(line, x=x_offset, y=y_offset, font=folder_font)
                y_offset += line_height

        # Add click handler
        def on_header_press(widget, x, y):
            # Check if click is on back button area
            if x < back_button_width:
                if self.on_navigate_back:
                    self.on_navigate_back()
            else:
                # Click on folder name - toggle selection and select the folder
                if self.current_folder_item and self.on_select:
                    logger.debug(f"Header clicked, selecting folder")

                    # Clear any selected cards and re-render them
                    cards_to_update = self.selected_cards.copy()
                    self.selected_cards.clear()
                    for idx in cards_to_update:
                        if idx < len(self.cards) and idx < len(self.card_data):
                            is_selected = False
                            new_canvas = self._render_card_canvas(self.card_data[idx], idx, is_selected)
                            old_canvas = self.cards[idx]
                            parent = old_canvas.parent
                            if parent:
                                children = list(parent.children)
                                try:
                                    position = children.index(old_canvas)
                                    parent.remove(old_canvas)
                                    parent.insert(position, new_canvas)
                                    # Update click handler
                                    def on_card_press(widget, x, y, card_idx=idx):
                                        logger.debug(f"Card {card_idx} clicked")
                                        self._handle_card_select(card_idx)
                                    new_canvas.on_press = on_card_press
                                    self.cards[idx] = new_canvas
                                except (ValueError, IndexError):
                                    pass

                    # Toggle header selection state
                    self.header_is_selected = not self.header_is_selected
                    # Re-render header with new selection state
                    self._update_header()
                    # Call selection callback
                    self.on_select(self.current_folder_item)

        canvas.on_press = on_header_press

        return canvas

    def _on_back_button_pressed(self, widget):
        """Handle back button press."""
        if self.on_navigate_back:
            self.on_navigate_back()

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

    def _get_container_width(self) -> int:
        """
        Get the actual container width from the widget.

        Returns:
            Container width in pixels, or 0 if not laid out yet
        """
        if not self.widget:
            return 0

        try:
            # Access native widget (platform-specific)
            if hasattr(self.widget, '_impl') and hasattr(self.widget._impl, 'native'):
                native = self.widget._impl.native

                # Try to get width from native widget
                width = 0
                if hasattr(native, 'frame'):
                    # macOS/iOS (NSView)
                    width = native.frame.size.width
                elif hasattr(native, 'get_width'):
                    # GTK
                    width = native.get_width()
                elif hasattr(native, 'GetSize'):
                    # Windows (wxPython)
                    width, _ = native.GetSize()

                # Also check parent/container width
                if hasattr(native, 'superview') and native.superview:
                    parent_width = native.superview.frame.size.width
                    if parent_width > 0:
                        width = parent_width

                # logger.debug(f"Container width detected: {width}px")  # Too noisy - commented out
                return int(width) if width > 0 else 0
        except Exception as e:
            logger.debug(f"Could not get container width: {e}")
            return 0

        return 0

    def update_container_width(self, width: int = None, skip_rerender: bool = False) -> bool:
        """
        Update card width based on container width.

        Args:
            width: Explicit width in pixels, or None to auto-detect
            skip_rerender: If True, don't trigger re-render after updating width

        Returns:
            True if width was updated, False otherwise
        """
        if width is None:
            width = self._get_container_width()

        if width <= 0:
            logger.debug("Container width is 0 or unknown, deferring update")
            return False

        # Calculate card width from container
        # Account for scroll bar and spacing
        scrollbar_width = 15
        card_spacing = self.card_spacing * 2  # Left and right
        available_width = width - scrollbar_width - card_spacing

        # For grid layout, divide by columns
        if self.layout == 'grid':
            available_width = (available_width - (self.grid_columns - 1) * self.card_spacing) // self.grid_columns

        # Ensure minimum width
        new_card_width = max(80, available_width)

        # Check if width actually changed
        if new_card_width == self.card_width:
            logger.debug(f"Card width unchanged: {self.card_width}px")
            return False

        # Update card width
        old_width = self.card_width
        self.card_width = new_card_width
        logger.info(f"Updated card width: {old_width}px -> {new_card_width}px (container: {width}px)")

        # Trigger re-render if we have data and not skipping
        if not skip_rerender and self.widget:
            # Use self.items if available (full data), otherwise card_data (filtered data)
            data_to_render = self.items if hasattr(self, 'items') and self.items else self.card_data
            if data_to_render:
                logger.info(f"Re-rendering {len(data_to_render)} cards with new width: {new_card_width}px")
                self.attach_source(data_to_render)
            else:
                logger.warning("No data to re-render after width change")

        return True

    def _start_resize_monitoring(self):
        """Start monitoring for container width changes (asyncio-based)."""
        import asyncio

        if self._resize_monitor_task is not None:
            # Already monitoring
            return

        async def monitor_width():
            """Periodically check container width and trigger re-render if changed."""
            while self._width_check_enabled:
                try:
                    await asyncio.sleep(0.5)  # Check twice per second

                    if not self.widget or not self.items:
                        continue

                    # Check current width
                    current_width = self._get_container_width()
                    if current_width <= 0:
                        continue

                    # Check if width changed
                    if current_width != self._last_container_width:
                        logger.info(f"📏 Auto-detected width change: {self._last_container_width}px → {current_width}px")
                        self._last_container_width = current_width

                        # Trigger re-render with new width
                        if self.update_container_width(current_width, skip_rerender=False):
                            logger.info(f"✓ Cards re-rendered at new width: {current_width}px")

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in resize monitor: {e}")

        try:
            loop = asyncio.get_event_loop()
            self._resize_monitor_task = loop.create_task(monitor_width())
            logger.debug("Started resize monitoring")
        except RuntimeError:
            logger.warning("Cannot start resize monitor - no event loop")

    def _stop_resize_monitoring(self):
        """Stop monitoring for container width changes."""
        self._width_check_enabled = False
        if self._resize_monitor_task:
            self._resize_monitor_task.cancel()
            self._resize_monitor_task = None
            logger.debug("Stopped resize monitoring")

    def _wrap_text(self, text: str, width: int, font_size: int) -> list:
        """
        Wrap text to fit within a given width, breaking long words if necessary.

        Args:
            text: Text to wrap
            width: Available width in pixels
            font_size: Font size in points

        Returns:
            List of text lines
        """
        if not text:
            return []

        # Estimate character width - be extremely conservative to prevent overflow
        # Proportional font assumption: 1 char ≈ 1.0 * font_size pixels (extremely conservative)
        char_width = font_size * 1.0
        chars_per_line = max(5, int(width / char_width))  # Minimum 5 chars per line

        logger.debug(f"Wrapping text '{text}' - width={width}, font_size={font_size}, char_width={char_width}, chars_per_line={chars_per_line}")

        # Wrap text manually by words, breaking long words if needed
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word)

            # Calculate space needed for this word (includes space separator if not first word on line)
            space_for_word = word_length + (1 if current_line else 0)

            # If word itself is too long for a line, break it into chunks
            if word_length > chars_per_line:
                # Finish current line first
                if current_line:
                    lines.append(' '.join(current_line))
                    current_line = []
                    current_length = 0

                # Break long word into chunks that fit
                for i in range(0, word_length, chars_per_line):
                    chunk = word[i:i + chars_per_line]
                    lines.append(chunk)

            # If adding this word would overflow current line, start new line
            elif current_length + space_for_word > chars_per_line:
                if current_line:
                    lines.append(' '.join(current_line))

                # Check if the word itself fits on a new line
                if word_length <= chars_per_line:
                    current_line = [word]
                    current_length = word_length
                else:
                    # Word is too long even for new line, break it
                    current_line = []
                    current_length = 0
                    for i in range(0, word_length, chars_per_line):
                        chunk = word[i:i + chars_per_line]
                        lines.append(chunk)

            # Word fits on current line
            else:
                current_line.append(word)
                current_length += word_length

        if current_line:
            lines.append(' '.join(current_line))

        logger.debug(f"Wrapped into {len(lines)} lines: {lines}")
        return lines

    def _render_card_canvas(self, item: Any, card_index: int, is_selected: bool = False) -> toga.Canvas:
        """
        Render an entire card as a canvas.

        Args:
            item: Item data
            card_index: Index of this card
            is_selected: Whether this card is selected

        Returns:
            Canvas widget with card rendered on it
        """
        # Get item values
        text = self._get_item_value(item, 'text', 'Untitled')
        subtitle = self._get_item_value(item, 'subtitle', '')

        logger.debug(f"Rendering card {card_index}: text='{text[:30]}...', subtitle='{subtitle[:30] if subtitle else 'None'}'")

        # Calculate dimensions - be very conservative with width
        padding = CARD_SETTINGS['card_padding']

        # Full width for text (no icon) - be very conservative with margins
        text_width = self.card_width - (padding * 2) - 20  # Extra safety margin

        # Wrap text with available width
        title_lines = self._wrap_text(text, text_width, CARD_SETTINGS['title_font_size'])
        subtitle_lines = self._wrap_text(subtitle, text_width, CARD_SETTINGS['subtitle_font_size']) if subtitle else []

        # Calculate heights
        title_line_height = CARD_SETTINGS['title_font_size'] * 1.4
        subtitle_line_height = CARD_SETTINGS['subtitle_font_size'] * 1.4
        text_baseline_offset = CARD_SETTINGS['title_font_size'] + 3  # Text baseline offset

        # Title height
        title_height = len(title_lines) * title_line_height

        # Subtitle height
        subtitle_height = len(subtitle_lines) * subtitle_line_height if subtitle_lines else 0

        # Total text height (including baseline offset)
        text_total_height = text_baseline_offset + title_height + (5 if subtitle_lines else 0) + subtitle_height

        # Card height is text height plus padding
        card_height = int(text_total_height + (padding * 2))

        # Create canvas - don't set fixed width, let it fill container
        canvas = toga.Canvas(
            style=Pack(
                height=card_height,
                flex=1,  # Fill available width
            )
        )

        # Determine colors based on selection
        bg_color = CARD_SETTINGS['card_selected_background'] if is_selected else CARD_SETTINGS['card_background']

        # Draw background (no border)
        with canvas.Fill(color=bg_color) as fill:
            fill.rect(0, 0, self.card_width, card_height)

        # Create fonts for title and subtitle
        title_font = Font(SYSTEM, CARD_SETTINGS['title_font_size'], weight=NORMAL)  # Not bold
        subtitle_font = Font(SYSTEM, CARD_SETTINGS['subtitle_font_size'], weight=NORMAL)

        # Draw content
        text_x = padding
        y = padding

        # Draw title lines (text_baseline_offset already calculated above)
        text_y = y + text_baseline_offset  # Start text lower
        with canvas.Fill(color='#000000') as fill:
            for line in title_lines:
                fill.write_text(line, x=text_x, y=text_y, font=title_font)
                text_y += title_line_height

        text_y += 3  # Reduced spacing after title

        # Draw subtitle lines (beside/below icon)
        with canvas.Fill(color=CARD_SETTINGS['subtitle_color']) as fill:
            for line in subtitle_lines:
                fill.write_text(line, x=text_x, y=text_y, font=subtitle_font)
                text_y += subtitle_line_height

        return canvas

    def create_widget(self) -> toga.Widget:
        """
        Create the card container widget.

        Returns:
            ScrollContainer with cards arranged according to layout setting
        """
        logger.debug(f"Creating Card renderer container (layout={self.layout})")

        # Determine direction based on layout
        if self.layout == 'vertical':
            direction = COLUMN
        elif self.layout == 'horizontal':
            direction = ROW
        elif self.layout == 'grid':
            # Grid layout: use COLUMN for rows, each row contains ROW of cards
            direction = COLUMN
            logger.debug(f"Grid layout with {self.grid_columns} columns")
        elif self.layout == 'spatial':
            # TODO: Implement spatial canvas layout
            direction = COLUMN  # For now, use vertical
            logger.warning("Spatial layout not yet implemented, using vertical")
        else:
            direction = COLUMN

        # Create a container box for header + cards
        self.container_box = toga.Box(
            style=Pack(direction=COLUMN, flex=1)
        )

        # Create header box for navigation (will be populated in attach_source if needed)
        self.header_box = toga.Box(
            style=Pack(direction=ROW)
        )
        self.container_box.add(self.header_box)

        # Create a box to hold all cards/rows
        self.cards_box = toga.Box(
            style=Pack(
                direction=direction,
            )
        )

        # Add empty space click handler to the box for deselection
        # Note: Box doesn't support click events, so we'll add a transparent button
        # that fills empty space to capture clicks

        # Wrap cards in scroll container
        # Note: Toga ScrollContainer currently only supports vertical scrolling
        # Horizontal and both directions would need custom implementation
        cards_scroll = toga.ScrollContainer(
            content=self.cards_box,
            style=Pack(flex=1),
        )
        self.container_box.add(cards_scroll)

        # Wrap container in outer widget with user's style
        self.widget = toga.Box(
            children=[self.container_box],
            style=self.toga_style or Pack(flex=1),
        )

        return self.widget

    def _create_card(self, item: Any, card_index: int) -> toga.Canvas:
        """
        Create a single card widget for an item using Canvas rendering.

        Args:
            item: Item data (dict or Row object) with 'text', 'subtitle', 'icon', etc.
            card_index: Index of this card in the cards list

        Returns:
            Canvas widget with card rendered on it
        """
        # Render the card as a canvas
        is_selected = card_index in self.selected_cards
        canvas = self._render_card_canvas(item, card_index, is_selected)

        # Add click handler to canvas
        def on_card_press(widget, x, y):
            logger.debug(f"Card {card_index} clicked at ({x}, {y})")
            self._handle_card_select(card_index)

        canvas.on_press = on_card_press

        return canvas

    def _handle_card_select(self, card_index: int):
        """
        Handle card selection with visual feedback by re-rendering canvas.

        Args:
            card_index: Index of the selected card
        """
        logger.debug(f"_handle_card_select called: index={card_index}, multiple_select={self.multiple_select}")

        # Clear header selection when selecting a card
        if self.header_is_selected:
            self.header_is_selected = False
            self._update_header()

        # Track which cards need updating
        cards_to_update = set()

        if self.multiple_select:
            # Toggle selection
            if card_index in self.selected_cards:
                self.selected_cards.remove(card_index)
            else:
                self.selected_cards.add(card_index)
            cards_to_update.add(card_index)
        else:
            # Single selection - toggle if clicking same card, otherwise select new one
            old_selected = self.selected_cards.copy()

            # If clicking the already selected card, deselect it
            if card_index in self.selected_cards:
                self.selected_cards.clear()
            else:
                # Otherwise select the new card
                self.selected_cards.clear()
                self.selected_cards.add(card_index)

            # Update both old and new selections
            cards_to_update.update(old_selected)
            cards_to_update.add(card_index)

        # Re-render affected cards
        for idx in cards_to_update:
            if idx < len(self.cards) and idx < len(self.card_data):
                is_selected = idx in self.selected_cards
                new_canvas = self._render_card_canvas(self.card_data[idx], idx, is_selected)

                # Replace old canvas
                old_canvas = self.cards[idx]
                parent = old_canvas.parent

                if parent:
                    children = list(parent.children)
                    try:
                        position = children.index(old_canvas)
                        parent.remove(old_canvas)
                        parent.insert(position, new_canvas)

                        # Update click handler
                        def on_card_press(widget, x, y, card_idx=idx):
                            logger.debug(f"Card {card_idx} clicked")
                            self._handle_card_select(card_idx)

                        new_canvas.on_press = on_card_press
                        self.cards[idx] = new_canvas
                    except ValueError:
                        logger.error(f"Could not find card {idx} in parent")

        # Call selection callback
        if self.on_select:
            if self.multiple_select:
                selected_items = [self.card_data[idx] for idx in sorted(self.selected_cards) if idx < len(self.card_data)]
                self.on_select(selected_items)
            else:
                if card_index < len(self.card_data):
                    self.on_select(self.card_data[card_index])

    def set_zoom(self, zoom_level: float):
        """
        Update zoom level and refresh cards.

        Args:
            zoom_level: New zoom factor (0.5 = 50%, 1.0 = 100%, 2.0 = 200%)
        """
        self.zoom_level = zoom_level
        self.card_width = int(self.base_card_width * zoom_level)
        self.card_height = int(self.base_card_height * zoom_level)

        # Refresh all cards with new size
        if self.widget and self.card_data:
            logger.debug(f"Updating zoom to {zoom_level} (card size: {self.card_width}x{self.card_height})")
            self.attach_source(self.card_data)

    def set_grid_columns(self, columns: int):
        """
        Update number of grid columns and refresh layout.

        Args:
            columns: New number of columns for grid layout
        """
        if self.layout != 'grid':
            logger.warning(f"Cannot set grid columns: layout is '{self.layout}', not 'grid'")
            return

        self.grid_columns = columns

        # Update container width since column count affects card width calculation
        self.update_container_width()

        # Refresh grid with new column count
        if self.widget and self.card_data:
            logger.debug(f"Updating grid to {columns} columns")
            self.attach_source(self.card_data)

    def get_accessors(self, headings: List[str]) -> List[str]:
        """
        Return accessor names.

        For cards, we use standard accessors: title, subtitle, icon, etc.

        Args:
            headings: The column headings (ignored for cards)

        Returns:
            List of accessor strings
        """
        return ['text', 'title', 'subtitle', 'icon', '_collection_data', '_item_id']

    def convert_to_source_format(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert app data to card-compatible format.

        For cards, we keep the data as-is since we're not using a Toga source.

        Args:
            data: Application data

        Returns:
            Data in card format (same as input)
        """
        logger.debug(f"Converting {len(data)} items to card format")
        return data

    def _schedule_deferred_render(self, data):
        """
        Wait for container to have non-zero width, then render.

        Args:
            data: Data to render once container width is available
        """
        if not hasattr(self, '_deferred_render_scheduled'):
            self._deferred_render_scheduled = False

        if self._deferred_render_scheduled:
            logger.debug("Deferred render already scheduled, skipping")
            return

        self._deferred_render_scheduled = True
        logger.info(f"Scheduling deferred render for {len(data)} items")

        async def _try_render():
            import asyncio
            max_retries = 50
            retry_interval = 0.1

            for attempt in range(max_retries):
                await asyncio.sleep(retry_interval)

                container_width = self._get_container_width()
                if container_width > 0:
                    logger.info(f"Container width now {container_width}px (attempt {attempt + 1}), rendering {len(data)} items")
                    self.update_container_width(container_width)
                    self.attach_source(data)  # Retry attach
                    self._deferred_render_scheduled = False
                    return

            logger.warning("Container width still 0 after 5s - may be hidden")
            self._deferred_render_scheduled = False

        import asyncio
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_try_render())
        except RuntimeError:
            # No event loop running
            logger.warning("Cannot schedule deferred render - no event loop")
            self._deferred_render_scheduled = False

    def attach_source(self, source):
        """
        Attach data to card renderer.

        Unlike native widgets, cards don't use a Toga source - we directly
        create card widgets from the data.

        Args:
            source: Data (list of dicts) to display as cards
        """
        if not self.widget:
            logger.warning("Cannot attach source - widget not created yet")
            return

        # Create card widgets from data
        if isinstance(source, list):
            data = source
        else:
            # If source is a ListSource or TreeSource, convert to list
            data = list(source)

        # Try to update width from container BEFORE rendering
        container_width = self._get_container_width()
        if container_width > 0:
            # Check if width changed since last render
            width_changed = (container_width != self._last_container_width)

            if width_changed:
                logger.info(f"📏 Container width changed: {self._last_container_width}px → {container_width}px")
                self._last_container_width = container_width

            # Container is laid out - update width (skip re-render to avoid infinite loop)
            logger.debug(f"Container width is {container_width}px, updating card width before rendering")
            self.update_container_width(container_width, skip_rerender=True)
        else:
            # Container not laid out yet - defer rendering
            logger.debug(f"Container width is 0, scheduling deferred render for {len(data)} items")
            self._schedule_deferred_render(data)
            return

        # Clear existing cards
        self.cards_box.clear()
        self.cards = []
        self.card_data = []
        self.selected_cards.clear()
        self.grid_rows = []

        # Store all items for navigation
        self.items = data

        # Update navigation header if we have a current_path
        self._update_header()

        # Filter out current folder from cards if navigating
        items_to_render = data
        if self.current_path:
            # Filter out the current folder item from the cards
            items_to_render = [
                item for item in data
                if self._get_item_value(item, 'path', '') != self.current_path
            ]
            logger.debug(f"Filtered {len(data)} items to {len(items_to_render)} (removed current folder)")

        data = items_to_render

        if self.layout == 'grid':
            # Grid layout: arrange cards in rows
            for i, item in enumerate(data):
                # Create new row if needed
                if i % self.grid_columns == 0:
                    row_box = toga.Box(
                        style=Pack(
                            direction=ROW,
                        )
                    )
                    self.cards_box.add(row_box)
                    self.grid_rows.append(row_box)

                # Create card and add to current row
                card = self._create_card(item, i)
                self.grid_rows[-1].add(card)
                self.cards.append(card)
                self.card_data.append(item)

            logger.debug(f"Created {len(self.cards)} cards in {len(self.grid_rows)} rows (grid layout)")
        else:
            # Vertical or horizontal layout: add cards directly
            for i, item in enumerate(data):
                card = self._create_card(item, i)
                self.cards_box.add(card)
                self.cards.append(card)
                self.card_data.append(item)

            logger.debug(f"Created {len(self.cards)} card widgets ({self.layout} layout)")

        # Start monitoring for resize events (only start once)
        if self._resize_monitor_task is None and self._width_check_enabled:
            self._start_resize_monitoring()


__all__ = ['CardRenderer']
