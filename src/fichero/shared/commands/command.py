"""
FicheroCommand - Unified command representation

A command encapsulates an action that can be triggered from:
- Native platform menus (desktop with keyboard shortcuts)
- Custom toolbar buttons (both platforms)
- Direct keyboard shortcuts (desktop only)

Platform-adaptive: Commands can be shown in menus, toolbars, or both,
with different behaviors on desktop vs mobile.
"""

import logging
import asyncio
import inspect
from typing import Callable, Optional, Any

logger = logging.getLogger(__name__)


class FicheroCommand:
    """
    Represents a single command in Fichero.

    Commands provide a unified, platform-adaptive way to define actions that can be triggered
    from multiple sources (native menus, custom toolbars, keyboard shortcuts).

    Example:
        rotate_left = FicheroCommand(
            id="output.edit.rotate_left",
            label=_("Rotate Left"),
            action=self._on_rotate_left,
            shortcut=toga.Key.MOD_1 + 'l',  # Cmd+L on Mac, Ctrl+L on Windows/Linux
            icon="resources/icons/rotate_left.png",
            group=toga.Group.EDIT,
            toolbar_text=_("Rotate\\nLeft"),  # Multi-line text for toolbar
            show_in_menu=True,  # Desktop: appears in Edit menu with keyboard shortcut
            show_in_toolbar=True,  # Both platforms: appears in custom toolbar
        )
    """

    def __init__(
        self,
        id: str,
        label: str,
        action: Callable,
        shortcut: Optional[Any] = None,  # toga.Key combination or None
        icon: Optional[str] = None,
        enabled: bool = True,
        description: Optional[str] = None,
        group: Optional[Any] = None,  # toga.Group (EDIT, VIEW, WINDOW, etc.)
        section: int = 0,  # Section within menu group (for ordering, lower = first)
        order: int = 0,  # Order within section (lower = first)
        parent: Optional[str] = None,  # Parent command ID for submenus
        toolbar_text: Optional[str] = None,  # Optional text for toolbar button
        show_in_menu: bool = True,  # Show in native menu (desktop only)
        show_in_toolbar: bool = False,  # Show in custom toolbar (both platforms) - deprecated, use specific toolbar flags
        show_in_top_toolbar: bool = False,  # Show in top toolbar
        show_in_bottom_toolbar: bool = False,  # Show in bottom toolbar
        mobile_only: bool = False,  # Only show on mobile
        desktop_only: bool = False,  # Only show on desktop
        toolbar_position: Optional[str] = None,  # 'left', 'center', 'right'
        context: str = 'normal',  # 'normal', 'edit', or other context
    ):
        """
        Initialize a Fichero command.

        Menu Organization Parameters:
            - group: Which menu (FILE, EDIT, VIEW, WINDOW, etc.)
            - section: Groups commands within a menu (lower numbers first, dividers between sections)
            - order: Position within section (lower numbers first)
            - parent: Parent command ID for creating submenus

        Example menu structure:
            Edit Menu:
                Section 0 (order 0-9):
                    - Undo (section=0, order=0)
                    - Redo (section=0, order=1)
                [divider]
                Section 1 (order 0-9):
                    - Cut (section=1, order=0)
                    - Copy (section=1, order=1)
                    - Paste (section=1, order=2)
                [divider]
                Section 2 (order 0-9):
                    - Rotate ▸ (section=2, order=0, parent=None) [submenu parent]
                        - Rotate Left (section=2, order=0, parent="edit.rotate")
                        - Rotate Right (section=2, order=1, parent="edit.rotate")

        Args:
            id: Unique identifier for this command (e.g., "output.edit.rotate_left")
            label: Human-readable label for menus and tooltips
            action: Callable to execute when command is triggered
            shortcut: Optional keyboard shortcut using toga.Key (e.g., toga.Key.MOD_1 + 'l')
            icon: Optional icon path for toolbar buttons
            enabled: Whether the command is currently enabled
            description: Optional longer description for help text
            group: Optional toga.Group for menu organization (EDIT, VIEW, WINDOW, etc.)
            section: Section number within menu (lower = first, dividers between sections)
            order: Order within section (lower = first, determines exact position)
            parent: Parent command ID for creating submenus (e.g., "edit.rotate" for submenu items)
            toolbar_text: Optional custom text for toolbar button (if different from label)
            show_in_menu: If True, add to native platform menu (desktop only, ignored on mobile)
            show_in_toolbar: DEPRECATED - use show_in_top_toolbar or show_in_bottom_toolbar instead
            show_in_top_toolbar: If True, show in top custom toolbar (can be platform-specific via mobile_only/desktop_only)
            show_in_bottom_toolbar: If True, show in bottom custom toolbar (can be platform-specific via mobile_only/desktop_only)
            mobile_only: If True, only show on mobile platforms
            desktop_only: If True, only show on desktop platforms
            toolbar_position: Position in toolbar - 'left', 'center', 'right' (optional)
            context: Context for when command is shown - 'normal', 'edit', etc.
        """
        self.id = id
        self.label = label
        self.action = action
        self.shortcut = shortcut
        self.icon = icon
        self.enabled = enabled
        self.description = description or label
        self.group = group
        self.section = section
        self.order = order
        self.parent = parent
        self.toolbar_text = toolbar_text or label
        self.show_in_menu = show_in_menu
        self.show_in_toolbar = show_in_toolbar  # Deprecated - use show_in_top_toolbar/show_in_bottom_toolbar
        self.show_in_top_toolbar = show_in_top_toolbar
        self.show_in_bottom_toolbar = show_in_bottom_toolbar
        self.mobile_only = mobile_only
        self.desktop_only = desktop_only
        self.toolbar_position = toolbar_position
        self.context = context

        logger.debug(f"Command created: {id} ({label}) [menu={show_in_menu}, section={section}, order={order}, parent={parent}, top_toolbar={show_in_top_toolbar}, bottom_toolbar={show_in_bottom_toolbar}, context={context}]")

    def execute(self, *args, **kwargs) -> Any:
        """
        Execute the command's action.

        Handles both sync and async actions automatically.

        Args:
            *args: Positional arguments to pass to the action
            **kwargs: Keyword arguments to pass to the action

        Returns:
            Result of the action, if any

        Raises:
            Exception: If the command is disabled or action fails
        """
        if not self.enabled:
            logger.warning(f"⚠️ Attempted to execute disabled command: {self.id}")
            return None

        try:
            logger.info(f"⚡ Executing command action: {self.id} ({self.label})")

            # Check if action is a coroutine function (async)
            if inspect.iscoroutinefunction(self.action):
                # Create task to run async action
                result = asyncio.create_task(self.action(*args, **kwargs))
                logger.info(f"✅ Async command scheduled: {self.id}")
            else:
                # Regular synchronous action
                result = self.action(*args, **kwargs)
                logger.info(f"✅ Command completed: {self.id}")

            return result
        except Exception as e:
            logger.error(f"❌ Error executing command {self.id}: {e}")
            raise

    def enable(self):
        """Enable this command."""
        self.enabled = True
        logger.debug(f"Command enabled: {self.id}")

    def disable(self):
        """Disable this command."""
        self.enabled = False
        logger.debug(f"Command disabled: {self.id}")

    def __repr__(self) -> str:
        """String representation of the command."""
        shortcut_str = f", shortcut={self.shortcut}" if self.shortcut else ""
        icon_str = f", icon={self.icon}" if self.icon else ""
        return f"FicheroCommand(id={self.id}, label={self.label}{shortcut_str}{icon_str})"
