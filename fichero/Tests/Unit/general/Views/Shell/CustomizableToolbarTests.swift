@testable import Fichero
import SwiftUI
import Testing

/// #6730 (the owner's comment, 2026-11-19): which toolbar buttons show is View ▸ Customize Toolbar…, not a Workspaces
/// submenu. Every window toolbar builder returns `some WindowToolbarContent`, which is `CustomizableToolbarContent` on
/// macOS, so the `.toolbar(id:)` sites that call them compile only with customizable items.
struct CustomizableToolbarTests {
    @Test("no window toolbar builder declares a non-customizable some ToolbarContent", arguments: [
        "Views/Shell/ContentView/ContentView+Toolbar.swift",
        "Views/Shell/ContentView/ContentView+SidebarButtons.swift",
        "Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift"
    ])
    func buildersAreCustomizableOnMac(path: String) throws {
        let source = try AppSource.code(path)
        #expect(!source.contains("some ToolbarContent"), "\(path) still declares a non-customizable builder")
    }

    @Test("WindowToolbarContent is CustomizableToolbarContent on macOS")
    func aliasIsCustomizableOnMac() {
        #if os(macOS)
        #expect(ObjectIdentifier((any WindowToolbarContent).self) == ObjectIdentifier((any CustomizableToolbarContent).self))
        #else
        #expect(ObjectIdentifier((any WindowToolbarContent).self) == ObjectIdentifier((any ToolbarContent).self))
        #endif
    }
}
