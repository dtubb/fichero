@testable import Fichero
import XCTest

/// Locks the per-platform VoiceOver hint wording for sidebar rows: pointer
/// gestures ("Right-click", "Double-click") must never be spoken to touch
/// VoiceOver users on iOS/iPadOS.
final class SidebarRowAccessibilityTests: XCTestCase {

    // Unit tests run on macOS, so these assert the macOS branch directly.

    func testMacRenameableHintMentionsPointerGestures() {
        let hint = sidebarRowAccessibilityHint(canBeRenamed: true)
        XCTAssertTrue(hint.contains("Double-click to rename"))
        XCTAssertTrue(hint.contains("Right-click"))
        XCTAssertTrue(hint.contains("Drag to reorder"))
    }

    func testMacNonRenameableHintIsTerse() {
        let hint = sidebarRowAccessibilityHint(canBeRenamed: false)
        XCTAssertEqual(hint, "Right-click for actions.")
    }

    /// The iOS branch can't execute in a macOS test run, so scan the source:
    /// the `#else` (touch) branch must use double-tap-and-hold wording and
    /// contain no pointer-gesture terms.
    func testTouchHintBranchAvoidsPointerWording() throws {
        let source = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift")
        guard let elseRange = source.range(of: "#else"),
              let endifRange = source.range(
                of: "#endif", range: elseRange.upperBound..<source.endIndex
              ) else {
            return XCTFail("expected a platform-conditional hint in the row body")
        }
        let touchBranch = source[elseRange.upperBound..<endifRange.lowerBound]
        XCTAssertTrue(touchBranch.contains("Double tap and hold"))
        XCTAssertFalse(touchBranch.contains("Right-click"))
        XCTAssertFalse(touchBranch.contains("Double-click"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
