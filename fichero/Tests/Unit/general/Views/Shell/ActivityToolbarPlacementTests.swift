@testable import Fichero
import Foundation
import Testing

/// #7090: the Activity button sits at the far right of the toolbar, after Workspaces, and its popover toggles.
struct ActivityToolbarPlacementTests {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    @Test("the Activity item is declared after Workspaces and outside the island's principal run")
    func activityFollowsWorkspaces() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+Toolbar.swift")
        let workspaces = try #require(source.range(of: "ToolbarItem(id: ContentToolbarID.workspacesMenu"))
        let activity = try #require(source.range(of: "ToolbarItem(id: ContentToolbarID.activityStatus, placement: .automatic)"))
        #expect(workspaces.lowerBound < activity.lowerBound)
        // The engine's item no longer hosts it.
        let engine = try #require(source.range(of: "ToolbarItem(id: ContentToolbarID.engineStatus"))
        let afterEngine = String(source[engine.upperBound...].prefix(400))
        #expect(!afterEngine.contains("ActivityStatusToolbarItem("))
    }

    @Test("a click toggles the popover, so two clicks never leave two")
    func clickToggles() throws {
        let source = try Self.appSource("Views/Shell/Toolbar/ActivityStatusToolbarItem.swift")
        #expect(!source.contains("showPopover = true"))
        #expect(source.components(separatedBy: "showPopover.toggle()").count - 1 == 3)
        // One popover, on one view.
        #expect(source.components(separatedBy: ".popover(isPresented: $showPopover)").count - 1 == 1)
    }
}
