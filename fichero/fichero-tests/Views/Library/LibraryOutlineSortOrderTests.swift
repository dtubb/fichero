@testable import Fichero
import Foundation
import XCTest

/// #4282 — CRASH clicking the Name column header in table view.
///
/// The outline Table's `sortOrder` binding must obey two invariants:
///
/// 1. The GETTER only ever emits comparators whose key path a sortable
///    column actually declares. A sort field with no backing column
///    (`updatedAt` / `fileType`, reachable via the toolbar sort menu and
///    persisted per folder) must yield an EMPTY order — on macOS the Table
///    bridges each comparator to an AppKit sort descriptor resolved against
///    a column, and a descriptor the bridge cannot map back to a column is
///    the NSSortDescriptor-bridge crash class (a plain `NSSortDescriptor`
///    reaching SwiftUI's private `TableColumnSortDescriptor` cast aborts).
/// 2. The SETTER mapping is total: a key path we never installed maps to
///    nil, and the caller treats that as a full no-op — the old code fell
///    through the field chain but still flipped `sortAscending` and saved.
///
/// These are the pure halves of `LibraryView.outlineSortOrder` /
/// `handleSortOrderChange`, extracted onto `LibrarySortField` so they are
/// testable without a rendered Table.
final class LibraryOutlineSortOrderTests: XCTestCase {

    private func node(
        _ name: String,
        status: Status = .pending,
        created: TimeInterval = 0
    ) -> LibraryOutlineNode {
        .document(
            Document(name: name, status: status, createdAt: Date(timeIntervalSince1970: created)),
            children: nil
        )
    }

    // MARK: - Getter invariant: only column-backed comparators

    func testColumnBackedFieldsProduceComparators() {
        XCTAssertNotNil(LibrarySortField.name.outlineColumnComparator(ascending: true))
        XCTAssertNotNil(LibrarySortField.createdAt.outlineColumnComparator(ascending: true))
        XCTAssertNotNil(LibrarySortField.status.outlineColumnComparator(ascending: true))
    }

    func testColumnlessFieldsProduceNoComparator() {
        // The table has no Modified or Type column; emitting a comparator for
        // them hands the AppKit bridge a descriptor it cannot resolve (#4282).
        XCTAssertNil(LibrarySortField.updatedAt.outlineColumnComparator(ascending: true))
        XCTAssertNil(LibrarySortField.fileType.outlineColumnComparator(ascending: false))
    }

    func testOutlineComparatorActuallySortsNodes() throws {
        let nodes = [node("cherry"), node("apple"), node("banana")]
        let asc = try XCTUnwrap(LibrarySortField.name.outlineColumnComparator(ascending: true))
        XCTAssertEqual(
            nodes.sorted(using: [asc]).map(\.document.name),
            ["apple", "banana", "cherry"]
        )
        let desc = try XCTUnwrap(LibrarySortField.name.outlineColumnComparator(ascending: false))
        XCTAssertEqual(
            nodes.sorted(using: [desc]).map(\.document.name),
            ["cherry", "banana", "apple"]
        )
    }

    func testOutlineCreatedComparatorSortsByDate() throws {
        let nodes = [node("a", created: 300), node("b", created: 100), node("c", created: 200)]
        let asc = try XCTUnwrap(LibrarySortField.createdAt.outlineColumnComparator(ascending: true))
        XCTAssertEqual(nodes.sorted(using: [asc]).map(\.document.name), ["b", "c", "a"])
    }

    // MARK: - Setter mapping: total and round-trips every sortable column

    func testEveryColumnComparatorRoundTripsToItsField() throws {
        for field in LibrarySortField.allCases {
            guard let comparator = field.outlineColumnComparator(ascending: true) else { continue }
            XCTAssertEqual(
                LibrarySortField.field(forOutlineKeyPath: comparator.keyPath), field,
                "\(field) comparator must map back to itself"
            )
        }
    }

    func testHeaderClickKeyPathsMapIndependentlyOfComparatorInstance() {
        // A header click hands the setter a comparator SwiftUI built from the
        // TableColumn's `value:` key path — a different instance from ours.
        // Freshly-formed key path literals must still map (appended key path
        // equality, not identity).
        XCTAssertEqual(
            LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.document.name), .name
        )
        XCTAssertEqual(
            LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.document.createdAt),
            .createdAt
        )
        XCTAssertEqual(
            LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.document.status.rawValue),
            .status
        )
        // Menu-only fields still map if a comparator for them ever arrives.
        XCTAssertEqual(
            LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.document.updatedAt),
            .updatedAt
        )
        XCTAssertEqual(
            LibrarySortField.field(
                forOutlineKeyPath: \LibraryOutlineNode.document.sortableFileType
            ),
            .fileType
        )
    }

    func testUnknownOutlineKeyPathMapsToNil() {
        // The setter must no-op (not flip direction) for a key path no column
        // declares — pin nil so the guard in `outlineSortOrder` stays honest.
        XCTAssertNil(LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.document.id))
        XCTAssertNil(LibrarySortField.field(forOutlineKeyPath: \LibraryOutlineNode.count))
    }

    // MARK: - Document-typed mapping (list-view sortOrder path)

    func testDocumentComparatorsRoundTripForAllFields() {
        for field in LibrarySortField.allCases {
            let keyPath = field.comparator(ascending: true)[0].keyPath
            XCTAssertEqual(
                LibrarySortField.field(forDocumentKeyPath: keyPath), field,
                "\(field) document comparator must map back to itself"
            )
        }
    }

    func testUnknownDocumentKeyPathMapsToNil() {
        XCTAssertNil(LibrarySortField.field(forDocumentKeyPath: \Document.id))
    }
}
