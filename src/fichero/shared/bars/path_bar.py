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
        Initialize the PathBar - PHASE 5: constrained width, ellipsis for overflow.

        Args:
            platform: 'desktop' or 'mobile'
        """
        self.platform = platform
        self.height = self.HEIGHT_DESKTOP if platform == 'desktop' else self.HEIGHT_MOBILE

        # Create the path label - will truncate with ellipsis if too long
        self.path_label = toga.Label(
            '',
            style=Pack(
                font_size=self.FONT_SIZE,
                text_align='center',  # Centered like status bar
                flex=1,  # Take available width
            )
        )

        # Container for label with grey background
        self.container = toga.Box(
            children=[self.path_label],
            style=Pack(
                direction='row',
                align_items='center',
                height=self.height,
                background_color='#E8E8E8',  # Same grey as status bar
                margin_left=10,
                margin_right=10,
            )
        )

        logger.debug(f"PathBar created for {platform} with constrained width")

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
