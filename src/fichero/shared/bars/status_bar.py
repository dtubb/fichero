"""
StatusBar component for displaying status information.

Similar to macOS Finder's status bar, shows item counts and selection info.
"""

import toga
from toga.style import Pack
import logging

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
    FONT_SIZE = 10

    def __init__(self, platform='desktop'):
        """
        Initialize the StatusBar.

        Args:
            platform: 'desktop' or 'mobile'
        """
        self.platform = platform
        self.height = self.HEIGHT_DESKTOP if platform == 'desktop' else self.HEIGHT_MOBILE

        # Create the status label (centered, 10pt, Finder-style)
        self.status_label = toga.Label(
            '',
            style=Pack(
                margin_left=10,
                margin_right=10,
                font_size=self.FONT_SIZE,
                flex=1,
                text_align='center'
            )
        )

        # Create the container with grey background (macOS default)
        self.container = toga.Box(
            children=[self.status_label],
            style=Pack(
                direction='row',
                align_items='center',
                height=self.height,
                flex=0,  # Don't expand - fixed height only
                background_color='#E8E8E8',  # macOS grey status bar color
                margin=0
            )
        )

        logger.debug(f"StatusBar created for {platform}")

    def set_status(self, text):
        """
        Set the status text to display.

        Args:
            text: String status text to display
        """
        if text:
            self.status_label.text = str(text)
            logger.debug(f"StatusBar status set to: {text}")
        else:
            self.status_label.text = ''
            logger.debug("StatusBar status cleared")

    def clear(self):
        """Clear the status display."""
        self.status_label.text = ''
        logger.debug("StatusBar cleared")
