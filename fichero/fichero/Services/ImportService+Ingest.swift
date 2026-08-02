import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

/// Same subsystem and category as `ImportService.swift`'s logger — that one is
/// file-private and cannot cross files, so this is a second declaration with
/// identical output rather than a moved one.
private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImportService")

// MARK: - Folder ingest (#4208)

/// The async folder-import half of `ImportService`: starting a task, polling it,
/// cancelling it, and the published progress state the #4203 UI observes.
///
/// A PURE MOVE out of `ImportService.swift` — no renames, no signature changes.
/// That file was over SwiftLint's type-body limit, which is configured at ERROR
/// severity while the phase still exits 0, so every Xcode build showed error
/// text from a build phase reporting success.
extension ImportService {
    // MARK: - Async Folder Import

    /// `POST /api/ingest/folder` — start a folder import task (returns
    /// immediately with a task id; poll the status endpoint for progress).
    func startFolderImport(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool? = nil,
        autoEmbed: Bool? = nil
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
        extractText: Bool? = nil,
        autoEmbed: Bool? = nil,
        pollInterval: TimeInterval = 0.5,
        timeout: TimeInterval = 300
    ) async throws -> [String] {
        // #4232: clear the published status on EVERY exit — completed, failed,
        // cancelled or thrown. `importFolder` already defers this, but the
        // drag-and-drop path (ImportService.swift:98) calls this function
        // directly, so a finished import left `activeIngest` holding its final
        // status and the toolbar island spun at "5/5" forever while the Activity
        // popover — which reads live engine state — correctly said "Nothing
        // running". Clearing here covers every caller instead of every caller
        // remembering.
        defer {
            activeIngest = nil
            activeIngestLibraryName = nil
        }

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
        extractText: Bool? = nil,
        autoEmbed: Bool? = nil,
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
}
