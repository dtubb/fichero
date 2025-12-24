import Foundation

/// Service for document CRUD operations.
///
/// Communicates with the Python backend via APIClient.
/// Uses the Document type from Document.swift.
actor DocumentService {
    private let api = APIClient.shared

    // MARK: - List Operations

    /// List documents with optional filters.
    func listDocuments(
        parentId: String? = nil,
        docType: DocType? = nil,
        fileType: FileType? = nil,
        status: Status? = nil,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [Document] {
        var query: [String: String] = [
            "limit": String(limit),
            "offset": String(offset)
        ]

        if let parentId = parentId {
            query["parent_id"] = parentId
        }
        if let docType = docType {
            query["doc_type"] = docType.rawValue
        }
        if let fileType = fileType {
            query["file_type"] = fileType.rawValue
        }
        if let status = status {
            query["status"] = status.rawValue
        }

        return try await api.get("/documents", query: query)
    }

    /// List all collections (top-level documents).
    func getCollections() async throws -> [Document] {
        try await api.get("/documents/collections")
    }

    /// List root documents (no parent).
    func getRoots() async throws -> [Document] {
        try await api.get("/documents/roots")
    }

    // MARK: - Single Document

    /// Get a single document by ID.
    func getDocument(_ id: String) async throws -> Document {
        try await api.get("/documents/\(id)")
    }

    /// Get children of a document.
    func getChildren(of documentId: String, limit: Int = 100) async throws -> [Document] {
        try await api.get("/documents/\(documentId)/children", query: ["limit": String(limit)])
    }

    /// Get ancestors (parent chain) of a document.
    func getAncestors(of documentId: String) async throws -> [Document] {
        try await api.get("/documents/\(documentId)/ancestors")
    }

    // MARK: - CRUD Operations

    /// Create a new document.
    func createDocument(_ document: DocumentCreateRequest) async throws -> Document {
        try await api.post("/documents", body: document)
    }

    /// Create a new collection.
    func createCollection(name: String) async throws -> Document {
        let doc = DocumentCreateRequest(
            name: name,
            parentId: nil,
            docType: .collection
        )
        return try await createDocument(doc)
    }

    /// Update an existing document.
    func updateDocument(_ id: String, _ update: DocumentUpdateRequest) async throws -> Document {
        try await api.put("/documents/\(id)", body: update)
    }

    /// Delete a document.
    func deleteDocument(_ id: String) async throws {
        try await api.delete("/documents/\(id)")
    }

    // MARK: - Convenience Methods

    /// Get the full hierarchy for a document (ancestors + self + descendants).
    func getHierarchy(for documentId: String) async throws -> DocumentHierarchy {
        async let ancestors = getAncestors(of: documentId)
        async let document = getDocument(documentId)
        async let children = getChildren(of: documentId)

        return try await DocumentHierarchy(
            ancestors: ancestors,
            document: document,
            children: children
        )
    }

    /// Check if the backend is available.
    func checkConnection() async -> Bool {
        do {
            _ = try await api.healthCheck()
            return true
        } catch {
            return false
        }
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
