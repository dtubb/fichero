@testable import Fichero
import Foundation
import Testing

// MARK: - Sidebar Reorder Helper Tests

/// Covers the pure helper that translates a SwiftUI `.onMove` event into
/// the ordered list of document IDs to persist. Keeps the index-math
/// and kind-gate logic out of the view layer so regressions (e.g. the
/// "flash-once-then-dies" symptom the old `.onMove` impl had) can be
/// caught by the test suite before hitting Daniel's build.
// @MainActor: `SidebarView.sidebarUnifiedRowsReorderKind` is implicitly
// MainActor-isolated (SwiftUI View statics). Calling it from Swift Testing's
// background executor trips dispatch_assert_queue → SIGTRAP and kills the
// whole test HOST mid-run (seen 2026-07-26: xcodebuild "Restarting after
// unexpected exit" → leg marked FAILED with 0 assertion failures).
@MainActor
struct SidebarReorderedDocIdsTests {

    private let libraryId = UUID()

    private func doc(_ id: String, name: String, sortOrder: Int = 0) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .document(Document(
                id: id,
                docType: .file,
                name: name,
                sortOrder: sortOrder
            )),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: sortOrder,
            isFolder: false
        )
    }

    private func savedSearch(_ id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: "search:\(id)",
            name: name,
            icon: "magnifyingglass",
            category: .search,
            itemType: .savedSearch(SavedSearch(id: id, name: name, query: "")),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: libraryId,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    @Test("Moving a single document down yields the new ordered IDs")
    func moveOneDown() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 3
        ))
        #expect(result == ["b", "c", "a"])
    }

    @Test("Moving a document up yields the new ordered IDs")
    func moveOneUp() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 2),
            to: 0
        ))
        #expect(result == ["c", "a", "b"])
    }

    @Test("No-op move (same position) returns nil")
    func noOpMoveReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 0
        ) == nil)
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 1
        ) == nil)
    }

    @Test("Mixed children: non-doc items keep position, docs get reordered")
    func mixedKindsReturnsDocIdsOnly() throws {
        let children = [
            doc("a", name: "A"),
            savedSearch("s", name: "S"),
            doc("b", name: "B")
        ]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 3
        ))
        #expect(result == ["b", "a"])
    }

    @Test("Moving a non-document item among docs is a no-op for reorder")
    func movingNonDocAmongDocsIsNoop() {
        let children = [
            doc("a", name: "A"),
            doc("b", name: "B"),
            savedSearch("s", name: "S")
        ]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 2),
            to: 0
        ) == nil)
    }

    @Test("List with no documents returns nil regardless of move")
    func noDocumentsReturnsNil() {
        let children = [savedSearch("s1", name: "S1"), savedSearch("s2", name: "S2")]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(integer: 0),
            to: 2
        ) == nil)
    }

    @Test("Empty source IndexSet returns nil")
    func emptySourceReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        #expect(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet(),
            to: 1
        ) == nil)
    }

    @Test("Moving multiple siblings together preserves group order")
    func multiMove() throws {
        let children = [
            doc("a", name: "A"), doc("b", name: "B"),
            doc("c", name: "C"), doc("d", name: "D")
        ]
        let result = try #require(sidebarReorderedDocIds(
            children: children,
            moving: IndexSet([0, 1]),
            to: 4
        ))
        #expect(result == ["c", "d", "a", "b"])
    }

    @Test("Unified row reorder dispatches by moved kind and rejects cross-kind moves")
    func unifiedRowReorderDispatchUsesMovedKindAndRejectsCrossKindMoves() throws {
        let rows = [doc("a", name: "A"), doc("b", name: "B"), savedSearch("s1", name: "S1"), savedSearch("s2", name: "S2")]
        let kind = try #require(SidebarView.sidebarUnifiedRowsReorderKind(items: rows, source: IndexSet(integer: 2), destination: 4))

        #expect(kind == .savedSearch)
        #expect(SidebarView.sidebarUnifiedRowsReorderKind(items: rows, source: IndexSet(integer: 2), destination: 1) == nil)
        #expect(SidebarView.sidebarUnifiedRowsReorderKind(items: rows, source: IndexSet([1, 2]), destination: 4) == nil)
    }
}

// MARK: - Cross-Hierarchy Insertion Tests

/// Covers `sidebarReorderedDocIdsWithInsert` — the helper that backs
/// `.dropDestination(for: String.self) { ids, offset in }` on both
/// `unifiedRows` (library-root insertion) and `childrenList` (nested
/// folder-children insertion). Cycle prevention is tested separately
/// via `CircularDropDetectionTests` since it lives in `isDescendant`.
struct SidebarReorderedDocIdsWithInsertTests {

    private func doc(_ id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: "doc:\(id)",
            name: name,
            icon: "doc",
            category: .folder,
            itemType: .document(
                Document(
                    id: id,
                    parentId: nil,
                    docType: .folder,
                    fileType: nil,
                    name: name,
                    status: .completed,
                    metadata: [:],
                    sortOrder: 0
                )
            ),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: nil,
            folderPath: "/",
            sortOrder: 0,
            isFolder: true
        )
    }

    private func savedSearch(_ id: String, name: String) -> SidebarItem {
        SidebarItem(
            id: "search:\(id)",
            name: name,
            icon: "magnifyingglass",
            category: .search,
            itemType: .folder(folderPath: "/"),
            children: nil,
            progress: nil,
            showProgress: false,
            libraryId: nil,
            folderPath: "/",
            sortOrder: 0,
            isFolder: false
        )
    }

    @Test("Empty bareIds → nil (nothing to insert)")
    func emptyBareIdsReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        #expect(sidebarReorderedDocIdsWithInsert(children: children, inserting: [], at: 1) == nil)
    }

    @Test("Insert new id at beginning → [new, a, b]")
    func insertAtBeginning() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: 0))
        #expect(result == ["new", "a", "b"])
    }

    @Test("Insert new id at end → [a, b, new]")
    func insertAtEnd() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: 2))
        #expect(result == ["a", "b", "new"])
    }

    @Test("Insert new id in middle → [a, new, b]")
    func insertInMiddle() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: 1))
        #expect(result == ["a", "new", "b"])
    }

    @Test("Moving an existing id dedupes — [a, b, c], move 'a' to offset 3 → [b, c, a]")
    func moveExistingDedup() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["a"], at: 3))
        #expect(result == ["b", "c", "a"])
    }

    @Test("Insert multiple new ids at offset → [a, x, y, b]")
    func insertMultipleNew() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["x", "y"], at: 1))
        #expect(result == ["a", "x", "y", "b"])
    }

    @Test("Mixed: insert two ids, one already present → dedupe + re-insert")
    func mixedInsertAndDedup() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new", "b"], at: 3))
        #expect(result == ["a", "c", "new", "b"])
    }

    @Test("Moving multiple existing IDs preserves the dropped order")
    func moveMultipleExistingIdsPreservesDroppedOrder() throws {
        let children = [
            doc("a", name: "A"), doc("b", name: "B"),
            doc("c", name: "C"), doc("d", name: "D")
        ]
        let result = try #require(sidebarReorderedDocIdsWithInsert(
            children: children,
            inserting: ["b", "a"],
            at: 4
        ))
        #expect(result == ["c", "d", "b", "a"])
    }

    @Test("Offset beyond count clamps to end")
    func offsetClampedToEnd() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: 9999))
        #expect(result == ["a", "b", "new"])
    }

    @Test("Negative offset clamps to 0")
    func negativeOffsetClampedToZero() throws {
        let children = [doc("a", name: "A"), doc("b", name: "B")]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: -5))
        #expect(result == ["new", "a", "b"])
    }

    @Test("Mixed-kind children: non-document partition preserved, docs reordered")
    func mixedKindChildren() throws {
        let children = [
            doc("a", name: "A"),
            savedSearch("s", name: "Searches"),
            doc("b", name: "B")
        ]
        let result = try #require(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["new"], at: 2))
        #expect(result == ["a", "b", "new"])
    }

    @Test("No-op: inserting an id already at the same position returns nil")
    func noOpInsertReturnsNil() {
        let children = [doc("a", name: "A"), doc("b", name: "B"), doc("c", name: "C")]
        #expect(sidebarReorderedDocIdsWithInsert(children: children, inserting: ["b"], at: 1) == nil)
    }
}

// MARK: - Transactional Move Batch Tests

@MainActor
struct SidebarTransactionalMoveBatchTests {
    @Test("transactional move batch succeeds without refreshing")
    func successDoesNotRefresh() async {
        enum TestError: Error {
            case unexpected
        }

        var calls: [String] = []
        var refreshCount = 0

        let result = await moveSidebarDocumentsTransactionally(
            ["a", "b"],
            toParent: "parent-folder",
            move: { itemId, parentId in
                calls.append("\(itemId)->\(parentId ?? "nil")")
                if itemId == "never" {
                    throw TestError.unexpected
                }
            },
            refresh: {
                refreshCount += 1
            }
        )

        #expect(result.isSuccessful)
        #expect(result.movedIds == ["a", "b"])
        #expect(result.failedItemId == nil)
        #expect(result.errorMessage == nil)
        #expect(calls == ["a->parent-folder", "b->parent-folder"])
        #expect(refreshCount == 0)
    }

    @Test("transactional move batch stops at the first failure and refreshes")
    func failureRefreshesAndStops() async {
        enum TestError: Error {
            case boom
        }

        var calls: [String] = []
        var refreshCount = 0

        let result = await moveSidebarDocumentsTransactionally(
            ["a", "b", "c"],
            toParent: nil,
            move: { itemId, parentId in
                calls.append("\(itemId)->\(parentId ?? "nil")")
                if itemId == "b" {
                    throw TestError.boom
                }
            },
            refresh: {
                refreshCount += 1
            }
        )

        #expect(result.isSuccessful == false)
        #expect(result.movedIds == ["a"])
        #expect(result.failedItemId == "b")
        #expect(result.errorMessage != nil)
        #expect(calls == ["a->nil", "b->nil"])
        #expect(refreshCount == 1)
    }
}
