@testable import Fichero
import Foundation
import XCTest

/// Locks the sidebar workflow-row Duplicate wiring: the menu item exists only
/// for workflow rows, routes through the existing backend duplicate endpoint
/// (the blessed duplicate-to-edit path for locked Default presets), and
/// surfaces failures instead of logging them away.
final class SidebarWorkflowDuplicateTests: XCTestCase {

    func testDuplicateMenuItemIsWorkflowGated() throws {
        let menu = try appSource("Views/Sidebar/ItemRow/SidebarItemContextMenu.swift")
        // Shown only when a workflow row provides the callback.
        XCTAssertTrue(menu.contains("if let onDuplicate, case .workflow = item.itemType {"))
        XCTAssertTrue(menu.contains(#"Label("Duplicate", systemImage: "plus.square.on.square")"#))
    }

    func testRowWiresDuplicateThroughWorkflowStore() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        // Non-workflow rows get nil (menu item hidden), workflow rows call the
        // one existing store endpoint and surface errors on the drop banner.
        XCTAssertTrue(row.contains("guard case .workflow(let workflow) = item.itemType,"))
        XCTAssertTrue(row.contains("try await store.duplicateWorkflow(workflow.id)"))
        XCTAssertTrue(row.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
