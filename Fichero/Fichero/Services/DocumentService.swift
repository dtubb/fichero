import Foundation
import OSLog

/// Service for document CRUD operations
/// Wraps the Python backend documents API
@MainActor
class DocumentService: ObservableObject {
    // MARK: - Published State

    @Published var isProcessing: Bool = false
    @Published var lastError: Error?

    private let api: APIClient
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "DocumentService")

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Create

    /// Create a new collection (folder)
    /// - Parameters:
    ///   - name: Collection name
    ///   - parentId: Optional parent collection ID (nil for root)
    /// - Returns: Created document
    func createCollection(name: String, parentId: String? = nil) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Creating collection: \(name)")

        let request = CreateDocumentRequest(
            name: name,
            parentId: parentId,
            docType: "collection"
        )

        let document: Document = try await api.post("/documents", body: request)
        logger.info("Created collection: \(document.id)")
        return document
    }

    /// Create a new document
    /// - Parameters:
    ///   - name: Document name
    ///   - parentId: Optional parent collection ID
    ///   - docType: Document type (file, collection, etc.)
    ///   - metadata: Optional metadata
    /// - Returns: Created document
    func createDocument(
        name: String,
        parentId: String? = nil,
        docType: String = "file",
        metadata: [String: String]? = nil
    ) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Creating document: \(name)")

        let request = CreateDocumentRequest(
            name: name,
            parentId: parentId,
            docType: docType,
            metadata: metadata
        )

        let document: Document = try await api.post("/documents", body: request)
        logger.info("Created document: \(document.id)")
        return document
    }

    // MARK: - Read

    /// Get a single document by ID
    /// - Parameter id: Document ID
    /// - Returns: Document
    func getDocument(_ id: String) async throws -> Document {
        logger.info("Fetching document: \(id)")
        let document: Document = try await api.get("/documents/\(id)")
        return document
    }

    /// Get children of a document/collection
    /// - Parameter parentId: Parent document ID
    /// - Returns: Array of child documents
    func getChildren(_ parentId: String) async throws -> [Document] {
        logger.info("Fetching children of: \(parentId)")
        let documents: [Document] = try await api.get("/documents/\(parentId)/children")
        logger.info("Found \(documents.count) children")
        return documents
    }

    /// Get ancestors of a document (for breadcrumb navigation)
    /// - Parameter id: Document ID
    /// - Returns: Array of ancestor documents (root to parent)
    func getAncestors(_ id: String) async throws -> [Document] {
        logger.info("Fetching ancestors of: \(id)")
        let documents: [Document] = try await api.get("/documents/\(id)/ancestors")
        logger.info("Found \(documents.count) ancestors")
        return documents
    }

    /// Get root-level documents
    /// - Returns: Array of root documents
    func getRoots() async throws -> [Document] {
        logger.info("Fetching root documents")
        let documents: [Document] = try await api.get("/documents/roots")
        logger.info("Found \(documents.count) root documents")
        return documents
    }

    /// Get all collections
    /// - Returns: Array of collection documents
    func getCollections() async throws -> [Document] {
        logger.info("Fetching all collections")
        let documents: [Document] = try await api.get("/documents/collections")
        logger.info("Found \(documents.count) collections")
        return documents
    }

    // MARK: - Update

    /// Update document metadata
    /// - Parameters:
    ///   - id: Document ID
    ///   - updates: Updates to apply
    /// - Returns: Updated document
    func updateDocument(_ id: String, updates: DocumentUpdate) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Updating document: \(id)")

        let document: Document = try await api.put("/documents/\(id)", body: updates)
        logger.info("Updated document: \(document.id)")
        return document
    }

    /// Move document to a different parent
    /// - Parameters:
    ///   - id: Document ID to move
    ///   - newParentId: New parent ID (nil for root)
    /// - Returns: Updated document
    func moveDocument(_ id: String, to newParentId: String?) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Moving document \(id) to parent: \(newParentId ?? "root")")

        let request = MoveDocumentRequest(parentId: newParentId)
        let document: Document = try await api.put("/documents/\(id)/move", body: request)
        logger.info("Moved document: \(document.id)")
        return document
    }

    /// Reorder documents within their parent
    /// - Parameter ids: Ordered array of document IDs
    func reorderDocuments(_ ids: [String]) async throws {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Reordering \(ids.count) documents")

        let request = ReorderDocumentsRequest(documentIds: ids)
        let _: EmptyResponse = try await api.post("/documents/reorder", body: request)
        logger.info("Documents reordered")
    }

    // MARK: - Delete

    /// Delete a document
    /// - Parameter id: Document ID to delete
    func deleteDocument(_ id: String) async throws {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Deleting document: \(id)")
        try await api.delete("/documents/\(id)")
        logger.info("Deleted document: \(id)")
    }

    // MARK: - Error Handling

    /// Clear last error
    func clearError() {
        lastError = nil
    }
}

// MARK: - Supporting Types

/// Request body for creating a document
struct CreateDocumentRequest: Codable {
    let name: String
    let parentId: String?
    let docType: String
    let metadata: [String: String]?

    enum CodingKeys: String, CodingKey {
        case name
        case parentId = "parent_id"
        case docType = "doc_type"
        case metadata
    }

    init(name: String, parentId: String?, docType: String, metadata: [String: String]? = nil) {
        self.name = name
        self.parentId = parentId
        self.docType = docType
        self.metadata = metadata
    }
}

/// Request body for updating a document
struct DocumentUpdate: Codable {
    let name: String?
    let metadata: [String: String]?

    init(name: String? = nil, metadata: [String: String]? = nil) {
        self.name = name
        self.metadata = metadata
    }
}

/// Request body for moving a document
struct MoveDocumentRequest: Codable {
    let parentId: String?

    enum CodingKeys: String, CodingKey {
        case parentId = "parent_id"
    }
}

/// Request body for reordering documents
struct ReorderDocumentsRequest: Codable {
    let documentIds: [String]

    enum CodingKeys: String, CodingKey {
        case documentIds = "document_ids"
    }
}

/// Empty response for endpoints that don't return data
struct EmptyResponse: Codable {}
