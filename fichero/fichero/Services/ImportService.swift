import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog
import UniformTypeIdentifiers

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImportService")

/// ImportService using the generated OpenAPI client.
/// Handles file and folder import operations.
/// Note: Folder imports are async - they return a task that must be polled for completion.
@MainActor
@Observable
class ImportService {
    // MARK: - Published State

    var isImporting: Bool = false
    var importProgress: ImportProgress?
    var lastError: ImportError?
    var currentTask: IngestTask?

    /// The live folder-import status, republished on every poll — nil when
    /// nothing is importing. The progress surfaces observe THIS rather than
    /// polling themselves, so the Activity window and the toolbar island always
    /// show the same numbers (#4203).
    var activeIngest: IngestTaskStatus?

    /// Display name of the library the active import is filling. Daniel's first
    /// question on seeing an import is WHICH library it's going into, and with
    /// several open the path alone doesn't answer that.
    var activeIngestLibraryName: String?

    private let client: FicheroClient

    /// How many per-file failures the client keeps from a task's failure list.
    /// The engine's list grows for the life of the import; the UI shows a
    /// handful and the exact total comes from `failed`, so retaining more would
    /// cost memory and republish churn for something never rendered (#4203).
    static let retainedFailureLimit = 50

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(baseURL: EngineConfig.host, libraryPath: libraryPath, transportMode: EngineConfig.transportMode)
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
                    // After-start attach (#3773): grant the sandboxed engine access
                    // to the folder and AWAIT it before the ingest request reads it.
                    logger.info("Detected folder: \(url.lastPathComponent), using async folder import")
                    let documentIds = try await FolderAccessManager.grantThenEngineWork(
                        grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
                        engineWork: {
                            try await importFolderAndWait(
                                url,
                                mode: mode,
                                parentId: parentId,
                                recursive: true,
                                extractText: extractText,
                                autoEmbed: autoEmbed
                            )
                        }
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
                // A cancelled import (task torn down / user aborted) is not a
                // per-file failure — abort the whole batch cleanly rather than
                // logging it and collecting it as an error.
                if error.isCancellationError { throw error }
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
                // Surface EVERY per-file failure, not one opaque "All imports
                // failed" — the previous blanket NSError discarded the
                // collected `errors` and left the user with no idea which files
                // failed or why (#4068, prefer-raise-over-silent-fallback).
                throw ImportError(
                    url: urls.first ?? URL(fileURLWithPath: ""),
                    error: Self.makeAllImportsFailedError(errors: errors)
                )
            }
        }

        logger.info("Import completed: \(imported.count) successful, \(errors.count) failed")
        return imported
    }

    /// Import a single file (synchronous - returns document immediately).
    /// `POST /api/ingest/file` for link/move; `POST /api/documents/import`
    /// for copy, which uploads the bytes instead of pointing at a path.
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
            // .copy: the app reads the file data and uploads it via multipart —
            // the engine never reads `url.path`, so no engine security-scoped
            // grant is needed (the app-side startAccessing above is enough).
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
                throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
            case .undocumented(let statusCode, _):
                throw ImportServiceError.unexpectedResponse(statusCode)
            }
        } else {
            // .link / .move: the engine reads (and for .move, deletes) the file
            // at `url.path`. The sandboxed engine (App Store build) cannot read
            // a path the Powerbox granted to the APP — that grant is
            // process-local and not inherited by the child engine. Mint a
            // security-scoped bookmark for the file's PARENT directory and hand
            // it to the running engine BEFORE the ingest call, mirroring the
            // folder seam (`grantThenEngineWork` / `saveBookmarkIfDirectory`,
            // #3773). Without it a single-file image drag from Finder errors
            // "All imports failed" in the sandboxed release build (#4068). For
            // .move the parent grant also authorises the delete (move = copy +
            // unlink, the unlink needs write access to the parent).
            //
            // `saveBookmarkIfDirectory` is a no-op for paths the engine can
            // already reach (non-sandboxed DMG build, transient temp paths the
            // app owns) and throws when a live grant is refused — the caller
            // surfaces the failure rather than letting the ingest race the
            // grant and fail with an inscrutable permission error.
            let parent = url.deletingLastPathComponent()
            return try await FolderAccessManager.grantThenEngineWork(
                grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(parent) },
                engineWork: {
                    let response = try await self.client.api.ingestFileApiIngestFilePost(
                        body: .json(.init(
                            path: url.path,
                            parentId: parentId,
                            copyMode: mode == .copy,
                            // Send the explicit ingest mode so .move is honoured instead of
                            // silently resolving to link (#3270 — data-loss: original never
                            // moved, library links to a file the user then deletes). Mapped
                            // by CASE to the generated lowercase enum, NOT `rawValue` (which
                            // is uppercase "MOVE" and would 422 the backend's
                            // Literal["link","copy","move"], the #3288 trap).
                            mode: mode == .copy ? .copy : (mode == .move ? .move : .link),
                            extractText: extractText,
                            autoEmbed: autoEmbed
                        ))
                    )
                    switch response {
                    case .ok(let okResponse):
                        return try self.convertToDocument(try okResponse.body.json)
                    case .unprocessableContent(let error):
                        let detail = try? error.body.json
                        throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
                    case .undocumented(let statusCode, _):
                        throw ImportServiceError.unexpectedResponse(statusCode)
                    }
                }
            )
        }
        return try convertToDocument(doc)
    }

    // MARK: - Async Folder Import

    /// `POST /api/ingest/folder` — start a folder import task (returns
    /// immediately with a task id; poll the status endpoint for progress).
    func startFolderImport(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false
    ) async throws -> IngestTask {
        logger.info("Starting async folder import: \(url.lastPathComponent)")

        // Enable app-side security-scoped access in sandboxed builds; non-sandboxed
        // builds return false but the URL remains accessible via normal file I/O.
        let didStartAccess = url.startAccessingSecurityScopedResource()
        defer {
            if didStartAccess { url.stopAccessingSecurityScopedResource() }
        }

        // After-start attach (#3773): grant the sandboxed ENGINE access to the
        // folder and AWAIT it before the ingest request reads it.
        let response = try await FolderAccessManager.grantThenEngineWork(
            grant: { try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
            engineWork: {
                try await client.api.ingestFolderApiIngestFolderPost(
                    body: .json(.init(
                        path: url.path,
                        parentId: parentId,
                        copyMode: mode == .copy,
                        // Explicit ingest mode so .move isn't downgraded to link
                        // (#3270); case-mapped to the generated enum, not rawValue
                        // (#3288 casing trap).
                        mode: mode == .copy ? .copy : (mode == .move ? .move : .link),
                        recursive: recursive,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    ))
                )
            }
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
            throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceError.unexpectedResponse(statusCode)
        }
    }

    /// `GET /api/ingest/status/{task_id}` — poll a folder import's progress.
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
                documentIds: status.documentIds ?? [],
                failed: status.failed ?? 0,
                // RETAINED failures are capped, not just displayed ones: the
                // engine accumulates every failure for the life of the task, so
                // a 100k-file import with a bad drive would hold — and
                // republish — an unbounded array twice a second. `failed` stays
                // the exact count; this list is a sample of the first ones,
                // which is what a user needs to see what KIND of thing failed.
                failures: (status.failures ?? []).prefix(Self.retainedFailureLimit).map { entry in
                    IngestFailure(
                        path: entry.additionalProperties["path"] ?? "",
                        error: entry.additionalProperties["error"] ?? "Import failed",
                        documentId: entry.additionalProperties["document_id"]
                    )
                },
                filesPerSecond: status.filesPerSecond ?? 0
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceError.unexpectedResponse(statusCode)
        }
    }

    /// `POST /api/ingest/folder/{task_id}/cancel` — ask the engine to stop
    /// between committed files. Cooperative: the task finishes the file in
    /// flight, so the reported status goes `cancelling` then `cancelled` rather
    /// than stopping instantly. Repeated calls are safe.
    @discardableResult
    func cancelIngest(_ taskId: String) async throws -> String {
        let response = try await client.api.cancelIngestApiIngestFolderTaskIdCancelPost(
            path: .init(taskId: taskId)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.status
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceError.unexpectedResponse(statusCode)
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
                throw ImportServiceError.timeout
            }

            let status = try await getIngestStatus(task.taskId)
            // Publish so the progress surfaces see scanning, rate, failures and
            // cancellation as they happen — but ONLY on a real change. A blind
            // assignment every 0.5s invalidates every observer for the whole
            // import even when no number moved.
            if activeIngest != status { activeIngest = status }

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
                throw ImportServiceError.taskFailed(errorMessage)

            case "cancelled":
                // The user asked to stop. Files committed before the stop stay
                // imported, so this returns them rather than throwing — a
                // cancelled import is a SHORTER import, not a failed one.
                logger.info("Folder import cancelled: \(status.documentIds.count) documents kept")
                return status.documentIds

            case "cancelling":
                // Cooperative: the file in flight still has to land. Keep
                // polling until the engine settles on `cancelled`.
                try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))

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
        // The status stays visible only while the import runs; a finished
        // import belongs in the sidebar, not in a progress row nobody dismissed.
        defer {
            isImporting = false
            activeIngest = nil
        }

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

    /// Stop the running folder import. The engine finishes the file in flight,
    /// so the status settles `cancelling` → `cancelled` and the poll loop
    /// returns whatever was committed before the stop.
    func cancelActiveIngest() async {
        guard let taskId = activeIngest?.taskId ?? currentTask?.taskId else { return }
        do {
            _ = try await cancelIngest(taskId)
        } catch {
            // A cancel that fails must not look like a cancel that worked: the
            // import keeps running and the button stays available.
            logger.error("Cancel request failed: \(error.localizedDescription)")
            lastError = ImportError(url: URL(fileURLWithPath: activeIngest?.path ?? "/"), error: error)
        }
    }

    /// Clear import progress and errors
    func clearProgress() {
        importProgress = nil
        activeIngest = nil
        activeIngestLibraryName = nil
        lastError = nil
        currentTask = nil
    }

    // MARK: - Type Conversions

    private func convertToDocument(_ generated: Components.Schemas.Document) throws -> Document {
        // Same typed-first / extras-fallback pattern as
        // DocumentService.convertToDocument — typed schema fields
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

/// One file the import could not take, surfaced rather than swallowed (#4203).
struct IngestFailure: Identifiable, Equatable {
    let path: String
    let error: String
    let documentId: String?

    /// The failed stub's document id when the engine made one, else the path —
    /// two files can't share a path within one import.
    var id: String { documentId ?? path }
}

/// Status of an ingest task
///
/// `Equatable` is load-bearing, not decoration: the poll loop republishes this
/// twice a second for the whole import, and observers must invalidate only when
/// a number actually MOVED. Otherwise every progress surface re-renders 2×/sec
/// for the duration — the no-wholesale-re-render rule, applied to a struct
/// instead of a list (#4203).
struct IngestTaskStatus: Equatable {
    let taskId: String
    let status: String
    let path: String
    let progress: Double?
    let total: Int?
    let processed: Int?
    let error: String?
    let documentIds: [String]
    let failed: Int
    let failures: [IngestFailure]
    /// Throughput the engine measured; 0 until the first file lands.
    let filesPerSecond: Double

    /// The walk hasn't finished counting yet, so `processed / total` would read
    /// "0 of 0" — the moment the user currently sees nothing at all (#4203).
    var isScanning: Bool { (total ?? 0) == 0 }

    /// Cancellation requested and not yet settled.
    var isCancelling: Bool { status == "cancelling" }

    /// Terminal, whatever the outcome — polling stops here.
    var isFinished: Bool { ["completed", "failed", "cancelled"].contains(status) }

    /// Seconds of work left at the measured rate, or nil while scanning, while
    /// the rate is still unknown, or once there's nothing left to do.
    var estimatedSecondsRemaining: Double? {
        guard !isScanning, filesPerSecond > 0,
              let total, let processed, total > processed else { return nil }
        return Double(total - processed) / filesPerSecond
    }
}

// MARK: - Error Types

enum ImportServiceError: Error, LocalizedError {
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
