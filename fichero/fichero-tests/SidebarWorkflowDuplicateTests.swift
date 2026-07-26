@testable import Fichero
import Foundation
import XCTest

/// Locks the sidebar workflow-row Duplicate wiring: the menu item exists only
/// for workflow rows, routes through the existing backend duplicate endpoint
/// (the blessed duplicate-to-edit path for locked Default presets), and
/// surfaces failures instead of logging them away.
final class SidebarWorkflowDuplicateTests: XCTestCase {

    func testDuplicateMenuItemIsKindGated() throws {
        let menu = try appSource("Views/Sidebar/ItemRow/SidebarItemContextMenu.swift")
        // Shown only for kinds with a backend duplicate endpoint.
        XCTAssertTrue(menu.contains("if let onDuplicate, itemTypeSupportsDuplicate {"))
        XCTAssertTrue(menu.contains("case .workflow, .savedSearch, .conversation:"))
        XCTAssertTrue(menu.contains(#"Label("Duplicate", systemImage: "plus.square.on.square")"#))
    }

    func testRowWiresDuplicateThroughExistingEndpoints() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        // Each duplicable kind calls its one existing endpoint; failures
        // surface on the drop banner.
        XCTAssertTrue(row.contains("try await store.duplicateWorkflow(workflow.id)"))
        XCTAssertTrue(row.contains("try await service.duplicateSavedSearch(search.id)"))
        XCTAssertTrue(row.contains("try await service.duplicateConversation(conversation.id)"))
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
