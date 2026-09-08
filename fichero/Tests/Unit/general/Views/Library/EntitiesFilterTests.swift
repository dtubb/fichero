@testable import Fichero
import XCTest

/// spec: kg-tables — `filter.text` / `filter.entity-type` / `filter.combines-with-search`.
///
/// An entity row survives only if the shared ⌘F search AND the per-table text AND
/// the type picker ALL pass (intersection). Pure rule, pinned without a rendered table.
final class EntitiesFilterTests: XCTestCase {

    private func match(
        name: String = "Quito",
        entityType: String = "location",
        search: String? = nil,
        filterText: String = "",
        filterType: String? = nil
    ) -> Bool {
        EntitiesLibraryContent.entityMatches(
            name: name, type: entityType,
            search: search, filterText: filterText, filterType: filterType
        )
    }

    func testNoFilterMatchesEverything() {
        XCTAssertTrue(match())
    }

    func testSharedSearch() {
        XCTAssertTrue(match(search: "quito"))
        XCTAssertFalse(match(search: "madrid"))
    }

    func testPerTableText() {
        XCTAssertTrue(match(filterText: "qui"))
        XCTAssertFalse(match(filterText: "madrid"))
    }

    func testTypePicker() {
        XCTAssertTrue(match(filterType: "location"))
        XCTAssertFalse(match(filterType: "person"))
    }

    func testIntersection() {
        // search matches but the type picker excludes it → out
        XCTAssertFalse(match(search: "quito", filterType: "person"))
        // both pass → in
        XCTAssertTrue(match(search: "quito", filterType: "location"))
        // text passes but search excludes → out
        XCTAssertFalse(match(search: "madrid", filterText: "qui"))
    }

    func testCaseInsensitive() {
        XCTAssertTrue(match(name: "Quito", entityType: "Location",
                            search: "QUITO", filterText: "QUI", filterType: "location"))
    }

    func testTypeMatchesOnTheTypeField_notTheName() {
        // "person" must match the type, not appear only in the name text
        XCTAssertFalse(match(name: "Person of Interest", entityType: "location", filterType: "person"))
    }
}
