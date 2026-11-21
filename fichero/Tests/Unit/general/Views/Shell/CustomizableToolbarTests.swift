@testable import Fichero
import SwiftUI
import Testing

/// #6730 (the owner's comment, 2026-11-19): which toolbar buttons show is View ▸ Customize Toolbar…, not a Workspaces
/// submenu. Every window toolbar builder returns `some WindowToolbarContent`; on macOS that is
/// `CustomizableToolbarContent`, so a builder with an item that has no id fails to compile at its `.toolbar(id:)` site.
struct CustomizableToolbarTests {
    @Test("WindowToolbarContent is CustomizableToolbarContent on macOS")
    func aliasIsCustomizableOnMac() {
        #if os(macOS)
        #expect(ObjectIdentifier((any WindowToolbarContent).self) == ObjectIdentifier((any CustomizableToolbarContent).self))
        #else
        #expect(ObjectIdentifier((any WindowToolbarContent).self) == ObjectIdentifier((any ToolbarContent).self))
        #endif
    }
}
