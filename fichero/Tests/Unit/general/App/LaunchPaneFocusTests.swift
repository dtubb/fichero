@testable import Fichero
import XCTest

/// #5824: a window opens with focus in the sidebar, never a text field.
final class LaunchPaneFocusTests: XCTestCase {
    func testTheLaunchFocusIsTheSidebar() {
        XCTAssertEqual(PaneFocus.launchDefault, .sidebar)
    }
}
