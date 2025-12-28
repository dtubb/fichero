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

    /// Load all documents from the backend to build full tree.
    func loadCollections() async {
        isLoading = true
        error = nil

        do {
            NSLog("[DocumentStore] Loading all documents for tree building...")
            // Load ALL documents so SidebarItemBuilder can construct full hierarchy from parent_id
            collections = try await service.listDocuments(limit: 10000)
            isConnected = true
            NSLog("[DocumentStore] Loaded %d documents total", collections.count)

            let rootCount = collections.filter { $0.parentId == nil }.count
            let childCount = collections.count - rootCount
            NSLog("[DocumentStore]   - %d root items, %d nested items", rootCount, childCount)

            // Publish change
            publish(.collectionsUpdated(collections))

            // Auto-select first root collection if none selected
            if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
                await selectCollection(first)
            }
        } catch {
            NSLog("[DocumentStore] ERROR loading documents: %@", String(describing: error))
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

        // Remove from local state - recursively removes item and all descendants
        removeDocumentRecursively(document.id)

        // Publish change - this triggers @Published update
        publish(.documentDeleted(document))

        // If this was the selected item, clear selection
        if selectedCollection?.id == document.id {
            selectedCollection = collections.first
            if let selected = selectedCollection {
                await loadChildren(of: selected)
            }
        }
    }

    /// Recursively remove a document and all its descendants from the collections array
    private func removeDocumentRecursively(_ documentId: String) {
        // Find and collect all descendant IDs
        var toRemove: Set<String> = [documentId]
        var queue = [documentId]

        while !queue.isEmpty {
            let parentId = queue.removeFirst()

            // Find all children of this parent in the flat collections array
            let children = collections.filter { $0.parentId == parentId }
            for child in children {
                toRemove.insert(child.id)
                queue.append(child.id)
            }
        }

        // Remove all collected IDs from collections array (triggers @Published update)
        collections.removeAll { toRemove.contains($0.id) }

        // Also remove from currentDocuments if present
        currentDocuments.removeAll { toRemove.contains($0.id) }

        // Clear from cache
        for id in toRemove {
            childrenCache.removeValue(forKey: id)
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
        let updated = try await service.moveDocument(documentId, toParent: parentId)

        // Update in-place (same pattern as renameDocument)
        updateLocal(updated)

        // If the document changed parent_id, update collections array structure
        // Moving TO root (parent_id becomes nil)
        if updated.parentId == nil && !collections.contains(where: { $0.id == updated.id }) {
            collections.append(updated)
            NSLog("[DocumentStore] Moved document to root: \(updated.name)")
        }

        // Moving FROM root to a parent (parent_id was nil, now has value)
        if let index = collections.firstIndex(where: { $0.id == updated.id }),
           updated.parentId != nil {
            collections.remove(at: index)
            NSLog("[DocumentStore] Moved document from root to parent: \(updated.name)")
        }

        // Publish change - this triggers @Published update and SwiftUI rebuild
        publish(.documentsUpdated(collections))

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
