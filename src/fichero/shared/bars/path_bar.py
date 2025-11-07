"""
PathBar component for displaying file paths.

Similar to macOS Finder's path bar, shows the current file path.
"""

import toga
from toga.style import Pack
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
    HEIGHT_DESKTOP = 26  # 52 retina pixels
    HEIGHT_MOBILE = 26
    FONT_SIZE = 10

    def __init__(self, platform='desktop'):
        """
        Initialize the PathBar.

        Args:
            platform: 'desktop' or 'mobile'
        """
        self.platform = platform
        self.height = self.HEIGHT_DESKTOP if platform == 'desktop' else self.HEIGHT_MOBILE

        # Create the path label with text truncation (no scrolling, Finder-style)
        self.path_label = toga.Label(
            '',
            style=Pack(
                margin_left=10,
                margin_right=10,
                font_size=self.FONT_SIZE,
                flex=1,
                text_align='center'  # Centered like status bar
            )
        )

        # Create the container with grey background (matches status bar)
        self.container = toga.Box(
            children=[self.path_label],
            style=Pack(
                direction='row',
                align_items='center',
                height=self.height,
                flex=0,  # Don't expand - fixed height only
                background_color='#E8E8E8',  # Same grey as status bar
                margin=0
            )
        )

        logger.debug(f"PathBar created for {platform}")

    def set_path(self, path):
        """
        Set the path to display.

        Args:
            path: String path to display
        """
        if path:
            self.path_label.text = str(path)
            logger.debug(f"PathBar path set to: {path}")
        else:
            self.path_label.text = ''
            logger.debug("PathBar path cleared")

    def clear(self):
        """Clear the path display."""
        self.path_label.text = ''
        logger.debug("PathBar cleared")
