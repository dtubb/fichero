"""
ToolbarMenu - Declarative system for defining toolbar dropdown menus

This is a SEPARATE system from FicheroCommand (per user request).
ToolbarMenus reference FicheroCommands by ID to populate menu items.

Platform support:
- macOS: Full NSMenuToolbarItem integration via rubicon-objc
- Windows/Linux/Mobile: Graceful no-op (commands still accessible via regular menus)
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Literal

logger = logging.getLogger(__name__)


@dataclass
class ToolbarMenu:
    """
    Declarative configuration for a toolbar dropdown menu.

    A toolbar menu is a toolbar button that displays a dropdown menu when clicked.
    The menu items are populated from FicheroCommand IDs, allowing reuse of existing
    command definitions and actions.

    Example:
        view_menu = ToolbarMenu(
            id="toolbar.view_menu",
            label="View",
            icon="resources/icons/view.png",
            display_mode="icon",
            items=["view.toggle_library", "view.toggle_collection", "view.toggle_inspector"],
            order=0,
            context="main",
            platform="darwin"
        )
    """

    id: str
    """Unique identifier for this toolbar menu (e.g., 'toolbar.view_menu')"""

    items: List[str]
    """List of FicheroCommand IDs to include in dropdown menu"""

    label: Optional[str] = None
    """Text label (if shown based on display_mode)"""

    icon: Optional[str] = None
    """Icon name/path from resources (recommended for toolbar)"""

    display_mode: Literal["icon", "text", "both"] = "icon"
    """How to display the toolbar item: icon only, text only, or both"""

    order: int = 0
    """Position in toolbar (0-based, lower numbers appear first)"""

    context: Optional[str] = None
    """When to show (view_id: 'main', 'preview', etc.). None = always show"""

    platform: str = "darwin"
    """Platform restriction ('darwin' for macOS only, 'all' for all platforms)"""

    tooltip: Optional[str] = None
    """Tooltip text (defaults to label if not specified)"""

    def __post_init__(self):
        """Validate configuration"""
        if not self.items:
            raise ValueError(f"ToolbarMenu {self.id} must have at least one item")

        if not self.label and not self.icon:
            raise ValueError(f"ToolbarMenu {self.id} must have either label or icon")

        if self.display_mode not in ["icon", "text", "both"]:
            raise ValueError(f"Invalid display_mode: {self.display_mode}")

        # Set default tooltip
        if not self.tooltip and self.label:
            self.tooltip = self.label

        logger.debug(f"ToolbarMenu created: {self.id} with {len(self.items)} items")

    def __repr__(self) -> str:
        """String representation for debugging"""
        return f"ToolbarMenu(id={self.id}, label={self.label}, items={len(self.items)}, order={self.order})"
