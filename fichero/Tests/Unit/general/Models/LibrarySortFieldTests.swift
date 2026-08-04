@testable import Fichero
import Foundation
import XCTest

/// Tests for LibrarySortField — the library document sort selector (#1993 Views).
/// The valuable lock is `comparator(ascending:)`: it must actually order
/// Documents by the chosen field and honour the ascending flag. Also covers the
/// metadata (cases, raw values, icons, id).
final class LibrarySortFieldTests: XCTestCase {

    private func doc(
        _ name: String,
        status: Status = .pending,
        created: TimeInterval = 0
    ) -> Document {
        Document(name: name, status: status, createdAt: Date(timeIntervalSince1970: created))
    }

    // MARK: - Metadata

    func testCasesRawValuesIconsAndId() {
        // Not a magic 5/6: every case must be complete, which is the property
        // the literal count was standing in for. `documentDate` joining the
        // enum (#3322) broke the literal and would not have broken this.
        XCTAssertEqual(Set(LibrarySortField.allCases.map(\.rawValue)).count,
                       LibrarySortField.allCases.count,
                       "raw values must be unique — they are the persisted identity")
        XCTAssertEqual(LibrarySortField.name.rawValue, "Name")
        XCTAssertEqual(LibrarySortField.createdAt.rawValue, "Date Created")
        XCTAssertEqual(LibrarySortField.updatedAt.rawValue, "Date Modified")
        XCTAssertEqual(LibrarySortField.fileType.rawValue, "Type")
        XCTAssertEqual(LibrarySortField.status.rawValue, "Status")
        for field in LibrarySortField.allCases {
            XCTAssertFalse(field.icon.isEmpty, "\(field) icon")
            XCTAssertEqual(field.id, field.rawValue)
        }
    }

    func testComparatorReturnsSingleKeyPath() {
        for field in LibrarySortField.allCases {
            XCTAssertEqual(field.comparator(ascending: true).count, 1, "\(field)")
        }
    }

    // MARK: - Actual ordering

    func testNameSortAscendingAndDescending() {
        let docs = [doc("cherry"), doc("apple"), doc("banana")]
        let asc = docs.sorted(using: LibrarySortField.name.comparator(ascending: true))
        XCTAssertEqual(asc.map(\.name), ["apple", "banana", "cherry"])

        let desc = docs.sorted(using: LibrarySortField.name.comparator(ascending: false))
        XCTAssertEqual(desc.map(\.name), ["cherry", "banana", "apple"])
    }

    func testCreatedAtSortOrdersByDate() {
        let docs = [
            doc("a", created: 300),
            doc("b", created: 100),
            doc("c", created: 200)
        ]
        let asc = docs.sorted(using: LibrarySortField.createdAt.comparator(ascending: true))
        XCTAssertEqual(asc.map(\.name), ["b", "c", "a"])
    }

    func testStatusSortOrdersByRawValue() {
        // raw values sort alphabetically: completed < failed < pending < processing
        let docs = [
            doc("p", status: .pending),
            doc("c", status: .completed),
            doc("x", status: .processing),
            doc("f", status: .failed)
        ]
        let asc = docs.sorted(using: LibrarySortField.status.comparator(ascending: true))
        XCTAssertEqual(asc.map(\.status), [.completed, .failed, .pending, .processing])
    }
}
