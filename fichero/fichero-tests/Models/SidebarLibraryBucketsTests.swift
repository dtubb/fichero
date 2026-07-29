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

    /// The library is ONE unified node list per tab: the Library / Saved Searches
    /// / Automation section headers (and the divider) are gone. Rows render as
    /// plain `unifiedRows` blocks with no `unifiedDisclosureSection` chrome.
    func testUnifiedLibraryHasNoSectionHeaders() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        XCTAssertFalse(source.contains("func unifiedDisclosureSection"))
        XCTAssertFalse(source.contains("Label(title, systemImage: icon)"))
        XCTAssertFalse(source.contains("Divider()"))
        XCTAssertTrue(source.contains("let libraryItems = flattenedLibraryItems(libraryId: libraryId, buckets: buckets)"))
        XCTAssertTrue(source.contains("unifiedRows(libraryItems, libraryId: libraryId)"))
        XCTAssertEqual(source.components(separatedBy: "unifiedRows(").count - 1, 1)
    }

    /// Slice 0: workflow nodes/folders now render inside the library tree (they
    /// were bucketed but never rendered — only counted). The render is gated on
    /// the workflows feature flag, consistent with the search/automation blocks,
    /// AND on the Global library (#4060 — Default Workflows is global-only).
    func testWorkflowItemsAreRenderedGatedOnFlag() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        XCTAssertTrue(source.contains("FeatureManager.shared.isWorkflowsEnabled"))
        XCTAssertTrue(source.contains("items.append(contentsOf: buckets.workflowItems)"))
        // #4060: the gate must also check isGlobalLibrary so Default Workflows
        // only renders under the Global library, not every individual library.
        XCTAssertTrue(
            source.contains("libraryId == LibraryManager.globalLibraryId"),
            "workflowItems render must be gated on libraryId == globalLibraryId (#4060)"
        )
    }

    /// A library header's count must reflect the same flattened rows that its
    /// disclosure content renders. Workflow mirrors are global-only, so summing
    /// every bucket would make a non-global library advertise hidden rows.
    func testLibraryHeaderCountUsesFlattenedVisibleRows() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")
        XCTAssertTrue(
            source.contains("let totalCount = flattenedLibraryItems(libraryId: libraryId, buckets: buckets).count")
        )
        XCTAssertFalse(source.contains("buckets.documentItems.count + buckets.searchItems.count + buckets.workflowItems.count"))
    }

    /// #4102: every library — global included — renders as its own collapsible
    /// disclosure group. The global library used to render headless, which made
    /// its contents (notably the Default Workflows subfolders) float at the
    /// sidebar's top level next to the real library rows, so libraries did not
    /// read as separate.
    func testEveryLibraryRendersItsOwnHeaderRow() throws {
        let source = try appSource("Views/Sidebar/Sections/SidebarView+UnifiedLibrarySections.swift")

        XCTAssertFalse(
            source.contains("if library.id == LibraryManager.globalLibraryId {"),
            "the global library must not take a headless branch (#4102)"
        )
        XCTAssertTrue(source.contains("libraryDisclosureLabel(library: library, totalCount: totalCount)"))
        XCTAssertEqual(
            source.components(separatedBy: "DisclosureGroup(").count - 1, 1,
            "one shared DisclosureGroup renders every library"
        )
    }

    private func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }
}
