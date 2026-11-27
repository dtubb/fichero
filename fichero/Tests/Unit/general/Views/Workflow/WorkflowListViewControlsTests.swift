@testable import Fichero
import XCTest

/// Controls of the workflow list that were drawn but did nothing.
/// spec: workflows `workflows.list.icon-double-click-opens`.
final class WorkflowListViewControlsTests: XCTestCase {

    private func viewsSource() throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent("Views/Workflow/Library/WorkflowListView+Views.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// A single-tap gesture attached before a double-tap one takes every
    /// click, so the double tap never fires. The icon grid attaches the
    /// double tap (open) first, as the canvas does for its nodes.
    func testTheIconGridAttachesTheDoubleTapBeforeTheSingleTap() throws {
        let source = try viewsSource()
        let grid = try XCTUnwrap(source.range(of: "var iconGridView: some View"))
        let list = try XCTUnwrap(source.range(of: "var listView: some View"))
        let body = source[grid.upperBound..<list.lowerBound]

        let double = try XCTUnwrap(body.range(of: ".onTapGesture(count: 2) {"))
        let single = try XCTUnwrap(body.range(of: ".onTapGesture {"))

        XCTAssertLessThan(double.lowerBound, single.lowerBound)
    }
}
