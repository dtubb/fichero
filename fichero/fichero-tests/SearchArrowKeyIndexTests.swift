import XCTest

@testable import Fichero

/// Edge-case coverage for the search arrow-key index math (#1843) — the clamping
/// behind ↑/↓ result navigation, factored out of the macOS view modifier.
final class SearchArrowKeyIndexTests: XCTestCase {

    func testNoItemsReturnsInvalidIndex() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: -1, delta: 1, count: 0), -1)
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 5, delta: -1, count: 0), -1)
    }

    func testNoSelectionDownSelectsFirst() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: -1, delta: 1, count: 5), 0)
    }

    func testNoSelectionUpSelectsFirst() {
        // current -1 + (-1) = -2 → clamped up to 0.
        XCTAssertEqual(SearchArrowKeyIndex.next(from: -1, delta: -1, count: 5), 0)
    }

    func testMidListMovesByOne() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 2, delta: 1, count: 5), 3)
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 2, delta: -1, count: 5), 1)
    }

    func testTopBoundaryClamps() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 0, delta: -1, count: 5), 0)
    }

    func testBottomBoundaryClamps() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 4, delta: 1, count: 5), 4)
    }

    func testSingleItemStaysAtZero() {
        XCTAssertEqual(SearchArrowKeyIndex.next(from: -1, delta: 1, count: 1), 0)
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 0, delta: 1, count: 1), 0)
        XCTAssertEqual(SearchArrowKeyIndex.next(from: 0, delta: -1, count: 1), 0)
    }
}
