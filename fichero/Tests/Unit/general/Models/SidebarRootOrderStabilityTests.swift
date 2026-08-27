@testable import Fichero
import XCTest

/// #4237 — "clicking a sidebar row moves the selection up one after the list
/// loads".
///
/// Selection is held by document id (`selectedItemId: String?`), so a list
/// mutation cannot move the selection. What moved is the ROW: the sidebar's
/// root order was arrival order, not a sort.
///
/// `DocumentStore.sidebarDocuments` is `collections + childrenCache.values`,
/// and `spliceDocuments` APPENDS a newly created root to the tail of
/// `collections` while `/documents/roots` serves `(sort_order, lower(name))`
/// (`_ordered_by_sort_order`). So a root that arrived via the change stream sat
/// at the end until the next `loadCollections()` re-sorted it into place — and
/// every row after its sorted position shifted by one at that moment. Dictionary
/// iteration over `childrenCache` adds a second, non-deterministic source of the
/// same shift.
///
/// The fix sorts root documents with `childOrder`, the same key the backend
/// uses, so the tree order is a function of the documents and not of when they
/// arrived.
@MainActor
final class SidebarRootOrderStabilityTests: XCTestCase {

    private let libraryId = UUID()

    private func folder(id: String, name: String, sortOrder: Int = 0) -> Document {
        Document(id: id, parentId: nil, docType: .folder, name: name, sortOrder: sortOrder)
    }

    private func names(_ items: [SidebarItem]) -> [String] {
        items.map(\.name)
    }

    // MARK: - Direct repro

    /// FAILS BEFORE THE FIX: the builder emitted roots in arrival order, so the
    /// spliced-in "Archive" stayed at the tail and every row moved when the
    /// next roots fetch put it first.
    func testRootOrderIsIndependentOfArrivalOrder() {
        let apples = folder(id: "apples", name: "Apples")
        let zebra = folder(id: "zebra", name: "Zebra")
        let archive = folder(id: "archive", name: "Archive")

        // Arrival order: a live splice appended `archive` last.
        let afterSplice = SidebarItemBuilder.buildLibraryHierarchy(
            from: [apples, zebra, archive],
            libraryId: libraryId
        )
        // Backend order: the next `loadCollections()` served them sorted.
        let afterReload = SidebarItemBuilder.buildLibraryHierarchy(
            from: [apples, archive, zebra],
            libraryId: libraryId
        )

        XCTAssertEqual(names(afterSplice), ["Apples", "Archive", "Zebra"])
        XCTAssertEqual(names(afterSplice), names(afterReload),
                       "A reload must not move the row the user just clicked.")
    }

    /// The row a user selected keeps its index across the reload — the exact
    /// acceptance criterion on the issue, expressed positionally because the
    /// symptom is positional.
    func testSelectedRowKeepsItsIndexWhenANewRootArrivesEarlier() {
        let beta = folder(id: "beta", name: "Beta")
        let gamma = folder(id: "gamma", name: "Gamma")
        let selectedId = "doc:gamma"

        let before = SidebarItemBuilder.buildLibraryHierarchy(from: [beta, gamma], libraryId: libraryId)
        let indexBefore = before.firstIndex { $0.id == selectedId }

        // "Alpha" is created by an import while the click is in flight; the
        // change stream appends it to `collections`.
        let alpha = folder(id: "alpha", name: "Alpha")
        let after = SidebarItemBuilder.buildLibraryHierarchy(from: [beta, gamma, alpha], libraryId: libraryId)
        let indexAfter = after.firstIndex { $0.id == selectedId }

        XCTAssertEqual(indexBefore, 1)
        // A root sorting BEFORE the selection legitimately shifts it down by
        // one; what must never happen is the shift arriving later, on a reload,
        // long after the list visually settled.
        XCTAssertEqual(indexAfter, 2)

        let reloaded = SidebarItemBuilder.buildLibraryHierarchy(from: [alpha, beta, gamma], libraryId: libraryId)
        XCTAssertEqual(reloaded.firstIndex { $0.id == selectedId }, indexAfter,
                       "The reload must be a no-op for row positions.")
    }

    // MARK: - Ordering keys

    /// User-defined `sortOrder` (persisted by `/documents/reorder`) wins over
    /// name, matching `_ordered_by_sort_order`.
    func testExplicitSortOrderBeatsName() {
        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [
                folder(id: "a", name: "Alpha", sortOrder: 2),
                folder(id: "z", name: "Zulu", sortOrder: 1)
            ],
            libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["Zulu", "Alpha"])
    }

    /// Names tie-break case-insensitively, as the backend's `lower(name)` does.
    func testNameOrderIsCaseInsensitive() {
        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [folder(id: "b", name: "beta"), folder(id: "a", name: "Alpha")],
            libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["Alpha", "beta"])
    }

    // MARK: - Regressions the sort must not cause

    /// Inbox stays pinned first regardless of its name's sort position.
    func testInboxStaysFirst() {
        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [folder(id: "a", name: "Alpha"), folder(id: "inbox", name: "Inbox")],
            libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["Inbox", "Alpha"])
    }

    /// Children were already sorted; sorting roots must not disturb them.
    func testChildrenRemainSorted() {
        let parent = folder(id: "parent", name: "Parent")
        let kidB = Document(id: "kb", parentId: "parent", docType: .folder, name: "B")
        let kidA = Document(id: "ka", parentId: "parent", docType: .folder, name: "A")

        let items = SidebarItemBuilder.buildLibraryHierarchy(
            from: [parent, kidB, kidA],
            libraryId: libraryId
        )
        XCTAssertEqual(names(items), ["Parent"])
        XCTAssertEqual(names(items.first?.children ?? []), ["A", "B"])
    }

    /// Two builds over the same documents in two different orders produce
    /// identical trees — the invariant the whole fix exists to guarantee.
    func testBuildIsOrderInsensitive() {
        let docs = [
            folder(id: "1", name: "Delta"),
            folder(id: "2", name: "Charlie"),
            folder(id: "3", name: "Bravo"),
            folder(id: "4", name: "Alpha")
        ]
        let forward = SidebarItemBuilder.buildLibraryHierarchy(from: docs, libraryId: libraryId)
        let reversed = SidebarItemBuilder.buildLibraryHierarchy(from: Array(docs.reversed()), libraryId: libraryId)
        XCTAssertEqual(forward.map(\.id), reversed.map(\.id))
    }
}
