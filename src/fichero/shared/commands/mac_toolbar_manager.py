"""
MacToolbarManager - macOS NSToolbar integration for Fichero

Provides full NSToolbar support with dropdown menus, customization, and autosave.
Integrates seamlessly with Fichero's command system.

Features:
- NSMenuToolbarItem (dropdown menus)
- NSSearchToolbarItem (search bars)
- NSToolbarItemGroup (grouped items)
- NSTrackingSeparatorToolbarItem (split view tracking)
- SF Symbols icons
- Toolbar customization (drag to reorder)
- Autosave configuration (persists between launches)
- Visibility priority (smart overflow)
- Badges, styles, colors
"""

import sys
import logging
from typing import Dict, List, Optional, Any, Tuple, Callable

logger = logging.getLogger(__name__)

# Platform check
PLATFORM_SUPPORTED = sys.platform == 'darwin'
RUBICON_AVAILABLE = False

if PLATFORM_SUPPORTED:
    try:
        from rubicon.objc import ObjCClass, objc_method, NSObject, SEL, at, NSArray, NSSize
        RUBICON_AVAILABLE = True
        logger.info("Rubicon-ObjC available - macOS NSToolbar support enabled")
    except ImportError as e:
        logger.warning(f"Rubicon-ObjC not available - macOS NSToolbar disabled: {e}")


# Module-level ObjC classes (created once)
_MacToolbarDelegate = None
_ActionHandler = None

if RUBICON_AVAILABLE:
    try:
        class MacToolbarDelegate(NSObject):
            """
            NSToolbar delegate for Fichero

            Implements the required delegate methods for NSToolbar:
            - toolbarDefaultItemIdentifiers_: Returns default items
            - toolbarAllowedItemIdentifiers_: Returns all available items
            - toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_: Creates items
            """

            # Class-level attributes (like the working demo)
            toolbar_items = {}
            command_handlers = {}
            menu_handlers = {}

            @objc_method
            def toolbarDefaultItemIdentifiers_(self, toolbar):
                """Return default item IDs in explicit order (like ULTIMATE demo)"""
                layout = [
                    "view.toggle_sidebar",       # Library - leftmost
                    "view.toggle_collection",    # Collection
                    "library.new_collection",    # New Collection button
                    "collection.import",         # Import dropdown menu
                    "NSToolbarFlexibleSpaceItem",
                    "library.search",            # Search field
                    "library.settings",          # Settings
                    "library.inspector",         # Show Inspector (desktop)
                    "collection.process",        # Process
                    "view.toggle_inspector",     # Adjust - far right
                ]

                # Debug: Log what's in toolbar_items
                logger.info(f"🔍 toolbar_items keys: {list(self.toolbar_items.keys())}")
                if "library.search" in self.toolbar_items:
                    logger.info(f"✅ library.search IS in toolbar_items")
                else:
                    logger.error(f"❌ library.search NOT in toolbar_items!")
                logger.info(f"🔍 Returning default layout: {layout}")

                # Use explicit layout as-is - NSToolbar will handle missing items
                # Don't filter based on toolbar_items because this method may be called
                # before all items are added (timing issue)
                item_ids = layout.copy()

                logger.debug(f"Using explicit layout: {item_ids}")

                # Add any remaining items not in our explicit list (at the end)
                # This catches any new commands added dynamically
                remaining = []
                for item_id in self.toolbar_items.keys():
                    if item_id not in item_ids:
                        remaining.append(item_id)
                        item_ids.append(item_id)

                if remaining:
                    logger.debug(f"Adding remaining items at end: {remaining}")

                logger.debug(f"NSToolbar final item order: {item_ids}")
                return at(item_ids)

            @objc_method
            def toolbarAllowedItemIdentifiers_(self, toolbar):
                """Return all item IDs available for customization"""
                allowed = list(self.toolbar_items.keys()) + [
                    "NSToolbarSpaceItem",
                    "NSToolbarFlexibleSpaceItem"
                ]
                logger.debug(f"NSToolbar calling toolbarAllowedItemIdentifiers: {len(allowed)} items")
                return at(allowed)

            @objc_method
            def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
                self, toolbar, identifier, insert: bool
            ):
                """Create and return toolbar item for identifier"""
                id_str = str(identifier)
                logger.info(f"🔍 NSToolbar requesting item: '{id_str}'")

                # Special handling for search items - NSSearchToolbarItem might need fresh creation
                if 'search' in id_str.lower():
                    logger.info(f"🔍 SPECIAL: Creating NSSearchToolbarItem dynamically for: {id_str}")
                    # Try to get from cache first
                    if id_str in self.toolbar_items:
                        cached_item = self.toolbar_items[id_str]
                        logger.info(f"✅ Found cached search item: {cached_item}")
                        return cached_item
                    else:
                        logger.error(f"❌ Search item not in cache, can't create dynamically without command")
                        return None

                # Standard items - return from cache
                if id_str in self.toolbar_items:
                    item = self.toolbar_items[id_str]
                    logger.info(f"✅ Returning item for: {id_str} (type: {type(item).__name__})")
                    return item

                logger.warning(f"Toolbar item not found: {id_str}")
                return None

            @objc_method
            def handleCommand_(self, sender):
                """
                Handle toolbar button clicks (following FICHERO_COMMAND_TOOLBAR_DEMO pattern)

                This is called when a toolbar item is clicked (target set to delegate)
                """
                # Get item identifier from sender
                item_id = str(sender.itemIdentifier)
                logger.debug(f"Toolbar button clicked: {item_id}")

                # Find and execute command
                command = self.command_handlers.get(item_id)
                if command:
                    try:
                        logger.info(f"Executing toolbar command: {command.id}")
                        command.execute(sender)
                    except Exception as e:
                        logger.error(f"Failed to execute command {item_id}: {e}")
                else:
                    logger.warning(f"No command found for toolbar item: {item_id}")

            # REMOVED validateToolbarItem_ - Following FICHERO_COMMAND_TOOLBAR_DEMO pattern
            # That demo has NO validation method and items work fine!
            # macOS defaults all toolbar items to enabled unless explicitly disabled

        class ActionHandler(NSObject):
            """Handler for toolbar/menu item actions"""

            @objc_method
            def handleAction_(self, sender):
                """Handle toolbar/menu action"""
                if hasattr(self, '_cmd') and self._cmd:
                    try:
                        logger.info(f"Toolbar action: {self._cmd.id} ({self._cmd.label})")
                        self._cmd.execute(sender)
                    except Exception as e:
                        logger.error(f"Failed to execute command {self._cmd.id}: {e}")

            @objc_method
            def validateToolbarItem_(self, item) -> bool:
                """
                Validate toolbar item (called by macOS when target implements NSToolbarItemValidation)

                This method is called on the item's target to determine if it should be enabled.
                """
                item_id = str(item.itemIdentifier)  # Property, not method
                logger.debug(f"ActionHandler.validateToolbarItem_ called for: {item_id}")
                if hasattr(self, '_cmd') and self._cmd:
                    enabled = self._cmd.enabled
                    logger.debug(f"Command: {self._cmd.id}, enabled={enabled}")
                    return enabled
                logger.debug(f"No command found for {item_id}, defaulting to True")
                return True

        class TitlebarMenuHandler(NSObject):
            """Handler for titlebar popup menu items"""
            _cmd_action = None  # Standardized naming to match _cmd convention

            @objc_method
            def handleMenuAction_(self, sender):
                """Handle menu item action"""
                logger.debug(f"Titlebar menu item clicked")
                if self._cmd_action:
                    try:
                        self._cmd_action(sender)
                    except Exception as e:
                        logger.error(f"Error executing menu action: {e}")
                        import traceback
                        traceback.print_exc()

        _MacToolbarDelegate = MacToolbarDelegate
        _ActionHandler = ActionHandler
        _TitlebarMenuHandler = TitlebarMenuHandler
        logger.debug("MacToolbarDelegate, ActionHandler, and TitlebarMenuHandler ObjC classes registered")

    except Exception as e:
        logger.error(f"Failed to create ObjC classes: {e}")


class MacToolbarManager:
    """
    macOS NSToolbar manager for Fichero

    Replaces Toga's NSToolbar with our own, enabling:
    - Dropdown menus (NSMenuToolbarItem)
    - Search bars (NSSearchToolbarItem)
    - Grouped items (NSToolbarItemGroup)
    - Customization and autosave
    - All NSToolbar features

    Usage:
        manager = MacToolbarManager(app, window)
        manager.build_toolbar(command_manager, toolbar_menus)
    """

    # NSToolbar display modes
    DISPLAY_MODE_ICON_AND_LABEL = 0
    DISPLAY_MODE_ICON_ONLY = 1
    DISPLAY_MODE_LABEL_ONLY = 2

    # NSToolbarItem styles
    TOOLBAR_STYLE_PLAIN = 0
    TOOLBAR_STYLE_PROMINENT = 1

    # NSTitlebarAccessoryViewController layout
    TITLEBAR_LAYOUT_LEADING = 5
    TITLEBAR_LAYOUT_TRAILING = 6

    # NSButton styles
    BUTTON_BEZEL_ROUNDED = 0
    BUTTON_TYPE_MOMENTARY = 0

    def __init__(self, app: Any, window: Optional[Any] = None) -> None:
        """
        Initialize Mac toolbar manager

        Args:
            app: Toga application instance
            window: Optional Toga window (can be set later)
        """
        self.app = app
        self.window = window
        self._toolbar = None
        self._delegate = None
        self._toolbar_id = "fichero.main.toolbar"
        self._toolbar_initialized = False  # Track if toolbar was created
        self._current_view_id = None  # Track current view
        self._all_items = {}  # Cache of all toolbar items across all views
        self._all_command_handlers = {}  # Cache of all command handlers
        self._all_menu_handlers = {}  # Cache of all menu handlers

        # Load ObjC classes
        if RUBICON_AVAILABLE:
            self._load_objc_classes()
        else:
            logger.warning("MacToolbarManager initialized but rubicon-objc not available")

    def _load_objc_classes(self) -> None:
        """Load ObjC classes needed for toolbar"""
        try:
            global NSToolbar, NSToolbarItem, NSMenuToolbarItem, NSSearchToolbarItem
            global NSToolbarItemGroup, NSTrackingSeparatorToolbarItem
            global NSMenu, NSMenuItem, NSImage, NSColor

            NSToolbar = ObjCClass("NSToolbar")
            NSToolbarItem = ObjCClass("NSToolbarItem")
            NSMenuToolbarItem = ObjCClass("NSMenuToolbarItem")
            NSSearchToolbarItem = ObjCClass("NSSearchToolbarItem")
            NSToolbarItemGroup = ObjCClass("NSToolbarItemGroup")
            NSTrackingSeparatorToolbarItem = ObjCClass("NSTrackingSeparatorToolbarItem")
            NSMenu = ObjCClass("NSMenu")
            NSMenuItem = ObjCClass("NSMenuItem")
            NSImage = ObjCClass("NSImage")
            NSColor = ObjCClass("NSColor")

            # Try to load NSItemBadge (macOS 14+)
            try:
                global NSItemBadge
                NSItemBadge = ObjCClass("NSItemBadge")
                self._badge_available = True
                logger.debug("NSItemBadge available (macOS 14+)")
            except:
                self._badge_available = False
                logger.debug("NSItemBadge not available (requires macOS 14+)")

            logger.debug("ObjC classes loaded for NSToolbar")

        except Exception as e:
            logger.error(f"Failed to load ObjC classes: {e}")
            raise

    def replace_toga_toolbar(self) -> None:
        """Remove Toga's NSToolbar from window"""
        if not RUBICON_AVAILABLE or not self.window:
            return

        try:
            native_window = self.window._impl.native
            old_toolbar = native_window.toolbar

            if old_toolbar:
                logger.info(f"Removing Toga toolbar: {old_toolbar} (identifier: {old_toolbar.identifier if hasattr(old_toolbar, 'identifier') else 'N/A'})")
                native_window.setToolbar(None)
                logger.debug("Toolbar removed successfully")
            else:
                logger.debug("No Toga toolbar to remove")

        except Exception as e:
            logger.error(f"Failed to remove Toga toolbar: {e}")

    def build_toolbar(
        self,
        command_manager,
        toolbar_menus=None,
        toolbar_id: Optional[str] = None,
        view_id: Optional[str] = None,
        context: str = 'normal',
        allow_customization: bool = True,
        autosave: bool = True
    ):
        """
        Build or update macOS NSToolbar from FicheroCommands and ToolbarMenus

        On first call: Creates the NSToolbar once
        On subsequent calls: Updates toolbar items without rebuilding

        Args:
            command_manager: CommandManager instance
            toolbar_menus: Optional list of ToolbarMenu instances for dropdowns
            toolbar_id: Unique toolbar identifier (for autosave)
            view_id: Optional view ID for filtering commands
            context: Context for filtering commands (e.g., "normal", "edit")
            allow_customization: Enable drag-to-reorder customization
            autosave: Save toolbar layout between launches
        """
        if not RUBICON_AVAILABLE or not self.window:
            logger.warning("Cannot build toolbar: rubicon not available or no window")
            logger.error(f"MacToolbarManager: Cannot build toolbar (rubicon={RUBICON_AVAILABLE}, window={self.window is not None})")
            return

        try:
            # On first call: Create delegate FIRST, then items, then initialize toolbar
            if not self._toolbar_initialized:
                logger.debug(f"MacToolbarManager.build_toolbar() - FIRST TIME for view '{view_id}'")

                # STEP 1: Create delegate FIRST (so self._delegate exists for item creation)
                logger.debug("Creating delegate...")
                self._delegate = _MacToolbarDelegate.alloc().init()
                logger.debug(f"Delegate created: {self._delegate}")

                # STEP 2: Get commands and create items (delegate now exists!)
                logger.debug("Getting initial toolbar commands...")
                commands = command_manager.get_toolbar_commands(
                    view_id=view_id,
                    context=context,
                    toolbar_type="native"
                )
                logger.debug(f"Found {len(commands)} commands for initial toolbar")

                # Create items (delegate exists now, so target will be set correctly)
                for command in commands:
                    # 🔍 DEBUG POINT 5: Log search command item creation attempt
                    if command.id.endswith('.search'):
                        logger.info(f"🔍 ATTEMPTING TO CREATE SEARCH ITEM: {command.id}, type={command.item_type}")

                    item = self._create_toolbar_item(command)
                    if item:
                        self._all_items[command.id] = item
                        self._all_command_handlers[command.id] = command
                        logger.debug(f"Pre-created item for: {command.id}")

                        # 🔍 DEBUG POINT 6: Log search item creation success
                        if command.id.endswith('.search'):
                            logger.info(f"✅ SEARCH ITEM CREATED SUCCESSFULLY: {command.id}")
                    elif command.id.endswith('.search'):
                        logger.error(f"❌ SEARCH ITEM CREATION FAILED: {command.id}")

                # Create dropdown menus if provided
                if toolbar_menus:
                    for menu in toolbar_menus:
                        menu_item, handlers = self._create_dropdown_menu(menu, command_manager)
                        if menu_item:
                            self._all_items[menu.id] = menu_item
                            self._all_menu_handlers[menu.id] = handlers
                            logger.debug(f"Pre-created menu for: {menu.id}")

                # STEP 3: Initialize toolbar with delegate and items
                self._initialize_toolbar(
                    toolbar_id=toolbar_id,
                    allow_customization=allow_customization,
                    autosave=autosave,
                    initial_items=self._all_items.copy(),  # Pass initial items
                    initial_command_handlers=self._all_command_handlers.copy(),
                    initial_menu_handlers=self._all_menu_handlers.copy(),
                    command_manager=command_manager  # Pass command_manager for titlebar accessories
                )

                # Track current view
                self._current_view_id = view_id

            else:
                # Subsequent calls: Update items dynamically
                self.update_toolbar_items(
                    command_manager=command_manager,
                    toolbar_menus=toolbar_menus,
                    view_id=view_id,
                    context=context
                )

        except Exception as e:
            logger.error(f"Failed to build/update macOS toolbar: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _initialize_toolbar(
        self,
        toolbar_id: Optional[str] = None,
        allow_customization: bool = True,
        autosave: bool = True,
        initial_items: Optional[Dict] = None,
        initial_command_handlers: Optional[Dict] = None,
        initial_menu_handlers: Optional[Dict] = None,
        command_manager = None
    ):
        """
        Initialize the NSToolbar (called only once)

        Args:
            toolbar_id: Unique toolbar identifier (for autosave)
            allow_customization: Enable drag-to-reorder customization
            autosave: Save toolbar layout between launches
            initial_items: Pre-created toolbar items to start with
            initial_command_handlers: Pre-created command handlers
            initial_menu_handlers: Pre-created menu handlers
        """
        logger.debug("MacToolbarManager._initialize_toolbar()")
        logger.debug(f"window={self.window.title}, toolbar_id={toolbar_id}")
        logger.debug(f"initial_items={len(initial_items) if initial_items else 0}")
        logger.info(f"Initializing macOS NSToolbar for window: {self.window.title}")

        # Remove Toga's toolbar (only needed once)
        self.replace_toga_toolbar()

        # Set toolbar identifier
        if toolbar_id:
            self._toolbar_id = toolbar_id

        # Delegate already created in build_toolbar() - just initialize its attributes
        # Initialize delegate attributes BEFORE setting it on toolbar
        # (macOS will immediately call delegate methods when we set the delegate)
        # Use initial items if provided, otherwise empty
        self._delegate.toolbar_items = initial_items or {}
        self._delegate.command_handlers = initial_command_handlers or {}
        self._delegate.menu_handlers = initial_menu_handlers or {}
        logger.debug(f"Delegate initialized with {len(self._delegate.toolbar_items)} items")

        # Create NSToolbar (only once)
        logger.debug(f"Creating NSToolbar with ID: {self._toolbar_id}")
        toolbar = NSToolbar.alloc().initWithIdentifier(self._toolbar_id)
        toolbar.setDelegate(self._delegate)
        logger.debug("Delegate set on toolbar")

        # Configure toolbar
        toolbar.setAllowsUserCustomization(allow_customization)
        toolbar.setAutosavesConfiguration(autosave)
        toolbar.setDisplayMode(self.DISPLAY_MODE_ICON_AND_LABEL)
        logger.debug(f"Toolbar configured (customization={allow_customization}, autosave={autosave})")
        logger.info(f"Toolbar customization: {allow_customization}, autosave: {autosave}")

        # Set toolbar on window
        native_window = self.window._impl.native
        native_window.setToolbar(toolbar)
        logger.debug("Toolbar set on window")

        # Set centered item identifier (optional - allows items left of center)
        # This makes sidebar toggle appear to the left of the window title
        # We don't set a specific item as centered, which lets the system handle title placement
        # Items will flow: [Library] [window title] [Collection] [Adjust] [...]
        try:
            # Leave centeredItemIdentifier unset - toolbar items before title, after title flows naturally
            pass  # NSToolbar automatically handles title placement
        except Exception as e:
            logger.debug(f"Could not configure centered item: {e}")

        # Ensure toolbar is visible
        toolbar.setVisible(True)
        logger.debug("Toolbar visibility set to True")

        # Verify toolbar was set
        current_toolbar = native_window.toolbar
        if current_toolbar == toolbar:
            logger.debug("Toolbar successfully attached to window")
        else:
            logger.warning(f"WARNING: Toolbar mismatch! Expected {toolbar}, got {current_toolbar}")

        # Keep reference
        self._toolbar = toolbar
        self._toolbar_initialized = True

        # EXPERIMENTAL: Try manually inserting search item if it wasn't requested by delegate
        # NSToolbar seems to skip search items in the delegate flow
        try:
            search_identifier = "library.search"
            if search_identifier in self._delegate.toolbar_items:
                logger.info(f"🔬 EXPERIMENTAL: Attempting to manually insert search item at index 5")
                toolbar.insertItemWithItemIdentifier_atIndex_(search_identifier, 5)
                logger.info(f"✅ Successfully inserted search item programmatically")
            else:
                logger.warning(f"Search item not in delegate's toolbar_items, skipping manual insertion")
        except Exception as e:
            logger.warning(f"Could not manually insert search item: {e}")

        # Explicitly validate toolbar items to fix greyed out state
        logger.debug("Validating toolbar items...")
        try:
            # Force validation by calling validateVisibleItems
            toolbar.validateVisibleItems()
            logger.debug("Toolbar items validated")
        except Exception as e:
            logger.warning(f"Could not validate toolbar items: {e}")

        # Add titlebar accessories from ALL commands (not just filtered ones)
        # Query CommandManager for all commands with show_in_titlebar=True
        if command_manager:
            logger.debug("Looking for titlebar commands...")
            # Get ALL registered commands
            all_commands = command_manager.registry.list_all()
            logger.debug(f"Total registered commands: {len(all_commands)}")

            # Filter for titlebar commands (no view_id filtering)
            titlebar_commands = [
                cmd for cmd in all_commands
                if getattr(cmd, 'show_in_titlebar', False)
            ]
            logger.debug(f"Found {len(titlebar_commands)} titlebar commands: {[cmd.id for cmd in titlebar_commands]}")

            if titlebar_commands:
                # Clear pending queue BEFORE adding to prevent duplicates
                command_manager._pending_titlebar_commands.clear()
                logger.debug("Cleared pending titlebar commands (will be added from registry)")
                self._add_titlebar_accessories(titlebar_commands)

        # Process any titlebar commands that were registered before initialization
        # NOTE: Should be empty now since we cleared the queue above
        if command_manager:
            window_id = id(self.window)
            command_manager._process_pending_titlebar_commands(window_id)
            logger.debug("Processed pending titlebar commands (should be none)")

        logger.info("MacOS NSToolbar initialized successfully")

    def update_toolbar_items(
        self,
        command_manager: Any,
        toolbar_menus=None,
        view_id: Optional[str] = None,
        context: str = 'normal'
    ):
        """
        Update toolbar items for a given view without rebuilding the toolbar

        Args:
            command_manager: CommandManager instance
            toolbar_menus: Optional list of ToolbarMenu instances for dropdowns
            view_id: Optional view ID for filtering commands
            context: Context for filtering commands (e.g., "normal", "edit")
        """
        if not self._toolbar_initialized:
            logger.error("Cannot update toolbar items - toolbar not initialized")
            return

        logger.info("MacToolbarManager.update_toolbar_items()")
        logger.debug(f"view_id={view_id}, context={context}")
        logger.info(f"Updating toolbar items for view_id='{view_id}', context='{context}'")

        # Track current view
        self._current_view_id = view_id

        # Get commands for this view
        logger.debug("Getting toolbar commands...")
        commands = command_manager.get_toolbar_commands(
            view_id=view_id,
            context=context,
            toolbar_type="native"
        )
        logger.debug(f"Found {len(commands)} commands for view '{view_id}'")
        if commands:
            logger.debug(f"Command IDs: {[c.id for c in commands]}")
        logger.info(f"Found {len(commands)} commands for native toolbar (view_id='{view_id}', context='{context}')")

        # Create/update toolbar items from commands
        logger.debug("Creating/updating toolbar items...")
        for command in commands:
            # Only create if not already cached
            if command.id not in self._all_items:
                item = self._create_toolbar_item(command)
                if item:
                    self._all_items[command.id] = item
                    self._all_command_handlers[command.id] = command
                    logger.debug(f"Created NEW item for: {command.id}")
                else:
                    logger.warning(f"Failed to create item for: {command.id}")
            else:
                logger.debug(f"Using cached item for: {command.id}")

        # Add dropdown menus if provided
        if toolbar_menus:
            for menu in toolbar_menus:
                if menu.id not in self._all_items:
                    menu_item, handlers = self._create_dropdown_menu(menu, command_manager)
                    if menu_item:
                        self._all_items[menu.id] = menu_item
                        self._all_menu_handlers[menu.id] = handlers
                        logger.debug(f"Created NEW menu for: {menu.id}")

        # Build items dict for current view
        current_view_items = {}
        current_command_handlers = {}
        current_menu_handlers = {}

        for command in commands:
            if command.id in self._all_items:
                current_view_items[command.id] = self._all_items[command.id]
                current_command_handlers[command.id] = self._all_command_handlers.get(command.id)

        if toolbar_menus:
            for menu in toolbar_menus:
                if menu.id in self._all_items:
                    current_view_items[menu.id] = self._all_items[menu.id]
                    current_menu_handlers[menu.id] = self._all_menu_handlers.get(menu.id)

        # Update delegate with current view's items
        logger.debug(f"Updating delegate with {len(current_view_items)} items for view '{view_id}'...")
        self._delegate.toolbar_items = current_view_items
        self._delegate.command_handlers = current_command_handlers
        self._delegate.menu_handlers = current_menu_handlers
        logger.info(f"Updated delegate with {len(current_view_items)} toolbar items")

        # Force toolbar to refresh its items
        # Note: NSToolbar doesn't automatically refresh when delegate items change
        # For now, just update the delegate and rely on macOS autosave/restore
        # A full refresh would require recreating the toolbar
        if self._toolbar:
            logger.debug("Toolbar delegate updated (items will appear on next launch due to autosave)")
            logger.debug("Toolbar delegate updated with new items")

        logger.info(f"Toolbar updated with {len(current_view_items)} items for view '{view_id}'")

    def initialize_empty_toolbar(self, toolbar_id: Optional[str] = None) -> None:
        """
        Initialize an empty NSToolbar (like how app.commands starts empty).

        Items will be added dynamically as commands are registered.

        Args:
            toolbar_id: Unique toolbar identifier (for autosave)
        """
        if self._toolbar_initialized:
            logger.debug("Toolbar already initialized")
            return

        logger.debug("MacToolbarManager.initialize_empty_toolbar()")
        logger.debug(f"window={self.window.title}, toolbar_id={toolbar_id}")
        logger.info(f"Initializing empty NSToolbar for window: {self.window.title}")

        # Remove Toga's toolbar
        self.replace_toga_toolbar()

        # Set toolbar identifier
        if toolbar_id:
            self._toolbar_id = toolbar_id

        # Create delegate
        logger.debug("Creating NSToolbar delegate")
        self._delegate = _MacToolbarDelegate.alloc().init()

        # Initialize delegate with empty items (items will be added dynamically)
        self._delegate.toolbar_items = {}
        self._delegate.command_handlers = {}
        self._delegate.menu_handlers = {}
        logger.debug("Delegate initialized with 0 items (will add dynamically)")

        # Create NSToolbar
        logger.debug(f"Creating empty NSToolbar with ID: {self._toolbar_id}")
        toolbar = NSToolbar.alloc().initWithIdentifier(self._toolbar_id)
        toolbar.setDelegate(self._delegate)
        logger.debug("Delegate set on toolbar")

        # Configure toolbar
        toolbar.setAllowsUserCustomization(True)
        toolbar.setAutosavesConfiguration(True)
        toolbar.setDisplayMode(self.DISPLAY_MODE_ICON_AND_LABEL)
        logger.debug("Toolbar configured")

        # Set toolbar on window
        native_window = self.window._impl.native
        native_window.setToolbar(toolbar)
        logger.debug("Toolbar set on window")

        # Ensure toolbar is visible
        toolbar.setVisible(True)
        logger.debug("Toolbar visibility set to True")

        # Keep reference
        self._toolbar = toolbar
        self._toolbar_initialized = True

        logger.info("Empty NSToolbar initialized (items will be added dynamically)")

    def add_toolbar_item(self, command: Any) -> None:
        """
        Add a single toolbar item dynamically (like adding to app.commands).

        Args:
            command: FicheroCommand to add as toolbar item
        """
        if not self._toolbar_initialized:
            logger.error(f"Cannot add toolbar item - toolbar not initialized")
            return

        try:
            logger.debug(f"Adding toolbar item: {command.id}")

            # Create toolbar item
            item = self._create_toolbar_item(command)
            if not item:
                logger.warning(f"Failed to create item for: {command.id}")
                return

            # Add to caches
            self._all_items[command.id] = item
            self._all_command_handlers[command.id] = command

            # Update delegate
            self._delegate.toolbar_items[command.id] = item
            self._delegate.command_handlers[command.id] = command

            logger.debug(f"Added toolbar item: {command.id}")
            logger.info(f"Added toolbar item: {command.id}")

            # Force toolbar to refresh by toggling autosave
            if self._toolbar:
                self._toolbar.setAutosavesConfiguration(False)
                self._toolbar.setAutosavesConfiguration(True)

        except Exception as e:
            logger.error(f"Failed to add toolbar item {command.id}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    def _set_item_labels_and_tooltip(self, item: Any, command: Any) -> None:
        """
        Set common labels and tooltip for toolbar item

        Args:
            item: NSToolbarItem (or subclass) to configure
            command: FicheroCommand with label/tooltip data
        """
        item.setLabel(command.toolbar_text or command.label)
        item.setPaletteLabel(command.palette_label or command.label)
        tooltip_text = command.tooltip or command.description or command.label
        item.setToolTip(tooltip_text)

    def _load_icon(self, icon_path: str, label: str, for_menu: bool = False) -> Optional[Any]:
        """
        Load icon from file path or SF Symbol name

        Args:
            icon_path: File path to PNG/JPEG or SF Symbol name
            label: Label for accessibility description
            for_menu: If True, resize to 20x20 for NSMenuToolbarItem

        Returns:
            NSImage or None
        """
        import os
        from pathlib import Path
        from rubicon.objc import NSSize

        logger.debug(f"🎨 _load_icon() START for: '{icon_path}' (label: '{label}', for_menu: {for_menu})")

        # Try loading as file first (PNG, JPEG, etc.)
        if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff')):
            logger.debug(f"   Detected as FILE path (contains '/' or file extension)")
            # Validate path to prevent path traversal attacks
            try:
                app_base_path = Path(self.app.paths.app).resolve()
            except Exception as e:
                logger.warning(f"Could not resolve app base path: {e}")
                app_base_path = None
            # It's a file path - try multiple possible locations
            possible_paths = [
                icon_path,  # Absolute path
                os.path.join(os.getcwd(), icon_path),  # Relative to CWD
                Path(self.app.paths.app) / icon_path,  # Relative to app
                os.path.join(os.path.dirname(__file__), icon_path),  # Relative to this file
                os.path.join(os.path.dirname(__file__), '..', '..', icon_path),  # Up two levels
            ]

            logger.debug(f"   Trying {len(possible_paths)} possible file paths...")
            for i, path in enumerate(possible_paths):
                logger.debug(f"   [{i+1}/{len(possible_paths)}] Checking: {path}")
                if os.path.exists(str(path)):
                    logger.debug(f"   ✓ File exists!")
                    try:
                        # Validate path to prevent path traversal
                        resolved_path = Path(path).resolve()

                        # Check if path is within app directory (if we have app_base_path)
                        if app_base_path:
                            try:
                                # This will raise ValueError if resolved_path is not relative to app_base_path
                                resolved_path.relative_to(app_base_path)
                            except ValueError:
                                logger.warning(f"Icon path outside app directory, skipping: {resolved_path}")
                                continue

                        # Load image from file
                        logger.debug(f"   Loading NSImage from: {resolved_path}")
                        image = NSImage.alloc().initWithContentsOfFile(at(str(resolved_path)))
                        if image:
                            # Resize to appropriate toolbar size
                            if for_menu:
                                size = NSSize(20, 20)  # Smaller for menu items
                            else:
                                size = NSSize(32, 32)  # Standard toolbar size
                            image.setSize(size)
                            logger.debug(f"✅ _load_icon() SUCCESS: Loaded from file: {path} (size: {size.width}x{size.height})")
                            return image
                        else:
                            logger.debug(f"   ✗ NSImage.initWithContentsOfFile returned None")
                    except Exception as e:
                        logger.debug(f"   ✗ Error loading icon: {e}")
                else:
                    logger.debug(f"   ✗ File does not exist")

        # Fall back to SF Symbol
        logger.debug(f"   Trying as SF Symbol...")
        try:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                icon_path, label
            )
            if image:
                # Menu items may need explicit sizing even for SF Symbols
                if for_menu:
                    from rubicon.objc import NSSize
                    size = NSSize(20, 20)
                    image.setSize(size)
                logger.debug(f"✅ _load_icon() SUCCESS: Loaded SF Symbol: {icon_path}")
                return image
            else:
                logger.debug(f"   ✗ SF Symbol not found: {icon_path}")
        except Exception as e:
            logger.debug(f"   ✗ Error loading SF Symbol: {e}")

        logger.warning(f"❌ _load_icon() FAILED: Could not load icon: {icon_path}")
        return None

    def _create_toolbar_item(self, command) -> Optional[Any]:
        """
        Create NSToolbarItem from FicheroCommand

        Dispatches to specialized methods based on command.item_type:
        - "button" (default): Standard toolbar button
        - "menu": NSMenuToolbarItem with dropdown
        - "group": NSToolbarItemGroup with subitems
        - "search": NSSearchToolbarItem
        - "space": Fixed space separator
        - "flexible_space": Flexible space separator

        Args:
            command: FicheroCommand instance

        Returns:
            NSToolbarItem (or subclass) or None
        """
        try:
            # Dispatch based on item_type
            item_type = getattr(command, 'item_type', 'button')

            # 🔍 DEBUG POINT 7: Log search item dispatch
            if command.id.endswith('.search'):
                logger.info(f"🔍 DISPATCHING SEARCH ITEM: {command.id}, item_type={item_type}")

            if item_type == "menu":
                return self._create_menu_toolbar_item(command)
            elif item_type == "group":
                return self._create_group_toolbar_item(command)
            elif item_type == "search":
                logger.info(f"🔍 CALLING _create_search_toolbar_item for {command.id}")
                return self._create_search_toolbar_item(command)
            elif item_type == "space":
                return self._create_space_item(command, flexible=False)
            elif item_type == "flexible_space":
                return self._create_space_item(command, flexible=True)
            else:  # "button" or unknown - default to button
                return self._create_button_toolbar_item(command)

        except Exception as e:
            logger.error(f"Failed to create toolbar item for {command.id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_button_toolbar_item(self, command) -> Optional[Any]:
        """
        Create standard NSToolbarItem button from FicheroCommand

        Args:
            command: FicheroCommand instance

        Returns:
            NSToolbarItem or None
        """
        try:
            logger.debug(f"🔨 _create_button_toolbar_item() START for: {command.id}")
            # Create toolbar item
            item = NSToolbarItem.alloc().initWithItemIdentifier(command.id)
            logger.debug(f"   NSToolbarItem created with identifier: {command.id}")

            # Set labels and tooltip
            self._set_item_labels_and_tooltip(item, command)

            # Set visibility priority
            item.visibilityPriority = command.visibility_priority

            # Set icon: Try toolbar_icon (SF Symbol) first, then fall back to icon (file)
            icon_loaded = False

            # Try toolbar_icon (SF Symbol) first
            if command.toolbar_icon:
                logger.debug(f"   Loading toolbar_icon (SF Symbol): '{command.toolbar_icon}' for {command.id}")
                icon = self._load_icon(command.toolbar_icon, command.label, for_menu=False)
                if icon:
                    item.setImage(icon)
                    logger.debug("   Toolbar icon loaded and set")
                    icon_loaded = True
                else:
                    logger.debug(f"   Toolbar icon NOT FOUND: '{command.toolbar_icon}'")

            # Fall back to icon (file path) if no toolbar_icon or it failed
            if not icon_loaded and command.icon:
                logger.debug(f"   Loading icon (file): '{command.icon}' for {command.id}")
                icon = self._load_icon(command.icon, command.label, for_menu=False)
                if icon:
                    item.setImage(icon)
                    logger.debug("   Icon file loaded and set")
                    icon_loaded = True
                else:
                    logger.debug(f"   Icon file NOT FOUND: '{command.icon}'")

            # Set bordered style
            item.bordered = command.toolbar_bordered

            # Set navigational style if requested (macOS 11+)
            if command.navigational:
                try:
                    item.navigational = True
                    logger.debug(f"Set navigational style for {command.id}")
                except:
                    logger.debug(f"Navigational style not available for {command.id}")

            # Set prominent style and tint color if requested (macOS 11+)
            if command.toolbar_style == "prominent":
                try:
                    item.style = self.TOOLBAR_STYLE_PROMINENT

                    # Set custom tint color if specified
                    if command.toolbar_tint_color:
                        color = self._hex_to_nscolor(command.toolbar_tint_color)
                        if color:
                            item.backgroundTintColor = color
                            logger.debug(f"Set tint color {command.toolbar_tint_color} for {command.id}")

                    logger.debug(f"Set prominent style for {command.id}")
                except Exception as style_err:
                    logger.debug(f"Prominent style not available: {style_err}")

            # Set badge if specified (macOS 14+)
            if command.toolbar_badge_count is not None and self._badge_available:
                try:
                    badge = NSItemBadge.alloc().initWithCount_(command.toolbar_badge_count)
                    item.badge = badge
                    logger.debug(f"Set badge count {command.toolbar_badge_count} for {command.id}")
                except Exception as badge_err:
                    logger.debug(f"Could not set badge: {badge_err}")

            # Set action target to DELEGATE (not individual handler)
            # Following FICHERO_COMMAND_TOOLBAR_DEMO pattern - this is critical!
            # macOS needs a single shared target to properly manage item states
            item.setTarget_(self._delegate)
            item.setAction_(SEL("handleCommand:"))

            # DEBUG: Verify target and action were set
            actual_target = item.target
            actual_action = item.action
            logger.debug(f"   command.enabled = {command.enabled} for {command.id}")
            logger.debug(f"   Target set to: {actual_target}")
            logger.debug(f"   Action set to: {actual_action}")
            logger.debug(f"   Delegate is: {self._delegate}")
            logger.debug(f"   Target == Delegate? {actual_target == self._delegate}")

            # FORCE enabled state to True (items were appearing greyed out)
            # Even though command.enabled = True, items were still disabled
            # Explicitly call setEnabled_(True) to fix greyed out appearance
            item.setEnabled_(True)
            logger.debug("   Forced item.setEnabled_(True)")
            logger.debug(f"   Item enabled state: {item.isEnabled()}")

            logger.debug(f"✅ _create_button_toolbar_item() COMPLETE for: {command.id}")
            logger.debug(f"   Item will be added to delegate.toolbar_items by caller")
            return item

        except Exception as e:
            logger.error(f"Failed to create button toolbar item for {command.id}: {e}")
            return None

    def _create_menu_toolbar_item(self, command) -> Optional[Any]:
        """
        Create NSMenuToolbarItem from FicheroCommand

        Args:
            command: FicheroCommand with item_type="menu"

        Returns:
            NSMenuToolbarItem or None
        """
        try:
            # Create NSMenuToolbarItem
            menu_item = NSMenuToolbarItem.alloc().initWithItemIdentifier(command.id)

            # Set labels and tooltip
            self._set_item_labels_and_tooltip(menu_item, command)

            # Configure dropdown indicator
            menu_item.showsIndicator = command.shows_menu_indicator

            # Set icon if provided
            if command.toolbar_icon or command.icon:
                icon = self._load_icon(command.toolbar_icon or command.icon, command.label, for_menu=True)
                if icon:
                    menu_item.setImage(icon)

            # Create NSMenu
            dropdown = NSMenu.alloc().initWithTitle(command.label)

            # Add menu items
            handlers = []
            for menu_item_dict in command.menu_items:
                item_label = menu_item_dict.get('label', 'Unnamed')
                item_action = menu_item_dict.get('action')
                item_icon = menu_item_dict.get('icon')

                ns_menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    item_label, SEL("handleMenuAction:"), ""
                )

                # Set icon if provided
                if item_icon:
                    icon = self._load_icon(item_icon, item_label, for_menu=True)
                    if icon:
                        ns_menu_item.setImage(icon)

                # Create handler for this menu item
                handler = _TitlebarMenuHandler.alloc().init()
                handler._cmd_action = item_action  # Standardized naming
                handlers.append(handler)

                ns_menu_item.setTarget_(handler)
                dropdown.addItem(ns_menu_item)

            # Set the menu
            menu_item.setMenu(dropdown)

            # Store handlers in all_menu_handlers
            if handlers:
                self._all_menu_handlers[command.id] = handlers

            logger.debug(f"Created menu toolbar item for command: {command.id}")
            return menu_item

        except Exception as e:
            logger.error(f"Failed to create menu toolbar item for {command.id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_group_toolbar_item(self, command) -> Optional[Any]:
        """
        Create NSToolbarItemGroup from FicheroCommand

        Args:
            command: FicheroCommand with item_type="group"

        Returns:
            NSToolbarItemGroup or None
        """
        try:
            # Create NSToolbarItemGroup
            group_item = NSToolbarItemGroup.alloc().initWithItemIdentifier(command.id)

            # Set labels and tooltip
            self._set_item_labels_and_tooltip(group_item, command)

            # Create subitems
            subitems_list = []
            for subitem_command in command.subitems:
                # Create toolbar items for each subitem (respects item_type)
                subitem = self._create_toolbar_item(subitem_command)
                if subitem:
                    subitems_list.append(subitem)

            # Set subitems
            if subitems_list:
                # NSArray is now imported at module level
                subitems_array = NSArray(subitems_list)
                group_item.setSubitems(subitems_array)

            logger.debug(f"Created group toolbar item with {len(subitems_list)} subitems for command: {command.id}")
            return group_item

        except Exception as e:
            logger.error(f"Failed to create group toolbar item for {command.id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_search_toolbar_item(self, command) -> Optional[Any]:
        """
        Create NSSearchToolbarItem from FicheroCommand

        Args:
            command: FicheroCommand with item_type="search"

        Returns:
            NSSearchToolbarItem or None
        """
        try:
            logger.info(f"🔍 DEBUG POINT 8: INSIDE _create_search_toolbar_item for {command.id}")

            # Create NSSearchToolbarItem
            search_item = NSSearchToolbarItem.alloc().initWithItemIdentifier(command.id)
            logger.info(f"🔍 NSSearchToolbarItem created: {search_item}")

            # Set labels and tooltip
            self._set_item_labels_and_tooltip(search_item, command)

            # Get the search field from the toolbar item
            search_field = search_item.searchField
            logger.info(f"🔍 Search field obtained: {search_field}")

            # Set placeholder text
            if command.search_placeholder:
                search_field.placeholderString = command.search_placeholder
                logger.info(f"🔍 Placeholder set: {command.search_placeholder}")

            # Set visibility priority (higher = more likely to stay visible when window narrows)
            if hasattr(command, 'visibility_priority') and command.visibility_priority:
                search_item.setVisibilityPriority_(command.visibility_priority)
                logger.info(f"🔍 Visibility priority set: {command.visibility_priority}")
            else:
                # Default high priority for search field
                search_item.setVisibilityPriority_(600)
                logger.info(f"🔍 Default visibility priority set: 600")

            # CRITICAL: Set preferredWidthForSearchField (NSSearchToolbarItem-specific property)
            # This is the proper way to size NSSearchToolbarItem according to Apple docs
            # NOTE: NSSearchToolbarItem does NOT support setMinSize/setMaxSize (those are for regular NSToolbarItem)
            search_item.setPreferredWidthForSearchField_(250.0)  # 250pt preferred width
            logger.info(f"🔍 Preferred search field width set: 250pt")

            # Set action on the search field (not the toolbar item)
            if command.search_action:
                # Create handler for search action
                handler = _ActionHandler.alloc().init()
                handler._cmd = command

                # Set action on the search field itself
                search_field.setTarget_(handler)
                search_field.setAction_(SEL("handleCommand:"))

                # Also handle search text changes
                search_field.setDelegate_(handler)

                # Store handler to prevent garbage collection
                self._all_command_handlers[command.id] = handler
                logger.info(f"🔍 Action handler configured")

            logger.info(f"✅ Search toolbar item created successfully for: {command.id}")
            return search_item

        except Exception as e:
            logger.error(f"Failed to create search toolbar item for {command.id}: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _create_space_item(self, command, flexible: bool = False) -> Optional[Any]:
        """
        Create space or flexible space toolbar item

        Args:
            command: FicheroCommand with item_type="space" or "flexible_space"
            flexible: If True, create flexible space, otherwise fixed space

        Returns:
            NSToolbarItem configured as space or None
        """
        try:
            # Use standard identifiers for space items
            if flexible:
                identifier = "NSToolbarFlexibleSpaceItem"
            else:
                identifier = "NSToolbarSpaceItem"

            item = NSToolbarItem.alloc().initWithItemIdentifier(identifier)

            logger.debug(f"Created {'flexible ' if flexible else ''}space toolbar item: {command.id}")
            return item

        except Exception as e:
            logger.error(f"Failed to create space toolbar item for {command.id}: {e}")
            return None

    def _create_dropdown_menu(self, menu: Any, command_manager: Any) -> Tuple[Optional[Any], List[Any]]:
        """
        Create NSMenuToolbarItem from ToolbarMenu

        Args:
            menu: ToolbarMenu instance
            command_manager: CommandManager to get commands

        Returns:
            Tuple of (NSMenuToolbarItem, handlers_list) or (None, None)
        """
        try:
            # Create NSMenuToolbarItem
            menu_item = NSMenuToolbarItem.alloc().initWithItemIdentifier(menu.id)

            # Set labels
            menu_item.setLabel(menu.label)
            menu_item.setPaletteLabel(menu.label)
            menu_item.setToolTip(menu.tooltip or menu.label)

            # Configure dropdown
            menu_item.showsIndicator = True  # Show dropdown arrow
            menu_item.isBordered = False  # No border - cleaner look

            # Set icon if provided (use for_menu=True for proper sizing)
            if hasattr(menu, 'icon') and menu.icon:
                icon = self._load_icon(menu.icon, menu.label, for_menu=True)
                if icon:
                    menu_item.setImage(icon)
                    logger.debug(f"Set icon for menu '{menu.id}'")

            # Create NSMenu
            dropdown = NSMenu.alloc().initWithTitle(menu.label)

            # Add menu items from command IDs
            handlers = []
            for cmd_id in menu.items:
                command = command_manager.get_command(cmd_id)
                if not command:
                    logger.warning(f"Command not found for menu: {cmd_id}")
                    continue

                # Create menu item
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    command.label,
                    SEL("handleAction:"),
                    ""
                )

                # Store command ID
                item.representedObject = cmd_id

                # Wire action
                handler = self._create_action_handler(command)
                if handler:
                    item.target = handler
                    handlers.append(handler)  # Keep alive

                # Set enabled state
                item.enabled = command.enabled

                dropdown.addItem(item)
                logger.debug(f"Added menu item: {command.label}")

            # Assign menu to toolbar item
            menu_item.menu = dropdown

            logger.info(f"Created dropdown menu '{menu.label}' with {len(menu.items)} items")
            return (menu_item, handlers)

        except Exception as e:
            logger.error(f"Failed to create dropdown menu {menu.id}: {e}")
            return (None, None)

    def _create_action_handler(self, command: Any) -> Optional[Any]:
        """
        Create action handler for command

        Args:
            command: FicheroCommand instance

        Returns:
            ObjC handler object or None
        """
        if not RUBICON_AVAILABLE or _ActionHandler is None:
            return None

        try:
            # Create instance of module-level ActionHandler class
            handler = _ActionHandler.alloc().init()
            handler._cmd = command  # Use _ prefix for Python attribute
            return handler

        except Exception as e:
            logger.error(f"Failed to create action handler for {command.id}: {e}")
            return None

    def _hex_to_nscolor(self, hex_color: str) -> Optional[Any]:
        """
        Convert hex color to NSColor

        Args:
            hex_color: Hex color string (e.g., "#FF6B35", "FF6B35")

        Returns:
            NSColor or None
        """
        try:
            # Remove # if present
            hex_color = hex_color.lstrip('#')

            # Convert hex to RGB
            r = int(hex_color[0:2], 16) / 255.0
            g = int(hex_color[2:4], 16) / 255.0
            b = int(hex_color[4:6], 16) / 255.0

            # Create NSColor
            color = NSColor.colorWithRed_green_blue_alpha_(r, g, b, 1.0)
            return color

        except Exception as e:
            logger.error(f"Failed to convert hex color {hex_color}: {e}")
            return None

    def _add_titlebar_accessories(self, commands: List[Any]) -> None:
        """
        Add titlebar accessory buttons from FicheroCommands

        Args:
            commands: List of FicheroCommand instances with show_in_titlebar=True
        """
        if not RUBICON_AVAILABLE:
            return

        try:
            logger.debug(f"Adding {len(commands)} titlebar accessory buttons...")

            # Load ObjC classes
            NSButton = ObjCClass('NSButton')
            NSMenu = ObjCClass('NSMenu')
            NSMenuItem = ObjCClass('NSMenuItem')
            NSTitlebarAccessoryViewController = ObjCClass('NSTitlebarAccessoryViewController')

            native_window = self.window._impl.native
            titlebar_accessories = []

            for command in commands:
                try:
                    logger.debug(f"Creating titlebar button for: {command.id}")

                    # Load icon (PNG file or SF Symbol)
                    icon_path = command.toolbar_icon or command.icon
                    if not icon_path:
                        logger.warning(f"No icon specified for titlebar button: {command.id}")
                        continue

                    icon = self._load_icon(icon_path, command.label, for_menu=False)
                    if not icon:
                        logger.warning(f"Could not load icon for titlebar button: {command.id} (path: {icon_path})")
                        continue

                    # Create action handler for button click
                    handler = self._create_action_handler(command)
                    if not handler:
                        logger.warning(f"Could not create handler for titlebar button: {command.id}")
                        continue

                    # Create button using class method (like demo)
                    # This is the key difference from the manual alloc().init() approach!
                    button = NSButton.buttonWithImage_target_action_(
                        icon,
                        handler,
                        SEL("handleAction:")
                    )

                    # Configure button style for titlebar accessory
                    button.bezelStyle = 0  # NSBezelStyleRounded
                    button.bordered = False
                    button.setButtonType(0)  # NSButtonTypeMomentaryLight
                    button.imagePosition = 1  # NSImageOnly (no title, just icon)

                    # Resize icon to appropriate size (24x24 for titlebar)
                    from rubicon.objc import NSSize
                    icon.setSize(NSSize(24, 24))

                    logger.debug(f"Titlebar button created for: {command.id}")

                    # If command has menu, create popup menu
                    if command.titlebar_has_menu and command.titlebar_menu_items:
                        menu = NSMenu.alloc().initWithTitle(command.label)

                        # Create menu items
                        menu_handlers = []
                        for menu_item_data in command.titlebar_menu_items:
                            menu_label = menu_item_data.get('label', 'Item')
                            menu_action = menu_item_data.get('action')

                            # Create menu item
                            menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                                menu_label, SEL("handleMenuAction:"), ""
                            )

                            # Create handler for menu item (use module-level class)
                            menu_handler = _TitlebarMenuHandler.alloc().init()
                            menu_handler._cmd_action = menu_action  # Standardized naming
                            menu_item.setTarget_(menu_handler)
                            menu_handlers.append(menu_handler)

                            menu.addItem(menu_item)

                        button.setMenu(menu)
                        # Keep menu handlers
                        self._titlebar_menu_handlers = getattr(self, '_titlebar_menu_handlers', []) + menu_handlers

                    # Note: handler from line 1280 is already set as button target/action
                    # No need to create a second handler for non-menu buttons

                    # Create view controller for button
                    vc = NSTitlebarAccessoryViewController.alloc().init()
                    vc.view = button

                    # Set position: leading = left, trailing = right
                    if command.titlebar_position == "trailing":
                        vc.layoutAttribute = self.TITLEBAR_LAYOUT_TRAILING
                    else:  # "leading" or default
                        vc.layoutAttribute = self.TITLEBAR_LAYOUT_LEADING

                    # Add to window
                    native_window.addTitlebarAccessoryViewController(vc)

                    # Keep references (including handler to prevent garbage collection)
                    titlebar_accessories.append({
                        'command_id': command.id,
                        'vc': vc,
                        'button': button,
                        'handler': handler  # Prevent garbage collection of button handler
                    })

                    logger.debug(f"Titlebar button added: {command.id} ({command.titlebar_position})")

                except Exception as e:
                    logger.warning(f"Failed to create titlebar button for {command.id}: {e}")

            # Keep references to prevent garbage collection
            self._titlebar_accessories = titlebar_accessories

            logger.info(f"Added {len(titlebar_accessories)} titlebar accessories")
            logger.info(f"Added {len(titlebar_accessories)} titlebar accessory buttons")

        except Exception as e:
            logger.warning(f"Error adding titlebar accessories: {e}")
            logger.error(f"Error adding titlebar accessories: {e}")
            import traceback
            traceback.print_exc()

    def add_titlebar_accessory(self, command: Any) -> None:
        """
        Add a single titlebar accessory button dynamically.

        This allows titlebar buttons to be added after toolbar initialization,
        similar to how menu commands can be added dynamically.

        Args:
            command: FicheroCommand with show_in_titlebar=True
        """
        if not RUBICON_AVAILABLE:
            logger.warning("Cannot add titlebar accessory: rubicon not available")
            return

        if not self.window:
            logger.warning("Cannot add titlebar accessory: no window")
            return

        try:
            logger.debug(f"Adding titlebar accessory for command: {command.id}")

            # Load ObjC classes
            NSButton = ObjCClass('NSButton')
            NSImage = ObjCClass('NSImage')
            NSTitlebarAccessoryViewController = ObjCClass('NSTitlebarAccessoryViewController')

            native_window = self.window._impl.native

            # Load icon (PNG file or SF Symbol)
            icon_path = command.toolbar_icon or command.icon
            if not icon_path:
                logger.warning(f"No icon specified for titlebar button: {command.id}")
                return

            icon = self._load_icon(icon_path, command.label, for_menu=False)
            if not icon:
                logger.warning(f"Could not load icon for titlebar button: {command.id} (path: {icon_path})")
                return

            # Create action handler
            handler = self._create_action_handler(command)
            if not handler:
                logger.warning(f"Could not create handler for titlebar button: {command.id}")
                return

            # Create button using class method
            button = NSButton.buttonWithImage_target_action_(
                icon,
                handler,
                SEL("handleAction:")
            )

            # Configure button style for titlebar accessory
            button.bezelStyle = 0  # NSBezelStyleRounded
            button.bordered = False
            button.setButtonType(0)  # NSButtonTypeMomentaryLight
            button.imagePosition = 1  # NSImageOnly (no title, just icon)

            # Resize icon to appropriate size (24x24 for titlebar)
            from rubicon.objc import NSSize
            icon.setSize(NSSize(24, 24))

            # If command has menu, create popup menu
            if command.titlebar_has_menu and command.titlebar_menu_items:
                NSMenu = ObjCClass('NSMenu')
                NSMenuItem = ObjCClass('NSMenuItem')

                menu = NSMenu.alloc().initWithTitle(command.label)

                # Create menu items
                menu_handlers = []
                for menu_item_data in command.titlebar_menu_items:
                    menu_label = menu_item_data.get('label', 'Item')
                    menu_action = menu_item_data.get('action')

                    # Create menu item
                    menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                        menu_label, SEL("handleMenuAction:"), ""
                    )

                    # Create handler for menu item (use different variable name to avoid shadowing)
                    menu_handler = _TitlebarMenuHandler.alloc().init()
                    menu_handler._cmd_action = menu_action
                    menu_item.setTarget_(menu_handler)
                    menu_handlers.append(menu_handler)

                    menu.addItem(menu_item)

                button.setMenu(menu)

                # Keep menu handlers
                if not hasattr(self, '_titlebar_menu_handlers'):
                    self._titlebar_menu_handlers = []
                self._titlebar_menu_handlers.extend(menu_handlers)

            # Create view controller for button
            vc = NSTitlebarAccessoryViewController.alloc().init()
            vc.view = button

            # Set position: leading = left, trailing = right
            if command.titlebar_position == "trailing":
                vc.layoutAttribute = self.TITLEBAR_LAYOUT_TRAILING
            else:  # "leading" or default
                vc.layoutAttribute = self.TITLEBAR_LAYOUT_LEADING

            # Add to window
            native_window.addTitlebarAccessoryViewController(vc)

            # Keep references to prevent garbage collection
            if not hasattr(self, '_titlebar_accessories'):
                self._titlebar_accessories = []

            self._titlebar_accessories.append({
                'command_id': command.id,
                'vc': vc,
                'button': button,
                'handler': handler
            })

            logger.info(f"✅ Added titlebar accessory: {command.id} ({command.titlebar_position})")

        except Exception as e:
            logger.error(f"Failed to add titlebar accessory for {command.id}: {e}")
            import traceback
            traceback.print_exc()

    def update_item_states(self) -> None:
        """Update enable/disable states of all toolbar items"""
        if not RUBICON_AVAILABLE or not self._toolbar or not self._delegate:
            return

        try:
            toolbar = self._toolbar
            items = list(toolbar.items or [])

            for item in items:
                item_id = str(item.itemIdentifier())

                # Get corresponding command
                command = self._delegate._command_handlers.get(item_id)
                if not command:
                    continue

                # Update enabled state
                item.setEnabled_(command.enabled)

                # Update dropdown menu states
                if hasattr(item, 'menu'):
                    menu = item.menu
                    if menu:
                        for i in range(menu.numberOfItems()):
                            menu_item = menu.itemAtIndex(i)
                            if not menu_item:
                                continue

                            cmd_id = str(menu_item.representedObject() or "")
                            cmd = self._delegate._command_handlers.get(cmd_id)
                            if cmd:
                                menu_item.enabled = cmd.enabled

            logger.debug("Updated toolbar item states")

        except Exception as e:
            logger.error(f"Failed to update item states: {e}")

    def rebuild_toolbar(
        self,
        command_manager,
        toolbar_menus=None,
        view_id: Optional[str] = None,
        context: str = 'normal'
    ):
        """
        Rebuild toolbar (for dynamic updates)

        Args:
            command_manager: CommandManager instance
            toolbar_menus: Optional list of ToolbarMenu instances
            view_id: Optional view ID for filtering commands
            context: Context for filtering commands
        """
        if not RUBICON_AVAILABLE or not self.window:
            return

        logger.info("Rebuilding toolbar")
        self.build_toolbar(
            command_manager=command_manager,
            toolbar_menus=toolbar_menus,
            view_id=view_id,
            context=context
        )


__all__ = ['MacToolbarManager', 'PLATFORM_SUPPORTED', 'RUBICON_AVAILABLE']
