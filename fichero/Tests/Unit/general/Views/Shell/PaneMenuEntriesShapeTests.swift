@testable import Fichero
import XCTest

/// `panes.chrome.one-pane-menu` (#5435), first slice: the head's + and its right-click list the same
/// entries (split, pin, close) from one view, and the X and the menu's Close run one close path.
/// Source-shape guard.
@MainActor
final class PaneMenuEntriesShapeTests: XCTestCase {
    func testPlusAndRightClickShareTheEntries() throws {
        let menu = try AppSource.code("Views/Shell/PaneHead/PaneChromeMenu.swift")
        let head = try AppSource.code("Views/Shell/PaneHead/PaneHead.swift")
        XCTAssertTrue(menu.contains("struct PaneMenuEntries: View"))
        XCTAssertTrue(menu.contains("PaneMenuEntries(splitActions: splitActions"), "the + no longer renders the shared entries")
        XCTAssertTrue(head.contains(".contextMenu {\n                PaneMenuEntries("), "the head lost its right-click menu")
        for label in ["\"Pin Pane\"", "\"Unpin Pane\""] {
            XCTAssertTrue(menu.contains(label), "pane menu lost \(label)")
        }
    }

    func testCloseIsOnePath() throws {
        let head = try AppSource.code("Views/Shell/PaneHead/PaneHead.swift")
        XCTAssertEqual(head.components(separatedBy: "closePane()").count - 1, 4,
                       "definition, the X, the + menu and the right-click each call closePane once")
    }
}
