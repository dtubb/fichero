@testable import Fichero
import XCTest

/// #5824: a window opens with focus in the sidebar, never a text field.
final class LaunchPaneFocusTests: XCTestCase {
    func testTheLaunchFocusIsTheSidebar() {
        XCTAssertEqual(PaneFocus.launchDefault, .sidebar)
    }

    /// The first onAppear used to set `.content`, which put the caret in the reader's find field.
    func testAWindowOpensInTheSidebarOrTheListWhenTheSidebarIsHidden() {
        XCTAssertEqual(PaneFocus.launchFocus(sidebarHidden: false), .sidebar)
        XCTAssertEqual(PaneFocus.launchFocus(sidebarHidden: true), .content)
    }
}
