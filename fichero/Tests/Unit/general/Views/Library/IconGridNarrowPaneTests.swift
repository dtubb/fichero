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
/// have to keep in sync by hand. No mounted render exists in this target (checked
/// before writing this), so these are structural checks: they prove there is ONE mechanism in the
/// source, not that it visually collapses correctly at a given width — that needs a screen check.
final class LibraryHeaderFooterCollapseAgreementTests: XCTestCase {

    private func source(_ relativePath: String) throws -> String {
        try AppSource.code(relativePath)
    }

    func testKgFilterIsTheSharedFilterFieldInTheFooter() throws {
        // owner 2026-11-13 (`panes.chrome.one-filter-pattern`): the Claims/Entities filter is the one shared field in
        // the footer's right-hand cluster, which every rung of the ladder draws; no separate KG controls or popover.
        let mini = try source("Views/Library/LibraryView+MiniToolbar.swift")
        XCTAssertTrue(mini.contains("kgContentFilterField"))
        let bar = try source("Views/Library/LibraryView+BottomActionBar.swift")
        XCTAssertFalse(bar.contains("kgContentFilterPopoverButton"))
        XCTAssertTrue(bar.contains("libraryMiniToolbar(condensed: true)"))
    }
}

/// #6086: arrow-key Up/Down in the Icon filmstrip (one row) step one tile, not the pane-width column count.
final class IconFilmstripArrowStepTests: XCTestCase {
    func testAGridStepsARowOfColumns() {
        XCTAssertEqual(LibraryView.verticalStep(isIcon: true, columns: 5, filmstrip: false), 5)
    }

    func testAFilmstripStepsOneTile() {
        XCTAssertEqual(LibraryView.verticalStep(isIcon: true, columns: 5, filmstrip: true), 1)
    }

    func testAListStepsOneRowWhateverTheColumns() {
        XCTAssertEqual(LibraryView.verticalStep(isIcon: false, columns: 5, filmstrip: false), 1)
    }

    func testAZeroColumnCountNeverStepsZero() {
        XCTAssertEqual(LibraryView.verticalStep(isIcon: true, columns: 0, filmstrip: false), 1)
    }

    func testAShortPaneIsTheFilmstripTheArrowsFollow() {
        // The same height rule `iconsView` feeds into `gridIsFilmstrip`.
        XCTAssertTrue(LibraryView.iconIsFilmstrip(paneHeight: 180, scale: 1.0))
        XCTAssertFalse(LibraryView.iconIsFilmstrip(paneHeight: 900, scale: 1.0))
    }
}
