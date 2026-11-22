@testable import Fichero
import XCTest

/// `ios.item.pages`, `ios.item.header-says-where`, `ios.item.swipe-changes-page`, `ios.item.zoom-wins-over-paging`,
/// `ios.item.segments-own-their-gestures`, `ios.item.voiceover-reaches-every-page` (#6947): the page list with no view.
final class ItemPageTests: XCTestCase {
    func testThePagesAndTheirOrder() {
        XCTAssertEqual(ItemPage.allCases.map(\.title), ["Source", "Reader", "Segments", "Info"])
    }

    func testSwipingStopsAtBothEnds() {
        XCTAssertNil(ItemPage.source.previous)
        XCTAssertEqual(ItemPage.source.next, .reader)
        XCTAssertEqual(ItemPage.info.previous, .segments)
        XCTAssertNil(ItemPage.info.next)
    }

    func testEveryPageSaysItsPlace() {
        XCTAssertEqual(ItemPage.allCases.map(\.position), ["1 of 4", "2 of 4", "3 of 4", "4 of 4"])
    }

    func testAZoomedPictureAndTheSegmentsPageDoNotChangePage() {
        XCTAssertTrue(ItemPage.source.swipePages(imageZoomed: false))
        XCTAssertFalse(ItemPage.source.swipePages(imageZoomed: true))
        XCTAssertFalse(ItemPage.segments.swipePages(imageZoomed: false))
        XCTAssertTrue(ItemPage.reader.swipePages(imageZoomed: true))
        XCTAssertTrue(ItemPage.info.swipePages(imageZoomed: false))
    }

    func testTheWindowStartsOnSource() {
        XCTAssertEqual(WindowState(libraryId: UUID()).compactItemPage, .source)
    }
}
