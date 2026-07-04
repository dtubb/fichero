import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentService")

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

        let request = Components.Schemas.DocumentCreate(
            name: name,
            parentId: parentId,
            docType: .folder
        )

        let response = try await client.api.createDocumentApiDocumentsPost(.init(
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

        // metadata is now an explicit typed property (schema no longer accepts
        // free-form additionalProperties — OpenAPI two-stack sync, #3002).
        let metadataPayload = try metadata.map {
            Components.Schemas.DocumentCreate.MetadataPayload(
                additionalProperties: try OpenAPIObjectContainer(
                    unvalidatedValue: $0.mapValues { $0 as (any Sendable)? }
                )
            )
        }
        let request = Components.Schemas.DocumentCreate(
            name: name,
            parentId: parentId,
            docType: convertToGeneratedDocType(docType),
            metadata: metadataPayload
        )

        let response = try await client.api.createDocumentApiDocumentsPost(.init(
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

    /// Fetch the geo points (lat / lon / place name) the engine derived for a
    /// document (#3055 / #2755 remnant). Read-only — routed through the generated,
    /// tokened client with typed errors (no hand-rolled URLSession). Returns []
    /// when the document has no geo data.
    /// - Parameter id: Document ID
    /// - Returns: The document's geo points
    func documentGeoPoints(_ id: String) async throws -> [Components.Schemas.DocGeoPoint] {
        logger.info("Fetching geo points for document: \(id)")

        let response = try await client.api.listDocumentGeoApiDocumentsDocIdGeoGet(.init(
            path: .init(docId: id),
        ))

        switch response {
        case .ok(let ok):
            return try ok.body.json.points
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Export the library (or a subtree) as an Eleventy (11ty) static site
    /// (#3055 / #2755 remnant). Routed through the generated, tokened client with
    /// typed errors (no hand-rolled URLSession).
    /// - Returns: The export result (output path + document/collection counts + files).
    func exportEleventySite(
        outputPath: String,
        targetId: String? = nil,
        recursive: Bool = true,
        overwrite: Bool = false,
        siteTitle: String? = nil
    ) async throws -> Components.Schemas.EleventySiteExportResponse {
        logger.info("Exporting Eleventy static site to: \(outputPath)")

        let request = Components.Schemas.EleventySiteExportRequest(
            outputPath: outputPath,
            targetId: targetId,
            recursive: recursive,
            overwrite: overwrite,
            siteTitle: siteTitle
        )
        let response = try await client.api.exportEleventySiteRouteApiExportEleventySitePost(
            .init(body: .json(request))
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
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
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) children")
            return try docs.items.map { try convertToDocument($0) }
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
        ))

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) ancestors")
            return try docs.items.map { try convertToDocument($0) }
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

        let response = try await client.api.listRootsApiDocumentsRootsGet(.init())

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) root documents")
            return try docs.items.map { try convertToDocument($0) }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// List documents (flat) via the generated `list_documents` op. Pass `limit`
    /// to cap results (e.g. chat scope search); pass nil to load the full tree
    /// (the backend default, used by the sidebar). Throws on non-`.ok` (#3030).
    /// - Parameter limit: Maximum documents to return, or nil for the backend default.
    /// - Returns: Array of documents.
    func listDocuments(limit: Int? = nil) async throws -> [Document] {
        logger.info("Listing documents (limit \(limit.map(String.init) ?? "default"))")

        let response = try await client.api.listDocumentsApiDocumentsGet(
            .init(query: .init(limit: limit))
        )

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.items.count) documents")
            return try docs.items.map { try convertToDocument($0) }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get all collections
    /// - Returns: Array of collection documents
    func getCollections() async throws -> [Document] {
        logger.info("Fetching all collections")

        let response = try await client.api.listCollectionsApiDocumentsCollectionsGet(.init())

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.count) collections")
            return try docs.items.map { try convertToDocument($0) }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get all workspace folders from the active library.
    /// - Returns: Array of workspace folder documents
    func getWorkspaces() async throws -> [Document] {
        logger.info("Fetching all workspaces")

        let response = try await client.api.listWorkspacesApiDocumentsWorkspacesGet()

        switch response {
        case .ok(let ok):
            let docs = try ok.body.json
            logger.info("Found \(docs.items.count) workspaces")
            return try docs.items.map { generated in
                var document = try convertToDocument(generated)
                document.isWorkspace = generated.isWorkspace ?? true
                return document
            }
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Patch workspace curated items for a folder in the active library.
    /// - Parameters:
    ///   - folderId: Workspace folder document ID
    ///   - itemsToAdd: Curated items to add or replace
    /// - Returns: Updated workspace items response
    func patchWorkspaceItems(
        folderId: String,
        itemsToAdd: [Components.Schemas.WorkspaceCuratedItem]
    ) async throws -> Components.Schemas.WorkspaceItemsResponse {
        logger.info("Patching workspace items for: \(folderId)")

        let response = try await client.api.patchWorkspaceItemsApiDocumentsDocIdWorkspacePatch(
            path: .init(docId: folderId),
            body: .json(.init(add: itemsToAdd))
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get resolved curated items for a workspace folder in the active library.
    /// - Parameter folderId: Workspace folder document ID
    /// - Returns: Workspace items response
    func getWorkspaceItems(folderId: String) async throws -> Components.Schemas.WorkspaceItemsResponse {
        logger.info("Fetching workspace items for: \(folderId)")

        let response = try await client.api.getWorkspaceItemsApiDocumentsDocIdWorkspaceItemsGet(
            path: .init(docId: folderId),
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
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
    ///   - metadataPayload: Optional metadata with mixed value types
    ///   - pageContent: Optional extracted content text
    /// - Returns: Updated document
    func updateDocument(
        _ id: String,
        name: String? = nil,
        metadata: [String: String]? = nil,
        metadataPayload: [String: any Sendable]? = nil,
        pageContent: String? = nil
    ) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }

        logger.info("Updating document: \(id)")

        // Use the generated typed fields on DocumentUpdate instead of jamming
        // everything through additionalProperties. Previously page_content
        // was being sent only via additionalProperties — when both the
        // declared pageContent property and the additionalProperties dict
        // were encoded, the typed nil could clobber the extras-supplied
        // value, so edits to page content round-tripped as 200 OK but never
        // persisted. This is exactly the OpenAPI drift Daniel flagged:
        // use the schema-typed properties, not hand-built dicts.
        var metadataPayloadValue: Components.Schemas.DocumentUpdate.MetadataPayload?
        if let metadataPayload = metadataPayload {
            let container = try OpenAPIObjectContainer(unvalidatedValue: metadataPayload)
            metadataPayloadValue = .init(additionalProperties: container)
        } else if let metadata = metadata {
            let castMetadata: [String: any Sendable] = metadata.reduce(into: [:]) { acc, pair in
                acc[pair.key] = pair.value
            }
            let container = try OpenAPIObjectContainer(unvalidatedValue: castMetadata)
            metadataPayloadValue = .init(additionalProperties: container)
        }

        let request = Components.Schemas.DocumentUpdate(
            name: name,
            pageContent: pageContent,
            metadata: metadataPayloadValue
        )

        let response = try await client.api.updateDocumentApiDocumentsDocIdPut(.init(
            path: .init(docId: id),
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

    /// Toggle exclude-from-processing on a batch of documents.
    /// Uses the generated `/api/documents/batch-exclude` operation, then
    /// re-fetches the affected records through the generated document getter
    /// so callers can refresh local state without raw URL paths.
    func batchExclude(
        documentIds: [String],
        excluded: Bool
    ) async throws -> [Document] {
        isProcessing = true
        defer { isProcessing = false }

        let request = Components.Schemas.DocumentBatchExcludeRequest(
            documentIds: documentIds,
            excluded: excluded,
            reason: nil
        )

        let response = try await client.api.batchExcludeDocumentsApiDocumentsBatchExcludePatch(
            .init(
                body: .json(request)
            )
        )

        switch response {
        case .ok(let ok):
            let result = try ok.body.json
            var documents: [Document] = []
            for id in result.documentIds {
                documents.append(try await getDocument(id))
            }
            return documents
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
        // Every field that's TYPED on the OpenAPI Document schema decodes
        // into the typed property, NOT additionalProperties. Reading them
        // from extras silently returns nil and corrupts the local cache.
        // Verified with the Types.swift audit on 2026-05-03: parent_id,
        // file_type, path, sequence, bbox, page_content,
        // expected_thumbnail_path, expected_display_path are ALL typed.
        // Always read typed-first; fall back to extras for legacy compat
        // (and for any field we add to the schema that lags this list).
        let extras = doc.additionalProperties.value
        let parentId = doc.parentId ?? (extras["parent_id"] as? String)
        // fileType is a typed enum (Components.Schemas.FileType?); take its
        // raw value so the local Document's own FileType enum can decode it.
        let fileType = doc.fileType?.rawValue ?? (extras["file_type"] as? String)
        let path = doc.path ?? (extras["path"] as? String)
        let sequence = doc.sequence ?? (extras["sequence"] as? Int)
        // bbox is OpenAPIArrayContainer — extract its inner [Int] payload.
        let bbox = (doc.bbox?.value as? [Int]) ?? (extras["bbox"] as? [Int])
        let pageContent = doc.pageContent ?? (extras["page_content"] as? String)

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
            excludeFromProcessing: doc.excludeFromProcessing ?? false,
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
        case .docx: return .word  // docx is a Word variant
        case .audio: return .audio
        case .video: return .video
        case .epub: return .epub
        case .spreadsheet: return .spreadsheet
        case .presentation: return .presentation
        case .other: return .other
        }
    }

    /// Convert generated Status to local Status
    private func convertFromGeneratedStatus(_ status: Components.Schemas.Status?) -> Status {
        guard let status = status else { return .pending }
        switch status {
        case .pending: return .pending
        case .processing: return .processing
        case .active: return .processing  // active is an in-progress state
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

private extension Sequence {
    func asyncMap<T>(_ transform: (Element) async throws -> T) async rethrows -> [T] {
        var results: [T] = []
        for element in self {
            let transformed = try await transform(element)
            results.append(transformed)
        }
        return results
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
