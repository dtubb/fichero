#!/usr/bin/env python3
"""
Minimal test - Create NSToolbar with 1 button to verify basic functionality
"""
import toga
from toga.style import Pack
from rubicon.objc import ObjCClass, objc_method, NSObject, SEL, at

NSToolbar = ObjCClass("NSToolbar")
NSToolbarItem = ObjCClass("NSToolbarItem")
NSImage = ObjCClass("NSImage")


class SimpleDelegate(NSObject):
    """Minimal toolbar delegate"""

    @objc_method
    def toolbarDefaultItemIdentifiers_(self, toolbar):
        print("📍 toolbarDefaultItemIdentifiers called")
        return at(["test.button"])

    @objc_method
    def toolbarAllowedItemIdentifiers_(self, toolbar):
        print("📍 toolbarAllowedItemIdentifiers called")
        return at(["test.button"])

    @objc_method
    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, identifier, insert: bool
    ):
        print(f"📍 toolbar_itemForItemIdentifier called: {identifier}")

        # Create item
        item = NSToolbarItem.alloc().initWithItemIdentifier("test.button")
        item.setLabel("Test Button")
        item.setPaletteLabel("Test")

        # Try SF Symbol
        print("   Loading SF Symbol: folder.fill")
        icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            "folder.fill",
            "Test"
        )
        if icon:
            print("   ✓ Icon loaded!")
            item.setImage(icon)
        else:
            print("   ✗ Icon NOT loaded")

        print(f"   Returning item: {item}")
        return item


class SimpleApp(toga.App):
    def startup(self):
        print("\n🚀 Starting simple toolbar test")

        # Create main window
        main_box = toga.Box(style=Pack(flex=1))
        self.main_window = toga.MainWindow(title="Simple Toolbar Test")
        self.main_window.content = main_box

        print("📍 Window created, now building toolbar...")

        # Get native window
        native_window = self.main_window._impl.native
        print(f"   Native window: {native_window}")

        # Create delegate
        delegate = SimpleDelegate.alloc().init()
        print(f"   Delegate created: {delegate}")

        # Create toolbar
        toolbar = NSToolbar.alloc().initWithIdentifier("test.toolbar")
        toolbar.setDelegate(delegate)
        toolbar.setDisplayMode(0)  # Icon + label
        toolbar.setAllowsUserCustomization(True)
        print(f"   Toolbar created: {toolbar}")

        # Attach to window
        native_window.setToolbar(toolbar)
        print("   ✓ Toolbar attached to window")

        # Verify
        current = native_window.toolbar
        print(f"   Window's toolbar: {current}")
        print(f"   Toolbar visible: {toolbar.visible if hasattr(toolbar, 'visible') else 'N/A'}")

        # Show window
        print("📍 Showing window...")
        self.main_window.show()
        print("✅ Window shown - check if toolbar is visible!")


def main():
    return SimpleApp("Simple Toolbar Test", "org.test.simple")


if __name__ == "__main__":
    main().main_loop()
