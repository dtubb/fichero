#!/usr/bin/env python3
"""
FINAL SOLUTION: Replace Toga's toolbar_itemForItemIdentifier delegate method
with our own version that creates NSMenuToolbarItem for dropdown menus
"""

import sys
import toga
from toga.style import Pack


def enable_toolbar_dropdown_menus(window):
    """
    Enable NSMenuToolbarItem support for a Toga window by replacing
    the delegate's toolbar item creation method.

    Call this after window.show() to enable dropdown menu support.
    Then add dropdown menus via toolbar.add() with NSMenuToolbarItemSpec objects.
    """
    from rubicon.objc import ObjCClass, objc_method, NSObject, SEL

    NSToolbarItem = ObjCClass("NSToolbarItem")
    NSMenuToolbarItem = ObjCClass("NSMenuToolbarItem")
    NSMenu = ObjCClass("NSMenu")
    NSMenuItem = ObjCClass("NSMenuItem")

    window_impl = window._impl
    delegate = window_impl.native.toolbar.delegate

    # Save Toga's original method
    original_itemFor = delegate.toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_

    def custom_itemFor(toolbar, identifier, insert: bool):
        """
        Custom delegate method that creates NSMenuToolbarItem for dropdown menus,
        regular NSToolbarItem for normal commands.
        """
        id_str = str(identifier)

        # Check if this is a dropdown menu item
        if id_str in window_impl._toolbar_items:
            item = window_impl._toolbar_items[id_str]

            # Check if this item has a _is_nsmenu_item marker
            if hasattr(item, '_is_nsmenu_item') and item._is_nsmenu_item:
                # Create NSMenuToolbarItem
                menu_toolbar_item = NSMenuToolbarItem.alloc().initWithItemIdentifier_(id_str)
                menu_toolbar_item.setLabel(item.text)
                menu_toolbar_item.setPaletteLabel(item.text)
                if item.tooltip:
                    menu_toolbar_item.setToolTip(item.tooltip)

                # Set menu properties
                menu_toolbar_item.showsIndicator = item._menu_shows_indicator
                menu_toolbar_item.isBordered = item._menu_is_bordered

                # Get the menu from the item
                if hasattr(item, '_menu'):
                    menu_toolbar_item.menu = item._menu

                print(f"✅ Created NSMenuToolbarItem for '{id_str}'", flush=True)
                return menu_toolbar_item

        # Otherwise, use Toga's original method
        return original_itemFor(toolbar, identifier, insert)

    # Replace the delegate method
    delegate.toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_ = custom_itemFor
    print("✅ Enabled dropdown menu support for toolbar", flush=True)


class NSMenuToolbarItemSpec:
    """
    Specification for a toolbar dropdown menu item.
    Used with window.toolbar.add() after enable_toolbar_dropdown_menus().
    """
    def __init__(self, item_id, label, menu_items, on_select,
                 tooltip=None, shows_indicator=True, is_bordered=True):
        from rubicon.objc import ObjCClass, objc_method, NSObject, SEL

        NSMenu = ObjCClass("NSMenu")
        NSMenuItem = ObjCClass("NSMenuItem")

        self.text = label  # Required by Toga
        self.tooltip = tooltip or label
        self.icon = None
        self.enabled = True
        self._impl = type('obj', (object,), {'native': []})()  # Empty native list

        # Marker for our custom delegate
        self._is_nsmenu_item = True
        self._menu_shows_indicator = shows_indicator
        self._menu_is_bordered = is_bordered

        # Create the NSMenu
        menu = NSMenu.alloc().initWithTitle(label)

        # Create action handler
        class MenuHandler(NSObject):
            callback = None
            item_name = None

            @objc_method
            def handleAction_(self, sender):
                if self.callback and self.item_name:
                    self.callback(self.item_name)

        # Add menu items
        handlers = []
        for item_name in menu_items:
            menu_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                item_name, SEL("handleAction:"), ""
            )
            handler = MenuHandler.alloc().init()
            handler.callback = on_select
            handler.item_name = item_name
            menu_item.target = handler
            handlers.append(handler)
            menu.addItem(menu_item)

        self._menu = menu
        self._handlers = handlers  # Keep handlers alive


class FinalSolutionDemo(toga.App):
    def startup(self):
        """Demonstrate the final working solution"""
        print("=== Final Solution Demo ===", flush=True)

        self.label = toga.Label("Final Solution - Working Dropdowns!", style=Pack(margin=50))
        box = toga.Box(children=[self.label])

        self.main_window = toga.MainWindow(title="Final Solution")
        self.main_window.content = box

        # Add a regular Toga command
        test_cmd = toga.Command(
            lambda w: setattr(self.label, 'text', "Toga Command Clicked"),
            text="Test",
            tooltip="Test command",
            group=toga.Group.VIEW
        )
        self.main_window.toolbar.add(test_cmd)

        self.main_window.show()
        print("✅ Window shown", flush=True)

        # Enable dropdown menu support
        async def add_dropdowns(app, **kwargs):
            import asyncio
            await asyncio.sleep(0.5)

            # Enable dropdown support
            enable_toolbar_dropdown_menus(self.main_window)

            # Create View dropdown
            view_menu = NSMenuToolbarItemSpec(
                item_id="view.dropdown",
                label="View",
                menu_items=["Thumbnails", "List", "Columns", "Gallery"],
                on_select=self.on_view_selected,
                tooltip="Change view mode"
            )

            # Add via Toga's toolbar system
            window_impl = self.main_window._impl
            window_impl._toolbar_items["view.dropdown"] = view_menu

            # Trigger toolbar rebuild
            window_impl.create_toolbar()

            print("\n=== Checking result ===", flush=True)
            toolbar = window_impl.native.toolbar
            items = list(toolbar.items or [])
            print(f"Toolbar has {len(items)} items:", flush=True)
            for i, item in enumerate(items):
                item_type = type(item).__name__
                print(f"   {i}: {item.itemIdentifier} - '{item.label}' ({item_type})", flush=True)

        self.on_running = add_dropdowns

    def on_view_selected(self, view_name):
        """Handle view menu selection"""
        self.label.text = f"View: {view_name}"
        print(f"✅ Selected: {view_name}", flush=True)


def main():
    return FinalSolutionDemo("Final Solution", "org.test.final")


if __name__ == "__main__":
    app = main()
    app.main_loop()
