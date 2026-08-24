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
        // Expansion REFRESHES (2026-08-23, Daniel: sidebar showed 3 children
        // while the grid showed 151). The cache-first helper below made a
        // sparse early fetch permanent for the session; an explicit expand
        // is the user asking what is in here NOW, so it answers with a fetch
        // and leaves the cache to the chevron prefetch, where stale but
        // instant is the point.
        if let fresh = await fetchSidebarChildren(of: document),
           childrenCache[document.id] != fresh {
            childrenCache[document.id] = fresh
        }
        let children = childrenCache[document.id] ?? []
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
    /// The ancestor DOCUMENTS of `id`, ROOT-FIRST, excluding `id` itself — the
    /// folders the sidebar must expand and load to make the row exist. `nil`
    /// when this store does not know the document at all, so a multi-library
    /// caller can try the next library. Walks parentId with a visited-set and
    /// a depth cap: an ancestors loop once ran a test suite to 50GB
    /// (2026-08-16), and a cycle in bad data must degrade to a short path,
    /// never a hang.
    func sidebarRevealPath(to id: String) async -> [Document]? {
        // CACHE-ONLY walk first: answers with zero network when the rows are
        // already loaded (relaunch reveal while the engine is still booting).
        // A CYCLE degrades to the partial chain here — malformed data, and
        // the 50GB scar (2026-08-16) says never hand it to a loop again.
        func cached(_ docId: String) -> Document? {
            if let hit = currentDocuments.first(where: { $0.id == docId }) { return hit }
            return childrenCache.values.lazy
                .compactMap({ $0.first(where: { $0.id == docId }) }).first
        }
        if let anchor = cached(id) {
            var chain: [Document] = []
            var visited: Set<String> = [id]
            var current = anchor
            var incomplete = false
            for _ in 0..<32 {
                guard let parentId = current.parentId, !parentId.isEmpty else { break }
                guard !visited.contains(parentId) else { break }  // cycle → partial
                guard let parent = cached(parentId) else { incomplete = true; break }
                visited.insert(parentId)
                chain.append(parent)
                current = parent
            }
            if !incomplete { return chain.reversed() }
        }
        // Consumer 2 of the outline endpoint (Mandate 1): when the cache
        // doesn't know the whole chain, the server walks it ONCE —
        // cycle-guarded, root-first — instead of the old per-ancestor
        // getDocument loop. nil keeps its contract: "this store does not
        // know the doc", so a multi-library caller can try the next library.
        do {
            let outline = try await documentService.getDocumentView(id)
            outlineCache[id] = outline
            return outline.ancestors
        } catch {
            return nil
        }
    }

    private func fetchSidebarChildren(of document: Document) async -> [Document]? {
        do {
            // Consumer 3 (Mandate 1): the sidebar's STORED-tier children from
            // the outline endpoint — the same answer getChildren gave, plus
            // the ancestors ride along free and warm the crumb cache.
            let outline = try await fetchWithRetry {
                try await self.documentService.getDocumentView(document.id, level: .stored)
            }
            outlineCache[document.id] = outline
            return applyStatusOverrides(outline.children)
        } catch {
            if error.isCancellationError { return nil }   // superseded — not a failure
            logger.error("cacheSidebarChildren failed: \(error.localizedDescription)")
            self.error = error
            return nil
        }
    }
}
