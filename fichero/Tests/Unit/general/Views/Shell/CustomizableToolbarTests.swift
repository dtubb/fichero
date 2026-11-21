@testable import Fichero
import Testing

/// #6730 (the owner's comment, 2026-11-19): which toolbar buttons show is View ▸ Customize Toolbar…, not a Workspaces
/// submenu. On the Mac every window `.toolbar` site names the one toolbar id, and every builder those sites call
/// returns `some WindowToolbarContent`, which is `CustomizableToolbarContent` on macOS: an item without an id there
/// does not compile.
struct CustomizableToolbarTests {
    @Test("every Mac toolbar site is toolbar(id:) with the shared id", arguments: [
        ("Views/Shell/ContentView/Layout/ContentView+RootLayout.swift", 2),
        ("Views/Shell/ContentView/Layout/ContentView+SidebarLayout.swift", 1),
        ("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift", 1)
    ])
    func macSitesAreCustomizable(path: String, sites: Int) throws {
        let source = try AppSource.code(path)
        let found = source.components(separatedBy: ".toolbar(id: ContentToolbarID.customizableToolbar)").count - 1
        #expect(found == sites, "\(path): \(found) customizable toolbar sites, expected \(sites)")
    }

    @Test("every window toolbar builder returns WindowToolbarContent", arguments: [
        ("Views/Shell/ContentView/ContentView+Toolbar.swift", 5),
        ("Views/Shell/ContentView/ContentView+SidebarButtons.swift", 1),
        ("Views/Shell/ContentView/Layout/ContentView+InspectorContainer.swift", 2)
    ])
    func buildersAreCustomizableOnMac(path: String, builders: Int) throws {
        let source = try AppSource.code(path)
        #expect(!source.contains("some ToolbarContent"), "\(path) still declares a non-customizable builder")
        let found = source.components(separatedBy: "some WindowToolbarContent").count - 1
        #expect(found == builders, "\(path): \(found) builders, expected \(builders)")
    }

    @Test("WindowToolbarContent is CustomizableToolbarContent on macOS")
    func aliasIsCustomizableOnMac() throws {
        let source = try AppSource.code("Views/Shell/ContentView/ContentView+Toolbar.swift")
        #expect(source.contains("#if os(macOS)\ntypealias WindowToolbarContent = CustomizableToolbarContent\n#else"))
    }

    @Test("the sidebar column's item has its own id")
    func sidebarItemHasId() throws {
        let source = try AppSource.code("Views/Shell/ContentView/ContentView+SidebarButtons.swift")
        #expect(source.contains("ToolbarItem(id: ContentToolbarID.sidebarColumnButtons"))
    }
}
