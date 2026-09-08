@testable import Fichero
import XCTest

/// spec: kg-tables — `filter.text` / `filter.claim-type` / `filter.combines-with-search`.
///
/// A claim row survives only if the shared ⌘F search AND the per-table text AND the
/// type picker ALL pass (intersection). Pure rule, pinned without a rendered table.
final class ClaimsFilterTests: XCTestCase {

    private func match(
        haystack: String = "Matheo del Mazo vende cargas de ropa",
        type: String = "fact",
        search: String? = nil,
        filterText: String = "",
        filterType: String? = nil
    ) -> Bool {
        ClaimsLibraryContent.claimMatches(
            haystack: haystack, type: type,
            search: search, filterText: filterText, filterType: filterType
        )
    }

    func testNoFilterMatchesEverything() {
        XCTAssertTrue(match())
    }

    func testSharedSearch() {
        XCTAssertTrue(match(search: "mazo"))
        XCTAssertFalse(match(search: "quito"))
    }

    func testPerTableText() {
        XCTAssertTrue(match(filterText: "vende"))
        XCTAssertFalse(match(filterText: "compra"))
    }

    func testTypePicker() {
        XCTAssertTrue(match(filterType: "fact"))
        XCTAssertFalse(match(filterType: "analysis"))
    }

    func testIntersection() {
        XCTAssertFalse(match(search: "mazo", filterType: "analysis"))
        XCTAssertTrue(match(search: "mazo", filterType: "fact"))
        XCTAssertFalse(match(search: "quito", filterText: "vende"))
    }

    func testCaseInsensitive() {
        XCTAssertTrue(match(search: "MAZO", filterText: "VENDE", filterType: "fact"))
    }
}
