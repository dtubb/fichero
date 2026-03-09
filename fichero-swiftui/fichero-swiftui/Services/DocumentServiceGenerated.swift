import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "DocumentService")

/// DocumentService using the generated OpenAPI client.
/// Handles document CRUD operations via the Python backend documents API.
@MainActor
class DocumentServiceGenerated: ObservableObject {
    // MARK: - Published State

    @Published var isProcessing: Bool = false
    @Published var lastError: Error?

    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
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

        // Build optional fields using additionalProperties
        var optionalData: [String: any Sendable] = [:]
        if let parentId = parentId { optionalData["parent_id"] = parentId }

        let container = try OpenAPIObjectContainer(unvalidatedValue: optionalData)
        let request = Components.Schemas.DocumentCreate(
            name: name,
            docType: .folder,
            additionalProperties: container
        )

        let response = try await client.api.createDocumentApiDocumentsPost(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .created(let created):
            let doc = try created.body.json
            logger.info("Created collection: \(doc.id ?? "unknown")")
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
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
        docType: DocType = .file,
        metadata: [String: String]? = nil
    ) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Creating document: \(name)")

        // Build metadata and optional fields
        var optionalData: [String: any Sendable] = [:]
        if let parentId = parentId { optionalData["parent_id"] = parentId }
        if let metadata = metadata { optionalData["metadata"] = metadata }

        let container = try OpenAPIObjectContainer(unvalidatedValue: optionalData)
        let request = Components.Schemas.DocumentCreate(
            name: name,
            docType: convertToGeneratedDocType(docType),
            additionalProperties: container
        )

        let response = try await client.api.createDocumentApiDocumentsPost(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .created(let created):
            let doc = try created.body.json
            logger.info("Created document: \(doc.id ?? "unknown")")
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    // MARK: - Read

    /// Get a single document by ID
    /// - Parameter id: Document ID
    /// - Returns: Document
    func getDocument(_ id: String) async throws -> Document {
        logger.info("Fetching document: \(id)")

        let response = try await client.api.getDocumentApiDocumentsDocIdGet(.init(
            path: .init(docId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let ok):
            let doc = try ok.body.json
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get children of a document/collection
    /// - Parameter parentId: Parent document ID
    /// - Returns: Array of child documents
    func getChildren(_ parentId: String) async throws -> [Document] {
        logger.info("Fetching children of: \(parentId)")

        let response = try await client.api.getChildrenApiDocumentsDocIdChildrenGet(.init(
            path: .init(docId: parentId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) children")
            return try docs.map { try convertToDocument($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get ancestors of a document (for breadcrumb navigation)
    /// - Parameter id: Document ID
    /// - Returns: Array of ancestor documents (root to parent)
    func getAncestors(_ id: String) async throws -> [Document] {
        logger.info("Fetching ancestors of: \(id)")

        let response = try await client.api.getAncestorsApiDocumentsDocIdAncestorsGet(.init(
            path: .init(docId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) ancestors")
            return try docs.map { try convertToDocument($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get root-level documents
    /// - Returns: Array of root documents
    func getRoots() async throws -> [Document] {
        logger.info("Fetching root documents")

        let response = try await client.api.listRootsApiDocumentsRootsGet(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) root documents")
            return try docs.map { try convertToDocument($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get all collections
    /// - Returns: Array of collection documents
    func getCollections() async throws -> [Document] {
        logger.info("Fetching all collections")

        let response = try await client.api.listCollectionsApiDocumentsCollectionsGet(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) collections")
            return try docs.map { try convertToDocument($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    // MARK: - Update

    /// Update document metadata
    /// - Parameters:
    ///   - id: Document ID
    ///   - name: Optional new name
    ///   - metadata: Optional new metadata
    ///   - pageContent: Optional extracted content text
    /// - Returns: Updated document
    func updateDocument(
        _ id: String,
        name: String? = nil,
        metadata: [String: String]? = nil,
        pageContent: String? = nil
    ) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Updating document: \(id)")

        // Build all fields using additionalProperties
        var data: [String: any Sendable] = [:]
        if let name = name { data["name"] = name }
        if let metadata = metadata { data["metadata"] = metadata }
        if let pageContent = pageContent { data["page_content"] = pageContent }

        let container = try OpenAPIObjectContainer(unvalidatedValue: data)
        let request = Components.Schemas.DocumentUpdate(additionalProperties: container)

        let response = try await client.api.updateDocumentApiDocumentsDocIdPut(.init(
            path: .init(docId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .ok(let ok):
            let doc = try ok.body.json
            logger.info("Updated document: \(doc.id ?? id)")
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
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

        // Use query parameter instead of request body
        let response = try await client.api.moveDocumentApiDocumentsDocIdMovePut(
            path: .init(docId: id),
            query: .init(parentId: newParentId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            let doc = try ok.body.json
            logger.info("Moved document: \(doc.id ?? id)")
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try error.body.json
            throw DocumentServiceError.serverError(detail.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Reorder documents within their parent
    /// - Parameter ids: Ordered array of document IDs
    func reorderDocuments(_ ids: [String]) async throws {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Reordering \(ids.count) documents")

        let response = try await client.api.reorderDocumentsApiDocumentsReorderPost(.init(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(ids)
        ))

        switch response {
        case .ok:
            logger.info("Documents reordered")
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    // MARK: - Delete

    /// Delete a document
    /// - Parameter id: Document ID to delete
    func deleteDocument(_ id: String) async throws {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Deleting document: \(id)")

        let response = try await client.api.deleteDocumentApiDocumentsDocIdDelete(.init(
            path: .init(docId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        ))

        switch response {
        case .noContent:
            logger.info("Deleted document: \(id)")
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    // MARK: - Error Handling

    /// Clear last error
    func clearError() {
        lastError = nil
    }

    // MARK: - Type Conversion

    /// Convert generated Document to local Document
    private func convertToDocument(_ doc: Components.Schemas.Document) throws -> Document {
        // Extract optional fields from additionalProperties
        let extras = doc.additionalProperties.value
        let parentId = extras["parent_id"] as? String
        let fileType = extras["file_type"] as? String
        let path = extras["path"] as? String
        let sequence = extras["sequence"] as? Int
        let bbox = extras["bbox"] as? [Int]
        let pageContent = extras["page_content"] as? String

        return Document(
            id: doc.id ?? UUID().uuidString,
            parentId: parentId,
            docType: convertFromGeneratedDocType(doc.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: doc.name,
            path: path,
            sequence: sequence,
            bbox: bbox,  // Already [Int]? from additionalProperties
            status: convertFromGeneratedStatus(doc.status),
            metadata: convertMetadata(doc.metadata),
            pageContent: pageContent,
            createdAt: doc.createdAt ?? Date(),
            updatedAt: doc.updatedAt ?? Date(),
            expectedThumbnailPath: doc.expectedThumbnailPath,
            expectedDisplayPath: doc.expectedDisplayPath
        )
    }

    /// Convert local DocType to generated DocType
    private func convertToGeneratedDocType(_ docType: DocType) -> Components.Schemas.DocType {
        switch docType {
        case .folder: return .folder
        case .group: return .group
        case .file: return .file
        case .page: return .page
        case .chunk: return .chunk
        }
    }

    /// Convert generated DocType to local DocType
    private func convertFromGeneratedDocType(_ docType: Components.Schemas.DocType?) -> DocType {
        guard let docType = docType else { return .file }
        switch docType {
        case .folder: return .folder
        case .group: return .group
        case .file: return .file
        case .page: return .page
        case .chunk: return .chunk
        }
    }

    /// Convert generated FileType to local FileType
    private func convertFromGeneratedFileType(_ fileType: Components.Schemas.FileType?) -> FileType? {
        guard let fileType = fileType else { return nil }
        switch fileType {
        case .image: return .image
        case .pdf: return .pdf
        case .text: return .text
        case .word: return .word
        case .audio: return .audio
        case .video: return .video
        case .epub: return .epub
        case .other: return .other
        }
    }

    /// Convert generated Status to local Status
    private func convertFromGeneratedStatus(_ status: Components.Schemas.Status?) -> Status {
        guard let status = status else { return .pending }
        switch status {
        case .pending: return .pending
        case .processing: return .processing
        case .completed: return .completed
        case .failed: return .failed
        }
    }

    /// Convert bbox from OpenAPIArrayContainer to [Int]
    private func convertBbox(_ bbox: OpenAPIRuntime.OpenAPIArrayContainer?) -> [Int]? {
        guard let bbox = bbox else { return nil }
        // Extract array values - bbox should be an array of integers
        return bbox.value.compactMap { item -> Int? in
            if let intValue = item as? Int {
                return intValue
            }
            if let doubleValue = item as? Double {
                return Int(doubleValue)
            }
            return nil
        }
    }

    /// Convert metadata from generated type to local type
    private func convertMetadata(_ metadata: Components.Schemas.Document.MetadataPayload?) -> [String: AnyCodable] {
        guard let metadata = metadata else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in metadata.additionalProperties.value {
            result[key] = AnyCodable(value ?? "")
        }
        return result
    }
}

// MARK: - Error Types

enum DocumentServiceError: Error, LocalizedError {
    case unexpectedResponse
    case notFound(String)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .notFound(let id):
            return "Document not found: \(id)"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}
