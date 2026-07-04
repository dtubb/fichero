@testable import Fichero
import SwiftUI
import XCTest

/// Table-driven collapse-decision coverage for the extracted ShellLayoutPolicy
/// (#3035): width × size class × visibility → (collapseSidebar, collapseInspector).
/// Guards the extraction (no behavior change) and the boundary widths.
final class ShellCollapsePolicyTableTests: XCTestCase {
    private let detail = 600.0
    private var sidebarBoundary: Double { detail + ContentView.sidebarMinWidth }
    private var inspectorBoundary: Double { detail + ContentView.sidebarMinWidth + ContentView.inspectorMinWidth }

    private func collapse(_ width: Double?, _ sizeClass: UserInterfaceSizeClass?,
                          sidebar: Bool = true, inspector: Bool = true) -> ContentView.ShellCollapsePolicy {
        ContentView.shellCollapsePolicy(
            windowWidth: width,
            horizontalSizeClass: sizeClass,
            sidebarVisible: sidebar,
            inspectorVisible: inspector,
            detailMinWidth: detail
        )
    }

    func testRegularWidthCollapseTable() {
        // Roomy: nothing collapses.
        XCTAssertEqual(collapse(inspectorBoundary + 40, .regular),
                       .init(collapseSidebar: false, collapseInspector: false))
        // Exactly at the inspector boundary: nothing collapses (strict `<`).
        XCTAssertEqual(collapse(inspectorBoundary, .regular),
                       .init(collapseSidebar: false, collapseInspector: false))
        // Just below inspector boundary: inspector collapses, sidebar stays.
        XCTAssertEqual(collapse(inspectorBoundary - 1, .regular),
                       .init(collapseSidebar: false, collapseInspector: true))
        // Exactly at the sidebar boundary: sidebar stays (strict `<`).
        XCTAssertEqual(collapse(sidebarBoundary, .regular),
                       .init(collapseSidebar: false, collapseInspector: true))
        // Just below the sidebar boundary: both collapse.
        XCTAssertEqual(collapse(sidebarBoundary - 1, .regular),
                       .init(collapseSidebar: true, collapseInspector: true))
    }

    func testNilOrZeroWidthNeverCollapses() {
        for width in [nil, 0.0, -5.0] as [Double?] {
            XCTAssertEqual(collapse(width, .regular),
                           .init(collapseSidebar: false, collapseInspector: false),
                           "width \(String(describing: width))")
        }
    }

    func testCompactAlwaysCollapsesSidebarOnly() {
        for width in [nil, 300.0, 5000.0] as [Double?] {
            XCTAssertEqual(collapse(width, .compact),
                           .init(collapseSidebar: true, collapseInspector: false),
                           "width \(String(describing: width))")
        }
    }

    func testHiddenPanesDoNotCollapse() {
        // A hidden pane can't collapse regardless of width.
        XCTAssertFalse(collapse(100, .regular, sidebar: false, inspector: true).collapseSidebar)
        XCTAssertFalse(collapse(100, .regular, sidebar: true, inspector: false).collapseInspector)
    }
}
