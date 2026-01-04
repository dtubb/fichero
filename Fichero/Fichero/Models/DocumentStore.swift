import Foundation
import SwiftUI
import Combine
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "DocumentStore")

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

    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "DocumentStore")

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

    let api: APIClient  // Internal access for LibraryImageView and other components

    /// Publish a document change event.
    private func publish(_ change: DocumentChange) {
        documentChanges.send(change)
    }

    /// Cache of children by parent ID
    private var childrenCache: [String: [Document]] = [:]

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
            collections = try await api.get("/documents", query: query)
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

        logger.info("loadChildren called for document: \(document.id), library path: \(self.api.currentLibraryPath ?? "nil")")

        do {
            let children: [Document] = try await self.api.get("/documents/\(document.id)/children")
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
            let children: [Document] = try await api.get("/documents/\(documentId)/children")
            childrenCache[documentId] = children
            return children
        } catch {
            return []
        }
    }

    // MARK: - CRUD Operations

    /// Create a new collection (deprecated - use createFolder instead).
    func createCollection(name: String) async throws -> Document {
        let doc = DocumentCreateRequest(
            name: name,
            parentId: nil,
            docType: .folder
        )
        let collection: Document = try await api.post("/documents", body: doc)
        collections.append(collection)
        publish(.documentCreated(collection))
        return collection
    }

    /// Create a new folder.
    func createFolder(name: String, parentId: String? = nil) async throws -> Document {
        let doc = DocumentCreateRequest(
            name: name,
            parentId: parentId,
            docType: .folder
        )
        let folder: Document = try await api.post("/documents", body: doc)

        // Reload collections to show the newly created folder
        // This handles both root-level folders and nested folders
        await loadCollections()
        publish(.collectionsUpdated(collections))

        return folder
    }

    /// Delete a document.
    func deleteDocument(_ document: Document) async throws {
        try await api.delete("/documents/\(document.id)")

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

    /// Delete document by ID (for non-document items like searches, chats, workflows)
    func deleteDocumentById(_ id: String) async throws {
        try await api.delete("/documents/\(id)")
        // Reload collections to refresh UI
        await loadCollections()
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
        let updated: Document = try await api.put("/documents/\(document.id)", body: update)

        // Update local state
        updateLocal(updated)

        // Force @Published trigger by creating new array reference
        collections = collections.map { $0 }

        // Publish change
        publish(.documentsUpdated(collections))

        return updated
    }

    /// Rename document by ID (for non-document items like searches, chats, workflows)
    func renameDocumentById(_ id: String, to newName: String) async throws -> Document {
        let update = DocumentUpdateRequest(name: newName)
        let updated: Document = try await api.put("/documents/\(id)", body: update)
        // Reload collections to refresh UI
        await loadCollections()
        return updated
    }

    /// Import a folder recursively.
    func importFolder(at url: URL, parentId: String? = nil) async throws {
        struct IngestFolderRequest: Encodable {
            let path: String
            let parentId: String?
            let copyMode: Bool
            let recursive: Bool
            let extractText: Bool
            let autoEmbed: Bool

            enum CodingKeys: String, CodingKey {
                case path
                case parentId = "parent_id"
                case copyMode = "copy_mode"
                case recursive
                case extractText = "extract_text"
                case autoEmbed = "auto_embed"
            }
        }

        let request = IngestFolderRequest(
            path: url.path,
            parentId: parentId,
            copyMode: true,  // Copy files into library
            recursive: true,  // Include subdirectories
            extractText: true,  // Extract text for search
            autoEmbed: true  // Create embeddings
        )

        // Call the ingest/folder endpoint (returns task_id for async processing)
        let _: [String: String] = try await api.post("/ingest/folder", body: request)

        // Reload collections to show the imported folder
        // The backend processes the folder in the background
        // We reload immediately to show the folder structure
        try await Task.sleep(nanoseconds: 500_000_000)  // Wait 0.5s for initial folder creation
        await loadCollections()
        publish(.collectionsUpdated(collections))
    }

    /// Import a file into a specific location.
    func importFile(at url: URL, parentId: String? = nil) async throws -> Document {
        // Create form data for file upload
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/api/documents/import")!)
        request.httpMethod = "POST"

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        // Add library path header for multi-library support
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
            logger.info("Importing to library: \(libraryPath)")
        } else {
            logger.warning("WARNING: No library path set for import!")
        }

        var body = Data()

        // Add parentId if provided
        if let parentId = parentId {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"parent_id\"\r\n\r\n".data(using: .utf8)!)
            body.append("\(parentId)\r\n".data(using: .utf8)!)
        }

        // Add file
        let filename = url.lastPathComponent
        let mimeType = mimeType(for: url)
        let fileData = try Data(contentsOf: url)

        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        body.append(fileData)
        body.append("\r\n".data(using: .utf8)!)

        // End boundary
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)

        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let document = try JSONDecoder().decode(Document.self, from: data)

        // Reload collections to show the newly imported file
        // This handles both root-level imports and imports into nested folders
        await loadCollections()
        publish(.collectionsUpdated(collections))

        return document
    }

    /// Helper to determine MIME type from file extension
    private func mimeType(for url: URL) -> String {
        let ext = url.pathExtension.lowercased()
        switch ext {
        case "pdf": return "application/pdf"
        case "jpg", "jpeg": return "image/jpeg"
        case "png": return "image/png"
        case "txt": return "text/plain"
        case "doc", "docx": return "application/msword"
        default: return "application/octet-stream"
        }
    }

    /// Move a document to a new parent.
    func moveDocument(_ documentId: String, toParent parentId: String?) async throws -> Document {
        logger.info("Moving \(documentId) to parent: \(parentId ?? "nil (root)")")

        // Use dedicated /move endpoint with proper query parameter handling
        let query: [String: String] = parentId == nil ? [:] : ["parent_id": parentId!]
        let updated: Document = try await api.put("/documents/\(documentId)/move", query: query)

        logger.info("Response: \(updated.name), parent_id: \(updated.parentId ?? "nil")")

        // Update in-place (updates the document in collections, cache, etc.)
        updateLocal(updated)

        // Force @Published trigger by creating new array reference
        // This ensures SwiftUI detects the change even for folder-to-folder moves
        collections = collections.map { $0 }
        logger.info("Moved document: \(updated.name) to parent: \(parentId ?? "root")")

        // Publish change - this triggers PassthroughSubject for any subscribers
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

// MARK: - Request Types

/// Request model for creating a document.
struct DocumentCreateRequest: Codable {
    let name: String
    var parentId: String?
    var docType: DocType = .file
    var fileType: FileType?
    var path: String?
    var pageContent: String?
    var metadata: [String: AnyCodable] = [:]

    enum CodingKeys: String, CodingKey {
        case name
        case parentId = "parent_id"
        case docType = "doc_type"
        case fileType = "file_type"
        case path
        case pageContent = "page_content"
        case metadata
    }
}

/// Request model for updating a document.
struct DocumentUpdateRequest: Codable {
    var name: String?
    var parentId: String?
    var docType: DocType?
    var fileType: FileType?
    var path: String?
    var pageContent: String?
    var status: Status?
    var metadata: [String: AnyCodable]?

    enum CodingKeys: String, CodingKey {
        case name
        case parentId = "parent_id"
        case docType = "doc_type"
        case fileType = "file_type"
        case path
        case pageContent = "page_content"
        case status
        case metadata
    }
}

// MARK: - Helper Types

/// Represents a document with its context in the hierarchy.
struct DocumentHierarchy {
    let ancestors: [Document]  // Sorted from root to immediate parent
    let document: Document
    let children: [Document]

    /// The immediate parent, if any.
    var parent: Document? {
        ancestors.last
    }

    /// Breadcrumb path from root to this document.
    var breadcrumb: [Document] {
        ancestors + [document]
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
