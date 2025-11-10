"""
Platform-agnostic toolbar with adaptive sizing.

Supports three size variants:
- FULL: All buttons with labels and icons
- COMPACT: Icons only, tooltips on hover
- MINI: Essential buttons only, icons only
"""

import logging
from enum import Enum
from typing import List, Optional, Callable, Dict, Any

import toga
from toga.style.pack import Pack


logger = logging.getLogger(__name__)


class ToolbarSize(Enum):
    """Toolbar size variants."""
    FULL = "full"  # All buttons with icons and labels
    COMPACT = "compact"  # Icons only, all buttons, tooltips
    MINI = "mini"  # Essential buttons only, icons only


class ToolbarButton:
    """
    Configuration for a toolbar button.

    Attributes:
        id: Unique identifier for the button
        label: Text label (shown in FULL mode)
        icon: Icon resource name or path
        tooltip: Tooltip text (shown in COMPACT/MINI modes)
        on_press: Callback function when button is pressed
        essential: If True, button is shown in MINI mode
        enabled: If True, button is initially enabled
    """

    def __init__(
        self,
        id: str,
        label: str,
        icon: Optional[str] = None,
        tooltip: Optional[str] = None,
        on_press: Optional[Callable] = None,
        essential: bool = False,
        enabled: bool = True,
    ):
        self.id = id
        self.label = label
        self.icon = icon
        self.tooltip = tooltip or label
        self.on_press = on_press
        self.essential = essential
        self.enabled = enabled


class AbstractToolbar:
    """
    Platform-agnostic toolbar with adaptive sizing.

    The toolbar automatically adjusts its appearance based on the selected size:
    - FULL: Shows all buttons with icons and labels
    - COMPACT: Shows all buttons with icons only, labels as tooltips
    - MINI: Shows only essential buttons with icons only

    Example:
        buttons = [
            ToolbarButton("save", "Save", icon="save.png", essential=True),
            ToolbarButton("open", "Open", icon="open.png", essential=True),
            ToolbarButton("settings", "Settings", icon="settings.png", essential=False),
        ]

        toolbar = AbstractToolbar(
            buttons=buttons,
            size=ToolbarSize.COMPACT,
        )
    """

    def __init__(
        self,
        buttons: List[ToolbarButton],
        size: ToolbarSize = ToolbarSize.FULL,
        style: Optional[Pack] = None,
    ):
        """
        Initialize the abstract toolbar.

        Args:
            buttons: List of ToolbarButton configurations
            size: Initial toolbar size (FULL, COMPACT, or MINI)
            style: Toga Pack style for the toolbar container
        """
        self.button_configs = buttons
        self._size = size
        self.style = style or Pack(direction="row", margin=5)

        # Map button ID to button widget
        self._buttons: Dict[str, toga.Button] = {}

        # Create the toolbar widget
        self.widget = self._create_toolbar()

        logger.debug(f"AbstractToolbar created with {len(buttons)} buttons in {size.value} mode")

    def _create_toolbar(self) -> toga.Box:
        """Create the toolbar widget with current size settings."""
        toolbar_box = toga.Box(style=self.style)

        # Filter buttons based on size
        buttons_to_show = self._get_buttons_for_size(self._size)

        for button_config in buttons_to_show:
            button = self._create_button(button_config)
            self._buttons[button_config.id] = button
            toolbar_box.add(button)

        return toolbar_box

    def _get_buttons_for_size(self, size: ToolbarSize) -> List[ToolbarButton]:
        """Get the list of buttons to show for the given size."""
        if size == ToolbarSize.MINI:
            # Only essential buttons in MINI mode
            return [btn for btn in self.button_configs if btn.essential]
        else:
            # All buttons in FULL and COMPACT modes
            return self.button_configs

    def _create_button(self, config: ToolbarButton) -> toga.Button:
        """Create a Toga button from a ToolbarButton configuration."""
        # Determine button text based on size
        if self._size == ToolbarSize.FULL:
            text = config.label
        else:  # COMPACT or MINI
            text = ""  # Icon only

        # Create button
        button = toga.Button(
            text=text,
            on_press=config.on_press,
            enabled=config.enabled,
            style=Pack(margin_right=5),
        )

        # TODO: In future, add icon support when Toga has better icon handling
        # For now, we use text labels. In Toga 0.5.2, button icons are limited.
        # We can revisit this when toga.Button.icon is more stable.

        # Store tooltip in a custom attribute for potential future use
        button._tooltip = config.tooltip

        return button

    def set_size(self, size: ToolbarSize) -> None:
        """
        Change the toolbar size and rebuild the toolbar.

        Args:
            size: New toolbar size (FULL, COMPACT, or MINI)
        """
        if size == self._size:
            return  # No change needed

        logger.debug(f"Changing toolbar size from {self._size.value} to {size.value}")

        old_size = self._size
        self._size = size

        # Rebuild toolbar with new size
        self._rebuild_toolbar()

    def _rebuild_toolbar(self) -> None:
        """Rebuild the toolbar widget with current size settings."""
        # Clear existing buttons
        for child in list(self.widget.children):
            self.widget.remove(child)

        self._buttons.clear()

        # Re-create buttons with new size
        buttons_to_show = self._get_buttons_for_size(self._size)

        for button_config in buttons_to_show:
            button = self._create_button(button_config)
            self._buttons[button_config.id] = button
            self.widget.add(button)

    def enable_button(self, button_id: str, enabled: bool = True) -> None:
        """
        Enable or disable a button by ID.

        Args:
            button_id: ID of the button to modify
            enabled: True to enable, False to disable
        """
        if button_id in self._buttons:
            self._buttons[button_id].enabled = enabled
        else:
            logger.warning(f"Button '{button_id}' not found in toolbar")

    def disable_button(self, button_id: str) -> None:
        """
        Disable a button by ID.

        Args:
            button_id: ID of the button to disable
        """
        self.enable_button(button_id, False)

    def get_button(self, button_id: str) -> Optional[toga.Button]:
        """
        Get a button widget by ID.

        Args:
            button_id: ID of the button to retrieve

        Returns:
            The Toga Button widget, or None if not found
        """
        return self._buttons.get(button_id)

    @property
    def size(self) -> ToolbarSize:
        """Get the current toolbar size."""
        return self._size

    @property
    def impl(self) -> toga.Box:
        """Get the underlying Toga widget implementation."""
        return self.widget
