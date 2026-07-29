import Foundation

// MARK: - ObservableDomainStore (#1995 / #1996)

/// DocumentStore is the first/proving consumer of the generic change-stream
/// substrate (`ObservableDomainStore`). It makes the library table update live:
/// a `document.*` event from any window patches the affected row(s) in place —
/// the sidebar tree (`collections`), the grid (`currentDocuments`), and the
/// children cache — instead of the user having to refresh. Registered on
/// `LibraryReference` alongside the other stores (see
/// `LibraryManager.changeStream`).
///
/// Kept in its own extension file (matching `+CRUD` / `+Helpers`) so the core
/// `DocumentStore.swift` stays under the file-length gate.
extension DocumentStore: ObservableDomainStore {
    nonisolated var changeDomain: String { "document" }

    /// Full re-fetch used for reconnect resync (`resync()` → `reload()`). Maps
    /// onto the existing `refresh()`, which reloads `collections` AND the
    /// selected collection's children — the same recovery a manual refresh does.
    func reload() async {
        await refresh()
    }

    /// Apply one `document.*` change event. Stays synchronous and non-blocking
    /// (the beachball rule): deletes are an O(n) in-place removal; updates and
    /// creates only *record* the affected ids and arm the debouncer, so a
    /// workflow event storm coalesces into a single trailing fetch+splice that
    /// touches just those rows — never a wholesale table reload.
    func apply(_ event: ChangeEvent) {
        let ids = Set(event.documentIds)
        guard !ids.isEmpty else { return }
        switch event.verb {
        case "deleted":
            removeDocuments(ids: ids)
        case "updated", "created":
            // Drop the echo of writes THIS device just made — re-fetching and
            // re-splicing our own save changes the row's identity and forces the
            // page editor to rebuild (width / cursor / scroll reset, #2478). A
            // legitimate update from another device has no fresh own-write marker
            // and is still patched in place (#2479).
            let remoteIds = ids.filter { !consumeOwnWriteEcho($0) }
            guard !remoteIds.isEmpty else { return }
            pendingPatchIds.formUnion(remoteIds)
            reloadDebouncer.schedule { [weak self] in
                await self?.flushPendingPatches()
            }
        default:
            break
        }
    }

    /// Remove the given document ids in place from every list/cache that holds
    /// them. Purely local — no network — so it runs synchronously inside `apply`.
    private func removeDocuments(ids: Set<String>) {
        collections.removeAll { ids.contains($0.id) }
        currentDocuments.removeAll { ids.contains($0.id) }
        workspaces.removeAll { ids.contains($0.id) }
        for (parentId, kids) in childrenCache {
            let filtered = kids.filter { !ids.contains($0.id) }
            if filtered.count != kids.count {
                childrenCache[parentId] = filtered
            }
        }
    }

    /// Fetch each pending document once and splice the fresh value in place.
    /// Coalesced by the debouncer so a burst flushes once; granular so only the
    /// affected rows change. A fetch failure (doc deleted between event and
    /// fetch, or transient error) is skipped — a missed update is recovered by
    /// `resync()` on the next reconnect.
    private func flushPendingPatches() async {
        let ids = pendingPatchIds
        pendingPatchIds.removeAll()
        // Collect the whole batch, then splice ONCE (#4235). Splicing inside
        // this loop published a change per document, so a 500-file import
        // rebuilt the sidebar 500 times over a list that was itself growing.
        var fetched: [Document] = []
        fetched.reserveCapacity(ids.count)
        for id in ids {
            let fresh: Document
            do {
                fresh = try await documentService.getDocument(id)
            } catch {
                logger.debug(
                    "granular patch fetch failed for \(id, privacy: .public): \(error.localizedDescription, privacy: .public)"
                )
                continue
            }
            fetched.append(applyStatusOverrides([fresh]).first ?? fresh)
        }
        spliceDocuments(fetched)
    }

    /// Replace `doc` in place wherever it already appears; if it's new and
    /// belongs to a surface we're showing, insert it. Untouched rows keep
    /// referential identity so SwiftUI's Table/List re-renders only the one row
    /// that changed (no whole-list flash — see `refreshPendingStatusesOnly`).
    /// Internal, not private: the delivery invariant below (a child of a LOADED
    /// parent must reach `childrenCache` and must NOT reach `collections`) is
    /// load-bearing and was undefended, so the tests drive this directly.
    func spliceDocument(_ doc: Document) {
        spliceDocuments([doc])
    }

    /// Splice a whole batch with ONE write to each published container (#4235).
    ///
    /// `spliceDocument` per document meant a 500-file import performed 500
    /// separate mutations of `collections`, and every one of them invalidates
    /// the sidebar — which then rebuilds the entire hierarchy from a list that
    /// is itself growing. That is O(N²) work AND O(N²) allocation during the
    /// exact window the user is watching, which is what made a fast import feel
    /// like a hung app.
    ///
    /// Batching does not change WHAT lands, only how often observers are told.
    /// The per-document rules are unchanged and still live in one place.
    func spliceDocuments(_ docs: [Document]) {
        guard !docs.isEmpty else { return }

        var nextCollections = collections
        var nextCurrent = currentDocuments
        var nextChildren = childrenCache
        let selectedId = selectedCollection?.id
        var changed = SpliceChanges()

        for doc in docs {
            Self.splice(
                doc,
                collections: &nextCollections,
                currentDocuments: &nextCurrent,
                childrenCache: &nextChildren,
                selectedCollectionId: selectedId,
                changes: &changed
            )
        }

        // One assignment each, gated on the CHANGED FLAGS the splice rules set
        // — not on deep `!=` compares: Document is Equatable across ~24 fields
        // (structure nodes, AnyCodable metadata), so comparing the whole
        // library per flush would put an O(N) deep-equality walk on the main
        // actor for exactly the no-op polls this path exists to reject.
        // Untouched rows keep referential identity either way.
        if changed.collections { collections = nextCollections }
        if changed.currentDocuments { currentDocuments = nextCurrent }
        if changed.childrenCache { childrenCache = nextChildren }
    }

    /// Which published containers a batch actually mutated.
    private struct SpliceChanges {
        var collections = false
        var currentDocuments = false
        var childrenCache = false
    }

    /// The per-document splice rules, over plain values so a batch can apply
    /// them without touching published state until it is done.
    private static func splice(
        _ doc: Document,
        collections: inout [Document],
        currentDocuments: inout [Document],
        childrenCache: inout [String: [Document]],
        selectedCollectionId: String?,
        changes: inout SpliceChanges
    ) {
        // ROOTS ONLY — `loadCollections()` assigns `getRoots()`
        // (`/api/documents/roots`), so a nested document does not belong here.
        // The append used to be unguarded, unlike the two blocks below, and an
        // import of N files appended all N to a roots list until the next
        // `loadCollections()` silently reset it (#4203).
        //
        // Careful: that same append was ALSO how imported children reached the
        // sidebar, because `SidebarItemBuilder` files anything with a parentId
        // under its parent. Dropping it without the `childrenCache` insert
        // below would have "fixed" the pollution by breaking live delivery —
        // and no test would have noticed.
        if let index = collections.firstIndex(where: { $0.id == doc.id }) {
            if collections[index] != doc {
                collections[index] = doc
                changes.collections = true
            }
        } else if doc.parentId == nil {
            collections.append(doc)
            changes.collections = true
        } else if childrenCache[doc.parentId ?? ""] == nil {
            // Parent's children are NOT loaded, so the `childrenCache` block
            // below cannot deliver this row — and `SidebarItemBuilder` files
            // anything with a `parentId` under its parent, so `collections` is
            // the only container that makes it visible. Dropping it here is what
            // broke live delivery when the roots guard first landed: importing
            // into a folder the user had not expanded showed nothing at all.
            //
            // The cost is that `collections` briefly holds non-roots for
            // unexpanded parents, until the next `loadCollections()`. That is
            // the lesser evil: the pollution is transient and invisible, a
            // missing row is neither.
            collections.append(doc)
            changes.collections = true
        }

        // Grid for the selected collection.
        if let index = currentDocuments.firstIndex(where: { $0.id == doc.id }) {
            if currentDocuments[index] != doc {
                currentDocuments[index] = doc
                changes.currentDocuments = true
            }
        } else if let selectedCollectionId, doc.parentId == selectedCollectionId {
            currentDocuments.append(doc)
            changes.currentDocuments = true
        }

        // Children cache (only a parent already loaded — i.e. a folder the user
        // has open). This is the live-delivery path during an import: rows
        // appear under the folder being imported into, without a refresh.
        // A closed folder stays unfetched; expanding it loads its children.
        if let parentId = doc.parentId, var kids = childrenCache[parentId] {
            if let index = kids.firstIndex(where: { $0.id == doc.id }) {
                if kids[index] != doc {
                    kids[index] = doc
                    childrenCache[parentId] = kids
                    changes.childrenCache = true
                }
            } else {
                kids.append(doc)
                childrenCache[parentId] = kids
                changes.childrenCache = true
            }
        }
    }
}
