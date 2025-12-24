"""
FocusBorder - Universal focus indicator for all views.

Extracted from OutputPane implementation (Phase 5) and generalized
for use across all views in the universal navigation system (Phase 6).
"""

import logging
import toga
from toga.colors import rgb
from typing import Optional


class FocusBorder:
    """
    Manages focus border visual indicator for any view.

    Creates a visual focus border using background color and margin on a container.
    This is the standard approach used in Fichero for indicating focused views.

    Example:
        # In a view's __init__:
        self._focus_border = FocusBorder(self.container)

        # When view receives/loses focus:
        self._focus_border.set_focused(True)   # Show focus border
        self._focus_border.set_focused(False)  # Hide focus border

    The focus border is implemented by:
    - Setting a blue background color (VSCode blue: rgb(0, 122, 204))
    - Adding a 2px margin to create the border effect
    - The inner container maintains its original appearance

    Note:
        The container passed should be the outer wrapper box, not the
        content container, to ensure the border surrounds the entire view.
    """

    # Default focus color - VSCode blue
    DEFAULT_FOCUS_COLOR = rgb(0, 122, 204)

    # Default border width (margin)
    DEFAULT_BORDER_WIDTH = 2

    def __init__(
        self,
        container: toga.Box,
        color: Optional[rgb] = None,
        border_width: int = DEFAULT_BORDER_WIDTH,
        logger: Optional[logging.Logger] = None
    ):
        """
        Initialize focus border for a container.

        Args:
            container: The outer container box to apply focus border to
            color: Custom focus color (defaults to VSCode blue)
            border_width: Width of focus border in pixels (default: 2)
            logger: Optional logger for debug messages
        """
        self.container = container
        self.color = color or self.DEFAULT_FOCUS_COLOR
        self.border_width = border_width
        self.logger = logger or logging.getLogger(__name__)
        self._focused = False

    @property
    def is_focused(self) -> bool:
        """
        Whether the container currently has focus border showing.

        Returns:
            True if focus border is active, False otherwise
        """
        return self._focused

    def set_focused(self, focused: bool):
        """
        Show or hide the focus border.

        Args:
            focused: True to show focus border, False to hide it
        """
        if focused == self._focused:
            # Already in desired state, no change needed
            return

        self._focused = focused

        if focused:
            # Show focus border
            self.container.style.background_color = self.color
            self.container.style.margin = self.border_width
            self.logger.debug(f"Focus border applied (width={self.border_width}px)")
        else:
            # Remove focus border
            if hasattr(self.container.style, 'background_color'):
                del self.container.style.background_color
            self.container.style.margin = 0
            self.logger.debug("Focus border removed")

    def toggle(self):
        """Toggle focus border on/off"""
        self.set_focused(not self._focused)


__all__ = ['FocusBorder']
