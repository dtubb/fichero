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
        XCTAssertTrue(menu.contains("if onDuplicate != nil, itemTypeSupportsDuplicate {"))
        XCTAssertTrue(menu.contains("case .document, .workflow, .savedSearch, .conversation:"))
        // File's own Duplicate item (#5652), on the row's target.
        XCTAssertTrue(menu.contains("DuplicateItemMenuItem(target: copyTarget)"))
    }

    func testRowWiresDuplicateThroughExistingEndpoints() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift")
        // Each duplicable kind calls its one existing endpoint; failures
        // surface on the drop banner.
        XCTAssertTrue(row.contains("try await store.duplicateWorkflow(workflow.id)"))
        // The audited document.duplicate, through the one undo helper since #5658 (a step ⌘Z takes back).
        XCTAssertNotNil(row.range(of: #"UndoableChange\.invoke\(\s*"document\.duplicate""#, options: .regularExpression))
        XCTAssertTrue(row.contains("try await service.duplicateSavedSearch(search.id)"))
        XCTAssertTrue(row.contains("try await service.duplicateConversation(conversation.id)"))
        XCTAssertTrue(row.contains("sidebarState.dropErrorMessage = error.localizedDescription"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
