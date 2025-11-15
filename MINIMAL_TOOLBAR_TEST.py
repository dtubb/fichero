#!/usr/bin/env python3
"""
Minimal test - Copy EXACT pattern from ULTIMATE_TOOLBAR_DEMO
"""

import toga
from toga.style import Pack
from rubicon.objc import ObjCClass, objc_method, NSObject, at, SEL
from rubicon.objc.runtime import load_library

appkit = load_library('AppKit')
NSToolbar = ObjCClass('NSToolbar')
NSToolbarItem = ObjCClass('NSToolbarItem')
NSImage = ObjCClass('NSImage')


class MinimalDelegate(NSObject):
    """Minimal delegate - EXACT copy of working pattern"""

    toolbar_items = {}

    @objc_method
    def toolbarDefaultItemIdentifiers_(self, toolbar):
        print(f"🔔 toolbarDefaultItemIdentifiers: {len(self.toolbar_items)} items", flush=True)
        item_ids = list(self.toolbar_items.keys())
        print(f"   IDs: {item_ids}", flush=True)
        return at(item_ids)

    @objc_method
    def toolbarAllowedItemIdentifiers_(self, toolbar):
        return self.toolbarDefaultItemIdentifiers_(toolbar)

    @objc_method
    def toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_(
        self, toolbar, identifier, insert: bool
    ):
        id_str = str(identifier)
        print(f"🔔 itemForItemIdentifier: '{id_str}'", flush=True)

        if id_str in self.toolbar_items:
            return self.toolbar_items[id_str]

        return None

    @objc_method
    def handleButton_(self, sender):
        print(f"🔔 Button clicked!", flush=True)


class MinimalApp(toga.App):
    def startup(self):
        print("=== Minimal Toolbar Test ===", flush=True)

        # Create window
        self.label = toga.Label("Minimal toolbar test", style=Pack(margin=50))
        self.main_window = toga.MainWindow(title="Minimal Test")
        self.main_window.content = self.label

        # Add dummy Toga command to initialize toolbar infrastructure
        dummy_cmd = toga.Command(
            lambda w: None,
            text="Dummy",
            group=toga.Group.VIEW
        )
        self.main_window.toolbar.add(dummy_cmd)

        self.main_window.show()
        print("✅ Window shown", flush=True)

        # Create toolbar AFTER app is running (like ULTIMATE demo)
        async def create_after_running(app, **kwargs):
            import asyncio
            await asyncio.sleep(0.5)
            self.create_toolbar()

        self.on_running = create_after_running

    def create_toolbar(self):
        print("\n📍 Creating toolbar...", flush=True)

        native_window = self.main_window._impl.native
        native_window.setToolbar(None)

        # Create delegate
        delegate = MinimalDelegate.alloc().init()

        # Create ONE item
        print("📍 Creating item...", flush=True)
        item1 = NSToolbarItem.alloc().initWithItemIdentifier("test.button")
        item1.setLabel("Test")
        item1.setPaletteLabel("Test Button")

        # Use system image
        icon = NSImage.imageWithSystemSymbolName_accessibilityDescription_("star.fill", "Test")
        if icon:
            item1.setImage(icon)

        item1.setTarget_(delegate)
        item1.setAction_(SEL("handleButton:"))
        print("   ✅ Item created", flush=True)

        # Store in delegate - EXACT pattern from working demo
        delegate.toolbar_items = {
            "test.button": item1,
        }
        print(f"   ✅ Stored {len(delegate.toolbar_items)} items in delegate", flush=True)

        # Create toolbar
        print("📍 Creating NSToolbar...", flush=True)
        toolbar = NSToolbar.alloc().initWithIdentifier("minimal.toolbar")
        toolbar.setDelegate(delegate)
        toolbar.setDisplayMode(0)
        print("   ✅ Toolbar created", flush=True)

        # Attach
        print("📍 Attaching toolbar...", flush=True)
        native_window.setToolbar(toolbar)
        toolbar.setVisible(True)
        print("   ✅ Toolbar attached", flush=True)

        # Keep references
        self.toolbar = toolbar
        self.delegate = delegate

        print("\n✅ DONE - check for toolbar", flush=True)


def main():
    return MinimalApp('Minimal Test', 'org.example.minimal')


if __name__ == '__main__':
    main().main_loop()
