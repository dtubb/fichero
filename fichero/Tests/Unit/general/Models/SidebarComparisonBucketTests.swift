@testable import Fichero
import Foundation
import XCTest

/// #4335 — the comparisons bucket existed (`buildComparisonItems` /
/// `SidebarItem.fromComparison`) but was never loaded into the sidebar, and
/// even when built its rows were dropped by the unified-section bucket filter
/// and its id ("comparison:<id>") fell through `SidebarDestination` to the
/// `.document` fallback, so clicking routed to nothing. These tests pin the
/// three seams: item building, destination round-trip, and bucket filtering.
@MainActor
final class SidebarComparisonBucketTests: XCTestCase {

    private let libraryId = UUID()

    private func makeSummary(
        id: String = "cmp-1",
        prompt: String = "Compare the two model answers"
    ) -> ComparisonSummary {
        ComparisonSummary(
            prompt: prompt,
            modelsCompared: ["provider/a", "provider/b"],
            totalCostUsd: 0.0123,
            comparisonId: id,
            timestamp: "2026-07-29T12:00:00Z"
        )
    }

    // MARK: - Item building

    func testBuildComparisonItemsProducesTypedRows() throws {
        let items = SidebarItemBuilder.buildComparisonItems(
            from: [makeSummary()],
            libraryId: libraryId
        )

        XCTAssertEqual(items.count, 1)
        let item = try XCTUnwrap(items.first)
        XCTAssertEqual(item.id, "comparison:cmp-1")
        XCTAssertEqual(item.category, .chat)
        guard case .comparison(let summary) = item.itemType else {
            return XCTFail("expected a .comparison item, got \(item.itemType)")
        }
        XCTAssertEqual(summary.comparisonId, "cmp-1")
        XCTAssertFalse(item.isFolder)
    }

    func testLongPromptIsTruncatedForDisplay() throws {
        let longPrompt = String(repeating: "x", count: 60)
        let items = SidebarItemBuilder.buildComparisonItems(
            from: [makeSummary(prompt: longPrompt)],
            libraryId: libraryId
        )
        let name = try XCTUnwrap(items.first?.name)
        XCTAssertTrue(name.hasSuffix("..."))
        XCTAssertLessThanOrEqual(name.count, 43)
    }

    // MARK: - Destination round-trip

    /// Without a dedicated case, "comparison:<id>" parsed to nil and
    /// `SidebarItem.destination` re-prefixed it to "doc:comparison:<id>" —
    /// the same failure mode virtual folders hit in #11.
    func testComparisonDestinationRoundTrips() {
        let destination = SidebarDestination(serializedID: "comparison:cmp-1")
        XCTAssertEqual(destination, .comparisonItem("cmp-1"))
        XCTAssertEqual(destination?.serializedID, "comparison:cmp-1")
    }

    func testComparisonItemDestinationResolvesToItsOwnRowId() throws {
        let items = SidebarItemBuilder.buildComparisonItems(
            from: [makeSummary()],
            libraryId: libraryId
        )
        let item = try XCTUnwrap(items.first)
        // The row's destination must serialize back to the row's id so the
        // cached item index can resolve the click (#4335).
        XCTAssertEqual(item.destination.serializedID, item.id)
    }

    // MARK: - Unified-section bucket filter

    /// The bucket filter used to drop comparison rows entirely — loaded but
    /// never rendered. The comparisons bucket must capture them and must not
    /// leak them into the document bucket.
    func testComputeLibraryItemBucketsSeparatesComparisonRows() {
        let comparisonItem = SidebarItem.fromComparison(makeSummary(), libraryId: libraryId)
        let docItem = SidebarItem.fromDocument(
            Document(id: "doc-1", docType: .folder, name: "Folder"),
            libraryId: libraryId
        )
        let header = SidebarItem(
            id: "header",
            name: "Library",
            icon: "books.vertical",
            category: .library,
            itemType: .libraryHeader,
            children: [docItem, comparisonItem],
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )

        let buckets = SidebarView.computeLibraryItemBuckets(from: header)

        XCTAssertEqual(buckets.comparisonItems.map(\.id), ["comparison:cmp-1"])
        XCTAssertFalse(buckets.documentItems.contains { $0.id == "comparison:cmp-1" })
        XCTAssertTrue(buckets.documentItems.contains { $0.id.hasSuffix("doc-1") })
    }
}
