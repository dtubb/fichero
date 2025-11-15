"""
ToolbarMenuManager - Singleton manager for toolbar dropdown menus

Platform-adaptive toolbar menu system:
- macOS: Uses NSMenuToolbarItem via rubicon-objc for native dropdown menus
- Windows/Linux/Mobile: Graceful no-op (commands still in regular menus)

Integration:
- References FicheroCommand by ID (reuses existing command definitions)
- Uses CommandManager to get command instances and actions
- Respects command visibility flags and platform restrictions
"""

import sys
import logging
from typing import Dict, Optional, List, Any
from fichero.shared.commands.toolbar_menu import ToolbarMenu

logger = logging.getLogger(__name__)

# Check platform and rubicon availability
PLATFORM_SUPPORTED = sys.platform == 'darwin'
RUBICON_AVAILABLE = False

if PLATFORM_SUPPORTED:
    try:
        from rubicon.objc import ObjCClass, objc_method, NSObject, at, SEL
        RUBICON_AVAILABLE = True
        logger.info("Rubicon-ObjC available - macOS toolbar menu support enabled")
    except ImportError as e:
        logger.warning(f"Rubicon-ObjC not available - toolbar menus disabled: {e}")


# Define MenuActionHandler class at module level to avoid ObjC class name conflicts
# This class is only created once, not every time _create_action_handler is called
_MenuActionHandler = None
_ToolbarDelegate = None

if RUBICON_AVAILABLE:
    try:
        class MenuActionHandler(NSObject):
            """NSObject subclass for handling menu item actions"""

            command = None  # Will be set per instance

            @objc_method
            def handleAction_(self, sender):
                """Handle menu item selection"""
                try:
                    if self.command:
                        logger.info(f"🎯 Toolbar menu triggered: {self.command.id} ({self.command.label})")
                        self.command.execute(None)
                except Exception as e:
                    logger.error(f"Failed to execute toolbar menu command: {e}")

        _MenuActionHandler = MenuActionHandler
        logger.debug("MenuActionHandler ObjC class registered")

        # Note: NSToolbarDelegate is complex and causes crashes with rubicon-objc
        # Disabling for now - will use manual item insertion instead
        _ToolbarDelegate = None
        # logger.debug("ToolbarDelegate ObjC class registered")
    except Exception as e:
        logger.warning(f"Failed to create ObjC classes: {e}")


class ToolbarMenuManager:
    """
    Platform-adaptive toolbar menu manager (singleton)

    macOS:
      - Creates NSMenuToolbarItem with NSMenu
      - Populates menu items from FicheroCommand IDs
      - Wires actions to FicheroCommand callbacks

    Other platforms:
      - No-op (returns early from all methods)
      - Commands still accessible via regular menus
    """

    _instance: Optional['ToolbarMenuManager'] = None

    def __init__(self, app):
        """Initialize the toolbar menu manager"""
        self.app = app
        self._platform = sys.platform
        self._menus: Dict[str, ToolbarMenu] = {}  # id -> ToolbarMenu
        self._toolbar_items: Dict[str, Any] = {}  # id -> NSToolbarItem (macOS only)
        self._toolbar_delegate = None  # NSToolbarDelegate instance

        # Only initialize rubicon classes on macOS
        if PLATFORM_SUPPORTED and RUBICON_AVAILABLE:
            self._init_objc_classes()
        else:
            logger.info(f"Toolbar menus not supported on platform: {self._platform}")

        logger.info(f"ToolbarMenuManager initialized (platform={self._platform}, supported={PLATFORM_SUPPORTED})")

    def _init_objc_classes(self):
        """Lazy-load ObjC classes (macOS only)"""
        try:
            global NSToolbar, NSToolbarItem, NSMenu, NSMenuItem, NSImage, NSMenuToolbarItem

            NSToolbar = ObjCClass("NSToolbar")
            NSToolbarItem = ObjCClass("NSToolbarItem")
            NSMenu = ObjCClass("NSMenu")
            NSMenuItem = ObjCClass("NSMenuItem")
            NSImage = ObjCClass("NSImage")
            NSMenuToolbarItem = ObjCClass("NSMenuToolbarItem")

            logger.debug("ObjC classes loaded for toolbar menus")
        except Exception as e:
            logger.error(f"Failed to load ObjC classes: {e}")
            raise

    @classmethod
    def get_instance(cls, app=None) -> 'ToolbarMenuManager':
        """Get singleton instance"""
        if cls._instance is None:
            if app is None:
                raise ValueError("First call to get_instance() requires app parameter")
            cls._instance = cls(app)
        return cls._instance

    def register_menu(self, menu: ToolbarMenu) -> None:
        """
        Register a toolbar menu

        Args:
            menu: ToolbarMenu to register

        Platform behavior:
            macOS: Stores menu for toolbar building
            Other: No-op (silent)
        """
        # Check platform compatibility
        if menu.platform != "all" and menu.platform != self._platform:
            logger.debug(f"Skipping menu {menu.id} (platform mismatch: {menu.platform} != {self._platform})")
            return

        # Store menu
        self._menus[menu.id] = menu
        logger.debug(f"Registered toolbar menu: {menu.id}")

    def build_native_toolbar(self, window, view_id: Optional[str] = None, command_manager=None) -> None:
        """
        Build macOS toolbar with menu buttons

        Args:
            window: Toga window to add toolbar to
            view_id: Optional view identifier to filter menus by context
            command_manager: CommandManager instance to get command actions

        Platform behavior:
            macOS: Creates NSMenuToolbarItem for each menu, adds to window.toolbar
                   NOTE: If MacToolbarManager is available, this method delegates to it
            Other: No-op (returns early)
        """
        # Early return on unsupported platforms
        if not PLATFORM_SUPPORTED or not RUBICON_AVAILABLE:
            logger.debug("Skipping toolbar menu building (platform not supported)")
            return

        if not command_manager:
            logger.warning("Cannot build toolbar menus without CommandManager")
            return

        # If MacToolbarManager is available, let it handle the entire toolbar
        # (MacToolbarManager builds both commands AND dropdown menus)
        if hasattr(command_manager, '_mac_toolbar_available') and command_manager._mac_toolbar_available:
            logger.info("MacToolbarManager available - skipping legacy toolbar menu implementation")
            logger.info("Toolbar menus will be built by MacToolbarManager via command_manager.build_native_toolbar()")
            return

        try:
            # Get menus for this context
            menus = self.get_menus_for_context(view_id)

            if not menus:
                logger.debug(f"No toolbar menus to build for view '{view_id}'")
                return

            # Access native window
            if not hasattr(window, '_impl') or not hasattr(window._impl, 'native'):
                logger.warning("Cannot access native window for toolbar menus")
                return

            native_window = window._impl.native

            # Create or get toolbar
            toolbar = native_window.toolbar
            if not toolbar:
                # Create new toolbar
                toolbar_identifier = f"fichero.toolbar.{view_id or 'main'}"
                toolbar = NSToolbar.alloc().initWithIdentifier(toolbar_identifier)
                toolbar.displayMode = 1  # NSToolbarDisplayModeIconOnly (can change per item)
                toolbar.allowsUserCustomization = False  # Disable customization to avoid delegate issues
                toolbar.autosavesConfiguration = False
                native_window.toolbar = toolbar
                logger.debug(f"Created new NSToolbar: {toolbar_identifier}")

            # Build menu items
            for menu in sorted(menus, key=lambda m: m.order):
                self._add_menu_to_toolbar(toolbar, menu, command_manager)

            logger.info(f"✅ Built {len(menus)} toolbar menus for view '{view_id}'")

        except Exception as e:
            logger.error(f"Failed to build native toolbar menus: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _add_menu_to_toolbar(self, toolbar, menu: ToolbarMenu, command_manager) -> None:
        """
        Add a single menu to the toolbar (macOS only)

        Creates NSMenuToolbarItem with dropdown menu - the PROPER way for toolbar menus.
        This uses NSMenuToolbarItem which requires NSToolbarDelegate to provide items.
        """
        try:
            item_identifier = menu.id

            # Create NSMenuToolbarItem (the proper class for toolbar dropdown menus)
            toolbar_item = NSMenuToolbarItem.alloc().initWithItemIdentifier(item_identifier)

            # Set labels
            if menu.label:
                toolbar_item.label = menu.label
                toolbar_item.paletteLabel = menu.label

            # Set tooltip
            if menu.tooltip:
                toolbar_item.toolTip = menu.tooltip

            # Enable the dropdown indicator (the down arrow)
            toolbar_item.showsIndicator = True

            # Enable bordered appearance for hover effect
            toolbar_item.isBordered = True

            # Create NSMenu for the dropdown
            dropdown_menu = NSMenu.alloc().initWithTitle(menu.label or menu.id)

            # Add menu items from command IDs
            for cmd_id in menu.items:
                command = command_manager.get_command(cmd_id)
                if not command:
                    logger.warning(f"Command not found: {cmd_id}")
                    continue

                # Create NSMenuItem
                menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    command.label,
                    SEL("handleAction:"),
                    ""  # No keyboard shortcut in dropdown menu
                )

                # Store command ID for later state updates
                menu_item.representedObject = cmd_id

                # Wire action to command
                action_handler = self._create_action_handler(command)
                if action_handler:
                    menu_item.target = action_handler

                # Set enabled state
                menu_item.enabled = command.enabled

                # Set initial checkmark state for toggle commands
                if cmd_id.startswith('view.toggle_'):
                    is_visible = self._get_column_visibility_for_command(cmd_id)
                    menu_item.state = 1 if is_visible else 0  # 1 = checked, 0 = unchecked

                # Add to menu
                dropdown_menu.addItem(menu_item)
                logger.debug(f"Added menu item: {command.label}")

            # Assign the menu to the toolbar item
            toolbar_item.menu = dropdown_menu

            # Set icon if available (SF Symbols or system icons)
            # For now, skip icon to match Finder's text-only dropdowns

            # Store reference
            self._toolbar_items[menu.id] = toolbar_item

            # Try to add to toolbar using NSToolbarDelegate approach
            # NSMenuToolbarItem requires delegate to provide items
            try:
                # Try to insert item - this may require delegate setup
                toolbar.insertItemWithItemIdentifier_atIndex_(item_identifier, len(list(toolbar.items or [])))
                logger.info(f"✅ Added toolbar menu: {menu.id} with {len(menu.items)} items")
            except Exception as add_error:
                logger.warning(f"Could not add toolbar item directly: {add_error}")
                logger.info(f"Created toolbar menu '{menu.id}' (delegate setup may be required)")

        except Exception as e:
            logger.error(f"Failed to create toolbar menu: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _create_action_handler(self, command):
        """
        Create an action handler object for menu item

        This creates an instance of the module-level MenuActionHandler class
        and sets the command reference on it.
        """
        if not RUBICON_AVAILABLE or _MenuActionHandler is None:
            return None

        try:
            # Create instance of the module-level ObjC class
            handler = _MenuActionHandler.alloc().init()
            # Set the command on this instance
            handler.command = command
            return handler
        except Exception as e:
            logger.error(f"Failed to create action handler for {command.id}: {e}")
            return None

    def get_menus_for_context(self, view_id: Optional[str] = None) -> List[ToolbarMenu]:
        """
        Filter menus by context

        Args:
            view_id: View identifier to filter by context (e.g., "main", "preview")

        Returns:
            List of ToolbarMenu instances for this context
        """
        menus = []

        for menu in self._menus.values():
            # Filter by context
            if menu.context is not None and menu.context != view_id:
                continue

            menus.append(menu)

        logger.debug(f"Found {len(menus)} toolbar menus for context '{view_id}'")
        return menus

    def get_menu(self, menu_id: str) -> Optional[ToolbarMenu]:
        """Get a registered ToolbarMenu by ID"""
        return self._menus.get(menu_id)

    def _get_column_visibility_for_command(self, cmd_id: str) -> bool:
        """
        Get visibility state for a toggle command.

        Args:
            cmd_id: Command ID (e.g., "view.toggle_library")

        Returns:
            True if column is visible, False otherwise
        """
        # Extract column name from command ID
        # "view.toggle_library" -> "Library"
        # "view.toggle_collection" -> "Collection"
        # "view.toggle_inspector" -> "Adjust"
        column_map = {
            'view.toggle_library': 'Library',
            'view.toggle_collection': 'Collection',
            'view.toggle_inspector': 'Adjust'
        }

        column_name = column_map.get(cmd_id)
        if not column_name:
            return False

        # Get layout manager from main window
        try:
            if hasattr(self.app, 'main_window_wrapper') and self.app.main_window_wrapper:
                main_window = self.app.main_window_wrapper
                if hasattr(main_window, 'navigation_controller') and main_window.navigation_controller:
                    nav_controller = main_window.navigation_controller
                    if hasattr(nav_controller, 'layout_manager') and nav_controller.layout_manager:
                        return nav_controller.layout_manager.get_column_visibility(column_name)
        except Exception as e:
            logger.debug(f"Could not get visibility for {column_name}: {e}")

        return True  # Default to visible

    def update_menu_states(self):
        """
        Update checkmark states on all toolbar menus.

        Call this after toggling pane visibility to update the checkmarks.
        """
        if not PLATFORM_SUPPORTED or not RUBICON_AVAILABLE:
            return

        try:
            for menu_id, toolbar_item in self._toolbar_items.items():
                menu = toolbar_item.menu
                if not menu:
                    continue

                # Update each menu item
                for i in range(menu.numberOfItems()):
                    menu_item = menu.itemAtIndex(i)
                    if not menu_item:
                        continue

                    # Get command ID from representedObject
                    cmd_id = menu_item.representedObject
                    if not cmd_id:
                        continue

                    # Update checkmark for toggle commands
                    if cmd_id.startswith('view.toggle_'):
                        is_visible = self._get_column_visibility_for_command(cmd_id)
                        menu_item.state = 1 if is_visible else 0

            logger.debug("Updated toolbar menu states")

        except Exception as e:
            logger.error(f"Failed to update menu states: {e}")


__all__ = ['ToolbarMenuManager', 'PLATFORM_SUPPORTED', 'RUBICON_AVAILABLE']
