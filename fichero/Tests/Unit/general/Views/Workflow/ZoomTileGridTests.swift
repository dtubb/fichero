@testable import Fichero
import Foundation
import XCTest

/// Tile-grid math behind the Zoom node's config preview (#4323). Mirrors the
/// server's zoom.py strip computation: rows (0 = auto from height), overlap
/// as a fraction of strip height, extents clamped to the page.
final class ZoomTileGridTests: XCTestCase {

    // MARK: - Auto rows (rows = 0 chooses from image height)

    func testAutoRowsUsesOneStripPer400Pixels() {
        // Server: rows = max(1, ceil(height / 400)).
        XCTAssertEqual(ZoomTileGrid.effectiveRows(imageHeight: 1600, rows: 0), 4)
        XCTAssertEqual(ZoomTileGrid.effectiveRows(imageHeight: 1601, rows: 0), 5)
        XCTAssertEqual(ZoomTileGrid.effectiveRows(imageHeight: 100, rows: 0), 1)
    }

    func testExplicitRowsWins() {
        XCTAssertEqual(ZoomTileGrid.effectiveRows(imageHeight: 1600, rows: 7), 7)
    }

    // MARK: - Tile extents

    func testNoOverlapTilesPartitionThePage() {
        let tiles = ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: 0)
        XCTAssertEqual(tiles.count, 4)
        XCTAssertEqual(tiles.first?.top, 0)
        XCTAssertEqual(tiles.last?.bottom, 1.0)
        // Adjacent strips meet exactly with zero overlap.
        for index in 1..<tiles.count {
            XCTAssertEqual(tiles[index].top, tiles[index - 1].bottom, accuracy: 0.001)
        }
    }

    func testOverlapExtendsInteriorStripsBothWays() {
        // 1000px, 4 rows → strip 250px; 20% overlap → 50px each side.
        let tiles = ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: 0.2)
        XCTAssertEqual(tiles[1].top, 0.2, accuracy: 0.001)     // 250 − 50
        XCTAssertEqual(tiles[1].bottom, 0.55, accuracy: 0.001) // 500 + 50
    }

    func testTilesClampToPageBounds() {
        let tiles = ZoomTileGrid.tiles(imageHeight: 1000, rows: 3, overlap: 0.3)
        for tile in tiles {
            XCTAssertGreaterThanOrEqual(tile.top, 0)
            XCTAssertLessThanOrEqual(tile.bottom, 1.0)
            XCTAssertLessThan(tile.top, tile.bottom)
        }
    }

    func testOverlapIsClampedToServerMaximum() {
        // Server clamps overlap to [0, 0.3]; a wild config value must
        // preview the same clamped geometry the server will cut.
        let wild = ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: 5.0)
        let clamped = ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: 0.3)
        XCTAssertEqual(wild, clamped)
        XCTAssertEqual(
            ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: -1),
            ZoomTileGrid.tiles(imageHeight: 1000, rows: 4, overlap: 0)
        )
    }

    func testCeilRoundedStripHeightMatchesServer() {
        // 1000px / 3 rows → strip = ceil(333.3) = 334. Last strip clamps.
        let tiles = ZoomTileGrid.tiles(imageHeight: 1000, rows: 3, overlap: 0)
        XCTAssertEqual(tiles[0].bottom, 0.334, accuracy: 0.0005)
        XCTAssertEqual(tiles[2].bottom, 1.0)
    }

    func testZeroHeightProducesNoTiles() {
        XCTAssertTrue(ZoomTileGrid.tiles(imageHeight: 0, rows: 4, overlap: 0.1).isEmpty)
    }

    func testAutoRowsSamplePageMatchesPreviewDerivation() {
        // The preview's sample page (1600px) with rows=0 shows 4 strips.
        let tiles = ZoomTileGrid.tiles(
            imageHeight: ZoomTileGridPreview.samplePageHeight, rows: 0, overlap: 0.15
        )
        XCTAssertEqual(tiles.count, 4)
    }
}
