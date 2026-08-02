import FicheroAPIClient
import Foundation
import Observation
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

    /// Display name of the library the active import is filling. The user's first
    /// question on seeing an import is WHICH library it's going into, and with
    /// several open the path alone doesn't answer that.
    var activeIngestLibraryName: String?

    /// Internal, not private, so `ImportService+Ingest.swift` can reach it.
    /// Swift has no extension-scoped access level: an extension in another file
    /// is a different file, so `private` hides this from the type's own folder
    /// -ingest half. Widened deliberately as part of the #4208 split rather than
    /// duplicating the client or threading it through every call.
    let client: FicheroClient

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
    ///
    /// `extractText`/`autoEmbed` are `nil` by default and OMITTED from the
    /// request, so the engine's documented defaults apply (#3276). They used to
    /// default to `false` here, which silently overrode the backend's `True` on
    /// every drag-drop and menu import — the engine chose `True` precisely to
    /// avoid the first-run "search returns nothing because nothing is indexed"
    /// trap, and the app was re-deciding it four layers away with no UI saying
    /// so. A caller that genuinely wants indexing off now has to say `false`.
    func importFiles(
        _ urls: [URL],
        mode: IngestMode = .link,
        parentId: String? = nil,
        extractText: Bool? = nil,
        autoEmbed: Bool? = nil,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> ImportOutcome {
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
                    try await importFolderGrantingAccess(
                        url,
                        mode: mode,
                        parentId: parentId,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    )
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

        try recordImportErrors(errors, imported: imported, urls: urls)

        logger.info("Import completed: \(imported.count) successful, \(errors.count) failed")
        // Failures ride back with the successes (#3276). Returning a bare
        // [Document] made the partial case indistinguishable from a clean one
        // at every call site, and the only record of it — `lastError` — was
        // read by no view.
        return ImportOutcome(documents: imported, failures: errors, attempted: urls.count)
    }

    /// A folder import needs the sandboxed engine granted access BEFORE the
    /// ingest request reads it, and the grant must be awaited (#3773). Only
    /// document ids come back, not documents, so nothing is returned — the
    /// caller fetches what it needs.
    private func importFolderGrantingAccess(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool?,
        autoEmbed: Bool?
    ) async throws {
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
    }

    /// Record what failed, and throw only when NOTHING imported. A partial
    /// batch still returns its successes.
    private func recordImportErrors(
        _ errors: [ImportError],
        imported: [Document],
        urls: [URL]
    ) throws {
        guard !errors.isEmpty else { return }
        lastError = errors.first
        logger.warning("Import completed with \(errors.count) errors")
        guard imported.isEmpty else { return }
        // Surface EVERY per-file failure, not one opaque "All imports
        // failed" — the previous blanket NSError discarded the
        // collected `errors` and left the user with no idea which files
        // failed or why (#4068, prefer-raise-over-silent-fallback).
        throw ImportError(
            url: urls.first ?? URL(fileURLWithPath: ""),
            error: Self.makeAllImportsFailedError(errors: errors)
        )
    }

    /// Import a single file (synchronous - returns document immediately).
    /// `POST /api/ingest/file` for link/move; `POST /api/documents/import`
    /// for copy, which uploads the bytes instead of pointing at a path.
    private func importFile(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool?,
        autoEmbed: Bool?
    ) async throws -> Document {
        // Enable security-scoped access in sandboxed builds; non-sandboxed builds
        // return false but the URL remains accessible via normal file I/O.
        let didStartAccess = url.startAccessingSecurityScopedResource()
        defer {
            if didStartAccess { url.stopAccessingSecurityScopedResource() }
        }

        if mode == .copy {
            return try convertToDocument(try await uploadFileContents(url, parentId: parentId))
        }
        return try await ingestFileInPlace(
            url,
            mode: mode,
            parentId: parentId,
            extractText: extractText,
            autoEmbed: autoEmbed
        )
    }

    /// `.copy`: the app reads the file data and uploads it via multipart — the
    /// engine never reads `url.path`, so no engine security-scoped grant is
    /// needed (the caller's app-side `startAccessing` is enough).
    private func uploadFileContents(
        _ url: URL,
        parentId: String?
    ) async throws -> Components.Schemas.Document {
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
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ImportServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ImportServiceError.unexpectedResponse(statusCode)
        }
    }

    private func ingestFileInPlace(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool?,
        autoEmbed: Bool?
    ) async throws -> Document {
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

}
