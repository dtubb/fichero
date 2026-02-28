import Foundation

// MARK: - Helpers

extension DocumentStore {

    /// Update a document in all local caches.
    func updateLocal(_ document: Document) {
        // Update in collections
        if let index = collections.firstIndex(where: { $0.id == document.id }) {
            collections[index] = document
        }

        // Update in current documents
        if let index = currentDocuments.firstIndex(where: { $0.id == document.id }) {
            currentDocuments[index] = document
        }

        // Update in cache
        for (parentId, children) in childrenCache {
            if let index = children.firstIndex(where: { $0.id == document.id }) {
                childrenCache[parentId]?[index] = document
            }
        }

        // Update selection if needed
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
