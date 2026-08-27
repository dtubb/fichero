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

    /// The ROW's full-name tooltip was REMOVED on Daniel's direction
    /// (2026-08-08): hovering the name must not pop anything over it — the
    /// accepted trade is that a truncated row name has no hover reveal.
    /// The library HEADER keeps its tooltip (not part of that complaint).
    func testRowTooltipRemovedHeaderTooltipKept() throws {
        let row = try appSource("Views/Sidebar/ItemRow/SidebarItemRow.swift")
        XCTAssertFalse(
            row.contains(#".help(renameState.renamingItemId == item.id ? "" : item.name)"#),
            "The row name tooltip was removed (Daniel, 2026-08-08) — do not re-add it without a new decision."
        )

        let header = try appSource("Views/Sidebar/Sections/SidebarSectionHeader.swift")
        XCTAssertTrue(header.contains(".help(libraryName)"))
        XCTAssertTrue(header.contains("sidebarLibraryHeaderAccessibilityValue(isCurrent: isCurrentLibrary)"))
    }

    /// #571 restoration: on expandable rows the drop highlight, drop target,
    /// and context menu must sit on the OUTER DisclosureGroup (covering the
    /// chevron/indent strip). The drop HIGHLIGHT, by contrast, sits INSIDE the
    /// label (#4229): on the group it painted the expanded subtree's whole
    /// frame, reading as a mass selection.
    func testExpandableRowModifiersSitOnOuterDisclosureGroup() throws {
        let source = try appSource("Views/Sidebar/ItemRow/SidebarItemRow+Presentation+Body.swift")
        guard let disclosureRange = source.range(of: "DisclosureGroup(isExpanded: isExpanded)") else {
            return XCTFail("expected the expandable-row DisclosureGroup")
        }
        let afterDisclosure = source[disclosureRange.upperBound...]
        // The label is fullWidthLabel carrying the row-scoped highlight —
        // folderLabel/leafLabel (which carry their own copies for
        // non-expandable rows) must not appear inside this branch's label.
        XCTAssertTrue(
            afterDisclosure.contains("} label: {\n                fullWidthLabel\n                    .sidebarDropHighlight(")
        )
        // The old `stronger:` translucent-wash signature is gone with the
        // Finder-style solid drop fill (Daniel, 2026-08-08) — its group-level
        // misplacement (#4229) can no longer be re-introduced by that
        // spelling. The first assertion pins where the highlight lives now.
        XCTAssertFalse(afterDisclosure.contains("stronger:"))
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root()
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
