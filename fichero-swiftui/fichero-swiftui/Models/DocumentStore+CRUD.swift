import Foundation
import OSLog

// MARK: - CRUD Operations

extension DocumentStore {

    /// Create a new collection (deprecated - use createFolder instead).
    func createCollection(name: String) async throws -> Document {
        try await createFolder(name: name, parentId: nil)
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
    /// The backend handles cascade deletion of all descendants.
    func deleteDocument(_ document: Document) async throws {
        try await api.delete("/documents/\(document.id)")

        // Publish change before refresh
        publish(.documentDeleted(document))

        // Clear selection if this was selected
        if selectedCollection?.id == document.id {
            selectedCollection = nil
        }

        // Refresh from backend - it handles cascade deletes
        await loadCollections()

        // Re-select first collection if needed
        if selectedCollection == nil, let first = collections.first(where: { $0.parentId == nil }) {
            await selectCollection(first)
        }
    }

    /// Delete document by ID (for non-document items like searches, chats, workflows)
    func deleteDocumentById(_ id: String) async throws {
        try await api.delete("/documents/\(id)")
        // Refresh from backend
        await loadCollections()
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
        var request = URLRequest(url: URL(string: "http://127.0.0.1:8765/api/documents/import")!)
        request.httpMethod = "POST"

        let boundary = "Boundary-\(UUID().uuidString)"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        // Add library path header for multi-library support
        if let libraryPath = api.currentLibraryPath {
            // Sanitize library path to prevent header injection
            let sanitizedPath = libraryPath
                .replacingOccurrences(of: "\r", with: "")
                .replacingOccurrences(of: "\n", with: "")
            request.setValue(sanitizedPath, forHTTPHeaderField: "X-Fichero-Library-Path")
            logger.info("Importing to library: \(sanitizedPath)")
        } else {
            logger.warning("WARNING: No library path set for import!")
        }

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

        let (data, response) = try await URLSession.shared.data(for: request)

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
}
