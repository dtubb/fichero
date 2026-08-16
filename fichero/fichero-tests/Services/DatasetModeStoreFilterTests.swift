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

    /// Daniel 2026-08-15 night: "its not in order though" — the cards feed is
    /// chronological, name-tiebroken, undated last, and it respects filters.
    func testOrderedVisibleRowsAreDateThenNameUndatedLast() {
        let sut = store()
        let ordered = sut.orderedVisibleRows
        let dates = ordered.map { sut.dateValue(of: $0) }
        let datedPrefix = dates.prefix(while: { $0 != nil }).compactMap { $0 }
        XCTAssertEqual(datedPrefix, datedPrefix.sorted(), "dated rows run chronologically")
        XCTAssertTrue(dates.drop(while: { $0 != nil }).allSatisfy { $0 == nil },
                      "undated rows sit at the end, never interleaved")
        sut.dateFilter = .dated
        XCTAssertFalse(sut.orderedVisibleRows.contains { sut.dateValue(of: $0) == nil })
    }

    /// The date is the card's headline — a body that STARTS with the same
    /// date as a printed heading drops that line at display time, so
    /// entries extracted before the engine stripped headings stop
    /// repeating too ("February 15, 1914 / SATURDAY, FEBRUARY 15").
    func testDisplayExcerptDropsLeadingDateHeading() {
        typealias Strip = DatasetModeStore
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading(
                "SATURDAY, FEBRUARY 15\nTraded for plantains.", dateIso: "1914-02-15"),
            "Traded for plantains."
        )
        // OCR noise in the heading still reads as a heading: weekday + month.
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading(
                "TUESDAY, JANUARY § 7\nSan José left.", dateIso: "1918-01-08"),
            "San José left."
        )
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading(
                "MONDAY. JANUARY F. 19186 3\nWillian Hilton infured.", dateIso: "1918-01-07"),
            "Willian Hilton infured."
        )
        // Prose that merely mentions the month is NOT a heading.
        let prose = "We spent February 15 at the dredge.\nMore text."
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading(prose, dateIso: "1914-02-15"), prose,
            "a first line with no weekday and no bare day token stays"
        )
        // Wrong month = not this entry's heading; keep it.
        let otherMonth = "SATURDAY, MARCH 15\nBody."
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading(otherMonth, dateIso: "1914-02-15"), otherMonth
        )
        // A heading-only body empties rather than repeating the date.
        XCTAssertEqual(
            Strip.strippingLeadingDateHeading("SUNDAY, JANUARY 5", dateIso: "1919-01-05"), ""
        )
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
