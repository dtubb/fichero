import Foundation
import SwiftUI

/// Main state container for documents.
///
/// This is the bridge between the backend API and SwiftUI views.
/// It manages loading state, caching, and provides reactive updates.
@MainActor
class DocumentStore: ObservableObject {
    // MARK: - Published State

    /// All collections (top-level documents)
    @Published var collections: [Document] = []

    /// Currently selected collection
    @Published var selectedCollection: Document?

    /// Documents in the current view (children of selected item)
    @Published var currentDocuments: [Document] = []

    /// Currently selected document for detail view
    @Published var selectedDocument: Document?

    /// Loading states
    @Published var isLoading = false
    @Published var isLoadingChildren = false

    /// Connection status
    @Published var isConnected = false

    /// Last error
    @Published var error: Error?

    // MARK: - Private

    private let service = DocumentService()

    /// Cache of children by parent ID
    private var childrenCache: [String: [Document]] = [:]

    // MARK: - Initialization

    init() {
        // Initial connection check will happen on first load
    }

    // MARK: - Connection

    /// Check if the backend is available.
    func checkConnection() async {
        isConnected = await service.checkConnection()
    }

    // MARK: - Loading Collections

    /// Load all collections from the backend.
    func loadCollections() async {
        isLoading = true
        error = nil

        do {
            NSLog("[DocumentStore] Loading collections...")
            collections = try await service.getCollections()
            isConnected = true
            NSLog("[DocumentStore] Loaded %d collections", collections.count)
            for c in collections {
                NSLog("[DocumentStore]   - %@ (id: %@)", c.name, c.id)
            }

            // Auto-select first collection if none selected
            if selectedCollection == nil, let first = collections.first {
                await selectCollection(first)
            }
        } catch {
            NSLog("[DocumentStore] ERROR loading collections: %@", String(describing: error))
            self.error = error
            isConnected = false
        }

        isLoading = false
    }

    /// Refresh collections from the backend.
    func refresh() async {
        await loadCollections()
    }

    // MARK: - Selection

    /// Select a collection and load its children.
    func selectCollection(_ collection: Document) async {
        selectedCollection = collection
        await loadChildren(of: collection)
    }

    /// Load children of a document.
    func loadChildren(of document: Document) async {
        isLoadingChildren = true

        do {
            let children = try await service.getChildren(of: document.id)
            childrenCache[document.id] = children
            currentDocuments = children
        } catch {
            self.error = error
            currentDocuments = []
        }

        isLoadingChildren = false
    }

    /// Get cached children or load from backend.
    func children(of documentId: String) async -> [Document] {
        if let cached = childrenCache[documentId] {
            return cached
        }

        do {
            let children = try await service.getChildren(of: documentId)
            childrenCache[documentId] = children
            return children
        } catch {
            return []
        }
    }

    // MARK: - CRUD Operations

    /// Create a new collection.
    func createCollection(name: String) async throws -> Document {
        let collection = try await service.createCollection(name: name)
        collections.append(collection)
        return collection
    }

    /// Delete a document.
    func deleteDocument(_ document: Document) async throws {
        try await service.deleteDocument(document.id)

        // Remove from local state
        collections.removeAll { $0.id == document.id }
        currentDocuments.removeAll { $0.id == document.id }
        childrenCache.removeValue(forKey: document.id)

        // If this was the selected item, clear selection
        if selectedCollection?.id == document.id {
            selectedCollection = collections.first
            if let selected = selectedCollection {
                await loadChildren(of: selected)
            }
        }
    }

    /// Rename a document.
    func renameDocument(_ document: Document, to newName: String) async throws -> Document {
        let update = DocumentUpdateRequest(name: newName)
        let updated = try await service.updateDocument(document.id, update)

        // Update local state
        updateLocal(updated)

        return updated
    }

    // MARK: - Helpers

    /// Update a document in all local caches.
    private func updateLocal(_ document: Document) {
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
}

// MARK: - Preview Support

extension DocumentStore {
    /// Create a store with empty data for previews.
    static var preview: DocumentStore {
        let store = DocumentStore()
        store.collections = []
        return store
    }
}
