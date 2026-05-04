import Combine
import Foundation
import OSLog
import SwiftUI

let documentStoreLogger = Logger(subsystem: "com.fichero.fichero", category: "DocumentStore")

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

    let logger = Logger(subsystem: "com.fichero.fichero", category: "DocumentStore")

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

    /// Per-document workflow status overlay, keyed by document.id. Survives
    /// reloads of `currentDocuments` / `collections` / `childrenCache` so a
    /// failed-state (red X) icon stays visible after navigating away and back.
    /// Without this, Document.status was reset to .pending on every reload —
    /// success icons appeared persistent only because artifact existence
    /// derived completion separately, while errors silently disappeared (#791).
    /// In-memory only; clears on app restart.
    @Published var workflowStatusOverrides: [String: Status] = [:]

    /// Publisher for document changes.
    var documentChangePublisher: AnyPublisher<DocumentChange, Error> {
        documentChanges.eraseToAnyPublisher()
    }

    // MARK: - Private

    let api: APIClient  // Internal access for LibraryImageView and other components

    /// Publish a document change event.
    func publish(_ change: DocumentChange) {
        documentChanges.send(change)
    }

    /// Cache of children by parent ID
    var childrenCache: [String: [Document]] = [:]

    // MARK: - Initialization

    /// Initialize with a per-window APIClient instance.
    /// This ensures operations in one window don't affect other windows.
    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Connection

    /// Check if the backend is available.
    func checkConnection() async {
        do {
            _ = try await api.healthCheck()
            isConnected = true
        } catch {
            isConnected = false
        }
    }

    // MARK: - Loading Collections

    /// Load all documents from the backend to build full tree.
    func loadCollections() async {
        isLoading = true
        error = nil

        do {
            logger.info("Loading all documents for tree building...")
            // Load ALL documents so SidebarItemBuilder can construct full hierarchy from parent_id
            // No limit - load everything for complete tree structure
            let query = ["offset": "0"]
            let fresh: [Document] = try await api.get("/documents", query: query)
            collections = applyStatusOverrides(fresh)
            isConnected = true
            logger.info("Loaded \(self.collections.count) documents total")

            let rootCount = self.collections.filter { $0.parentId == nil }.count
            let childCount = self.collections.count - rootCount
            logger.info("  - \(rootCount) root items, \(childCount) nested items")

            // Publish change
            publish(.collectionsUpdated(collections))

            // Auto-select first root collection if none selected
            if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
                await selectCollection(first)
            }
        } catch {
            logger.error("ERROR loading documents: \(String(describing: error))")
            self.error = error
            isConnected = false
        }

        isLoading = false
    }

    /// Refresh collections AND the currently-selected collection's children
    /// from the backend. Reloading both is important because most callers
    /// ("I just imported a folder", "I just moved an item") want the grid
    /// view (`currentDocuments`) to reflect the change too — not just the
    /// sidebar tree (`collections`). Without the child reload, a drop into
    /// the currently-viewed folder shows the new folder in the sidebar but
    /// a stale empty grid (#576).
    func refresh() async {
        await loadCollections()
        if let selected = selectedCollection {
            await loadChildren(of: selected)
        }
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

        let libraryPath = self.api.currentLibraryPath ?? "nil"
        logger.info("loadChildren called for document: \(document.id), library path: \(libraryPath)")

        do {
            let fresh: [Document] = try await self.api.get("/documents/\(document.id)/children")
            let children = applyStatusOverrides(fresh)
            self.childrenCache[document.id] = children
            self.currentDocuments = children
            logger.info("loadChildren succeeded, got \(children.count) children")
        } catch {
            logger.error("loadChildren failed: \(error.localizedDescription)")
            self.error = error
            self.currentDocuments = []
        }

        self.isLoadingChildren = false
    }

    /// Get cached children or load from backend.
    func children(of documentId: String) async -> [Document] {
        if let cached = childrenCache[documentId] {
            return cached
        }

        do {
            let fresh: [Document] = try await api.get("/documents/\(documentId)/children")
            let children = applyStatusOverrides(fresh)
            childrenCache[documentId] = children
            return children
        } catch {
            return []
        }
    }
}

// MARK: - Preview Support

extension DocumentStore {
    /// Create a store with empty data for previews.
    static var preview: DocumentStore {
        let store = DocumentStore(apiClient: APIClient())
        store.collections = []
        return store
    }
}
