@testable import Fichero
import XCTest

/// Tests for display/value enums that lacked coverage: IngestMode's
/// wire raws + display strings (DocumentModelTests only checks Document.ingestMode
/// resolution, not the enum's own presentation) and the HuggingFace picker enums
/// HFSortOrder / HFTaskCategory (untested entirely). Pure value logic, no engine.
final class ImportAndModelDisplayEnumsTests: XCTestCase {

    // MARK: - IngestMode

    /// Raw values are the UPPERCASE tokens the Python engine expects.
    func testIngestModeRawValuesMatchEngine() {
        XCTAssertEqual(IngestMode.link.rawValue, "LINK")
        XCTAssertEqual(IngestMode.copy.rawValue, "COPY")
        XCTAssertEqual(IngestMode.move.rawValue, "MOVE")
    }

    func testIngestModeDecodesFromUppercaseRaw() throws {
        XCTAssertEqual(try JSONDecoder().decode(IngestMode.self, from: Data("\"LINK\"".utf8)), .link)
        XCTAssertEqual(try JSONDecoder().decode(IngestMode.self, from: Data("\"MOVE\"".utf8)), .move)
    }

    func testIngestModeDisplayName() {
        XCTAssertEqual(IngestMode.link.displayName, "Link Files")
        XCTAssertEqual(IngestMode.copy.displayName, "Copy Files")
        XCTAssertEqual(IngestMode.move.displayName, "Move Files")
    }

    func testIngestModeDescriptionAndIconDistinct() {
        // Each mode carries a non-empty, distinct description + icon.
        let descriptions = Set([IngestMode.link, .copy, .move].map(\.description))
        XCTAssertEqual(descriptions.count, 3)
        XCTAssertFalse(descriptions.contains(""))
        let icons = [IngestMode.link.icon, IngestMode.copy.icon, IngestMode.move.icon]
        XCTAssertEqual(icons, ["link", "doc.on.doc", "arrow.right.doc"])
    }

    // MARK: - HFSortOrder

    func testSortOrderAllCasesAndIds() {
        XCTAssertEqual(HFSortOrder.allCases, [.downloads, .likes, .trending, .lastModified])
        // id mirrors rawValue for each.
        for order in HFSortOrder.allCases {
            XCTAssertEqual(order.id, order.rawValue)
        }
        XCTAssertEqual(HFSortOrder.lastModified.rawValue, "lastModified")
    }

    func testSortOrderLabels() {
        XCTAssertEqual(HFSortOrder.downloads.label, "Most Downloads")
        XCTAssertEqual(HFSortOrder.likes.label, "Most Likes")
        XCTAssertEqual(HFSortOrder.trending.label, "Trending")
        XCTAssertEqual(HFSortOrder.lastModified.label, "Recently Updated")
    }

    // MARK: - HFTaskCategory.popularTasks

    func testPopularTasksAreStableAndUnique() {
        let tasks = HFTaskCategory.popularTasks
        XCTAssertEqual(tasks.count, 7)
        XCTAssertEqual(tasks.first?.id, "text-generation")
        XCTAssertEqual(tasks.first?.label, "Text Generation")
        // The embeddings task uses the HF "feature-extraction" id under a
        // friendlier label.
        XCTAssertEqual(tasks.first { $0.id == "feature-extraction" }?.label, "Embeddings")
        // Ids are unique.
        XCTAssertEqual(Set(tasks.map(\.id)).count, tasks.count)
    }
}
