#!/usr/bin/env python3
"""
Solution from StackOverflow: Configure allowed/default identifiers properly
Based on: https://stackoverflow.com/questions/38391875/
"""

import sys
import toga
from toga.style import Pack


class FixedWithIdentifiers(toga.App):
    def startup(self):
        """Create app and properly configure toolbar identifiers"""
        print("=== App starting ===", flush=True)

        self.label = toga.Label("Fixed with Identifiers", style=Pack(margin=50))
        box = toga.Box(children=[self.label])

        self.main_window = toga.MainWindow(title="Fixed with Identifiers")
        self.main_window.content = box

        # Add a Toga command
        test_cmd = toga.Command(
            lambda w: setattr(self.label, 'text', "Toga Command Clicked"),
            text="Test",
            tooltip="Test command",
            group=toga.Group.VIEW
        )
        self.main_window.toolbar.add(test_cmd)

        self.main_window.show()
        print("✅ Window shown", flush=True)

        # Add dropdown after toolbar is ready
        async def delayed_add(app, **kwargs):
            import asyncio
            await asyncio.sleep(0.5)
            self.add_dropdown_with_identifiers()

        self.on_running = delayed_add

    def add_dropdown_with_identifiers(self):
        """Add dropdown by updating toolbar's allowed/default identifiers"""
        print("\n=== Adding dropdown with identifiers ===", flush=True)

        try:
            from rubicon.objc import ObjCClass, objc_method, NSObject, SEL, CGRectMake, at

            NSToolbarItem = ObjCClass("NSToolbarItem")
            NSPopUpButton = ObjCClass("NSPopUpButton")

            window_impl = self.main_window._impl
            native_window = window_impl.native
            toolbar = native_window.toolbar

            if not toolbar:
                print("❌ No toolbar", flush=True)
                return

            print(f"✅ Found toolbar: {toolbar}", flush=True)
            delegate = toolbar.delegate
            print(f"   Delegate: {delegate}", flush=True)

            # Our new item ID
            item_id = "view.popup.button"

            # Step 1: Get current allowed and default identifiers
            try:
                current_allowed = list(toolbar.allowedItemIdentifiers() or [])
                current_default = list(toolbar.defaultItemIdentifiers() or [])
                print(f"   Current allowed: {len(current_allowed)} items", flush=True)
                print(f"   Current default: {len(current_default)} items", flush=True)
            except Exception as e:
                print(f"   ⚠️  Couldn't get identifiers: {e}", flush=True)
                current_allowed = []
                current_default = []

            # Step 2: Add our ID to both lists
            if item_id not in current_allowed:
                current_allowed.append(item_id)
            if item_id not in current_default:
                current_default.append(item_id)

            print(f"   New allowed: {len(current_allowed)} items", flush=True)
            print(f"   New default: {len(current_default)} items", flush=True)

            # Step 3: Update the toolbar's configuration
            toolbar.setAllowedItemIdentifiers_(at(current_allowed))
            toolbar.setDefaultItemIdentifiers_(at(current_default))
            print("   ✅ Updated identifier lists", flush=True)

            # Step 4: Create the toolbar item with popup button
            toolbar_item = NSToolbarItem.alloc().initWithItemIdentifier(item_id)
            toolbar_item.label = "View"
            toolbar_item.paletteLabel = "View"
            toolbar_item.toolTip = "Change view mode"

            # Create popup button
            button_rect = CGRectMake(0, 0, 80, 25)
            popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(button_rect, False)
            popup.bordered = True
            popup.bezelStyle = 1

            popup.addItemWithTitle("Thumbnails")
            popup.addItemWithTitle("List")
            popup.addItemWithTitle("Columns")
            popup.addItemWithTitle("Gallery")

            # Create action handler
            class PopupHandler(NSObject):
                label_ref = None

                @objc_method
                def handleAction_(self, sender):
                    if self.label_ref:
                        selected = sender.titleOfSelectedItem
                        self.label_ref.text = f"Selected: {selected}"
                        print(f"✅ Action: {selected}", flush=True)

            handler = PopupHandler.alloc().init()
            handler.label_ref = self.label
            popup.target = handler
            popup.action = SEL("handleAction:")

            toolbar_item.view = popup

            print("✅ Created toolbar item with popup", flush=True)

            # Step 5: Store in window_impl so delegate can find it
            if not hasattr(window_impl, '_custom_toolbar_items'):
                window_impl._custom_toolbar_items = {}

            window_impl._custom_toolbar_items[item_id] = toolbar_item

            # Keep references
            self._toolbar_item = toolbar_item
            self._popup = popup
            self._handler = handler

            # Step 6: Patch delegate to return our item
            original_itemFor = delegate.toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_

            def patched_itemFor(toolbar_arg, identifier, insert):
                id_str = str(identifier)
                print(f"🔔 itemForItemIdentifier: {id_str}", flush=True)

                if id_str in window_impl._custom_toolbar_items:
                    item = window_impl._custom_toolbar_items[id_str]
                    print(f"   ✅ Returning custom item", flush=True)
                    return item

                return original_itemFor(toolbar_arg, identifier, insert)

            delegate.toolbar_itemForItemIdentifier_willBeInsertedIntoToolbar_ = patched_itemFor
            print("✅ Patched delegate", flush=True)

            # Step 7: Try to force toolbar to rebuild/validate
            print("\n=== Forcing toolbar update ===", flush=True)
            try:
                # Insert the item
                current_count = len(list(toolbar.items or []))
                toolbar.insertItemWithItemIdentifier_atIndex_(item_id, current_count)
                print(f"   ✅ Inserted at index {current_count}", flush=True)

                # Validate
                toolbar.validateVisibleItems()
                print("   ✅ Validated", flush=True)

                # Check result
                final_count = len(list(toolbar.items or []))
                print(f"   Final count: {final_count}", flush=True)

            except Exception as e:
                print(f"   ⚠️  Update failed: {e}", flush=True)
                import traceback
                traceback.print_exc()

        except Exception as e:
            import traceback
            print(f"\n❌ ERROR: {e}", flush=True)
            traceback.print_exc()
            sys.stdout.flush()


def main():
    return FixedWithIdentifiers("Fixed with Identifiers", "org.test.fixed")


if __name__ == "__main__":
    app = main()
    app.main_loop()
