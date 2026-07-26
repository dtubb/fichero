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

    // MARK: - Library header current-state exposure + tooltips

    func testCurrentLibraryStateIsSpokenNotJustTinted() {
        XCTAssertEqual(sidebarLibraryHeaderAccessibilityValue(isCurrent: true), "current library")
        XCTAssertEqual(sidebarLibraryHeaderAccessibilityValue(isCurrent: false), "")
    }

    /// Truncated names have no other way to reveal themselves: the row and the
    /// library header must both carry a full-name `.help` tooltip, and the
    /// row's must disable (empty string idiom) during inline rename.
    func testTruncatedNameTooltipsArePresent() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        XCTAssertTrue(row.contains(#".help(renameState.renamingItemId == item.id ? "" : item.name)"#))

        let header = try appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(header.contains(".help(libraryName)"))
        XCTAssertTrue(header.contains("sidebarLibraryHeaderAccessibilityValue(isCurrent: isCurrentLibrary)"))
    }

    /// #571 restoration: on expandable rows the drop highlight, drop target,
    /// and context menu must sit on the OUTER DisclosureGroup (covering the
    /// chevron/indent strip), with a bare label so nothing is doubled.
    func testExpandableRowModifiersSitOnOuterDisclosureGroup() throws {
        let source = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift")
        guard let disclosureRange = source.range(of: "DisclosureGroup(isExpanded: isExpanded)") else {
            return XCTFail("expected the expandable-row DisclosureGroup")
        }
        let afterDisclosure = source[disclosureRange.upperBound...]
        // The bare label — folderLabel/leafLabel (which carry their own copies
        // for non-expandable rows) must not appear inside this branch's label.
        XCTAssertTrue(afterDisclosure.contains("} label: {\n                fullWidthLabel\n            }"))
        // And the three modifiers hang off the group itself.
        // Prefix match, no closing paren: the call gained an `operation:`
        // argument, and this test only cares that the highlight hangs off the
        // outer group with the row's own targeting/folder state — not about
        // the full argument list, which is free to grow.
        XCTAssertTrue(
            afterDisclosure.contains(".sidebarDropHighlight(isDropTargeted, stronger: isFolder")
        )
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
