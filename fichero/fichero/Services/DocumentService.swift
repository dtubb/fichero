import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "DocumentService")

/// DocumentService using the generated OpenAPI client.
/// Handles document CRUD operations via the Python backend documents API.
@MainActor
@Observable
class DocumentService {
    // MARK: - Published State

    var isProcessing: Bool = false
    var lastError: Error?

    // Internal, not private: `DocumentService+Roots.swift` is part of this type
    // and a `private` member is invisible across files.
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }
}

// MARK: - Create & read

// Same-file extension to keep the class body within SwiftLint's type_body_length
// budget; private members stay file-scoped and accessible (#4016).
extension DocumentService {
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
        case .ok(let okResponse):
            let doc = try okResponse.body.json
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Fetch a document's parent via the generated `get_document_parent` op.
    /// Throws on non-`.ok` (#3030). Used by KG/source navigation to bubble a
    /// page child up to its containing file.
    func getParent(_ id: String) async throws -> Document {
        logger.info("Fetching parent of: \(id)")

        let response = try await client.api.getDocumentParentApiDocumentsDocIdParentGet(.init(
            path: .init(docId: id)
        ))

        switch response {
        case .ok(let okResponse):
            return try convertToDocument(try okResponse.body.json)
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
        case .ok(let okResponse):
            return try okResponse.body.json.points
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Hierarchical source outline for a document (#3440). Flat depth-ordered
    /// rows (id/depth/kind/label/count) the inspector folds into a native
    /// OutlineView. Typed OpenAPI op — no hand-rolled URL. Source anchors for
    /// reveal are added by #3441.
    func documentOutline(_ id: String) async throws -> [Components.Schemas.DocumentOutlineRow] {
        logger.info("Fetching outline for document: \(id)")

        let response = try await client.api.documentOutlineApiDocumentsDocumentIdOutlineGet(.init(
            path: .init(documentId: id)
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.rows
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
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Get children of a document/collection
    ///
    /// - Parameters:
    ///   - parentId: Parent document ID
    ///   - sort: Server-side ordering, or nil for the stored sibling order.
    ///     Only fields the ENGINE can order pass a value here — see
    ///     `LibrarySortField.ordersOnServer` (#3322). Passing nil is the
    ///     pre-existing behaviour, not a missing argument.
    /// - Returns: Array of child documents, in the order the server returned
    ///   them. Callers must not re-sort a server-ordered result.
    func getChildren(_ parentId: String, sort: ListingSort? = nil) async throws -> [Document] {
        logger.info("Fetching children of: \(parentId) sort: \(sort?.field ?? "default")")

        let response = try await client.api.getChildrenApiDocumentsDocIdChildrenGet(.init(
            path: .init(docId: parentId),
            query: .init(sortBy: sort?.field, sortDirection: sort?.direction)
        ))

        switch response {
        case .ok(let okResponse):
            let docs = try okResponse.body.json
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
        case .ok(let okResponse):
            let docs = try okResponse.body.json
            logger.info("Found \(docs.count) ancestors")
            return try docs.items.map { try convertToDocument($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
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
        case .ok(let okResponse):
            let docs = try okResponse.body.json
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
        case .ok(let okResponse):
            let docs = try okResponse.body.json
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
        case .ok(let okResponse):
            let docs = try okResponse.body.json
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

    /// Restore a soft-deleted document subtree from Trash.
    func restoreDocument(_ id: String) async throws {
        logger.info("Restoring document: \(id)")

        let response = try await client.api.restoreDocumentApiDocumentsDocIdRestorePost(.init(
            path: .init(docId: id)
        ))

        switch response {
        case .noContent:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
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
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Mark a folder as a workspace via an empty `workspace` PATCH (#3030). An
    /// empty body flips `is_workspace` and leaves curated items untouched — the
    /// generated request omits nil fields, so this serializes to `{}`, matching
    /// the old hand-rolled EmptyWorkspacePatch. Throws on non-`.ok`.
    func markAsWorkspace(folderId: String) async throws {
        logger.info("Marking folder as workspace: \(folderId)")

        let response = try await client.api.patchWorkspaceItemsApiDocumentsDocIdWorkspacePatch(
            path: .init(docId: folderId),
            body: .json(.init())
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Recursively ingest a folder via the generated `ingest_folder` op (#3030).
    /// Returns the async task descriptor; throws on non-`.ok`.
    ///
    /// `extractText`/`autoEmbed` are omitted when nil so the engine's
    /// documented defaults decide (#3276). This path hard-coded them ON while
    /// `ImportService` hard-coded them OFF, for the same two fields of the same
    /// endpoint: two app-side copies of a decision that belongs to the engine,
    /// disagreeing with each other.
    func ingestFolder(
        path: String,
        parentId: String? = nil,
        copyMode: Bool = true,
        recursive: Bool = true,
        extractText: Bool? = nil,
        autoEmbed: Bool? = nil
    ) async throws -> Components.Schemas.IngestTaskResponse {
        logger.info("Ingesting folder: \(path)")

        let request = Components.Schemas.IngestFolderRequest(
            path: path,
            parentId: parentId,
            copyMode: copyMode,
            recursive: recursive,
            extractText: extractText,
            autoEmbed: autoEmbed
        )
        let response = try await client.api.ingestFolderApiIngestFolderPost(.init(body: .json(request)))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
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
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    // MARK: - Update

}

// MARK: - Mutations & workspace ops

// Same-file extension to keep the class body within SwiftLint's type_body_length
// budget; private members stay file-scoped and accessible (#4016).
extension DocumentService {
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
        // persisted. This is exactly the OpenAPI drift the maintainer flagged:
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
        case .ok(let okResponse):
            let doc = try okResponse.body.json
            logger.info("Updated document: \(doc.id ?? id)")
            return try convertToDocument(doc)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            // #4286: never surface the generic "unexpected response" for a
            // SAVE — name the operation and the status so a 409 (concurrent
            // write conflict) or 500 reads as a retryable failure, not a
            // mystery. The caller keeps the dirty buffer and retries (#4285).
            throw DocumentServiceError.httpStatus(operation: "save", code: statusCode)
        }
    }

    /// Combine documents into ONE reversible group/stack node (#3535) — the
    /// inverse of the reversible split (#1595). The children reference the new
    /// group as parent; each stays independently workable. POST
    /// /api/documents/groups
    func createGroup(name: String, childIds: [String]) async throws -> Document {
        isProcessing = true
        defer { isProcessing = false }
        logger.info("Grouping \(childIds.count) documents into a stack")
        let request = Components.Schemas.DocumentGroupRequest(name: name, childIds: childIds)
        let response = try await client.api.createDocumentGroupApiDocumentsGroupsPost(
            body: .json(request)
        )
        switch response {
        case .ok(let okResponse):
            return try convertToDocument(try okResponse.body.json)
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }

    /// Reverse a group/stack — the engine restores each child to its original
    /// parent and order (#3535). POST /api/documents/groups/{group_id}/ungroup
    func ungroupDocument(groupId: String) async throws {
        isProcessing = true
        defer { isProcessing = false }
        logger.info("Ungrouping stack \(groupId)")
        let response = try await client.api
            .ungroupDocumentApiDocumentsGroupsGroupIdUngroupPost(path: .init(groupId: groupId))
        switch response {
        case .ok:
            return
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
        case .ok(let okResponse):
            let doc = try okResponse.body.json
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
        case .ok(let okResponse):
            let result = try okResponse.body.json
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
}

// MARK: - Type Conversion

// Split into a same-file extension so the primary class body stays within
// SwiftLint's type_body_length budget (#3030 added several ops). It was
// `private` only because every caller lived in this file;
// `DocumentService+Roots.swift` now calls `convertToDocument` too, so these are
// internal — still confined to the app target. The split was always for the
// lint budget, never for encapsulation.
extension DocumentService {
    /// Convert generated Document to local Document
    func convertToDocument(_ doc: Components.Schemas.Document) throws -> Document {
        // A field this converter forgets is a field the whole app does not have.
        //
        // Every key TYPED on the schema decodes into its typed property and
        // NEVER into `additionalProperties` — the generated decoder strips
        // known keys first — so the `?? extras[…]` fallbacks that used to sit
        // on these lines were dead code, not defence. They read as
        // belt-and-braces and hid the neighbours with no read at all: #4515
        // child_count, #4516 prototype_key/node_kind/alias_target_id, #4514
        // attributes, plus sort_order and is_workspace.
        // `DocumentConverterFieldSourceTests` fails if a typed key is read
        // from extras here again.
        //
        // fileType is a typed enum; take its raw value so the local FileType
        // can decode it.
        let fileType = doc.fileType?.rawValue
        let childCount = doc.childCount ?? 0
        // `date_meta`'s ABSENCE is the "never extracted" state, so this stays
        // nil when the server sent nothing. Defaulting it to [:] would read as
        // "extraction ran and found nothing" — a different fact.
        let dateMeta = doc.dateMeta.map { payload in
            payload.additionalProperties.value.mapValues { AnyCodable($0 ?? "") }
        }
        // bbox is OpenAPIArrayContainer — extract its inner [Int] payload.
        let bbox = doc.bbox?.value as? [Int]

        return Document(
            id: doc.id ?? UUID().uuidString,
            parentId: doc.parentId,
            docType: convertFromGeneratedDocType(doc.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: doc.name,
            path: doc.path,
            sequence: doc.sequence,
            bbox: bbox,
            status: convertFromGeneratedStatus(doc.status),
            metadata: convertMetadata(doc.metadata),
            pageContent: doc.pageContent,
            excludeFromProcessing: doc.excludeFromProcessing ?? false,
            isWorkspace: doc.isWorkspace ?? false,
            childCount: childCount,
            dateOriginal: doc.dateOriginal,   // #3322
            dateJdn: doc.dateJdn,
            dateMeta: dateMeta,
            sortOrder: doc.sortOrder ?? 0,
            // #4516: `prototypeKey` is what `isWorkflowNode` reads; dropping
            // it made the workflow icon, the mirror lock badge, the running
            // spinner and mirror selection routing dead code at once. #2591's
            // alias fields died the same way. #4514: `attributes` carries the
            // engine's `read_only`.
            prototypeKey: doc.prototypeKey,
            nodeKind: doc.nodeKind,
            aliasTargetId: doc.aliasTargetId,
            attributes: convertAttributes(doc.attributes),
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

    /// Prototype-scoped node attributes (`read_only`, `scope`, …). Same shape
    /// as `convertMetadata`, distinct generated payload type (#4514).
    private func convertAttributes(
        _ attributes: Components.Schemas.Document.AttributesPayload?
    ) -> [String: AnyCodable] {
        guard let attributes = attributes else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in attributes.additionalProperties.value {
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
    /// #4286: an operation got a status the OpenAPI spec doesn't document.
    /// Carries the operation name and the code so the surfaced message says
    /// WHAT failed and WHY-shaped ("save failed — HTTP 409"), per the #4269
    /// error-surface rules — never the bare "unexpected response" string.
    case httpStatus(operation: String, code: Int)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .notFound(let id):
            return "Document not found: \(id)"
        case .serverError(let message):
            return "Server error: \(message)"
        case .httpStatus(let operation, let code):
            let hint = code == 409
                ? " (another writer got there first — retrying keeps your edit)"
                : ""
            return "The \(operation) failed — the server returned HTTP \(code)\(hint)."
        }
    }
}

// MARK: - Batch library-item column metadata (#3758)

extension DocumentService {
    /// Batch per-item column metadata (#3758) — for each of `itemIds`, the
    /// entity / annotation / note / bbox counts aggregated across that item's
    /// document scope. Read-only, set-based: it powers the library list and
    /// column-browser columns, never mutates. Typed OpenAPI op — no hand-rolled
    /// URL. The backend caps the batch at 200 ids (422 beyond that). Lives on an
    /// extension so the primary service type stays within its body-length limit.
    func libraryItemColumns(
        itemIds: [String],
        includeDescendants: Bool = false
    ) async throws -> [Components.Schemas.LibraryItemColumnsRow] {
        let request = Components.Schemas.LibraryItemColumnsRequest(
            itemIds: itemIds,
            includeDescendants: includeDescendants
        )
        let response = try await client.api.libraryItemColumnsApiLibraryItemsColumnsPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }
}

// MARK: - Related documents (#4120)

extension DocumentService {
    /// Documents related to `id` (#4120): shared knowledge-graph entities
    /// and/or semantic embedding neighbors, ranked best-first by the engine.
    func getRelatedDocuments(_ id: String, limit: Int = 20) async throws
        -> [Components.Schemas.RelatedDocumentsResponse] {
        let response = try await client.api.relatedDocumentsApiDocumentsDocIdRelatedGet(.init(
            path: .init(docId: id),
            query: .init(limit: limit)
        ))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw DocumentServiceError.serverError(detail?.detail?.description ?? "Validation error")
        default:
            throw DocumentServiceError.unexpectedResponse
        }
    }
}
