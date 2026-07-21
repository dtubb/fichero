@testable import Fichero
import XCTest

/// Locks the one chat surface's tab contract (#3, step 4 adds Plan). A regression
/// here means a tab was dropped or reordered — the surface's shape is a product
/// decision, so guard it.
final class ChatSurfaceTabTests: XCTestCase {
    func testTabOrderIsTheConvergedSurface() {
        XCTAssertEqual(
            ChatSurfaceTab.allCases,
            [.conversation, .sources, .plan, .knowledge, .compare]
        )
    }

    func testEveryTabHasTitleIconHelp() {
        for tab in ChatSurfaceTab.allCases {
            XCTAssertFalse(tab.title.isEmpty)
            XCTAssertFalse(tab.icon.isEmpty)
            XCTAssertFalse(tab.help.isEmpty)
        }
    }
}
