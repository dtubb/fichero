@testable import Fichero
import XCTest

/// #6447: the window's minimum width does not follow the width it is measured from.
final class ShellMinimumStabilityTests: XCTestCase {
    private static func appSource(_ relativePath: String) throws -> String {
        try String(contentsOf: AppSource.root().appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// #6447: the window's minimum width fed back into the width it is measured from, so the split view's column
    /// size changed inside its own constraints pass (SIGABRT). With the pane floor as the detail minimum, the minimum
    /// does not move with the measured width, and each width settles in one pass.
    func testTheShellMinimumDoesNotChaseTheMeasuredWidth() {
        let floor = WidescreenPanePlan.make(
            showDocumentGrid: true, showDocumentCanvas: true, showReadingPane: true, showChatPane: true, availableWidth: 0
        ).minimumWidth
        XCTAssertEqual(floor, ContentView.contentListMinWidth, "everything that can shed has shed: the list is the spine")
        for sidebar in [true, false] {
            for inspector in [true, false] {
                for width in stride(from: 100.0, through: 2400.0, by: 7.0) {
                    func minimum(at measured: Double) -> Double {
                        ContentView.shellWindowMinWidth(
                            windowWidth: measured, horizontalSizeClass: .regular, sidebarVisible: sidebar,
                            inspectorVisible: inspector, detailMinWidth: floor
                        )
                    }
                    let first = max(width, minimum(at: width))  // the window is held to its minimum
                    let second = max(first, minimum(at: first))
                    XCTAssertEqual(first, second, "width \(width) sidebar \(sidebar) inspector \(inspector) did not settle in one pass")
                }
            }
        }
    }

    /// #6447: the property that becomes the window's minimum width must not read the plan made for the measured
    /// width (the old code returned `adaptiveWidescreenPanePlan.minimumWidth`, which moves as the window does).
    func testTheDetailMinimumIsNotReadFromThePlanForTheMeasuredWidth() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+StateLayout.swift")
        let start = try XCTUnwrap(source.range(of: "var paneAwareDetailMinWidth: Double {"))
        let end = try XCTUnwrap(source.range(of: "static func adaptiveWidescreenAvailableWidth", range: start.upperBound..<source.endIndex))
        XCTAssertFalse(source[start.upperBound..<end.lowerBound].contains("adaptiveWidescreenPanePlan"))
        XCTAssertTrue(source[start.upperBound..<end.lowerBound].contains("availableWidth: 0"))
    }
}
