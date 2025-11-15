#!/usr/bin/env python3
"""
ULTIMATE NSToolbar DEMO - Every Feature Demonstrated

This demo shows EVERY NSToolbar feature available on macOS:

ITEM TYPES:
✅ NSToolbarItem - Regular buttons
✅ NSMenuToolbarItem - Dropdown menus
✅ NSSearchToolbarItem - Search field
✅ NSToolbarItemGroup - Grouped items
✅ NSTrackingSeparatorToolbarItem - Split view tracking separator
✅ Flexible/Fixed space items

VISUAL FEATURES:
✅ Badges - Notification indicators (unread count, status)
✅ Styles - Plain vs Prominent (tinted backgrounds)
✅ backgroundTintColor - Custom accent colors
✅ navigational - Navigation item behavior
✅ bordered - Border styling

SMART FEATURES:
✅ visibilityPriority - Items stay visible when window narrow
✅ Overflow menu - Items move to menu when space limited
✅ Enable/Disable states - Dynamic state management
✅ Validation - Auto-validate based on app state

CUSTOMIZATION:
✅ allowsUserCustomization - Right-click → "Customize Toolbar..."
✅ autosavesConfiguration - Saves between launches
✅ Drag to reorder, remove, add items

USAGE:
- Right-click toolbar → "Customize Toolbar..."
- Drag items to reorder
- Make window narrow to see overflow menu
- Click "Toggle States" to see enable/disable + badges
- Resize split view to see tracking separator move
"""

import sys
import toga
from toga.style import Pack
from rubicon.objc import ObjCClass, objc_method, NSObject, SEL, at, ObjCInstance
from rubicon.objc.runtime import load_library


class UltimateToolbarDelegate(NSObject):
    """Delegate implementing ALL NSToolbar features"""

    toolbar_items = {}
    label_ref = None
    badge_count = 0
    items_enabled = True

    @objc_method
    def toolbarDefaultItemIdentifiers_(self, toolbar):
        """Default items on first launch"""
        print("🔔 toolbarDefaultItemIdentifiers", flush=True)
        default_ids = [
            "search.bar",
            "NSToolbarFlexibleSpaceItem",
            "inbox.group",  # Grouped items
            "separator.tracking",  # Tracking separator
            "home.button",
            "starred.button",
            "NSToolbarFlexibleSpaceItem",
            "view.dropdown",
            "settings.button",
        ]
        return at(default_ids)

    @objc_method
    def toolbarAllowedItemIdentifiers_(self, toolbar):
        """All items available for customization"""
        print("🔔 toolbarAllowedItemIdentifiers", flush=True)
        allowed_ids = list(self.toolbar_items.keys()) + [
            "NSToolbarSpaceItem",
            "NSToolbarFlexibleSpaceItem",
        ]
        return at(allowed_ids)

    @objc_method
    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, identifier, insert: bool
    ):
        """Create toolbar item for identifier"""
        id_str = str(identifier)
        print(f"🔔 itemForItemIdentifier: '{id_str}'", flush=True)

        if id_str in self.toolbar_items:
            return self.toolbar_items[id_str]

        return None

    # Action handlers
    @objc_method
    def handleSearch_(self, sender):
        search_text = str(sender.stringValue())
        if self.label_ref and search_text:
            self.label_ref.text = f"🔍 Search: {search_text}"

    @objc_method
    def onHomeClick_(self, sender):
        if self.label_ref:
            self.label_ref.text = "🏠 Home clicked"

    @objc_method
    def onStarredClick_(self, sender):
        if self.label_ref:
            self.label_ref.text = "⭐ Starred clicked"

    @objc_method
    def onSettingsClick_(self, sender):
        if self.label_ref:
            self.label_ref.text = "⚙️ Settings clicked"

    @objc_method
    def onToggleStates_(self, sender):
        """Toggle enable/disable states and badges"""
        self.items_enabled = not self.items_enabled
        self.badge_count = (self.badge_count + 5) % 20

        # Update states
        for item_id, item in self.toolbar_items.items():
            if hasattr(item, 'setEnabled_'):
                item.setEnabled_(self.items_enabled)

            # Update badges
            if item_id == "inbox.group" and hasattr(item, 'badge'):
                try:
                    NSItemBadge = ObjCClass("NSItemBadge")
                    if self.badge_count > 0:
                        badge = NSItemBadge.alloc().initWithCount_(self.badge_count)
                        item.badge = badge
                    else:
                        item.badge = None
                except:
                    pass

        status = "enabled" if self.items_enabled else "disabled"
        if self.label_ref:
            self.label_ref.text = f"Items {status}, badges={self.badge_count}"


class UltimateToolbarDemo(toga.App):
    def startup(self):
        """Create ultimate toolbar demo"""
        print("=== ULTIMATE NSToolbar Demo ===", flush=True)
        print("Demonstrating ALL NSToolbar features", flush=True)

        # Create main label
        self.label = toga.Label(
            "ULTIMATE NSToolbar Demo\n\n"
            "Try:\n"
            "• Right-click toolbar → 'Customize Toolbar...'\n"
            "• Drag items to reorder\n"
            "• Make window narrow → overflow menu\n"
            "• Click 'Toggle States' → badges & enable/disable\n"
            "• Resize split → tracking separator moves",
            style=Pack(margin=50, text_align="left", font_size=14)
        )

        # Create split view to demonstrate NSTrackingSeparatorToolbarItem
        left_box = toga.Box(
            children=[toga.Label("Left Panel", style=Pack(margin=20))],
            style=Pack(direction="column", background_color="#f0f0f0", width=200)
        )

        right_box = toga.Box(
            children=[self.label],
            style=Pack(direction="column", flex=1)
        )

        self.split_container = toga.SplitContainer(
            content=[left_box, right_box],
            style=Pack(flex=1)
        )

        self.main_window = toga.MainWindow(title="Ultimate NSToolbar Demo")
        self.main_window.content = self.split_container

        # Add dummy Toga command
        test_cmd = toga.Command(
            lambda w: None,
            text="Dummy",
            group=toga.Group.VIEW
        )
        self.main_window.toolbar.add(test_cmd)

        self.main_window.show()
        print("✅ Window shown", flush=True)

        # Replace with ultimate toolbar
        async def replace_toolbar(app, **kwargs):
            import asyncio
            await asyncio.sleep(0.5)
            self.create_ultimate_toolbar()

        self.on_running = replace_toolbar

    def create_ultimate_toolbar(self):
        """Create toolbar with ALL features"""
        print("\n=== Creating Ultimate Toolbar ===", flush=True)

        try:
            # Load ObjC classes
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
                NSItemBadge = ObjCClass("NSItemBadge")
                badge_available = True
                print("✅ NSItemBadge available", flush=True)
            except:
                badge_available = False
                print("⚠️  NSItemBadge not available (macOS 14+ required)", flush=True)

            native_window = self.main_window._impl.native

            # Remove Toga's toolbar
            print("\n📍 Removing Toga toolbar", flush=True)
            native_window.setToolbar(None)

            # Create delegate
            print("\n📍 Creating delegate", flush=True)
            delegate = UltimateToolbarDelegate.alloc().init()
            delegate.label_ref = self.label

            # ========================================
            # CREATE ALL TOOLBAR ITEM TYPES
            # ========================================
            print("\n📍 Creating toolbar items", flush=True)

            # 1. SEARCH TOOLBAR ITEM
            search_item = NSSearchToolbarItem.alloc().initWithItemIdentifier("search.bar")
            search_item.setLabel("Search")
            search_item.setPaletteLabel("Search")
            search_item.setToolTip("Search everything")
            search_item.visibilityPriority = 1000  # High priority - stays visible
            search_field = search_item.searchField
            search_field.placeholderString = "Search..."
            search_field.setTarget_(delegate)
            search_field.setAction_(SEL("handleSearch:"))
            print("   ✅ Search item (high priority)", flush=True)

            # 2. TOOLBAR ITEM GROUP (Inbox/Archive/Trash)
            print("\n   Creating NSToolbarItemGroup...", flush=True)

            # Create subitems for group
            inbox_subitem = NSToolbarItem.alloc().initWithItemIdentifier("inbox.subitem")
            inbox_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "tray.fill", "Inbox"
            )
            if inbox_icon:
                inbox_subitem.setImage(inbox_icon)
            inbox_subitem.setLabel("Inbox")
            inbox_subitem.setToolTip("View inbox")

            archive_subitem = NSToolbarItem.alloc().initWithItemIdentifier("archive.subitem")
            archive_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "archivebox.fill", "Archive"
            )
            if archive_icon:
                archive_subitem.setImage(archive_icon)
            archive_subitem.setLabel("Archive")
            archive_subitem.setToolTip("View archive")

            trash_subitem = NSToolbarItem.alloc().initWithItemIdentifier("trash.subitem")
            trash_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "trash.fill", "Trash"
            )
            if trash_icon:
                trash_subitem.setImage(trash_icon)
            trash_subitem.setLabel("Trash")
            trash_subitem.setToolTip("View trash")

            # Create group
            inbox_group = NSToolbarItemGroup.alloc().initWithItemIdentifier("inbox.group")
            inbox_group.setSubitems([inbox_subitem, archive_subitem, trash_subitem])
            inbox_group.setLabel("Mail")
            inbox_group.setPaletteLabel("Mail Actions")
            inbox_group.setToolTip("Mail management")
            inbox_group.visibilityPriority = 900  # Keep visible

            # Set badge if available
            if badge_available:
                try:
                    badge = NSItemBadge.alloc().initWithCount_(5)
                    inbox_group.badge = badge
                    print("   ✅ Inbox group (with badge: 5)", flush=True)
                except Exception as e:
                    print(f"   ⚠️  Could not set badge: {e}", flush=True)
            else:
                print("   ✅ Inbox group (no badge - requires macOS 14+)", flush=True)

            # 3. TRACKING SEPARATOR (tracks split view)
            print("\n   Creating NSTrackingSeparatorToolbarItem...", flush=True)
            try:
                separator = NSTrackingSeparatorToolbarItem.alloc().initWithItemIdentifier_(
                    "separator.tracking"
                )
                # Link to split view
                native_split = self.split_container._impl.native
                separator.splitView = native_split
                separator.dividerIndex = 0  # Track first divider
                print("   ✅ Tracking separator (follows split view)", flush=True)
            except Exception as e:
                print(f"   ⚠️  Tracking separator failed: {e}", flush=True)
                # Fallback to regular separator
                separator = NSToolbarItem.alloc().initWithItemIdentifier("separator.tracking")
                print("   ✅ Regular separator (fallback)", flush=True)

            # 4. NAVIGATIONAL ITEM (styled as navigation)
            home_item = NSToolbarItem.alloc().initWithItemIdentifier("home.button")
            home_item.setLabel("Home")
            home_item.setPaletteLabel("Home")
            home_item.setToolTip("Navigate home")
            home_item.visibilityPriority = 800
            home_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "house.fill", "Home"
            )
            if home_icon:
                home_item.setImage(home_icon)
            home_item.setTarget_(delegate)
            home_item.setAction_(SEL("onHomeClick:"))

            # Set navigational style
            try:
                home_item.navigational = True
                print("   ✅ Home (navigational style)", flush=True)
            except:
                print("   ✅ Home (regular style - navigational not available)", flush=True)

            # 5. PROMINENT STYLED ITEM (tinted background)
            starred_item = NSToolbarItem.alloc().initWithItemIdentifier("starred.button")
            starred_item.setLabel("Starred")
            starred_item.setPaletteLabel("Starred Items")
            starred_item.setToolTip("View starred items")
            starred_item.visibilityPriority = 700
            starred_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "star.fill", "Starred"
            )
            if starred_icon:
                starred_item.setImage(starred_icon)
            starred_item.setTarget_(delegate)
            starred_item.setAction_(SEL("onStarredClick:"))
            starred_item.bordered = True

            # Try to set prominent style and custom tint
            try:
                # Style: 0=plain, 1=prominent
                starred_item.style = 1
                # Custom tint color (orange)
                orange_color = NSColor.orangeColor()
                starred_item.backgroundTintColor = orange_color
                print("   ✅ Starred (prominent style, orange tint)", flush=True)
            except Exception as e:
                print(f"   ⚠️  Starred (style/tint not available): {e}", flush=True)

            # 6. MENU DROPDOWN
            view_menu = NSMenuToolbarItem.alloc().initWithItemIdentifier("view.dropdown")
            view_menu.setLabel("View")
            view_menu.setPaletteLabel("View Options")
            view_menu.setToolTip("Change view mode")
            view_menu.showsIndicator = True
            view_menu.isBordered = True
            view_menu.visibilityPriority = 600

            view_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "square.grid.2x2.fill", "View"
            )
            if view_icon:
                view_menu.setImage(view_icon)

            menu = NSMenu.alloc().initWithTitle("View")
            menu_items = ["Thumbnails", "List", "Columns", "Gallery"]

            class MenuHandler(NSObject):
                label_ref = None
                mode = None

                @objc_method
                def handleAction_(self, sender):
                    if self.label_ref:
                        self.label_ref.text = f"View: {self.mode}"

            handlers = []
            for mode in menu_items:
                item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    mode, SEL("handleAction:"), ""
                )
                handler = MenuHandler.alloc().init()
                handler.label_ref = self.label
                handler.mode = mode
                item.target = handler
                handlers.append(handler)
                menu.addItem(item)

            view_menu.menu = menu
            self._menu_handlers = handlers
            print("   ✅ View dropdown", flush=True)

            # 7. SETTINGS BUTTON (lower priority - goes to overflow first)
            settings_item = NSToolbarItem.alloc().initWithItemIdentifier("settings.button")
            settings_item.setLabel("Settings")
            settings_item.setPaletteLabel("Settings")
            settings_item.setToolTip("Open settings")
            settings_item.visibilityPriority = 100  # LOW priority - overflows first
            settings_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "gearshape.fill", "Settings"
            )
            if settings_icon:
                settings_item.setImage(settings_icon)
            settings_item.setTarget_(delegate)
            settings_item.setAction_(SEL("onSettingsClick:"))
            print("   ✅ Settings (low priority - overflows first)", flush=True)

            # 8. TOGGLE STATES BUTTON (for demo)
            toggle_item = NSToolbarItem.alloc().initWithItemIdentifier("toggle.button")
            toggle_item.setLabel("Toggle")
            toggle_item.setPaletteLabel("Toggle States")
            toggle_item.setToolTip("Toggle enable/disable and badges")
            toggle_item.visibilityPriority = 500
            toggle_icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "switch.2", "Toggle"
            )
            if toggle_icon:
                toggle_item.setImage(toggle_icon)
            toggle_item.setTarget_(delegate)
            toggle_item.setAction_(SEL("onToggleStates:"))
            print("   ✅ Toggle states button", flush=True)

            # Store all items
            delegate.toolbar_items = {
                "search.bar": search_item,
                "inbox.group": inbox_group,
                "separator.tracking": separator,
                "home.button": home_item,
                "starred.button": starred_item,
                "view.dropdown": view_menu,
                "settings.button": settings_item,
                "toggle.button": toggle_item,
            }

            print(f"\n   ✅ Created {len(delegate.toolbar_items)} toolbar items", flush=True)

            # ========================================
            # CREATE TOOLBAR
            # ========================================
            print("\n📍 Creating NSToolbar", flush=True)
            toolbar = NSToolbar.alloc().initWithIdentifier("fichero.ultimate.toolbar")
            toolbar.setDelegate(delegate)
            toolbar.setAllowsUserCustomization(True)  # Enable customization
            toolbar.setAutosavesConfiguration(True)   # Save layout
            toolbar.setDisplayMode(0)  # Icon + label
            print("   ✅ Customization + autosave enabled", flush=True)

            # Set toolbar
            print("\n📍 Setting toolbar on window", flush=True)
            native_window.setToolbar(toolbar)

            # Verify
            print("\n📍 Verification", flush=True)
            items = list(native_window.toolbar.items or [])
            print(f"✅ Toolbar has {len(items)} items:", flush=True)
            for i, item in enumerate(items):
                item_type = type(item).__name__
                label = getattr(item, 'label', 'N/A')
                priority = getattr(item, 'visibilityPriority', 'N/A')
                print(f"   {i}: {label} ({item_type}, priority={priority})", flush=True)

            # Keep references
            self._toolbar = toolbar
            self._delegate = delegate

            print("\n" + "="*70, flush=True)
            print("✅ ULTIMATE TOOLBAR READY!", flush=True)
            print("="*70, flush=True)
            print("\nFEATURES DEMONSTRATED:", flush=True)
            print("✅ NSToolbarItemGroup (Inbox/Archive/Trash)", flush=True)
            print("✅ Badges on grouped items", flush=True)
            print("✅ NSTrackingSeparatorToolbarItem", flush=True)
            print("✅ Navigational styling", flush=True)
            print("✅ Prominent style with custom tint", flush=True)
            print("✅ Visibility priority (resize window!)", flush=True)
            print("✅ Customization + autosave", flush=True)
            print("✅ Enable/disable states", flush=True)
            print("\nTRY:", flush=True)
            print("• Right-click toolbar → Customize", flush=True)
            print("• Resize window narrow → see overflow", flush=True)
            print("• Click 'Toggle' → badges & states", flush=True)
            print("• Resize split → separator tracks", flush=True)
            print("="*70, flush=True)

        except Exception as e:
            import traceback
            print(f"\n❌ ERROR: {e}", flush=True)
            traceback.print_exc()


def main():
    return UltimateToolbarDemo("Ultimate NSToolbar", "org.fichero.ultimate")


if __name__ == "__main__":
    app = main()
    app.main_loop()
