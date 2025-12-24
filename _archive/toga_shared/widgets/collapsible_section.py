"""
CollapsibleSection Widget

A reusable collapsible section with disclosure triangle, title, and settings button.
Inspired by Tinderbox's collapsible sections.
"""

import logging
from typing import Optional, Callable

import toga
from toga.style import Pack
from toga.constants import ROW, COLUMN

logger = logging.getLogger(__name__)


class CollapsibleSection:
    """
    Reusable collapsible section with disclosure triangle.

    Structure:
    [Box: container]
      [Box: header_box (grey background)]
        [Button: disclosure_triangle] [Label: title] [spacer] [Button: settings_button]
      [Box: content_box]  # Hidden when collapsed
        ... content widgets ...
    """

    HEADER_HEIGHT = 20  # Compact header
    HEADER_HEIGHT_MOBILE = 32
    DISCLOSURE_EXPANDED = "\u25BE"  # Small down-pointing triangle
    DISCLOSURE_COLLAPSED = "\u25B8"  # Small right-pointing triangle

    def __init__(
        self,
        title: str,
        is_expanded: bool = True,
        show_settings: bool = True,
        show_disclosure: bool = True,
        on_toggle: Optional[Callable[[bool], None]] = None,
        on_settings_clicked: Optional[Callable[[], None]] = None,
        is_mobile: bool = False,
        max_title_length: int = 30
    ):
        """
        Initialize collapsible section.

        Args:
            title: Section title (will be truncated if too long)
            is_expanded: Whether to start expanded
            show_settings: Whether to show settings button
            show_disclosure: Whether to show disclosure triangle
            on_toggle: Callback when expand/collapse state changes
            on_settings_clicked: Callback when settings button clicked
            is_mobile: Whether running on mobile (larger touch targets)
            max_title_length: Max characters before truncating title
        """
        self._full_title = title
        self.title = self._truncate_title(title, max_title_length)
        self._is_expanded = is_expanded
        self.on_toggle = on_toggle
        self.on_settings_clicked = on_settings_clicked
        self.is_mobile = is_mobile
        self.max_title_length = max_title_length
        self.show_disclosure = show_disclosure

        # Compact sizes
        header_height = self.HEADER_HEIGHT_MOBILE if is_mobile else self.HEADER_HEIGHT
        button_width = 32 if is_mobile else 24  # Wider button
        button_height = 24 if is_mobile else 16
        font_size = 10 if is_mobile else 9

        # Create container
        self.container = toga.Box(style=Pack(direction=COLUMN, flex=0))

        # Create header
        self.header_box = toga.Box(style=Pack(
            direction=ROW,
            height=header_height,
            margin=(0, 0, 0, 0)
        ))

        # Title label (on left)
        self.title_label = toga.Label(
            self.title,
            style=Pack(
                font_weight="bold",
                font_size=10 if is_mobile else 9,
                flex=1,
                margin=(3 if is_mobile else 2, 4)
            )
        )

        # Build header: [Title] [... button] [arrow (optional)]
        self.header_box.add(self.title_label)

        # Settings button (using middle dot ellipsis) - wider
        if show_settings:
            self.settings_button = toga.Button(
                "\u22EF",  # Midline horizontal ellipsis (···)
                on_press=self._on_settings_pressed,
                style=Pack(
                    width=button_width,
                    height=button_height,
                    margin=(1, 2),
                    font_size=10
                )
            )
            self.header_box.add(self.settings_button)
        else:
            self.settings_button = None

        # Disclosure arrow (optional, on right as label)
        self.disclosure_label = None
        if show_disclosure:
            self.disclosure_label = toga.Label(
                self.DISCLOSURE_EXPANDED if is_expanded else self.DISCLOSURE_COLLAPSED,
                style=Pack(
                    font_size=font_size,
                    margin=(2, 4),
                    color="#666"
                )
            )
            self.header_box.add(self.disclosure_label)

        # Make header clickable for toggle (wrap in button-like behavior)
        # Since we can't make Box clickable, we'll use the disclosure label area

        # Content box
        self.content_box = toga.Box(style=Pack(direction=COLUMN, flex=0))

        # Build container
        self.container.add(self.header_box)
        self.container.add(self.content_box)

        # Apply initial state
        if not is_expanded:
            self._apply_collapsed_state()

        logger.debug(f"CollapsibleSection '{title}' created, expanded={is_expanded}")

    @property
    def is_expanded(self) -> bool:
        """Get current expanded state."""
        return self._is_expanded

    def set_expanded(self, expanded: bool):
        """
        Set expanded state.

        Args:
            expanded: True to expand, False to collapse
        """
        if self._is_expanded == expanded:
            return

        self._is_expanded = expanded
        if self.disclosure_label:
            self.disclosure_label.text = (
                self.DISCLOSURE_EXPANDED if expanded else self.DISCLOSURE_COLLAPSED
            )

        if expanded:
            self._apply_expanded_state()
        else:
            self._apply_collapsed_state()

        logger.debug(f"CollapsibleSection '{self.title}' set to expanded={expanded}")

        if self.on_toggle:
            self.on_toggle(expanded)

    def _apply_expanded_state(self):
        """Show content box."""
        # Remove height constraint to let content flow naturally
        try:
            if hasattr(self.content_box.style, 'height'):
                del self.content_box.style.height
        except (AttributeError, KeyError):
            pass

        # Make visible
        try:
            if hasattr(self.content_box.style, 'visibility'):
                del self.content_box.style.visibility
        except (AttributeError, KeyError):
            pass

    def _apply_collapsed_state(self):
        """Hide content box."""
        self.content_box.style.height = 0
        self.content_box.style.visibility = "hidden"

    def toggle(self):
        """Toggle expanded state."""
        self.set_expanded(not self._is_expanded)

    def add_content(self, widget: toga.Widget):
        """
        Add widget to content area.

        Args:
            widget: Widget to add
        """
        self.content_box.add(widget)

    def remove_content(self, widget: toga.Widget):
        """
        Remove widget from content area.

        Args:
            widget: Widget to remove
        """
        try:
            self.content_box.remove(widget)
        except ValueError:
            pass  # Widget not in content_box

    def clear_content(self):
        """Remove all content widgets."""
        while len(self.content_box.children) > 0:
            self.content_box.remove(self.content_box.children[0])

    def _truncate_title(self, title: str, max_length: int) -> str:
        """Truncate title with ellipsis if too long."""
        if len(title) <= max_length:
            return title
        return title[:max_length - 1] + "\u2026"  # Ellipsis character

    def set_title(self, title: str):
        """
        Update the section title.

        Args:
            title: New title (will be truncated if too long)
        """
        self._full_title = title
        self.title = self._truncate_title(title, self.max_title_length)
        self.title_label.text = self.title

    def get_full_title(self) -> str:
        """Get the full (non-truncated) title."""
        return self._full_title

    def _on_disclosure_pressed(self, widget):
        """Handle disclosure button press."""
        self.toggle()

    def _on_settings_pressed(self, widget):
        """Handle settings button press."""
        if self.on_settings_clicked:
            self.on_settings_clicked()
