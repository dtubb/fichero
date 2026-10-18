@testable import Fichero
import XCTest

/// `panes.chrome.breadcrumb-only-when-pinned` (#5437): the pane head draws its breadcrumb capsule on macOS
/// only while the pane is pinned (an unpinned crumb repeats the window toolbar). Source-shape guard.
@MainActor
final class BreadcrumbOnlyWhenPinnedShapeTests: XCTestCase {
    func testHeadGatesTheBreadcrumbOnPinOnMac() throws {
        let source = try AppSource.code("Views/Shell/PaneHead/PaneHead.swift")
        XCTAssertTrue(source.contains("if showsBreadcrumb { breadcrumbCapsule }"), "the crumb is drawn unconditionally again")
        let gate = try XCTUnwrap(source.range(of: "private var showsBreadcrumb: Bool {"))
        let body = String(source[gate.upperBound...].prefix(200))
        XCTAssertTrue(body.contains("#if os(macOS)") && body.contains("isPinned?.wrappedValue ?? false"),
                      "the macOS crumb is no longer tied to the pin state")
    }
}
