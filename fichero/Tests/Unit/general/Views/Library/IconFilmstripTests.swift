@testable import Fichero
import Foundation
import XCTest

/// `source.items.icon-filmstrip-when-short`: a pane that fits one row of thumbnails is a filmstrip, a tall one the grid.
final class IconFilmstripTests: XCTestCase {
    func testAPaneThatFitsOneRowIsAFilmstripAndATallOneStaysTheGrid() {
        let row = LibraryView.iconRowHeight(scale: 1)
        XCTAssertTrue(LibraryView.iconIsFilmstrip(paneHeight: row + 32, scale: 1), "one row fits: the transcribe layout's strip")
        XCTAssertTrue(LibraryView.iconIsFilmstrip(paneHeight: 2 * row, scale: 1), "a second row would be cut off")
        XCTAssertFalse(LibraryView.iconIsFilmstrip(paneHeight: 2 * row + 20 + 32, scale: 1), "two rows fit: the grid")
        XCTAssertFalse(LibraryView.iconIsFilmstrip(paneHeight: 900, scale: 1))
    }

    func testTheRowGrowsWithTheScaleSoTheSamePaneCanTipToAFilmstrip() {
        let height = 2 * LibraryView.iconRowHeight(scale: 1) + 20 + 32
        XCTAssertFalse(LibraryView.iconIsFilmstrip(paneHeight: height, scale: 1))
        XCTAssertTrue(LibraryView.iconIsFilmstrip(paneHeight: height, scale: 2), "bigger tiles: only one row fits now")
    }
}
