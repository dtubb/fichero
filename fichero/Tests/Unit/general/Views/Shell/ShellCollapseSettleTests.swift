@testable import Fichero
import XCTest

/// #7065: the Inspector's collapse rule must not read its own result, or full screen shows and hides it forever.
final class ShellCollapseSettleTests: XCTestCase {
    func testInspectorCollapseSettlesAtEveryWidth() {
        for window in stride(from: 600.0, through: 2600.0, by: 50.0) {
            for inspector in stride(from: 260.0, through: 800.0, by: 20.0) {
                for sidebar in [true, false] {
                    for detailMin in [220.0, 330.0, 550.0] {
                        // The measured width excludes the Inspector column while it is shown.
                        func apply(shown: Bool) -> Bool {
                            let width = ContentView.shellCollapseWidth(
                                measured: shown ? window - inspector : window,
                                inspectorFrameWidth: shown ? inspector : nil)
                            let policy = ContentView.shellCollapsePolicy(
                                windowWidth: width, horizontalSizeClass: .regular, sidebarVisible: sidebar,
                                inspectorVisible: shown, detailMinWidth: detailMin)
                            return shown && !policy.collapseInspector
                        }
                        let first = apply(shown: true)
                        let second = apply(shown: first)
                        XCTAssertEqual(
                            first, second,
                            "window \(window) inspector \(inspector) sidebar \(sidebar) detailMin \(detailMin) did not settle")
                    }
                }
            }
        }
    }
}
