import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImportServiceGenerated")

/// ImportService using the generated OpenAPI client.
/// Handles file and folder import operations.
/// Note: Folder imports are async - they return a task that must be polled for completion.
@MainActor
@Observable
class ImportServiceGenerated {
    // MARK: - Published State

    var isImporting: Bool = false
    var importProgress: ImportProgress?
    var lastError: ImportError?
    var currentTask: IngestTask?

    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(baseURL: EngineConfig.host, libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Import Files

    /// Import multiple files from URLs
    /// For folders, this starts an async task and polls until completion
    func importFiles(
        _ urls: [URL],
        mode: IngestMode = .link,
        parentId: String? = nil,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [Document] {
        isImporting = true
        defer { isImporting = false }

        var imported: [Document] = []
        var errors: [ImportError] = []

        logger.info("Starting import of \(urls.count) files")

        for (index, url) in urls.enumerated() {
            do {
                // Update progress
                onProgress?(index + 1, urls.count)
                importProgress = ImportProgress(
                    current: index + 1,
                    total: urls.count,
                    currentFile: url.lastPathComponent
                )

                // Check if URL is a directory
                var isDirectory: ObjCBool = false
                let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)

                if exists && isDirectory.boolValue {
                    // Persist sandbox permission when folder is added.
                    FolderAccessManager.shared.saveBookmarkIfDirectory(url)

                    // Import folder using async task pattern
                    logger.info("Detected folder: \(url.lastPathComponent), using async folder import")
                    let documentIds = try await importFolderAndWait(
                        url,
                        mode: mode,
                        parentId: parentId,
                        recursive: true,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    )
                    logger.info("Successfully imported folder with \(documentIds.count) documents: \(url.lastPathComponent)")
                    // Note: We only have document IDs, not full documents
                    // The caller can fetch full documents if needed
                } else {
                    // Import single file (synchronous)
                    let doc = try await importFile(
                        url,
                        mode: mode,
                        parentId: parentId,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    )
                    imported.append(doc)
                    logger.info("Successfully imported: \(url.lastPathComponent)")
                }

            } catch {
                logger.error("Failed to import \(url.lastPathComponent): \(error.localizedDescription)")
                errors.append(ImportError(url: url, error: error))
            }
        }

        importProgress = nil
        currentTask = nil

        if !errors.isEmpty {
            lastError = errors.first
            logger.warning("Import completed with \(errors.count) errors")
            if imported.isEmpty {
                throw ImportError(
                    url: urls.first ?? URL(fileURLWithPath: ""),
                    error: NSError(
                        domain: "ImportService",
                        code: -1,
                        userInfo: [NSLocalizedDescriptionKey: "All imports failed"]
                    )
                )
            }
        }

        logger.info("Import completed: \(imported.count) successful, \(errors.count) failed")
        return imported
    }

    /// Import a single file (synchronous - returns document immediately)
    private func importFile(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool,
        autoEmbed: Bool
    ) async throws -> Document {
        // Enable security-scoped access in sandboxed builds; non-sandboxed builds
        // return false but the URL remains accessible via normal file I/O.
        let didStartAccess = url.startAccessingSecurityScopedResource()
        defer {
            if didStartAccess { url.stopAccessingSecurityScopedResource() }
        }

        let doc: Components.Schemas.Document
        if mode == .copy {
            let fileData = try Data(contentsOf: url)
            let response = try await client.api.importFileApiDocumentsImportPost(
                Self.makeImportUploadInput(
                    data: fileData,
                    filename: url.lastPathComponent,
                    parentId: parentId
                )
            )
            switch response {
            case .ok(let okResponse):
                doc = try okResponse.body.json
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                throw ImportServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
            case .undocumented(let statusCode, _):
                throw ImportServiceGeneratedError.unexpectedResponse(statusCode)
            }
        } else {
            let response = try await client.api.ingestFileApiIngestFilePost(
                body: .json(.init(
                    path: url.path,
                    parentId: parentId,
                    copyMode: mode == .copy,
                    extractText: extractText,
                    autoEmbed: autoEmbed
                ))
            )
            switch response {
            case .ok(let okResponse):
                doc = try okResponse.body.json
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                throw ImportServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
            case .undocumented(let statusCode, _):
                throw ImportServiceGeneratedError.unexpectedResponse(statusCode)
            }
        }
        return try convertToDocument(doc)
    }

    // MARK: - Async Folder Import

    /// Start a folder import task (returns immediately with task ID)
    func startFolderImport(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false
    ) async throws -> IngestTask {
        logger.info("Starting async folder import: \(url.lastPathComponent)")

        // Persist sandbox permission when folder import starts directly.
        FolderAccessManager.shared.saveBookmarkIfDirectory(url)

        // Enable security-scoped access in sandboxed builds; non-sandboxed builds
        // return false but the URL remains accessible via normal file I/O.
        let didStartAccess = url.startAccessingSecurityScopedResource()
        defer {
            if didStartAccess { url.stopAccessingSecurityScopedResource() }
        }

        let response = try await client.api.ingestFolderApiIngestFolderPost(
            body: .json(.init(
                path: url.path,
                parentId: parentId,
                copyMode: mode == .copy,
                recursive: recursive,
                extractText: extractText,
                autoEmbed: autoEmbed
            ))
        )

        switch response {
        case .ok(let okResponse):
            let taskResponse = try okResponse.body.json
            let task = IngestTask(
                taskId: taskResponse.taskId,
                status: taskResponse.status,
                path: taskResponse.path
            )
            currentTask = task
            logger.info("Folder import task started: \(task.taskId)")
            return task
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ImportServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get the status of an ingest task
    func getIngestStatus(_ taskId: String) async throws -> IngestTaskStatus {
        let response = try await client.api.getIngestStatusApiIngestStatusTaskIdGet(
            path: .init(taskId: taskId)
        )

        switch response {
        case .ok(let okResponse):
            let status = try okResponse.body.json
            return IngestTaskStatus(
                taskId: status.taskId,
                status: status.status,
                path: status.path,
                progress: status.progress,
                total: status.total,
                processed: status.processed,
                error: status.error,
                documentIds: status.documentIds ?? []
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ImportServiceGeneratedError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Import a folder and wait for completion
    /// Polls the task status until it completes or fails
    func importFolderAndWait(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        pollInterval: TimeInterval = 0.5,
        timeout: TimeInterval = 300
    ) async throws -> [String] {
        // Start the import task
        let task = try await startFolderImport(
            url,
            mode: mode,
            parentId: parentId,
            recursive: recursive,
            extractText: extractText,
            autoEmbed: autoEmbed
        )

        let startTime = Date()

        // Poll until completion or timeout
        while true {
            // Check for cancellation
            try Task.checkCancellation()

            // Check timeout
            if Date().timeIntervalSince(startTime) > timeout {
                throw ImportServiceGeneratedError.timeout
            }

            let status = try await getIngestStatus(task.taskId)

            // Update progress
            if let total = status.total, let processed = status.processed {
                importProgress = ImportProgress(
                    current: processed,
                    total: total,
                    currentFile: url.lastPathComponent
                )
            }

            // Check status
            switch status.status.lowercased() {
            case "completed":
                logger.info("Folder import completed: \(status.documentIds.count) documents")
                return status.documentIds

            case "failed":
                let errorMessage = status.error ?? "Unknown error"
                logger.error("Folder import failed: \(errorMessage)")
                throw ImportServiceGeneratedError.taskFailed(errorMessage)

            case "pending", "processing", "running":
                // Continue polling. "running" is the backend's active status
                // (pending → running → completed/failed, #3283); "processing" is
                // kept for any legacy responses. Previously "running" fell to the
                // default and log-spammed "Unknown task status" every poll.
                try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))

            default:
                logger.warning("Unknown task status: \(status.status)")
                try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
            }
        }
    }

    /// Import an entire folder (convenience method that waits for completion)
    func importFolder(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [String] {
        isImporting = true
        defer { isImporting = false }

        return try await importFolderAndWait(
            url,
            mode: mode,
            parentId: parentId,
            recursive: recursive,
            extractText: extractText,
            autoEmbed: autoEmbed
        )
    }

    // MARK: - Progress Tracking

    /// Clear import progress and errors
    func clearProgress() {
        importProgress = nil
        lastError = nil
        currentTask = nil
    }

    // MARK: - Type Conversions

    private func convertToDocument(_ generated: Components.Schemas.Document) throws -> Document {
        // Same typed-first / extras-fallback pattern as
        // DocumentServiceGenerated.convertToDocument — typed schema fields
        // decode into typed properties, NOT additionalProperties. Reading
        // typed fields only from extras silently returns nil and corrupts
        // the local cache (#762, #774, audit on 2026-05-03).
        let extras = generated.additionalProperties.value
        let parentId = generated.parentId ?? (extras["parent_id"] as? String)
        let fileType = generated.fileType?.rawValue ?? (extras["file_type"] as? String)
        let sortOrder = extras["sort_order"] as? Int ?? 0

        return Document(
            id: generated.id ?? UUID().uuidString,
            parentId: parentId,
            docType: convertFromGeneratedDocType(generated.docType),
            fileType: fileType.flatMap { FileType(rawValue: $0) },
            name: generated.name,
            path: generated.path ?? (extras["path"] as? String),
            sequence: generated.sequence ?? (extras["sequence"] as? Int),
            bbox: (generated.bbox?.value as? [Int]) ?? (extras["bbox"] as? [Int]),
            status: convertFromGeneratedStatus(generated.status),
            metadata: convertMetadata(generated.metadata),
            pageContent: generated.pageContent ?? (extras["page_content"] as? String),
            excludeFromProcessing: generated.excludeFromProcessing ?? false,
            sortOrder: sortOrder,
            createdAt: generated.createdAt ?? Date(),
            updatedAt: generated.updatedAt ?? Date(),
            expectedThumbnailPath: generated.expectedThumbnailPath,
            expectedDisplayPath: generated.expectedDisplayPath
        )
    }

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

    private func convertMetadata(_ metadata: Components.Schemas.Document.MetadataPayload?) -> [String: AnyCodable] {
        guard let metadata = metadata else { return [:] }
        var result: [String: AnyCodable] = [:]
        for (key, value) in metadata.additionalProperties.value {
            result[key] = AnyCodable(value ?? "")
        }
        return result
    }
}

// MARK: - Ingest Task Types

/// Represents an async ingest task
struct IngestTask: Identifiable {
    let taskId: String
    let status: String
    let path: String

    var id: String { taskId }
}

/// Status of an ingest task
struct IngestTaskStatus {
    let taskId: String
    let status: String
    let path: String
    let progress: Double?
    let total: Int?
    let processed: Int?
    let error: String?
    let documentIds: [String]
}

// MARK: - Error Types

enum ImportServiceGeneratedError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)
    case taskFailed(String)
    case timeout

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from import service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        case .taskFailed(let message):
            return "Import task failed: \(message)"
        case .timeout:
            return "Import task timed out"
        }
    }
}
