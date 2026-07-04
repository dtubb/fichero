import FicheroAPIClient
import Foundation
import OSLog

/// Empty body for the workspace PATCH — only flips `is_workspace` true,
/// leaving curated_items untouched (#1617).
private struct EmptyWorkspacePatch: Encodable {}

/// Minimal decode of the workspace PATCH response (we only need it to type the
/// call; the refreshed list comes from loadWorkspaces).
private struct WorkspaceMarkResponse: Decodable {
    let documentId: String
    enum CodingKeys: String, CodingKey { case documentId = "document_id" }
}

// MARK: - CRUD Operations

extension DocumentStore {

    /// Create a new collection (deprecated - use createFolder instead).
    func createCollection(name: String) async throws -> Document {
        try await createFolder(name: name, parentId: nil)
    }

    /// Create a new folder.
    func createFolder(name: String, parentId: String? = nil) async throws -> Document {
        // Generated create_document op via the typed service (#3030); createCollection
        // posts docType .folder, matching the old hand-rolled DocumentCreateRequest.
        let folder = try await documentService.createCollection(name: name, parentId: parentId)

        // Reload collections to show the newly created folder
        // This handles both root-level folders and nested folders
        await loadCollections()
        publish(.collectionsUpdated(collections))

        return folder
    }

    /// Load all workspace documents (is_workspace == true) for the Workspaces
    /// section (#1617).
    func loadWorkspaces() async {
        do {
            workspaces = try await documentService.getWorkspaces()
        } catch {
            logger.error("Failed to load workspaces: \(error.localizedDescription)")
        }
    }

    /// Create a new workspace: make a folder, then flag it `is_workspace` via
    /// the workspace PATCH. An empty body only sets the flag — curated_items
    /// stay empty until the user adds aliases (#1617).
    @discardableResult
    func createWorkspace(name: String) async throws -> Document {
        let folder = try await createFolder(name: name)
        let _: WorkspaceMarkResponse = try await api.patch(
            "/documents/\(folder.id)/workspace", body: EmptyWorkspacePatch()
        )
        await loadWorkspaces()
        return folder
    }

    /// Delete a document.
    /// The backend handles cascade deletion of all descendants.
    ///
    /// Optimistic update (#705): remove from local state first so the row
    /// disappears immediately, then call the backend. On failure, reload
    /// from the backend to restore truth. Without this, the row lingered
    /// visibly while awaiting the HTTP round-trip.
    func deleteDocument(_ document: Document) async throws {
        let snapshot = collections
        let previousSelection = selectedCollection

        let descendantIds = collectDescendantIds(of: document.id, in: snapshot)
        let idsToRemove = descendantIds.union([document.id])
        collections = collections.filter { !idsToRemove.contains($0.id) }
        if selectedCollection.map({ idsToRemove.contains($0.id) }) == true {
            selectedCollection = nil
        }
        publish(.documentDeleted(document))

        do {
            try await documentService.deleteDocument(document.id)
        } catch {
            collections = snapshot
            selectedCollection = previousSelection
            publish(.documentsUpdated(collections))
            throw error
        }

        await loadCollections()

        if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
            await selectCollection(first)
        }
    }

    /// Returns the ID of every descendant of `rootId` in the given collection list.
    private func collectDescendantIds(of rootId: String, in list: [Document]) -> Set<String> {
        var result: Set<String> = []
        var frontier: [String] = [rootId]
        while let current = frontier.popLast() {
            for doc in list where doc.parentId == current {
                if result.insert(doc.id).inserted {
                    frontier.append(doc.id)
                }
            }
        }
        return result
    }

    /// Delete document by ID (for non-document items like searches, chats, workflows)
    func deleteDocumentById(_ id: String) async throws {
        try await documentService.deleteDocument(id)
        // Refresh from backend
        await loadCollections()
    }

    /// Rename a document.
    func renameDocument(_ document: Document, to newName: String) async throws -> Document {
        let updated = try await documentService.updateDocument(document.id, name: newName)

        // Update local state
        updateLocal(updated)

        // Publish change
        publish(.documentsUpdated(collections))

        return updated
    }

    /// Rename document by ID (for non-document items like searches, chats, workflows)
    func renameDocumentById(_ id: String, to newName: String) async throws -> Document {
        let updated = try await documentService.updateDocument(id, name: newName)
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

            // swiftlint:disable:next nesting
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

    // Import a file into a specific location.
    // swiftlint:disable:next function_body_length cyclomatic_complexity
    func importFile(at url: URL, parentId: String? = nil) async throws -> Document {
        // Validate URL exists and is readable
        guard FileManager.default.fileExists(atPath: url.path) else {
            throw DocumentStoreError.fileNotFound(url.path)
        }

        guard FileManager.default.isReadableFile(atPath: url.path) else {
            throw DocumentStoreError.fileNotReadable(url.path)
        }

        // Sanitize filename to prevent header injection
        let filename = url.lastPathComponent
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "")
            .replacingOccurrences(of: "\"", with: "\\\"")

        // Validate filename is not empty after sanitization
        guard !filename.isEmpty else {
            throw DocumentStoreError.invalidFilename
        }

        // Create form data for file upload
        var request = URLRequest(url: EngineConfig.apiBaseURL.appendingPathComponent("documents/import"))
        request.httpMethod = "POST"

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        // Sanitize library path to prevent header injection, then attach
        // auth + library path. Auth is required post-#742 for /api/documents.
        let sanitizedPath = api.currentLibraryPath?
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "")
        if let sanitizedPath {
            logger.info("Importing to library: \(sanitizedPath)")
        } else {
            logger.warning("WARNING: No library path set for import!")
        }
        request.addEngineAuth(libraryPath: sanitizedPath)

        var body = Data()

        // Add parentId if provided
        if let parentId = parentId {
            // Validate parentId format (should be UUID-like)
            guard parentId.count <= 100, !parentId.contains("\r"), !parentId.contains("\n") else {
                throw DocumentStoreError.invalidParentId
            }
            body.append(Data("--\(boundary)\r\n".utf8))
            body.append(Data("Content-Disposition: form-data; name=\"parent_id\"\r\n\r\n".utf8))
            body.append(Data("\(parentId)\r\n".utf8))
        }

        // Add file - backend determines MIME type from file content
        let fileData = try Data(contentsOf: url)

        body.append(Data("--\(boundary)\r\n".utf8))
        body.append(Data("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".utf8))
        body.append(Data("Content-Type: application/octet-stream\r\n\r\n".utf8))
        body.append(fileData)
        body.append(Data("\r\n".utf8))

        // End boundary
        body.append(Data("--\(boundary)--\r\n".utf8))

        request.httpBody = body

        let session = RemoteCertificatePinning.configuredSession()
        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw DocumentStoreError.invalidResponse
        }

        // Handle specific error codes
        switch httpResponse.statusCode {
        case 200:
            break // Success
        case 400:
            throw DocumentStoreError.badRequest
        case 401, 403:
            throw DocumentStoreError.unauthorized
        case 404:
            throw DocumentStoreError.notFound
        case 413:
            throw DocumentStoreError.fileTooLarge
        case 500...599:
            throw DocumentStoreError.serverError(httpResponse.statusCode)
        default:
            throw URLError(.badServerResponse)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let document = try decoder.decode(Document.self, from: data)

        // Reload collections to show the newly imported file
        // This handles both root-level imports and imports into nested folders
        await loadCollections()
        publish(.collectionsUpdated(collections))

        return document
    }

    /// Move a document to a new parent.
    func moveDocument(_ documentId: String, toParent parentId: String?) async throws -> Document {
        logger.info("Moving \(documentId) to parent: \(parentId ?? "nil (root)")")

        // Generated move_document op via the typed service (#3030).
        let updated = try await documentService.moveDocument(documentId, to: parentId)

        logger.info("Response: \(updated.name), parent_id: \(updated.parentId ?? "nil")")

        // Update in-place (updates the document in collections, cache, etc.)
        updateLocal(updated)

        logger.info("Moved document: \(updated.name) to parent: \(parentId ?? "root")")

        // Publish change - this triggers PassthroughSubject for any subscribers
        publish(.documentsUpdated(collections))

        return updated
    }

    /// Persist a new sort order for a set of sibling documents.
    ///
    /// The backend's `POST /documents/reorder` route accepts an ordered
    /// list of document IDs and assigns `sort_order = index` to each.
    /// The Swift-side `sortOrder` field (#572) then drives
    /// `SidebarItemBuilder.childOrder` on the next rebuild so the
    /// sidebar displays the new order.
    ///
    /// Used by the between-row drop handler (#580 spacer-row approach)
    /// so drops onto the blue insertion line reorder siblings within
    /// their parent folder.
    func reorderDocuments(_ idsInOrder: [String]) async throws {
        logger.info("Reordering \(idsInOrder.count) documents")
        try await documentService.reorderDocuments(idsInOrder)
        await refresh()
    }

    /// Optimistic, observer-driven reorder for a set of sibling documents.
    ///
    /// Mutates `sortOrder` in every local cache in-place so the sidebar's
    /// `SidebarItemBuilder.childOrder` comparator produces the new order
    /// on the very next render pass. This satisfies SwiftUI's `.onMove`
    /// contract — which expects the data source to reflect the move
    /// synchronously — without requiring a `@State` shadow in the view.
    ///
    /// The backend persist fires asynchronously afterwards. On success,
    /// the trailing `refresh()` in `reorderDocuments` pulls server state,
    /// which will match what we just wrote locally — no visual change.
    /// On failure, `refresh()` in the catch block overwrites our
    /// optimistic write with the server's canonical order and the
    /// sidebar snaps back.
    ///
    /// Used by #607 sidebar folder reorder via native `.onMove` insertion
    /// lines — see SidebarItemRow.childrenList.
    func reorderChildrenOptimistically(orderedIds: [String]) {
        for (index, id) in orderedIds.enumerated() {
            if let idx = collections.firstIndex(where: { $0.id == id }) {
                collections[idx].sortOrder = index
            }
            if let idx = currentDocuments.firstIndex(where: { $0.id == id }) {
                currentDocuments[idx].sortOrder = index
            }
            for parentId in childrenCache.keys {
                if let idx = childrenCache[parentId]?.firstIndex(where: { $0.id == id }) {
                    childrenCache[parentId]?[idx].sortOrder = index
                }
            }
        }
        Task {
            do {
                try await reorderDocuments(orderedIds)
            } catch {
                logger.error("reorderDocuments failed — reverting: \(error.localizedDescription)")
                await refresh()
            }
        }
    }
}
