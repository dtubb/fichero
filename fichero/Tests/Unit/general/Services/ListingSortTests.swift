@testable import Fichero
import XCTest

/// #3322 — decision (a): refetch on ENTERING and LEAVING a server-ordered sort,
/// never on every sort change.
///
/// The alternative considered was to refetch on every sort change so that no
/// field looks special. It was rejected: sorting by Name and by Type are free
/// today, and making them round-trip to keep Date company spends a request per
/// sort change to buy nothing. Paying uniformly for a capability one field uses
/// is a tax, not consistency.
///
/// The policy is expressed as "the request we would send is different", which
/// is why there is no per-field special case to keep in step with the enum.
/// These tests pin the CONSEQUENCES of that phrasing, because the phrasing is
/// the part that is easy to "simplify" into either extreme — always refetch, or
/// never.
final class ListingSortTests: XCTestCase {

    private let byDate = ListingSort(field: "document_date", ascending: true)
    private let byDateDescending = ListingSort(field: "document_date", ascending: false)

    // MARK: - The free case, which is most of them

    /// Name -> Type. Both are client-ordered, so nothing is asked of the
    /// server and no request goes out. If this ever fails, option (b) has crept
    /// back in and every sort change now costs a round trip.
    func testMovingBetweenTwoClientSortedFieldsDoesNotRefetch() {
        let fromName = ListingSort.forLibrarySort(field: .name, ascending: true)
        let toType = ListingSort.forLibrarySort(field: .fileType, ascending: true)

        XCTAssertNil(fromName)
        XCTAssertNil(toType)
        XCTAssertFalse(ListingSort.requiresRefetch(from: fromName, to: toType))
    }

    /// Reversing a client-ordered sort is also free — the client has the rows
    /// and the comparator.
    func testFlippingDirectionOnAClientSortedFieldDoesNotRefetch() {
        XCTAssertFalse(
            ListingSort.requiresRefetch(
                from: ListingSort.forLibrarySort(field: .name, ascending: true),
                to: ListingSort.forLibrarySort(field: .name, ascending: false)
            )
        )
    }

    // MARK: - Entering and leaving

    func testEnteringDocumentDateRefetches() {
        XCTAssertTrue(ListingSort.requiresRefetch(from: nil, to: byDate))
    }

    func testLeavingDocumentDateRefetches() {
        XCTAssertTrue(ListingSort.requiresRefetch(from: byDate, to: nil))
    }

    /// Leaving matters as much as entering, and is the easier one to forget:
    /// the rows on screen are in the ENGINE's order, and switching to Name
    /// without refetching would sort that stale set client-side. It would look
    /// right — the rows are sorted by name — while quietly being whichever
    /// subset and ordering the date query returned.
    func testLeavingIsNotOptionalEvenThoughTheClientCouldSortWhatItHas() {
        let leaving = ListingSort.forLibrarySort(field: .name, ascending: true)

        XCTAssertNil(leaving)
        XCTAssertTrue(ListingSort.requiresRefetch(from: byDate, to: leaving))
    }

    // MARK: - Direction within a server-ordered sort

    /// The engine decides direction too. Reversing the array client-side would
    /// flip the rows without re-deciding the precision ties — cheaper-looking
    /// than a re-sort and exactly as wrong.
    func testFlippingDirectionWithinDocumentDateRefetches() {
        XCTAssertTrue(ListingSort.requiresRefetch(from: byDate, to: byDateDescending))
    }

    // MARK: - No spurious refetches

    func testRepeatingTheSameSortDoesNotRefetch() {
        XCTAssertFalse(ListingSort.requiresRefetch(from: byDate, to: byDate))
        XCTAssertFalse(ListingSort.requiresRefetch(from: nil, to: nil))
    }

    // MARK: - Encoding

    func testDirectionIsEncodedAsTheEngineSpellsIt() {
        XCTAssertEqual(ListingSort(field: "document_date", ascending: true).direction, "asc")
        XCTAssertEqual(ListingSort(field: "document_date", ascending: false).direction, "desc")
    }

    /// The `sort_by` value must be the engine's, not the enum's display name —
    /// `LibrarySortField.documentDate.rawValue` is "Document Date", which the
    /// route would reject.
    func testTheFieldIsTheEnginesNameNotTheMenuLabel() {
        let sort = ListingSort.forLibrarySort(field: .documentDate, ascending: true)

        XCTAssertEqual(sort?.field, "document_date")
        XCTAssertNotEqual(sort?.field, LibrarySortField.documentDate.rawValue)
    }

    /// One place decides which fields go to the server, so "asks the server"
    /// and "skips the client sort" cannot drift apart. They are the same
    /// question; answering it twice is how two answers disagree.
    func testAskingTheServerAndSkippingTheClientSortAreTheSameSet() {
        for field in LibrarySortField.allCases {
            XCTAssertEqual(
                ListingSort.forLibrarySort(field: field, ascending: true) != nil,
                field.ordersOnServer,
                "\(field.rawValue) disagrees about who owns its ordering"
            )
        }
    }
}
