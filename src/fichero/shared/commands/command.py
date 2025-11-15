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
import warnings
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
        # macOS NSToolbar-specific properties
        toolbar_icon: Optional[str] = None,  # SF Symbol name for macOS (e.g., "house.fill", "folder.fill")
        visibility_priority: int = 500,  # NSToolbar visibility priority (0-1000, higher stays visible when window narrow)
        toolbar_style: str = "plain",  # "plain" or "prominent" (prominent = tinted background)
        navigational: bool = False,  # Navigation item behavior (macOS 11+)
        toolbar_bordered: bool = True,  # Border/hover effect on toolbar item
        toolbar_badge_count: Optional[int] = None,  # Badge count for notifications (macOS 14+)
        toolbar_tint_color: Optional[str] = None,  # Custom tint color hex (e.g., "#FF6B35")
        # macOS Titlebar Accessory properties
        show_in_titlebar: bool = False,  # Show as titlebar accessory button (left or right of title)
        titlebar_position: str = "leading",  # "leading" (left) or "trailing" (right) of title
        titlebar_has_menu: bool = False,  # If True, button shows popup menu on click
        titlebar_menu_items: Optional[list] = None,  # List of menu item dicts for popup menu
        # Additional NSToolbar properties
        item_type: str = "button",  # "button", "menu", "group", "search", "space", "flexible_space"
        tooltip: Optional[str] = None,  # Tooltip text for toolbar item
        palette_label: Optional[str] = None,  # Label in customize palette (defaults to label)
        menu_items: Optional[list] = None,  # Menu items for NSMenuToolbarItem (list of dicts with 'label', 'action', 'icon')
        subitems: Optional[list] = None,  # Subitems for NSToolbarItemGroup (list of FicheroCommand instances)
        search_placeholder: Optional[str] = None,  # Placeholder text for NSSearchToolbarItem
        search_action: Optional[Callable] = None,  # Action when search text changes
        shows_menu_indicator: bool = True,  # Show dropdown indicator for menu items (default True)
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
            toolbar_icon: SF Symbol name for macOS toolbar (e.g., "house.fill", "star.fill")
            visibility_priority: NSToolbar visibility priority 0-1000 (higher = stays visible when window narrow, default 500)
            toolbar_style: "plain" or "prominent" (prominent = tinted background, macOS 11+)
            navigational: If True, use navigation item styling (macOS 11+)
            toolbar_bordered: If True, show border/hover effect on toolbar item (default True)
            toolbar_badge_count: Badge count for notifications (macOS 14+, requires NSItemBadge)
            toolbar_tint_color: Custom tint color as hex string (e.g., "#FF6B35" for orange)
            item_type: Type of toolbar item - "button", "menu", "group", "search", "space", "flexible_space"
            tooltip: Tooltip text shown on hover (macOS)
            palette_label: Label shown in toolbar customization palette (defaults to label if not specified)
            menu_items: For item_type="menu" - list of dicts with 'label', 'action', optional 'icon'
            subitems: For item_type="group" - list of FicheroCommand instances to group together
            search_placeholder: For item_type="search" - placeholder text in search field
            search_action: For item_type="search" - callable invoked when search text changes
            shows_menu_indicator: For item_type="menu" - if True, show dropdown arrow indicator
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

        # Add deprecation warning for show_in_toolbar
        if show_in_toolbar:
            warnings.warn(
                f"Parameter 'show_in_toolbar' is deprecated for command '{id}' and will be removed in v2.0. "
                "Use 'show_in_top_toolbar' or 'show_in_bottom_toolbar' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            # Auto-migrate to new parameter if not already set
            if not show_in_top_toolbar and not show_in_bottom_toolbar:
                logger.debug(f"Auto-migrating '{id}': show_in_toolbar → show_in_top_toolbar")
                self.show_in_top_toolbar = True
        self.mobile_only = mobile_only
        self.desktop_only = desktop_only
        self.toolbar_position = toolbar_position
        self.context = context

        # macOS NSToolbar-specific properties
        self.toolbar_icon = toolbar_icon
        self.visibility_priority = visibility_priority
        self.toolbar_style = toolbar_style
        self.navigational = navigational
        self.toolbar_bordered = toolbar_bordered
        self.toolbar_badge_count = toolbar_badge_count
        self.toolbar_tint_color = toolbar_tint_color

        # macOS Titlebar Accessory properties
        self.show_in_titlebar = show_in_titlebar
        self.titlebar_position = titlebar_position
        self.titlebar_has_menu = titlebar_has_menu
        self.titlebar_menu_items = titlebar_menu_items or []

        # Additional NSToolbar properties
        self.item_type = item_type
        self.tooltip = tooltip
        self.palette_label = palette_label or label  # Default to label if not specified
        self.menu_items = menu_items or []
        self.subitems = subitems or []
        self.search_placeholder = search_placeholder
        self.search_action = search_action
        self.shows_menu_indicator = shows_menu_indicator

        # Validate parameters
        VALID_ITEM_TYPES = {"button", "menu", "group", "search", "space", "flexible_space"}
        if item_type not in VALID_ITEM_TYPES:
            raise ValueError(
                f"Invalid item_type '{item_type}' for command '{id}'. "
                f"Must be one of: {', '.join(sorted(VALID_ITEM_TYPES))}"
            )

        # Validate menu items structure (if item_type == "menu")
        if item_type == "menu":
            if not self.menu_items:
                logger.warning(f"Command '{id}' has item_type='menu' but no menu_items provided")
            else:
                for i, item in enumerate(self.menu_items):
                    if not isinstance(item, dict):
                        raise TypeError(
                            f"menu_items[{i}] for command '{id}' must be dict, got {type(item).__name__}"
                        )
                    if 'label' not in item:
                        raise ValueError(f"menu_items[{i}] for command '{id}' missing required key 'label'")
                    if 'action' not in item:
                        raise ValueError(f"menu_items[{i}] for command '{id}' missing required key 'action'")
                    if not callable(item['action']):
                        raise TypeError(
                            f"menu_items[{i}]['action'] for command '{id}' must be callable, "
                            f"got {type(item['action']).__name__}"
                        )

        # Validate subitems structure (if item_type == "group")
        if item_type == "group":
            if not self.subitems:
                logger.warning(f"Command '{id}' has item_type='group' but no subitems provided")
            else:
                for i, subitem in enumerate(self.subitems):
                    if not isinstance(subitem, FicheroCommand):
                        raise TypeError(
                            f"subitems[{i}] for command '{id}' must be FicheroCommand instance, "
                            f"got {type(subitem).__name__}"
                        )

        # Validate search parameters (if item_type == "search")
        if item_type == "search":
            if search_action and not callable(search_action):
                raise TypeError(
                    f"search_action for command '{id}' must be callable, got {type(search_action).__name__}"
                )

        # Reference to toga.Command (set by CommandManager when registered)
        self._toga_command: Optional[Any] = None  # toga.Command or None

        logger.debug(f"Command created: {id} ({label}) [menu={show_in_menu}, section={section}, order={order}, parent={parent}, top_toolbar={show_in_top_toolbar}, bottom_toolbar={show_in_bottom_toolbar}, context={context}, item_type={item_type}]")

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
        """Enable this command and sync with Toga Command if registered."""
        self.enabled = True

        # Also enable the toga.Command if one exists
        if self._toga_command is not None:
            self._toga_command.enabled = True
            logger.debug(f"Command enabled (synced with Toga): {self.id}")
        else:
            logger.debug(f"Command enabled: {self.id}")

    def disable(self):
        """Disable this command and sync with Toga Command if registered."""
        self.enabled = False

        # Also disable the toga.Command if one exists
        if self._toga_command is not None:
            self._toga_command.enabled = False
            logger.debug(f"Command disabled (synced with Toga): {self.id}")
        else:
            logger.debug(f"Command disabled: {self.id}")

    def __repr__(self) -> str:
        """String representation of the command."""
        shortcut_str = f", shortcut={self.shortcut}" if self.shortcut else ""
        icon_str = f", icon={self.icon}" if self.icon else ""
        return f"FicheroCommand(id={self.id}, label={self.label}{shortcut_str}{icon_str})"
