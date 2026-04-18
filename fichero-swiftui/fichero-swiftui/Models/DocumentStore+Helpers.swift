import Foundation

// MARK: - Helpers

extension DocumentStore {

    /// Update a document in all local caches.
    ///
    /// Handles the cross-folder move case: if the document's `parentId`
    /// no longer matches the currently-viewed `selectedCollection`, it
    /// must be REMOVED from `currentDocuments` — not just replaced in
    /// place — or the grid keeps showing a document that now lives
    /// somewhere else. Same logic for `childrenCache` buckets: the
    /// document only belongs in the bucket whose key equals its new
    /// `parentId`.
    func updateLocal(_ document: Document) {
        // Update in collections.
        if let index = collections.firstIndex(where: { $0.id == document.id }) {
            collections[index] = document
        }

        // Sync currentDocuments with the new parentId:
        //   - if it now belongs to the viewed folder, replace in place;
        //   - if not, remove it so the grid no longer shows it.
        let viewedFolderId = selectedCollection?.id
        if document.parentId == viewedFolderId {
            if let index = currentDocuments.firstIndex(where: { $0.id == document.id }) {
                currentDocuments[index] = document
            }
        } else {
            currentDocuments.removeAll { $0.id == document.id }
        }

        // Update / re-bucket the childrenCache. Remove from every bucket
        // that isn't the document's current parent; insert-or-replace in
        // the bucket that is.
        for parentId in childrenCache.keys {
            if parentId == document.parentId {
                if let index = childrenCache[parentId]?.firstIndex(where: { $0.id == document.id }) {
                    childrenCache[parentId]?[index] = document
                } else {
                    childrenCache[parentId]?.append(document)
                }
            } else {
                childrenCache[parentId]?.removeAll { $0.id == document.id }
            }
        }

        // Update selection if needed.
        if selectedCollection?.id == document.id {
            selectedCollection = document
        }
        if selectedDocument?.id == document.id {
            selectedDocument = document
        }
    }

    /// Clear all cached data.
    func clearCache() {
        childrenCache.removeAll()
    }

    // MARK: - Processing Status Updates

    /// Update the processing status of a document by its file path.
    /// This is used during workflow execution to show visual feedback.
    /// The status is in-memory only and reverts on app restart.
    func updateProcessingStatus(forPath filePath: String, status: Status) {
        // Update in collections
        if let index = collections.firstIndex(where: { $0.path == filePath }) {
            collections[index].status = status
        }

        // Update in current documents
        if let index = currentDocuments.firstIndex(where: { $0.path == filePath }) {
            currentDocuments[index].status = status
        }

        // Update in cache
        for (parentId, children) in childrenCache {
            if let index = children.firstIndex(where: { $0.path == filePath }) {
                childrenCache[parentId]?[index].status = status
            }
        }

        // Update selection if needed
        if selectedDocument?.path == filePath {
            selectedDocument?.status = status
        }
    }
}
