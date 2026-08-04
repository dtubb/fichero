import FicheroAPIClient
import Foundation

// MARK: - Sidebar child loading + one-level chevron prefetch (#3355)

extension DocumentStore {
    /// Populate the sidebar child cache without changing the current grid
    /// selection, then eagerly prefetch ONE level deeper (#3355).
    ///
    /// This premise was WRONG and is corrected here (#4515): the backend DOES
    /// send `child_count` on `/roots` and `/children` (`_with_child_counts`),
    /// and it is a typed schema field. The client threw it away in
    /// `convertToDocument`, so every folder decoded `childCount == 0` and
    /// looked childless — the missing disclosure triangle this prefetch was
    /// built to paper over. `SidebarItem.isExpandable` now answers from the
    /// count.
    ///
    /// What remains here is the CHILDREN themselves, not the chevron: caching
    /// one level down means an expand renders from cache instead of a
    /// round-trip. Whether that is still worth a fetch per root on window open
    /// is a separate question from the one it was filed to answer.
    func loadSidebarChildren(of document: Document) async {
        let children = await cacheSidebarChildren(of: document)
        await prefetchChildContainerChildren(of: children)
    }

    /// Fetch and cache a document's immediate children (idempotent). Does NOT
    /// prefetch further — the building block for the one-level chevron prefetch.
    @discardableResult
    func cacheSidebarChildren(of document: Document) async -> [Document] {
        if let existing = childrenCache[document.id] { return existing }

        guard let children = await fetchSidebarChildren(of: document) else { return [] }
        childrenCache[document.id] = children
        logger.info("Cached \(children.count) sidebar children for \(document.id)")
        return children
    }

    /// Prefetch one level down so folder chevrons are correct before expansion
    /// (#3355). Only containers are prefetched; leaf rows have nothing to reveal.
    ///
    /// Fetches sequentially but commits ONE `childrenCache` write (#4228). The
    /// loop used to call `cacheSidebarChildren`, which assigns `childrenCache`
    /// itself — and every assignment fires `SidebarView.observeDocumentStore`,
    /// which computes `sidebarTreeSignature` (a sort over every document) and
    /// then rebuilds the whole tree via `SidebarItemBuilder.buildLibraryGroup`.
    /// So expanding a folder with K subfolders did K full-tree rebuilds, and
    /// `loadCollections()` — which prefetches over ALL roots on window open —
    /// did one per root. That is the same O(N²)-on-the-main-thread shape that
    /// `spliceDocuments` was batched to fix, on the other half of the path, and
    /// it is what beachballs an expand and a window open.
    func prefetchChildContainerChildren(of documents: [Document]) async {
        let pending = Self.containersNeedingChildren(in: documents, cache: childrenCache)
        guard !pending.isEmpty else { return }

        // ponytail: still sequential — the cost that showed up was the republish
        // per fetch, not the fetches; parallelize only if a wide fan-out
        // measurably lags after this.
        var fetched: [String: [Document]] = [:]
        for container in pending {
            guard let children = await fetchSidebarChildren(of: container) else { continue }
            fetched[container.id] = children
        }

        let merged = Self.mergingChildren(fetched, into: childrenCache)
        if merged != childrenCache { childrenCache = merged }
    }

    /// The containers in `documents` whose children are not cached yet — the
    /// only ones worth a round-trip. Pure so the batching is testable without a
    /// live backend.
    static func containersNeedingChildren(
        in documents: [Document],
        cache: [String: [Document]]
    ) -> [Document] {
        documents.filter { $0.docType == .folder && cache[$0.id] == nil }
    }

    /// Fold a batch of freshly fetched child lists into a cache snapshot,
    /// never clobbering an entry that arrived while the batch was in flight
    /// (`cacheSidebarChildren` treats a present entry as authoritative).
    static func mergingChildren(
        _ fetched: [String: [Document]],
        into cache: [String: [Document]]
    ) -> [String: [Document]] {
        var merged = cache
        for (parentId, children) in fetched where merged[parentId] == nil {
            merged[parentId] = children
        }
        return merged
    }

    /// One child fetch with no cache write — the piece `cacheSidebarChildren`
    /// and the batched prefetch share. `nil` means "don't record anything"
    /// (cancelled, or failed and already reported).
    private func fetchSidebarChildren(of document: Document) async -> [Document]? {
        do {
            return applyStatusOverrides(
                try await fetchWithRetry { try await self.documentService.getChildren(document.id) }
            )
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.error("cacheSidebarChildren failed: \(error.localizedDescription)")
            self.error = error
            return nil
        }
    }
}
