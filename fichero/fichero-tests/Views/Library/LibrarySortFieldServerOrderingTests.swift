@testable import Fichero
import XCTest

/// #3322 — the client must NOT re-sort rows the engine ordered.
///
/// `document_date` is the one sort field whose ordering lives server-side,
/// because it is not expressible as a key path: `histdate.document_date_sort_key`
/// returns `(jdn, precision_rank)`, so ties on the start JDN break precise-first
/// and an undated document falls back to `created_at` converted to a JDN.
///
/// The correct client behaviour on that path is **to do nothing**, which is a
/// dangerous kind of correct: a `guard` that returns its input reads like an
/// unfinished function, and adding `.sorted(using:)` back reads like a fix. The
/// resulting list would still look sorted — just by a different, worse ordering
/// that silently dropped the tie-breaking and the fallback.
///
/// So these tests are adversarial about that specific edit. Every one of them
/// hands `orderedForDisplay` a comparator that WOULD reorder the input, and
/// requires the input order to survive.
///
/// A note on how "the sort did not run" is asserted. Swift arrays are values,
/// so there is no object identity to compare — `docs === docs` is not a thing
/// that can be written. The equivalent here is to make re-sorting observable:
/// the fixtures are built so that every client comparator disagrees with the
/// server order, and the assertion is on the exact resulting sequence. If the
/// guard is deleted, the order changes and these fail.
final class LibrarySortFieldServerOrderingTests: XCTestCase {

    // MARK: - Fixtures

    /// Server order deliberately disagrees with EVERY client comparator: names
    /// descend and the JDNs are shuffled, so any re-sort is visible.
    ///
    /// All three are DATED, which matters: `groupingUndatedLast` is a no-op on
    /// this fixture, so "the order survived verbatim" isolates the client-sort
    /// question from the grouping question. The grouping has its own tests.
    private func serverOrderedDocuments() -> [Document] {
        [
            makeDocument(id: "z", name: "Zulu diary", dateJdn: 2_375_000),
            makeDocument(id: "m", name: "Mike letter", dateJdn: 2_300_000),
            makeDocument(id: "a", name: "Alpha ledger", dateJdn: 2_260_000)
        ]
    }

    private func makeDocument(
        id: String,
        name: String,
        dateJdn: Int?,
        createdAt: Date = Date(timeIntervalSince1970: 0)
    ) -> Document {
        Document(
            id: id,
            parentId: nil,
            docType: .file,
            fileType: nil,
            name: name,
            path: nil,
            sequence: nil,
            bbox: nil,
            status: .completed,
            metadata: [:],
            pageContent: nil,
            dateJdn: dateJdn,
            sortOrder: 0,
            createdAt: createdAt,
            updatedAt: createdAt
        )
    }

    // MARK: - The trap

    /// The one that must go red if the client sort is applied on top.
    func testTheClientSortIsSkippedEntirelyForDocumentDate() {
        let server = serverOrderedDocuments()

        let displayed = LibrarySortField.orderedForDisplay(
            server,
            field: .documentDate,
            // A comparator that would visibly reorder this input.
            using: [KeyPathComparator(\Document.name, order: .forward)]
        )

        XCTAssertEqual(
            displayed.map(\.id), ["z", "m", "a"],
            "the engine's row order must survive verbatim — any client re-sort "
                + "discards the precision tie-breaking and the undated fallback"
        )
    }

    /// Same, with the comparator the Date column actually installs. This is the
    /// likelier accident: the header binding's key path is right there, and
    /// using it looks like wiring the column up properly.
    func testTheDateColumnsOwnComparatorAlsoDoesNotReorderRows() {
        let displayed = LibrarySortField.orderedForDisplay(
            serverOrderedDocuments(),
            field: .documentDate,
            using: LibrarySortField.documentDate.comparator(ascending: true)
        )

        XCTAssertEqual(displayed.map(\.id), ["z", "m", "a"])
    }

    /// Direction is the server's business too — flipping it client-side would
    /// reverse rows without re-deciding the ties.
    func testDescendingDoesNotReorderClientSideEither() {
        let displayed = LibrarySortField.orderedForDisplay(
            serverOrderedDocuments(),
            field: .documentDate,
            using: LibrarySortField.documentDate.comparator(ascending: false)
        )

        XCTAssertEqual(displayed.map(\.id), ["z", "m", "a"])
    }

    // MARK: - ...and the test is not vacuous

    /// If `orderedForDisplay` never sorted anything, every test above would
    /// pass while the library sat unsorted. This is the control.
    func testEveryOtherFieldIsStillSortedByTheClient() {
        let displayed = LibrarySortField.orderedForDisplay(
            serverOrderedDocuments(),
            field: .name,
            using: LibrarySortField.name.comparator(ascending: true)
        )

        XCTAssertEqual(
            displayed.map(\.id), ["a", "m", "z"],
            "client-ordered fields must still sort, or the guard above proves nothing"
        )
    }

    func testOnlyDocumentDateIsServerOrdered() {
        for field in LibrarySortField.allCases where field != .documentDate {
            XCTAssertFalse(
                field.ordersOnServer,
                "\(field.rawValue) has no server ordering — it must not stop sorting client-side"
            )
            XCTAssertNil(field.serverSortBy)
        }

        XCTAssertTrue(LibrarySortField.documentDate.ordersOnServer)
        XCTAssertEqual(LibrarySortField.documentDate.serverSortBy, "document_date")
    }

    // MARK: - #4282: the descriptor must map back

    /// Making the Date column sortable is exactly the thing #4282 punishes: a
    /// comparator in the Table's `sortOrder` binding that no column can resolve
    /// crashes the AppKit bridge. Both directions of the mapping must hold.
    func testTheDateComparatorMapsBackToItsField() {
        let comparator = LibrarySortField.documentDate.comparator(ascending: true)

        XCTAssertEqual(comparator.count, 1)
        XCTAssertEqual(
            LibrarySortField.field(forDocumentKeyPath: comparator[0].keyPath),
            .documentDate,
            "a header click on Date must resolve back to the Date field, or the "
                + "setter half-applies (#4282)"
        )
    }

    func testTheOutlineDateComparatorMapsBackToItsField() {
        guard let comparator = LibrarySortField.documentDate
            .outlineColumnComparator(ascending: true) else {
            return XCTFail("the Date column is sortable, so it must declare a comparator")
        }

        XCTAssertEqual(
            LibrarySortField.field(forOutlineKeyPath: comparator.keyPath),
            .documentDate
        )
    }

    /// Every field the outline exposes as a sortable column must round-trip.
    /// The nil cases are columns the toolbar offers but the table does not —
    /// deliberately, and they must stay nil rather than acquire an unbacked
    /// comparator.
    func testEverySortableColumnComparatorRoundTrips() {
        for field in LibrarySortField.allCases {
            guard let comparator = field.outlineColumnComparator(ascending: true) else { continue }
            XCTAssertEqual(
                LibrarySortField.field(forOutlineKeyPath: comparator.keyPath), field,
                "\(field.rawValue)'s column comparator does not map back to it"
            )
        }
    }

    // MARK: - The header key path is not a sort key

    /// `dateHeaderSortKey` exists only to satisfy the Table's bridge. This
    /// pins WHY it must never order rows, so the reason survives even if the
    /// doc comment on it is edited away: it collapses every undated document
    /// onto one value and knows nothing about precision.
    func testTheHeaderKeyPathIsDeliberatelyAPoorSortKey() {
        let undatedA = makeDocument(id: "a", name: "A", dateJdn: nil,
                                    createdAt: Date(timeIntervalSince1970: 0))
        let undatedB = makeDocument(id: "b", name: "B", dateJdn: nil,
                                    createdAt: Date(timeIntervalSince1970: 10_000_000))

        XCTAssertEqual(
            undatedA.dateHeaderSortKey, undatedB.dateHeaderSortKey,
            "undated documents collapse onto one value here — the engine's "
                + "created_at fallback is what separates them, and that is why "
                + "this key path must not be used to order rows"
        )
    }
}

// MARK: - The "No date" group (#3322 step 6)

/// The engine's fallback orders an undated document by its `created_at`
/// converted to a JDN. That is what makes the ordering total, and it stays.
///
/// But it places undated documents INTERLEAVED among dated ones — a diary
/// scanned in 2024 landing between two 1791 letters, which reads as a claim
/// about when it was written. The UI groups them instead.
///
/// The grouping is a stable PARTITION, never a sort: it does not compare two
/// documents, so it cannot become a second opinion about ordering. These tests
/// are mostly about that property.
final class LibraryUndatedGroupingTests: XCTestCase {

    private func doc(_ id: String, jdn: Int?) -> Document {
        Document(
            id: id, parentId: nil, docType: .file, fileType: nil, name: id,
            path: nil, sequence: nil, bbox: nil, status: .completed,
            metadata: [:], pageContent: nil, dateJdn: jdn, sortOrder: 0,
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )
    }

    func testUndatedDocumentsMoveToTheEnd() {
        let mixed = [doc("a", jdn: 100), doc("u1", jdn: nil), doc("b", jdn: 200),
                     doc("u2", jdn: nil), doc("c", jdn: 300)]

        XCTAssertEqual(
            LibrarySortField.groupingUndatedLast(mixed).map(\.id),
            ["a", "b", "c", "u1", "u2"]
        )
    }

    /// The important half. Within each group the ENGINE's order survives —
    /// including among the undated, where that order is the `created_at`
    /// fallback and is the only thing giving them a stable sequence at all.
    func testRelativeOrderSurvivesWithinBothGroups() {
        // Deliberately NOT ascending by JDN: this is the engine's order, and a
        // partition that quietly sorted would tidy it up.
        let engineOrder = [doc("b", jdn: 300), doc("u1", jdn: nil),
                           doc("a", jdn: 100), doc("u2", jdn: nil)]

        let grouped = LibrarySortField.groupingUndatedLast(engineOrder)

        XCTAssertEqual(grouped.map(\.id), ["b", "a", "u1", "u2"],
                       "a partition must not reorder within a group")
    }

    func testAnAllDatedListIsUnchanged() {
        let dated = [doc("b", jdn: 300), doc("a", jdn: 100)]

        XCTAssertEqual(LibrarySortField.groupingUndatedLast(dated).map(\.id), ["b", "a"])
    }

    func testAnAllUndatedListIsUnchanged() {
        let undated = [doc("u1", jdn: nil), doc("u2", jdn: nil)]

        XCTAssertEqual(LibrarySortField.groupingUndatedLast(undated).map(\.id), ["u1", "u2"])
    }

    func testNoDocumentIsLostOrDuplicated() {
        let mixed = [doc("a", jdn: 1), doc("u", jdn: nil), doc("b", jdn: 2)]
        let grouped = LibrarySortField.groupingUndatedLast(mixed)

        XCTAssertEqual(Set(grouped.map(\.id)), Set(mixed.map(\.id)))
        XCTAssertEqual(grouped.count, mixed.count)
    }

    func testEmptyIsEmpty() {
        XCTAssertTrue(LibrarySortField.groupingUndatedLast([]).isEmpty)
    }

    /// Grouping applies only where it means something. Sorting by Name must not
    /// exile undated documents to the bottom — under that sort "undated" is not
    /// a fact the ordering is about.
    func testGroupingDoesNotApplyToClientSortedFields() {
        let mixed = [doc("b", jdn: nil), doc("a", jdn: 100)]

        let byName = LibrarySortField.orderedForDisplay(
            mixed, field: .name, using: LibrarySortField.name.comparator(ascending: true)
        )

        XCTAssertEqual(byName.map(\.id), ["a", "b"],
                       "undated documents sort by name like any other")
    }

    /// The grouped order IS the order `filteredDocuments` holds, so keyboard
    /// navigation and the prefetch index agree with what is on screen. A
    /// grouping applied only at render time would put arrow-key order out of
    /// step with row order.
    func testTheGroupedOrderIsWhatTheSortPathReturns() {
        let mixed = [doc("a", jdn: 100), doc("u", jdn: nil), doc("b", jdn: 200)]

        let displayed = LibrarySortField.orderedForDisplay(
            mixed, field: .documentDate,
            using: LibrarySortField.documentDate.comparator(ascending: true)
        )

        XCTAssertEqual(displayed.map(\.id), ["a", "b", "u"])
    }

    // MARK: - Precision survives the sort (#3322 step 7)

    /// A year-precision document sorts by its start JDN and still RENDERS
    /// "1791". Sorting and rendering read different things — the sort reads
    /// `date_jdn`, the cell reads the engine's `display` — and this pins that
    /// passing through the sort path does not swap one for the other.
    func testAYearPrecisionDocumentStillRendersAsAYearAfterSorting() {
        let yearPrecision = Document(
            id: "y", parentId: nil, docType: .file, fileType: nil, name: "Ledger",
            path: nil, sequence: nil, bbox: nil, status: .completed,
            metadata: [:], pageContent: nil,
            dateOriginal: "1791",
            dateJdn: 2_375_260,
            dateMeta: ["status": AnyCodable("dated"),
                       "display": AnyCodable("1791"),
                       "precision": AnyCodable("year")],
            sortOrder: 0,
            createdAt: Date(timeIntervalSince1970: 0),
            updatedAt: Date(timeIntervalSince1970: 0)
        )

        let displayed = LibrarySortField.orderedForDisplay(
            [yearPrecision], field: .documentDate,
            using: LibrarySortField.documentDate.comparator(ascending: true)
        )

        XCTAssertEqual(displayed.first?.dateJdn, 2_375_260, "it sorts by the start JDN")
        XCTAssertEqual(
            DocumentDateDisplay.resolve(
                dateOriginal: displayed.first?.dateOriginal,
                dateJdn: displayed.first?.dateJdn,
                dateMeta: displayed.first?.dateMeta?.mapValues { $0.value }
            ),
            .dated(text: "1791"),
            "and still reads as a year — never '1 January 1791'"
        )
    }
}
