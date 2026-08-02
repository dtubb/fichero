@testable import Fichero
import XCTest

/// #4097 — sidebar rows had no wash telling you what the pointer was over.
///
/// The issue's premise ("there is no `.onHover` anywhere in `Views/Sidebar/`")
/// went stale: #2496 added row hover state and a trailing open-affordance that
/// appears with it. But that affordance sits at the row's FAR EDGE, and #4097's
/// argument is about aiming — the row is not hard to hit, it is hard to aim at,
/// because nothing under the pointer changes until selection has happened.
///
/// So the plumbing existed and the cue did not. This tests the rule; the fill
/// and the corner radius are house tokens, which leaves this predicate as the
/// only thing about the wash that can be wrong.
final class SidebarHoverWashTests: XCTestCase {

    func testWashAppearsWhileHoveringAnUnselectedRow() {
        XCTAssertTrue(sidebarRowShowsHoverWash(isHovered: true, isSelected: false))
    }

    func testNoWashWhenThePointerIsElsewhere() {
        XCTAssertFalse(sidebarRowShowsHoverWash(isHovered: false, isSelected: false))
    }

    func testSelectionSuppressesTheWashRatherThanLayeringUnderIt() {
        // Two washes on one row sum to a shade neither was designed to be, and
        // that shade lands close enough to the selected treatment to be mistaken
        // for it — the confusion #4371 is separately trying to remove.
        XCTAssertFalse(sidebarRowShowsHoverWash(isHovered: true, isSelected: true))
    }

    func testASelectedRowIsUnaffectedByHoverInEitherDirection() {
        // Stated as an equality so "selection wins, full stop" is one assertion
        // rather than an absence spread across cases.
        XCTAssertEqual(
            sidebarRowShowsHoverWash(isHovered: true, isSelected: true),
            sidebarRowShowsHoverWash(isHovered: false, isSelected: true)
        )
    }

    /// Every Frame Perfect: hovering must not move anything.
    ///
    /// A source assertion because the property is structural — the hover branch
    /// may only change a FILL. The moment it also changes padding, frame or
    /// font, hovering relayouts the row and re-truncates its name, which is the
    /// failure the trailing affordance already avoids by staying in the layout
    /// and toggling opacity instead of appearing.
    func testHoverChangesOnlyAFillAndNeverAMetric() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertFalse(source.isEmpty, "SidebarItemRow.swift is empty — this guard measures nothing")

        let block = try XCTUnwrap(
            source.range(of: "sidebarRowShowsHoverWash(isHovered: isRowHovered, isSelected: isRowSelected)")
        )
        // The modifier chain around the wash, not the whole file.
        let start = source.index(block.lowerBound, offsetBy: -400, limitedBy: source.startIndex) ?? source.startIndex
        let end = source.index(block.upperBound, offsetBy: 200, limitedBy: source.endIndex) ?? source.endIndex
        let window = String(source[start..<end])

        XCTAssertTrue(window.contains(".fill("), "the wash is a fill")
        XCTAssertTrue(window.contains("allowsHitTesting(false)"), "the wash must never eat a click")
        XCTAssertFalse(window.contains(".padding("), "hover must not change padding")
        XCTAssertFalse(window.contains(".frame("), "hover must not change frame")
    }

    /// `.background`, not `.overlay` — an overlay would tint the label itself
    /// and make hovered text read as disabled.
    func testTheWashSitsBehindTheRowContent() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero/Views/Sidebar/ItemRow/SidebarItemRow.swift")
        let source = try String(contentsOf: url, encoding: .utf8)

        let washRange = try XCTUnwrap(source.range(of: "LibrarySelectionStyle.hoverFill"))
        let start = source.index(washRange.lowerBound, offsetBy: -600, limitedBy: source.startIndex)
            ?? source.startIndex
        let preceding = String(source[start..<washRange.lowerBound])

        XCTAssertTrue(
            preceding.contains(".background("),
            "the hover wash must be a background; an overlay would dim the label"
        )
    }
}
