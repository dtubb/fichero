@testable import Fichero
import XCTest

/// #7065: the Inspector's collapse rule must not read its own result, or full screen shows and hides it forever.
final class ShellCollapseSettleTests: XCTestCase {
    func testInspectorCollapseSettlesAtEveryWidth() {
        for window in stride(from: 600.0, through: 2600.0, by: 50.0) {
            for inspector in stride(from: 260.0, through: 800.0, by: 20.0) {
                for sidebar in [true, false] {
                    for detailMin in [220.0, 330.0, 550.0] {
                        // The person's choice stays "Inspector on"; only the measured width moves with the column.
                        func collapses(measured: Double, frame: Double?) -> Bool {
                            ContentView.shellCollapsePolicy(
                                windowWidth: ContentView.shellCollapseWidth(measured: measured, inspectorFrameWidth: frame),
                                horizontalSizeClass: .regular, sidebarVisible: sidebar,
                                inspectorVisible: true, detailMinWidth: detailMin
                            ).collapseInspector
                        }
                        // The window reader sits outside the Inspector: window - inspector while shown, window while hidden.
                        XCTAssertEqual(
                            collapses(measured: window - inspector, frame: inspector),
                            collapses(measured: window, frame: nil),
                            "window \(window) inspector \(inspector) sidebar \(sidebar) detailMin \(detailMin) did not settle")
                    }
                }
            }
        }
    }
}
