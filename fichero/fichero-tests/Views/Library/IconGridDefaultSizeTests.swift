@testable import Fichero
import Foundation
import XCTest

/// #4281 — icons view rendered default-size tiles in double-width grid cells.
///
/// The grid slot was hardcoded 120…150pt while the tile's real footprint is
/// `DocumentThumbnailView.wellWidth * scale` (100pt at scale 1) — a slot up to
/// 1.5 tiles wide, so tiles sat centered in visibly oversized columns.
/// `iconGridItemBounds` now derives the slot from the tile: one tile = one
/// column at every scale.
final class IconGridDefaultSizeTests: XCTestCase {

    func testDefaultScaleSlotHugsTheTile() {
        let bounds = LibraryView.iconGridItemBounds(scale: 1.0)
        // Slot = tile + 8 breathing, +16 stretch allowance — expressed in
        // terms of the tile so the #112 enlargement (100 → 108 well) and any
        // future resize move this test with the ruling instead of failing it.
        XCTAssertEqual(bounds.min, DocumentThumbnailView.wellWidth + 8)
        XCTAssertEqual(bounds.max, DocumentThumbnailView.wellWidth + 24)
    }

    func testSlotCanNeverSpanTwoTiles() {
        // The regression class: a slot wide enough to look like two columns.
        for scale in [0.6, 0.8, 1.0, 1.05, 1.5, 2.0, 5.0] {
            let bounds = LibraryView.iconGridItemBounds(scale: scale)
            let tile = DocumentThumbnailView.wellWidth * CGFloat(scale)
            XCTAssertLessThan(
                bounds.max, tile * 2,
                "slot at scale \(scale) must be narrower than two tiles"
            )
            XCTAssertGreaterThanOrEqual(
                bounds.min, tile,
                "slot at scale \(scale) must still FIT the tile"
            )
            XCTAssertLessThan(bounds.min, bounds.max, "adaptive grid needs min < max")
        }
    }

    func testTinyScalesKeepAUsableFloor() {
        // Below the floor the tile is small; the slot keeps a 70pt minimum so
        // hit targets and labels stay usable.
        let bounds = LibraryView.iconGridItemBounds(scale: 0.3)
        XCTAssertEqual(bounds.min, 70)
        XCTAssertEqual(bounds.max, 86)
    }

    func testSlotScalesMonotonicallyWithZoom() {
        let small = LibraryView.iconGridItemBounds(scale: 1.0)
        let large = LibraryView.iconGridItemBounds(scale: 2.0)
        XCTAssertGreaterThan(large.min, small.min)
        XCTAssertGreaterThan(large.max, small.max)
    }
}
