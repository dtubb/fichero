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
