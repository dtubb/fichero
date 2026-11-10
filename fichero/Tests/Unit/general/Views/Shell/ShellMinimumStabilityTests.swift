@testable import Fichero
import XCTest

/// #6447: the window's minimum width does not follow the width it is measured from.
final class ShellMinimumStabilityTests: XCTestCase {
    /// #6447: the window's minimum width fed back into the width it is measured from, so the split view's column
    /// size changed inside its own constraints pass (SIGABRT). With the pane floor as the detail minimum, the minimum
    /// does not move with the measured width, and each width settles in one pass.
    func testTheShellMinimumDoesNotChaseTheMeasuredWidth() {
        let floor = ContentView.widescreenDetailMinWidth(grid: true, canvas: true, reading: true, chat: true)
        XCTAssertEqual(floor, ContentView.contentListMinWidth, "everything that can shed has shed: the list is the spine")
        for sidebar in [true, false] {
            for inspector in [true, false] {
                for width in stride(from: 100.0, through: 2400.0, by: 7.0) {
                    func minimum() -> Double {
                        ContentView.shellWindowMinWidth(
                            horizontalSizeClass: .regular, sidebarVisible: sidebar,
                            inspectorVisible: inspector, detailMinWidth: floor
                        )
                    }
                    let first = max(width, minimum())  // the window is held to its minimum
                    let second = max(first, minimum())
                    XCTAssertEqual(first, second, "width \(width) sidebar \(sidebar) inspector \(inspector) did not settle in one pass")
                }
            }
        }
    }

    /// #6447 (second repro, resizing the window with the Document Inspector open): the shell minimum used to drop by the
    /// inspector's width, then the sidebar's, as the window narrowed past a collapse threshold, so the split view's
    /// minimum changed inside its own constraints pass. Whatever the window's width, the minimum is the same.
    func testTheShellMinimumIsTheSameAtEveryWidthTheWindowCanBe() {
        let detail = 600.0
        for sidebar in [true, false] {
            for inspector in [true, false] {
                let expected = ContentView.windowMinWidth(
                    sidebarVisible: sidebar, inspectorVisible: inspector, detailMinWidth: detail)
                // The collapse policy still moves with the width (that is what is SHOWN)…
                let wide = ContentView.shellCollapsePolicy(
                    windowWidth: 3000, horizontalSizeClass: .regular, sidebarVisible: sidebar,
                    inspectorVisible: inspector, detailMinWidth: detail)
                let narrow = ContentView.shellCollapsePolicy(
                    windowWidth: expected - 1, horizontalSizeClass: .regular, sidebarVisible: sidebar,
                    inspectorVisible: inspector, detailMinWidth: detail)
                XCTAssertFalse(wide.collapseInspector)
                if inspector { XCTAssertTrue(narrow.collapseInspector) }
                // …but the window's minimum has no width to follow.
                XCTAssertEqual(
                    ContentView.shellWindowMinWidth(
                        horizontalSizeClass: .regular, sidebarVisible: sidebar,
                        inspectorVisible: inspector, detailMinWidth: detail),
                    expected)
            }
        }
    }

    /// #6447: the detail minimum is the floor the chosen panes shed to (the list is the spine), whatever panes are chosen.
    func testTheWidescreenDetailMinimumIsTheShedFloor() {
        for chat in [true, false] {
            XCTAssertEqual(
                ContentView.widescreenDetailMinWidth(grid: true, canvas: true, reading: true, chat: chat),
                ContentView.contentListMinWidth
            )
        }
        XCTAssertEqual(
            ContentView.widescreenDetailMinWidth(grid: true, canvas: false, reading: false, chat: false),
            ContentView.contentListMinWidth
        )
    }
}
