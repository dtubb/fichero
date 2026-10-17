@testable import Fichero
import XCTest

/// #3282: a phone imports by copy only. The Link and Move menu items are
/// compiled for macOS alone. Source-shape guard (no window server).
@MainActor
final class IOSImportCopyOnlyShapeTests: XCTestCase {
    private func assertGated(_ path: String, _ labels: [String]) throws {
        let source = try AppSource.text(path)
        for label in labels {
            let at = try XCTUnwrap(source.range(of: "Button(\"\(label)\""), "\(label) button not found in \(path)")
            let before = String(source[..<at.lowerBound].suffix(160))
            XCTAssertTrue(before.contains("#if os(macOS)"), "\(label) in \(path) is not macOS-only")
        }
    }

    func testAddItemMenuLinkAndMoveAreMacOnly() throws {
        try assertGated("App/Menus/AddItemMenu.swift", ["Link Files...", "Move Files..."])
    }

    func testFileMenuLinkAndMoveAreMacOnly() throws {
        try assertGated("App/Menus/FocusedCommands/FocusedCommandButtons+SidebarActions.swift",
                        ["Link Files...", "Move Files..."])
    }
}
