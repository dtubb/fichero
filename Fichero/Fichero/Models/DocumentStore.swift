import Foundation
import SwiftUI
import Combine

/// Document change types for reactive updates.
enum DocumentChange {
    case collectionsUpdated([Document])
    case collectionSelected(Document)
    case documentsUpdated([Document])
    case documentDeleted(Document)
    case documentCreated(Document)
}

/// Main state container for documents.
///
/// This is the bridge between the backend API and SwiftUI views.
/// It manages loading state, caching, and provides reactive updates.
@MainActor
class DocumentStore: ObservableObject {
    // MARK: - Private Properties
    
    /// Publisher for document changes.
    private let documentChanges = PassthroughSubject<DocumentChange, Error>()
    private var cancellables = Set<AnyCancellable>()
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

    /// Publisher for document changes.
    var documentChangePublisher: AnyPublisher<DocumentChange, Error> {
        documentChanges.eraseToAnyPublisher()
    }

    // MARK: - Private

    private let service = DocumentService()
    
    /// Publish a document change event.
    private func publish(_ change: DocumentChange) {
        documentChanges.send(change)
    }

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
            for collection in collections {
                NSLog("[DocumentStore]   - %@ (id: %@)", collection.name, collection.id)
            }

            // Publish change
            publish(.collectionsUpdated(collections))

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
        publish(.documentCreated(collection))
        return collection
    }

    /// Delete a document.
    func deleteDocument(_ document: Document) async throws {
        try await service.deleteDocument(document.id)

        // Remove from local state
        collections.removeAll { $0.id == document.id }
        currentDocuments.removeAll { $0.id == document.id }
        childrenCache.removeValue(forKey: document.id)

        // Publish change
        publish(.documentDeleted(document))

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

        // Publish change
        publish(.documentsUpdated(currentDocuments))

        return updated
    }

    /// Import a file into a specific location.
    func importFile(at url: URL, parentId: String? = nil) async throws -> Document {
        let document = try await service.importFile(at: url, parentId: parentId)
        
        // If this is a top-level import (no parent), add to collections
        if parentId == nil {
            collections.append(document)
            publish(.collectionsUpdated(collections))
        } else {
            // Refresh the parent's children
            if let parent = collections.first(where: { $0.id == parentId }) {
                await loadChildren(of: parent)
            }
            publish(.documentsUpdated(currentDocuments))
        }

        return document
    }

    /// Move a document to a new parent.
    func moveDocument(_ documentId: String, toParent parentId: String?) async throws -> Document {
        let document = try await service.moveDocument(documentId, toParent: parentId)
        
        // Remove from current location
        collections.removeAll { $0.id == documentId }
        currentDocuments.removeAll { $0.id == documentId }
        
        // Add to new location if it's a top-level collection
        if parentId == nil {
            collections.append(document)
        } else {
            // Refresh the parent's children
            if let parent = collections.first(where: { $0.id == parentId }) {
                await loadChildren(of: parent)
            }
        }

        publish(.documentsUpdated(currentDocuments))
        return document
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
