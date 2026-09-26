@testable import Fichero
import Foundation
import XCTest

/// #4966 (C8): "narrowing the left Library pushes its content off the left edge instead of
/// shrinking it." `LazyVGrid`'s `.adaptive` always draws a column at least its stated minimum
/// wide, even when that minimum is wider than the container — a scale-ideal minimum that ignores
/// the pane's own width is exactly how a narrow Browse pane overflowed. These pin the pane-aware
/// clamp (`iconGridItemBounds(scale:paneWidth:)`) and the column count it feeds
/// (`iconColumnCount`), the two pure pieces `iconsView` reads from `GeometryReader`.
final class IconGridNarrowPaneTests: XCTestCase {

    // MARK: - iconGridItemBounds(scale:paneWidth:) never exceeds the pane

    func testClampedBoundsNeverExceedThePaneWidth() {
        for paneWidth: CGFloat in [40, 80, 120, 160, 240, 400] {
            for scale in [0.5, 1.0, 1.5, 2.5, 5.0] {
                let bounds = LibraryView.iconGridItemBounds(scale: scale, paneWidth: paneWidth)
                let available = paneWidth - 32
                XCTAssertLessThanOrEqual(
                    bounds.min, max(1, available),
                    "scale \(scale) at pane width \(paneWidth): min must fit the pane"
                )
                XCTAssertLessThanOrEqual(
                    bounds.max, max(1, available),
                    "scale \(scale) at pane width \(paneWidth): max must fit the pane"
                )
                XCTAssertLessThanOrEqual(bounds.min, bounds.max, "min must never exceed max")
            }
        }
    }

    func testAGenerousPaneMatchesTheUnclampedIdealExactly() {
        // Plenty of room: the pane-aware clamp must not shrink a slot that already fits.
        let ideal = LibraryView.iconGridItemBounds(scale: 1.0)
        let clamped = LibraryView.iconGridItemBounds(scale: 1.0, paneWidth: 2000)
        XCTAssertEqual(clamped.min, ideal.min)
        XCTAssertEqual(clamped.max, ideal.max)
    }

    func testANarrowPaneShrinksTheSlotRatherThanOverflowing() {
        // At scale 1.0 the ideal minimum is DocumentThumbnailView.wellWidth + 8 (108pt per
        // IconGridDefaultSizeTests). A 100pt pane cannot fit that — the clamp must shrink it.
        let bounds = LibraryView.iconGridItemBounds(scale: 1.0, paneWidth: 100)
        let ideal = LibraryView.iconGridItemBounds(scale: 1.0)
        XCTAssertLessThan(bounds.min, ideal.min, "a pane narrower than the ideal tile must shrink it")
        XCTAssertLessThanOrEqual(bounds.min, 100 - 32)
    }

    // MARK: - iconColumnCount: the one-column floor, and a width below one thumbnail

    func testColumnCountNeverGoesBelowOne() {
        // Even a pane narrower than a single thumbnail's minimum must report ONE column — the
        // grid still draws something; it never asks for zero.
        XCTAssertEqual(LibraryView.iconColumnCount(paneWidth: 10, itemMin: 108), 1)
        XCTAssertEqual(LibraryView.iconColumnCount(paneWidth: 0, itemMin: 108), 1)
    }

    func testColumnCountAtExactlyOneThumbnailsWidth() {
        // Pane width == one item's width + the grid's own horizontal inset → exactly one column,
        // no room for a second.
        let itemMin: CGFloat = 108
        let paneWidth = itemMin + 32
        XCTAssertEqual(LibraryView.iconColumnCount(paneWidth: paneWidth, itemMin: itemMin), 1)
    }

    func testColumnCountGrowsWithPaneWidth() {
        let itemMin: CGFloat = 108
        let narrow = LibraryView.iconColumnCount(paneWidth: 200, itemMin: itemMin)
        let wide = LibraryView.iconColumnCount(paneWidth: 800, itemMin: itemMin)
        XCTAssertGreaterThan(wide, narrow, "a wider pane must never report FEWER columns")
    }

    func testColumnCountHandlesAZeroOrNegativeItemMinWithoutCrashing() {
        // Defensive: a caller passing a degenerate minimum must still get a sane floor, not a
        // division fault.
        XCTAssertEqual(LibraryView.iconColumnCount(paneWidth: 200, itemMin: 0), 1)
    }
}

// MARK: - Header/footer collapse: one mechanism, not two

/// #4966: the header's `PaneKindSelector` ladder and the footer's `AdaptiveMiniToolbarRow` ladder
/// already share one primitive — `ViewThatFits(in: .horizontal)` — each measuring its OWN
/// candidates against the SAME pane width, rather than a shared numeric breakpoint the two would
/// have to keep in sync by hand. `LibraryContentKindControl`'s fix (this file's second half) joins
/// that same primitive instead of adding a third. No mounted render exists in this target (checked
/// before writing this), so these are structural checks: they prove there is ONE mechanism in the
/// source, not that it visually collapses correctly at a given width — that needs a screen check.
final class LibraryHeaderFooterCollapseAgreementTests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        try AppSource.code(relativePath)
    }

    func testContentKindControlUsesViewThatFitsNotAFixedTruncation() throws {
        let source = try source("Views/Library/ViewModes/Table/LibraryContentKindControl.swift")
        XCTAssertTrue(
            source.contains("ViewThatFits(in: .horizontal)"),
            "the content-kind chip must collapse through the SAME ladder primitive the rest of the "
                + "chrome uses, not truncate under .fixedSize()"
        )
        // Both rungs exist. (Not a ternary: the two label styles are two types and do not compile as one.)
        XCTAssertTrue(source.contains(".labelStyle(.iconOnly)"))
        XCTAssertTrue(source.contains(".labelStyle(.titleAndIcon)"))
    }

    func testKgFilterHasACondensedAndAnOverflowCoatInTheSharedFooter() throws {
        let source = try source("Views/Library/LibraryView+BottomActionBar.swift")
        // The filter is no longer essential-tier-only (#4966: a 220pt TextField cannot shrink) —
        // it must appear in the secondary, condensed, and overflow rungs, the same three rungs
        // `entityFilterMenu` already rides for list mode.
        XCTAssertTrue(source.contains("kgContentFilterControls"))
        XCTAssertTrue(source.contains("kgContentFilterPopoverButton"))
        XCTAssertFalse(
            AppSource.codeOnly(source).components(separatedBy: "private var essentialBarButtons: some View {")
                .dropFirst().first.map { body in
                    body.components(separatedBy: "\n    }").first?.contains("kgContentFilterControls") ?? false
                } ?? false,
            "the filter must not be in the always-inline essential tier any more"
        )
    }

    func testTheSameShowingKgFilterPopoverStateBacksBothCollapsedTriggers() throws {
        let source = try source("Views/Library/LibraryView+BottomActionBar.swift")
        // Both the condensed button and the overflow-menu row must set the SAME popover flag, and
        // the popover itself must be attached once, at the bar's own outer container — not on
        // either trigger individually, which would vanish along with whichever rung isn't
        // currently rendered.
        XCTAssertEqual(
            source.components(separatedBy: "showingKgFilterPopover = true").count - 1, 2,
            "exactly two triggers (condensed button, overflow row) should open the popover"
        )
        XCTAssertEqual(
            source.components(separatedBy: ".popover(isPresented: $showingKgFilterPopover)").count - 1, 1,
            "the popover itself must be presented exactly once, not per-trigger"
        )
    }
}
