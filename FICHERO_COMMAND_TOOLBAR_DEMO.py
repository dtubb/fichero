"""
Standalone demo: NSToolbar + FicheroCommand integration

This demo combines:
1. Working NSToolbar code from ULTIMATE_TOOLBAR_DEMO.py
2. FicheroCommand system from Fichero

Goal: Get NSToolbar working with FicheroCommand pattern
"""

import toga
from toga.style import Pack
from toga.constants import COLUMN
from rubicon.objc import ObjCClass, objc_method, ObjCInstance, NSObject, at, SEL
from rubicon.objc.runtime import load_library

# Load AppKit
appkit = load_library('AppKit')
NSToolbar = ObjCClass('NSToolbar')
NSToolbarItem = ObjCClass('NSToolbarItem')
NSImage = ObjCClass('NSImage')
NSSearchToolbarItem = ObjCClass('NSSearchToolbarItem')
NSMenuToolbarItem = ObjCClass('NSMenuToolbarItem')
NSToolbarItemGroup = ObjCClass('NSToolbarItemGroup')
NSTrackingSeparatorToolbarItem = ObjCClass('NSTrackingSeparatorToolbarItem')
NSMenu = ObjCClass('NSMenu')
NSMenuItem = ObjCClass('NSMenuItem')

# ============================================================================
# FicheroCommand - Simplified version from Fichero
# ============================================================================

class FicheroCommand:
    """Represents a command that can be shown in menus, toolbars, etc."""

    def __init__(
        self,
        id: str,
        label: str,
        icon: str = None,
        action: callable = None,
        enabled: bool = True,
        show_in_toolbar: bool = True,
        item_type: str = "button",  # button, search, menu, group, separator
        menu_items: list = None,  # For menu type
        subitems: list = None,  # For group type
        visibility_priority: int = 500,  # For overflow behavior
    ):
        self.id = id
        self.label = label
        self.icon = icon
        self.action = action
        self.enabled = enabled
        self.show_in_toolbar = show_in_toolbar
        self.item_type = item_type
        self.menu_items = menu_items or []
        self.subitems = subitems or []
        self.visibility_priority = visibility_priority

    def execute(self, widget=None):
        """Execute the command's action"""
        if self.action:
            return self.action(widget)


# ============================================================================
# NSToolbar Delegate - From working demo
# ============================================================================

class ToolbarDelegate(NSObject):
    """ObjC delegate for NSToolbar"""

    # CRITICAL: Use CLASS attributes (NOT instance attributes)
    # NSToolbar delegate protocol requires these to be class-level
    toolbar_items = {}
    command_handlers = {}

    @objc_method
    def toolbarDefaultItemIdentifiers_(self, toolbar):
        """Return list of default item IDs with flexible spacing"""
        # Note: toggleSidebar is in titlebar accessory, not regular toolbar
        # Layout: [Title] [search] [items...]
        layout = [
            "demo.search",          # Search field
            "NSToolbarFlexibleSpaceItem",
            "demo.import",          # PNG icons
            "demo.export",
            "demo.collection",
            "demo.actions.group",   # Grouped items with PNG icons
            "NSToolbarFlexibleSpaceItem",
            "demo.view",            # Menu with PNG icon
            "demo.settings",        # PNG icon
            "demo.help",            # PNG icon
            "demo.info",            # SF Symbol (mixed demo)
        ]

        # Filter to only include items that exist
        item_ids = [id for id in layout if id.startswith("NSToolbar") or id in self.toolbar_items]

        print(f"🎯 toolbarDefaultItemIdentifiers: {len(item_ids)} items")
        print(f"   IDs: {item_ids}")

        return at(item_ids)

    @objc_method
    def toolbarSelectableItemIdentifiers_(self, toolbar):
        """Return list of selectable item IDs"""
        # No selectable items in this demo
        return at([])

    @objc_method
    def toolbarAllowedItemIdentifiers_(self, toolbar):
        """Return list of allowed item IDs (for customization)"""
        allowed_ids = list(self.toolbar_items.keys()) + [
            "NSToolbarSpaceItem",
            "NSToolbarFlexibleSpaceItem",
        ]
        return at(allowed_ids)

    @objc_method
    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, identifier, insert: bool
    ):
        """Return toolbar item for given ID"""
        item_id_str = str(identifier)
        print(f"🎯 toolbar_itemForItemIdentifier: '{item_id_str}'")

        if item_id_str in self.toolbar_items:
            print(f"   ✓ Returning item for: {item_id_str}")
            return self.toolbar_items[item_id_str]

        print(f"   ✗ No item found for: {item_id_str}")
        return None

    @objc_method
    def handleCommand_(self, sender):
        """Generic action handler for all toolbar items"""
        # Get the item identifier from the sender
        item_id = str(sender.itemIdentifier)
        print(f"🎯 Toolbar button clicked: {item_id}")

        if item_id in self.command_handlers:
            command = self.command_handlers[item_id]
            command.execute(sender)

    @objc_method
    def handleSearch_(self, sender):
        """Handle search field input"""
        search_text = str(sender.stringValue())
        print(f"🔍 Search: {search_text}")
        # Could trigger search command here

    @objc_method
    def handleSidebarToggle_(self, sender):
        """Handle sidebar toggle button (titlebar button)"""
        print(f"🎯 Titlebar sidebar button clicked!")
        # Execute toggleSidebar command if it exists
        if "toggleSidebar" in self.command_handlers:
            command = self.command_handlers["toggleSidebar"]
            command.execute(sender)


# ============================================================================
# Toolbar Manager - Manages NSToolbar for a window
# ============================================================================

class SimpleToolbarManager:
    """Manages NSToolbar with FicheroCommand integration"""

    def __init__(self, window):
        self.window = window
        self.toolbar = None
        self.delegate = None
        self.commands = {}
        self.toolbar_items = {}  # Keep strong references to prevent GC

    def build_toolbar(self, commands):
        """Build NSToolbar with all commands at once (like working demo)"""
        print("🔧 Building NSToolbar with commands...")

        # Remove Toga's toolbar if present
        native_window = self.window._impl.native
        if native_window.toolbar:
            print("   Removing existing toolbar")
            native_window.setToolbar(None)

        # Create delegate
        self.delegate = ToolbarDelegate.alloc().init()
        print("   Delegate created")

        # Pre-create ALL items BEFORE creating NSToolbar
        toolbar_items = {}
        command_handlers = {}

        print(f"   Creating {len(commands)} toolbar items...")
        for command in commands:
            if not command.show_in_toolbar:
                continue

            # Skip toggleSidebar - it's added as titlebar accessory instead
            if command.id == "toggleSidebar":
                # Still store command handler for the titlebar button
                command_handlers[command.id] = command
                self.commands[command.id] = command
                print(f"      ⏩ Skipping {command.id} (titlebar accessory)")
                continue

            # Create item
            item = self._create_toolbar_item(command)
            if item:
                toolbar_items[command.id] = item
                command_handlers[command.id] = command
                self.commands[command.id] = command
                self.toolbar_items[command.id] = item  # Keep strong reference
                item_type = command.item_type.upper()
                print(f"      ✓ [{item_type}] {command.id}")

        # Set items on delegate
        self.delegate.toolbar_items = toolbar_items
        self.delegate.command_handlers = command_handlers
        print(f"   Delegate populated with {len(toolbar_items)} items")

        # NOW create NSToolbar (it will query delegate for items)
        toolbar_id = "demo.toolbar"
        self.toolbar = NSToolbar.alloc().initWithIdentifier(toolbar_id)
        self.toolbar.setDelegate(self.delegate)
        print(f"   NSToolbar created: {toolbar_id}")

        # Configure toolbar
        self.toolbar.setAllowsUserCustomization(True)
        self.toolbar.setAutosavesConfiguration(True)
        self.toolbar.setDisplayMode(0)  # Icon + label

        # Set centered item identifier to position title and sidebar toggle
        # This makes the toolbar layout: [toggleSidebar] [Title] [other items...]
        try:
            self.toolbar.centeredItemIdentifier = at("demo.search")
            print("   Toolbar configured with centered item")
        except:
            print("   Toolbar configured (centeredItemIdentifier not available)")

        # Attach to window
        native_window.setToolbar(self.toolbar)
        self.toolbar.setVisible(True)
        print("   Toolbar attached to window")

        # Add sidebar toggle as titlebar accessory (appears BEFORE title)
        self._add_titlebar_button(native_window)
        print("   Titlebar sidebar button added")

        # Keep strong references to prevent GC
        self.window._toolbar_manager = self

        print(f"✅ NSToolbar built with {len(toolbar_items)} items")

    def _create_toolbar_item(self, command: FicheroCommand):
        """Create an NSToolbarItem from a FicheroCommand"""

        # Handle different item types
        if command.item_type == "search":
            return self._create_search_item(command)
        elif command.item_type == "menu":
            return self._create_menu_item(command)
        elif command.item_type == "group":
            return self._create_group_item(command)
        elif command.item_type == "separator":
            return self._create_separator_item(command)
        else:  # "button" or default
            return self._create_button_item(command)

    def _create_button_item(self, command: FicheroCommand):
        """Create a regular button toolbar item"""
        item = NSToolbarItem.alloc().initWithItemIdentifier(command.id)
        item.setLabel(command.label if command.label else "")
        item.setPaletteLabel(command.label if command.label else command.id)
        item.visibilityPriority = command.visibility_priority

        # Set icon if provided
        if command.icon:
            image = self._load_icon(command.icon, command.label if command.label else command.id)
            if image:
                item.setImage(image)

        # Set action
        item.setTarget_(self.delegate)
        item.setAction_(SEL("handleCommand:"))

        return item

    def _create_search_item(self, command: FicheroCommand):
        """Create a search toolbar item"""
        item = NSSearchToolbarItem.alloc().initWithItemIdentifier(command.id)
        item.setLabel(command.label)
        item.setPaletteLabel(command.label)
        item.visibilityPriority = command.visibility_priority

        search_field = item.searchField
        search_field.placeholderString = command.label + "..."
        search_field.setTarget_(self.delegate)
        search_field.setAction_(SEL("handleSearch:"))

        return item

    def _create_menu_item(self, command: FicheroCommand):
        """Create a menu dropdown toolbar item"""
        item = NSMenuToolbarItem.alloc().initWithItemIdentifier(command.id)
        item.setLabel(command.label)
        item.setPaletteLabel(command.label)
        item.showsIndicator = True  # Show dropdown arrow
        item.isBordered = False  # No border - matches other items
        item.visibilityPriority = command.visibility_priority

        # Set icon if provided
        if command.icon:
            image = self._load_icon(command.icon, command.label)
            if image:
                # NSMenuToolbarItem needs explicit size control
                from rubicon.objc import NSSize
                size = NSSize(20, 20)  # Smaller size for menu items
                image.setSize(size)
                item.setImage(image)

        # Create menu
        menu = NSMenu.alloc().initWithTitle(command.label)

        # Handler class for menu items
        class MenuHandler(NSObject):
            label_ref = None
            mode = None

            @objc_method
            def handleAction_(self, sender):
                print(f"📋 Menu item selected: {self.mode}")

        handlers = []
        for menu_label in command.menu_items:
            menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                menu_label, SEL("handleAction:"), ""
            )
            handler = MenuHandler.alloc().init()
            handler.mode = menu_label
            menu_item.target = handler
            handlers.append(handler)
            menu.addItem(menu_item)

        item.menu = menu
        self._menu_handlers = getattr(self, '_menu_handlers', []) + handlers

        return item

    def _create_group_item(self, command: FicheroCommand):
        """Create a grouped toolbar item"""
        # Create subitems
        subitems = []
        for subitem_data in command.subitems:
            subitem = NSToolbarItem.alloc().initWithItemIdentifier(subitem_data['id'])
            subitem.setLabel(subitem_data['label'])

            if 'icon' in subitem_data:
                image = self._load_icon(subitem_data['icon'], subitem_data['label'])
                if image:
                    subitem.setImage(image)

            subitems.append(subitem)

        # Create group
        item = NSToolbarItemGroup.alloc().initWithItemIdentifier(command.id)
        item.setSubitems(subitems)
        item.setLabel(command.label)
        item.setPaletteLabel(command.label)
        item.visibilityPriority = command.visibility_priority

        return item

    def _create_separator_item(self, command: FicheroCommand):
        """Create a tracking separator item"""
        try:
            item = NSTrackingSeparatorToolbarItem.alloc().initWithItemIdentifier_(command.id)
            # Note: splitView would be set separately if needed
            return item
        except:
            # Fallback to regular item
            item = NSToolbarItem.alloc().initWithItemIdentifier(command.id)
            return item

    def _load_icon(self, icon_path: str, label: str):
        """Load icon from file path or SF Symbol name"""
        import os
        from pathlib import Path

        # Try loading as file first (PNG, JPEG, etc.)
        if '/' in icon_path or icon_path.endswith(('.png', '.jpg', '.jpeg', '.pdf', '.tiff')):
            # It's a file path
            possible_paths = [
                icon_path,  # Absolute path
                os.path.join(os.getcwd(), icon_path),  # Relative to CWD
                os.path.join(os.path.dirname(__file__), icon_path),  # Relative to this file
                os.path.join(os.path.dirname(__file__), '..', icon_path),  # Parent dir
            ]

            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        # Load image from file
                        image = NSImage.alloc().initWithContentsOfFile(at(str(path)))
                        if image:
                            # Resize to toolbar size (32x32)
                            from rubicon.objc import NSSize
                            size = NSSize(32, 32)
                            image.setSize(size)
                            print(f"   ✅ Loaded icon from file: {path}")
                            return image
                    except Exception as e:
                        print(f"   ⚠️  Error loading icon from {path}: {e}")

        # Fall back to SF Symbol
        try:
            image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                icon_path, label
            )
            if image:
                print(f"   ✅ Loaded SF Symbol: {icon_path}")
                return image
        except Exception as e:
            print(f"   ⚠️  Error loading SF Symbol {icon_path}: {e}")

        print(f"   ❌ Could not load icon: {icon_path}")
        return None

    def _add_titlebar_button(self, native_window):
        """Add sidebar toggle button to titlebar (before window title)"""
        try:
            # Import additional ObjC classes
            NSButton = ObjCClass('NSButton')
            NSTitlebarAccessoryViewController = ObjCClass('NSTitlebarAccessoryViewController')

            # Create button with image
            sidebar_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "sidebar.left", "Toggle Sidebar"
            )

            button = NSButton.buttonWithImage_target_action_(
                sidebar_icon,
                self.delegate,
                SEL("handleSidebarToggle:")
            )
            button.bezelStyle = 0  # Rounded
            button.bordered = False
            button.setButtonType(0)  # Momentary light

            # Create view controller for button
            vc = NSTitlebarAccessoryViewController.alloc().init()
            vc.view = button

            # Position on leading edge (left side, before title)
            # NSLayoutAttributeLeading = 5 (left side in LTR, right in RTL)
            vc.layoutAttribute = 5

            # Add to window
            native_window.addTitlebarAccessoryViewController(vc)

            # Keep reference
            self._titlebar_vc = vc
            self._titlebar_button = button

            print("   ✅ Sidebar button added to titlebar (before title)")

        except Exception as e:
            print(f"   ⚠️  Could not add titlebar button: {e}")
            import traceback
            traceback.print_exc()

    def add_command(self, command: FicheroCommand):
        """Add a FicheroCommand as a toolbar item"""
        if not command.show_in_toolbar:
            return

        print(f"➕ Adding toolbar item: {command.id}")

        # Create NSToolbarItem
        item = NSToolbarItem.alloc().initWithItemIdentifier(command.id)

        # Set label
        item.setLabel(command.label)
        item.setPaletteLabel(command.label)

        # Try to load icon if provided
        if command.icon:
            success = self._set_item_icon(item, command.icon)
            if not success:
                print(f"   ⚠️  Failed to load icon: {command.icon}")

        # Set action (use delegate method)
        item.setTarget_(self.delegate)
        item.setAction_(SEL("handleCommand:"))

        # Add to delegate
        self.delegate.toolbar_items[command.id] = item
        self.delegate.command_handlers[command.id] = command
        self.commands[command.id] = command

        print(f"   ✓ Added: {command.id}")

        # Force toolbar to refresh
        if self.toolbar:
            self.toolbar.setAutosavesConfiguration(False)
            self.toolbar.setAutosavesConfiguration(True)
            print("   Toolbar refreshed")

    def _set_item_icon(self, item, icon_path: str) -> bool:
        """Set icon on toolbar item"""
        try:
            from pathlib import Path
            import os

            # Try to find icon file
            if os.path.exists(icon_path):
                path = icon_path
            elif os.path.exists(f"src/fichero/{icon_path}"):
                path = f"src/fichero/{icon_path}"
            else:
                return False

            # Load image
            NSImage = ObjCClass('NSImage')

            # Use at() to create NSString from Python string
            image = NSImage.alloc().initWithContentsOfFile(at(str(path)))

            if image:
                # Resize to toolbar size (32x32)
                from rubicon.objc import NSSize
                size = NSSize(32, 32)
                image.setSize(size)

                item.setImage(image)
                return True

            return False

        except Exception as e:
            print(f"   Error loading icon: {e}")
            return False

# ============================================================================
# Demo Application
# ============================================================================

class FicheroCommandToolbarDemo(toga.App):
    def startup(self):
        """Build the UI"""

        print("\n" + "="*70)
        print("🚀 FicheroCommand + NSToolbar Demo Starting")
        print("="*70)

        # Create main window
        self.main_window = toga.MainWindow(title="FicheroCommand Toolbar Demo")

        # Create simple content
        label = toga.Label(
            "NSToolbar + FicheroCommand Integration Demo\n\n"
            "ALL NSToolbar Item Types:\n"
            "✅ Titlebar Accessory - Sidebar toggle (left of title!)\n"
            "✅ NSSearchToolbarItem - Search field\n"
            "✅ NSToolbarItem - Regular buttons (Import, Export, etc.)\n"
            "✅ NSToolbarItemGroup - Grouped items (Actions group)\n"
            "✅ NSMenuToolbarItem - Dropdown menu (View)\n"
            "✅ PNG Icons - Using custom PNG files from resources!\n"
            "✅ SF Symbols - Mixed with system icons\n"
            "✅ Visibility Priority - Resize window → overflow menu\n\n"
            "Try:\n"
            "• Click sidebar button (far left, before title)\n"
            "• Click toolbar buttons (PNG icons!)\n"
            "• Use the search field\n"
            "• Open the View menu dropdown\n"
            "• Resize window narrow → see overflow menu",
            style=Pack(margin=20, font_size=12)
        )

        self.status_label = toga.Label(
            "Status: Ready",
            style=Pack(margin=20, font_size=12, color="#666")
        )

        # Main content box
        content_box = toga.Box(
            children=[label, self.status_label],
            style=Pack(direction=COLUMN, margin=20, flex=1)
        )

        # Sidebar
        self.sidebar = toga.Box(
            children=[
                toga.Label("Sidebar", style=Pack(margin=20, font_weight="bold")),
                toga.Label("This is a toggleable\nsidebar panel", style=Pack(margin=20)),
            ],
            style=Pack(direction=COLUMN, background_color="#f0f0f0", width=200)
        )

        # Split view with sidebar
        self.split_container = toga.SplitContainer(
            content=[self.sidebar, content_box],
            style=Pack(flex=1)
        )

        self.main_window.content = self.split_container
        self.sidebar_visible = True

        # Add dummy Toga command to initialize toolbar infrastructure
        dummy_cmd = toga.Command(
            lambda w: None,
            text="Dummy",
            group=toga.Group.VIEW
        )
        self.main_window.toolbar.add(dummy_cmd)

        # Show window FIRST
        self.main_window.show()

        # Define commands demonstrating ALL item types
        # Mix of SF Symbols and PNG files
        self.toolbar_commands = [
            # 0. SIDEBAR TOGGLE (appears before title)
            FicheroCommand(
                id="toggleSidebar",  # Special ID for left-side placement
                label="",  # No label - icon only
                icon="sidebar.left",  # SF Symbol
                action=lambda w: self.toggle_sidebar(),
                item_type="button",
                visibility_priority=1000,
                show_in_toolbar=True
            ),

            # 1. SEARCH ITEM
            FicheroCommand(
                id="demo.search",
                label="Search",
                item_type="search",
                visibility_priority=1000,  # High priority - stays visible
                show_in_toolbar=True
            ),

            # 2. BUTTON ITEMS - Mix of PNG files and SF Symbols
            FicheroCommand(
                id="demo.import",
                label="Import",
                icon="src/fichero/resources/icons/toolbar/import.png",  # PNG file!
                action=lambda w: self.update_status("📥 Import clicked!"),
                item_type="button",
                visibility_priority=900,
                show_in_toolbar=True
            ),
            FicheroCommand(
                id="demo.export",
                label="Export",
                icon="src/fichero/resources/icons/toolbar/export.png",  # PNG file!
                action=lambda w: self.update_status("📤 Export clicked!"),
                item_type="button",
                visibility_priority=850,
                show_in_toolbar=True
            ),
            FicheroCommand(
                id="demo.collection",
                label="Collection",
                icon="src/fichero/resources/icons/toolbar/collection.png",  # PNG file!
                action=lambda w: self.update_status("📚 Collection clicked!"),
                item_type="button",
                visibility_priority=800,
                show_in_toolbar=True
            ),

            # 3. GROUPED ITEMS - Using PNG files
            FicheroCommand(
                id="demo.actions.group",
                label="Actions",
                item_type="group",
                visibility_priority=850,
                subitems=[
                    {"id": "duplicate", "label": "Duplicate", "icon": "src/fichero/resources/icons/toolbar/duplicate.png"},
                    {"id": "rename", "label": "Rename", "icon": "src/fichero/resources/icons/toolbar/rename.png"},
                    {"id": "trash", "label": "Trash", "icon": "src/fichero/resources/icons/toolbar/trash.png"},
                ],
                show_in_toolbar=True
            ),

            # 4. MENU DROPDOWN - PNG file with size fix
            FicheroCommand(
                id="demo.view",
                label="View",
                icon="src/fichero/resources/icons/toolbar/square.grid.2x2@10x.png",  # PNG file
                item_type="menu",
                menu_items=["Thumbnails", "List", "Columns", "Gallery"],
                visibility_priority=700,
                show_in_toolbar=True
            ),

            # 5. MORE BUTTONS - Mix of both
            FicheroCommand(
                id="demo.settings",
                label="Settings",
                icon="src/fichero/resources/icons/toolbar/settings.png",  # PNG file!
                action=lambda w: self.update_status("⚙️ Settings clicked!"),
                item_type="button",
                visibility_priority=600,
                show_in_toolbar=True
            ),
            FicheroCommand(
                id="demo.help",
                label="Help",
                icon="src/fichero/resources/icons/toolbar/help.png",  # PNG file!
                action=lambda w: self.update_status("❓ Help clicked!"),
                item_type="button",
                visibility_priority=500,
                show_in_toolbar=True
            ),
            FicheroCommand(
                id="demo.info",
                label="Info",
                icon="info.circle.fill",  # SF Symbol!
                action=lambda w: self.update_status("ℹ️ Info clicked!"),
                item_type="button",
                visibility_priority=100,  # Low priority - overflows first
                show_in_toolbar=True
            ),
        ]

        # Create toolbar AFTER app is running (like ULTIMATE demo)
        async def create_toolbar_after_running(app, **kwargs):
            import asyncio
            await asyncio.sleep(0.5)

            print("\n" + "="*70)
            print("🚀 FicheroCommand + NSToolbar Demo Starting")
            print("="*70)
            print("\n" + "-"*70)
            print("📝 Defining commands...")
            print("\n" + "-"*70)
            print("🔧 Creating toolbar with commands...")

            self.toolbar_manager = SimpleToolbarManager(self.main_window)
            self.toolbar_manager.build_toolbar(self.toolbar_commands)

            print("\n" + "="*70)
            print("✅ Demo ready! Check the toolbar at the top of the window.")
            print("="*70 + "\n")

        self.on_running = create_toolbar_after_running

    def update_status(self, message: str):
        """Update status label"""
        print(f"📢 {message}")
        self.status_label.text = f"Status: {message}"

    def toggle_sidebar(self):
        """Toggle sidebar visibility"""
        self.sidebar_visible = not self.sidebar_visible

        # Get native split view and toggle
        try:
            native_split = self.split_container._impl.native
            if self.sidebar_visible:
                native_split.setPosition_ofDividerAtIndex_(200, 0)
                print("📂 Sidebar shown")
                self.update_status("Sidebar shown")
            else:
                native_split.setPosition_ofDividerAtIndex_(0, 0)
                print("📂 Sidebar hidden")
                self.update_status("Sidebar hidden")
        except Exception as e:
            print(f"⚠️  Error toggling sidebar: {e}")
            self.update_status(f"Sidebar toggle: {self.sidebar_visible}")


def main():
    return FicheroCommandToolbarDemo(
        'FicheroCommand Toolbar Demo',
        'org.example.ficherocommand'
    )


if __name__ == '__main__':
    main().main_loop()
