@testable import Fichero
import Foundation
import Testing

/// #4228 — beachball on window open and on the sidebar disclosure arrow.
///
/// `prefetchChildContainerChildren` looped over every child container calling
/// `cacheSidebarChildren`, and each of those assigns `childrenCache`. Every
/// assignment fires `SidebarView.observeDocumentStore`, which computes
/// `sidebarTreeSignature` (a sort over every document in the library) and then
/// rebuilds the entire tree through `SidebarItemBuilder.buildLibraryGroup`. So
/// the cost of one expand was K full-tree rebuilds, and `loadCollections()` —
/// which prefetches over ALL roots on window open — paid one per root. Same
/// O(N²)-on-the-main-thread shape that `spliceDocuments` was batched to fix.
///
/// The batching logic is pure and tested directly here; the network half is
/// unchanged.
@MainActor
@Suite("Sidebar child prefetch batches its cache writes (#4228)")
struct SidebarPrefetchBatchingTests {

    private func folder(_ id: String) -> Document {
        Document(id: id, parentId: nil, docType: .folder, name: id)
    }

    private func file(_ id: String) -> Document {
        Document(id: id, parentId: nil, docType: .file, name: id)
    }

    private func child(_ id: String, of parent: String) -> Document {
        Document(id: id, parentId: parent, docType: .file, name: id)
    }

    // MARK: - Which containers are worth a round-trip

    @Test("only folders are prefetched — leaf rows have nothing to reveal")
    func leavesAreSkipped() {
        let pending = DocumentStore.containersNeedingChildren(
            in: [folder("a"), file("b"), folder("c")],
            cache: [:]
        )
        #expect(pending.map(\.id) == ["a", "c"])
    }

    @Test("an already-cached folder is not re-fetched")
    func cachedFoldersAreSkipped() {
        let pending = DocumentStore.containersNeedingChildren(
            in: [folder("a"), folder("b")],
            cache: ["a": [child("a1", of: "a")]]
        )
        #expect(pending.map(\.id) == ["b"])
    }

    @Test("an empty folder counts as cached — an empty array is a real answer")
    func emptyCachedFolderIsSkipped() {
        let pending = DocumentStore.containersNeedingChildren(
            in: [folder("a")],
            cache: ["a": []]
        )
        #expect(pending.isEmpty, "[] means 'fetched, has none', not 'unknown'")
    }

    @Test("nothing pending when every container is cached")
    func nothingPendingShortCircuits() {
        let pending = DocumentStore.containersNeedingChildren(
            in: [folder("a"), folder("b")],
            cache: ["a": [], "b": []]
        )
        #expect(pending.isEmpty)
    }

    // MARK: - Folding the batch back in

    @Test("a whole batch merges into one cache value")
    func batchMerges() {
        let merged = DocumentStore.mergingChildren(
            ["a": [child("a1", of: "a")], "b": [child("b1", of: "b")]],
            into: [:]
        )
        #expect(merged.keys.sorted() == ["a", "b"])
        #expect(merged["a"]?.map(\.id) == ["a1"])
        #expect(merged["b"]?.map(\.id) == ["b1"])
    }

    @Test("existing entries survive — the batch only adds")
    func existingEntriesSurvive() {
        let merged = DocumentStore.mergingChildren(
            ["a": [child("a1", of: "a")]],
            into: ["z": [child("z1", of: "z")]]
        )
        #expect(merged["z"]?.map(\.id) == ["z1"])
        #expect(merged["a"]?.map(\.id) == ["a1"])
    }

    /// A live splice can insert a child of `a` while the prefetch of `a` is in
    /// flight; `cacheSidebarChildren` treats a present entry as authoritative
    /// and the batch must do the same, or the newly delivered row is dropped.
    @Test("a value that arrived mid-flight is not clobbered by the stale batch")
    func inFlightArrivalWins() {
        let live = [child("a1", of: "a"), child("a2-new", of: "a")]
        let merged = DocumentStore.mergingChildren(
            ["a": [child("a1", of: "a")]],   // fetched before a2-new existed
            into: ["a": live]
        )
        #expect(merged["a"]?.map(\.id) == ["a1", "a2-new"])
    }

    @Test("an empty batch leaves the cache untouched")
    func emptyBatchIsANoOp() {
        let cache = ["a": [child("a1", of: "a")]]
        #expect(DocumentStore.mergingChildren([:], into: cache) == cache)
    }

    /// The property the fix exists for: the merged result is one value, so one
    /// assignment publishes it — the observer count is independent of K.
    @Test("merging is a single value regardless of how many folders were fetched")
    func mergeIsOneValue() {
        var fetched: [String: [Document]] = [:]
        for index in 0..<50 { fetched["f\(index)"] = [child("c\(index)", of: "f\(index)")] }

        let merged = DocumentStore.mergingChildren(fetched, into: [:])

        #expect(merged.count == 50)
        // Idempotent: re-folding the same batch changes nothing, so a retry
        // cannot republish.
        #expect(DocumentStore.mergingChildren(fetched, into: merged) == merged)
    }
}
