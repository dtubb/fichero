"""
PathBar component for displaying file paths.

Similar to macOS Finder's path bar, shows the current file path.
"""

import toga
from toga.style import Pack
from toga.fonts import Font, SYSTEM
import logging

logger = logging.getLogger(__name__)


class PathBar:
    """
    A Finder-style path bar component.

    Displays the current file path with a white background.
    Height: 52 retina pixels (26pt)
    Font: 10pt San Francisco
    """

    # HIG specifications for path bar height
    HEIGHT_DESKTOP = 32  # Increased for better visibility
    HEIGHT_MOBILE = 32
    FONT_SIZE = 9  # Compact font for path display

    def __init__(self, platform='desktop'):
        """
        Initialize the PathBar - Canvas-based with dynamic truncation.

        Args:
            platform: 'desktop' or 'mobile'
        """
        self.platform = platform
        self.height = self.HEIGHT_DESKTOP if platform == 'desktop' else self.HEIGHT_MOBILE
        self.current_path = ''
        self.font = Font(SYSTEM, self.FONT_SIZE)

        # Create canvas for custom text rendering with middle truncation
        self.canvas = toga.Canvas(
            style=Pack(
                flex=1,  # Fill available width horizontally
                height=self.height,
            ),
            on_resize=self._on_resize
        )

        # Container with grey background - fixed height but fills width
        self.container = toga.Box(
            children=[self.canvas],
            style=Pack(
                direction='row',
                height=self.height,  # Fixed height
                # No flex property - fills width by default in parent column
                background_color='#E8E8E8',  # Same grey as status bar
            )
        )

        logger.debug(f"PathBar created for {platform} with fixed height {self.height}px")

    def _on_resize(self, widget, width, height):
        """Redraw when canvas is resized."""
        self._draw_path()

    def _truncate_path(self, path_str, available_width):
        """
        Truncate path in the middle to fit available width.
        For "Item › Step" format, always keep step name and truncate item name.

        Args:
            path_str: Full path string (e.g., "Document Name › Original")
            available_width: Available width in pixels

        Returns:
            Truncated path string
        """
        # Estimate character width (rough approximation)
        # For 9pt font, average char width is ~5-6 pixels
        char_width = 6
        max_chars = int(available_width / char_width) - 2  # Leave margin

        if len(path_str) <= max_chars:
            return path_str

        # Split on separator
        separator = ' › '
        parts = path_str.split(separator)

        if len(parts) == 2:
            # Format is "Item › Step" - always keep step, truncate item
            item_name = parts[0]
            step_name = parts[1]

            # Reserve space for step and separator
            step_length = len(step_name) + len(separator)
            available_for_item = max_chars - step_length - 1  # -1 for ellipsis

            if available_for_item > 5:
                # Truncate item name in the middle
                item_truncated = item_name[:available_for_item] + '…'
                return f"{item_truncated} › {step_name}"
            else:
                # Very narrow, just show step with ellipsis
                return f"… › {step_name}"
        else:
            # Simple middle truncation for other formats
            half = max_chars // 2 - 1
            return f"{path_str[:half]}…{path_str[-half:]}"

    def _draw_path(self):
        """Draw the path text on the canvas with middle truncation."""
        if not self.canvas or self.canvas.layout.width == 0:
            return

        # Clear canvas first
        self.canvas.context.clear()

        # Draw background
        with self.canvas.context.Fill(color='#E8E8E8') as fill:
            fill.rect(0, 0, self.canvas.layout.width, self.canvas.layout.height)

        if self.current_path:
            # Truncate path to fit canvas width (with padding)
            padding = 20
            available_width = self.canvas.layout.width - padding
            display_text = self._truncate_path(self.current_path, available_width)

            # Draw text centered
            with self.canvas.context.Fill(color='#000000') as fill:
                # Measure text width for centering (rough estimate)
                text_width = len(display_text) * 6  # ~6 pixels per char for 9pt font

                # Center horizontally
                x = (self.canvas.layout.width - text_width) / 2

                # Center vertically (baseline positioning)
                y = (self.canvas.layout.height / 2) + (self.FONT_SIZE / 3)

                fill.write_text(display_text, x, y, font=self.font)

        # Force redraw
        self.canvas.redraw()

    def set_path(self, path):
        """
        Set the path to display with automatic truncation based on available width.

        Args:
            path: String path to display (e.g., "Library › Collection › Item › Step")
        """
        if path:
            self.current_path = str(path)
            logger.debug(f"PathBar path set to: {path}")
        else:
            self.current_path = ''
            logger.debug("PathBar path cleared")

        # Redraw with new path
        self._draw_path()

    def clear(self):
        """Clear the path display."""
        self.current_path = ''
        self._draw_path()
        logger.debug("PathBar cleared")
