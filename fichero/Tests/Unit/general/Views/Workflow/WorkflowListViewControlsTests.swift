@testable import Fichero
import XCTest

/// The workflow list's table view.
/// spec: workflows `workflows.list.table-sorts-by-its-headers`.
final class WorkflowListViewControlsTests: XCTestCase {

    /// The table hands SwiftUI a `sortOrder` binding, so its headers show a
    /// sort arrow when clicked. The rows it lists follow that order.
    func testTheTableRowsFollowTheOrderTheHeadersSet() {
        let workflows = [
            WorkflowSidebarItem(id: "b", name: "Beta", nodeCount: 2, edgeCount: 1),
            WorkflowSidebarItem(id: "c", name: "Gamma", nodeCount: 9, edgeCount: 8),
            WorkflowSidebarItem(id: "a", name: "Alpha", nodeCount: 5, edgeCount: 4)
        ]

        let byName = WorkflowListView.tableRows(
            workflows, sortedBy: [KeyPathComparator(\WorkflowSidebarItem.name)]
        )
        let byNodesDescending = WorkflowListView.tableRows(
            workflows, sortedBy: [KeyPathComparator(\WorkflowSidebarItem.nodeCount, order: .reverse)]
        )

        XCTAssertEqual(byName.map(\.id), ["a", "b", "c"])
        XCTAssertEqual(byNodesDescending.map(\.id), ["c", "a", "b"])
    }
}
