@testable import Fichero
import XCTest

/// Covers the header-derived bucket filtering that #3862 moved out of the body's
/// per-eval `unifiedLibraryBuckets` into the cached, pure
/// `SidebarView.computeLibraryItemBuckets`. The cache is only correct if this
/// pure function sorts a library header's children into the same document /
/// search / workflow buckets the inline filter used to.
@MainActor
final class SidebarLibraryBucketsTests: XCTestCase {
    func testComputeSortsChildrenIntoTypeBuckets() {
        let lib = UUID()
        let doc = SidebarItem.fromDocument(Document(docType: .folder, name: "Report"), libraryId: lib)
        let docFolder = SidebarItem.folder(name: "Docs", folderPath: "/docs", category: .folder, libraryId: lib)
        let searchFolder = SidebarItem.folder(name: "Saved", folderPath: "/s", category: .search, libraryId: lib)
        let workflowFolder = SidebarItem.folder(name: "Flows", folderPath: "/w", category: .workflow, libraryId: lib)

        let header = SidebarItem.folder(
            name: "root", folderPath: "/", category: .folder, libraryId: lib,
            children: [doc, docFolder, searchFolder, workflowFolder]
        )

        let buckets = SidebarView.computeLibraryItemBuckets(from: header)

        // Documents + category:.folder folders land in documentItems (order kept).
        XCTAssertEqual(buckets.documentItems.map(\.id), [doc.id, docFolder.id])
        XCTAssertEqual(buckets.searchItems.map(\.id), [searchFolder.id])
        XCTAssertEqual(buckets.workflowItems.map(\.id), [workflowFolder.id])
    }

    func testHeaderWithoutChildrenYieldsEmptyBuckets() {
        let header = SidebarItem.folder(name: "empty", folderPath: "/", category: .folder, libraryId: UUID())
        let buckets = SidebarView.computeLibraryItemBuckets(from: header)
        XCTAssertTrue(buckets.documentItems.isEmpty)
        XCTAssertTrue(buckets.searchItems.isEmpty)
        XCTAssertTrue(buckets.workflowItems.isEmpty)
    }
}
