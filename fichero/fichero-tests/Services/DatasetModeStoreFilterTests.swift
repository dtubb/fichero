@testable import Fichero
import XCTest

/// The dataset facet model (Daniel 2026-08-15: "can we easily filter
/// undated" / "pull quotes in a folder … is this facet"): `visibleRows` is
/// the ONE filtered feed every renderer draws, so a choice made in cards
/// holds in timeline and calendar.
@MainActor
final class DatasetModeStoreFilterTests: XCTestCase {
    private func store() -> DatasetModeStore {
        DatasetModeStore.previewDiary()
    }

    func testAllFilterShowsEveryRow() {
        let sut = store()
        XCTAssertEqual(sut.visibleRows.count, sut.page?.rows.count)
    }

    func testUndatedFilterShowsOnlyRowsWithNoDateFromAnySource() {
        let sut = store()
        sut.dateFilter = .undated
        // The fixture has exactly one row with neither a date-role attribute
        // value nor a document ISO date.
        XCTAssertEqual(sut.visibleRows.map(\.id), ["undated"])
    }

    func testDatedFilterKeepsAttributeDatedAndColumnDatedRows() {
        let sut = store()
        sut.dateFilter = .dated
        let ids = Set(sut.visibleRows.map(\.id))
        XCTAssertFalse(ids.contains("undated"))
        // Extract-Dates rows carry their date on the document columns, not
        // attributes — they are DATED (the 2026-08-15 visibility fix).
        XCTAssertTrue(ids.contains("dated-scan"))
        XCTAssertEqual(sut.visibleRows.count, (sut.page?.rows.count ?? 0) - 1)
    }

    func testPrototypeFilterNarrowsAndComposesWithDateFilter() {
        let sut = store()
        sut.prototypeFilter = "diary_entry"
        XCTAssertFalse(sut.visibleRows.map(\.id).contains("dated-scan"))
        sut.dateFilter = .undated
        XCTAssertEqual(sut.visibleRows.map(\.id), ["undated"])
        sut.dateFilter = .dated
        XCTAssertFalse(sut.visibleRows.map(\.id).contains("undated"))
    }

    func testRowsByMonthGroupsOnlyVisibleRows() {
        let sut = store()
        sut.dateFilter = .dated
        let months = sut.rowsByMonth()
        XCTAssertFalse(months.contains { $0.month == DatasetModeStore.undatedMonthKey })
        sut.dateFilter = .all
        XCTAssertTrue(sut.rowsByMonth().contains { $0.month == DatasetModeStore.undatedMonthKey })
    }

    func testAvailablePrototypesAreDistinctSorted() {
        XCTAssertEqual(store().availablePrototypes, ["diary_entry"])
    }

    /// Optional vars default to nil in the memberwise init, so the in-place
    /// edit used to rebuild the row WITHOUT `parentId` — severing the
    /// source-page reference the moment a cell was edited (found in the
    /// 2026-08-15 filter review).
    func testApplyLocalEditPreservesSourceReference() throws {
        let sut = store()
        let row = try XCTUnwrap(sut.page?.rows.first { $0.parentId != nil })
        sut.applyLocalEdit(rowId: row.id, attr: "weather", value: "storm")
        let edited = try XCTUnwrap(sut.page?.rows.first { $0.id == row.id })
        XCTAssertEqual(edited.parentId, row.parentId)
        XCTAssertEqual(edited.attributes["weather"] as? String, "storm")
    }
}
