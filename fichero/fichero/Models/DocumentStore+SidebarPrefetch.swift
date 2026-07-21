import Foundation

// MARK: - Sidebar child loading + one-level chevron prefetch (#3355)

extension DocumentStore {
    /// Populate the sidebar child cache without changing the current grid
    /// selection, then eagerly prefetch ONE level deeper (#3355).
    ///
    /// The backend does not send `child_count` on `getRoots`/`getChildren`, so a
    /// folder whose children haven't been fetched decodes `childCount == 0` and
    /// looks childless — its disclosure triangle is missing until it's clicked
    /// (today the children only load as a side-effect of SELECTING the folder).
    /// Caching each child container's children gives it a non-nil `children`
    /// array in the rebuilt sidebar tree, so "a folder of folders" shows the
    /// right chevrons before the user expands anything. One level only — the
    /// grandchildren's own children wait for the next expand / option-click.
    func loadSidebarChildren(of document: Document) async {
        let children = await cacheSidebarChildren(of: document)
        await prefetchChildContainerChildren(of: children)
    }

    /// Fetch and cache a document's immediate children (idempotent). Does NOT
    /// prefetch further — the building block for the one-level chevron prefetch.
    @discardableResult
    func cacheSidebarChildren(of document: Document) async -> [Document] {
        if let existing = childrenCache[document.id] { return existing }

        do {
            let children = applyStatusOverrides(
                try await fetchWithRetry { try await self.documentService.getChildren(document.id) }
            )
            childrenCache[document.id] = children
            logger.info("Cached \(children.count) sidebar children for \(document.id)")
            return children
        } catch {
            logger.error("cacheSidebarChildren failed: \(error.localizedDescription)")
            self.error = error
            return []
        }
    }

    /// Prefetch one level down so folder chevrons are correct before expansion
    /// (#3355). Only containers are prefetched; leaf rows have nothing to reveal.
    func prefetchChildContainerChildren(of documents: [Document]) async {
        // ponytail: sequential fetches — fine for a folder's handful of subfolders;
        // parallelize with a task group only if a wide fan-out measurably lags.
        for child in documents where child.docType == .folder {
            _ = await cacheSidebarChildren(of: child)
        }
    }
}
