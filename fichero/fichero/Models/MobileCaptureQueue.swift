// swiftlint:disable file_length
import Observation
import Foundation
import OSLog
import SwiftUI

private let mobileCaptureQueueLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "MobileCaptureQueue"
)

private let mobileCaptureInterruptedUploadError =
    "This upload was interrupted before it completed. Tap Retry to upload it again."

struct MobileCaptureCatalogFields: Codable, Hashable {
    var title: String
    var folderName: String
    var seriesName: String
    var pageOrder: Int?
    var notes: String
    var sourceArchiveHint: String

    init(
        title: String = "",
        folderName: String = "",
        seriesName: String = "",
        pageOrder: Int? = nil,
        notes: String = "",
        sourceArchiveHint: String = ""
    ) {
        self.title = title
        self.folderName = folderName
        self.seriesName = seriesName
        self.pageOrder = pageOrder
        self.notes = notes
        self.sourceArchiveHint = sourceArchiveHint
    }

    func documentName(fallback: String) -> String {
        let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? fallback : trimmed
    }

    func documentMetadata() -> [String: String] {
        var metadata: [String: String] = [:]

        if let folderName = folderName.trimmedValue {
            metadata["capture_folder"] = folderName
        }
        if let seriesName = seriesName.trimmedValue {
            metadata["capture_series"] = seriesName
        }
        if let pageOrder, pageOrder > 0 {
            metadata["capture_page_order"] = String(pageOrder)
        }
        if let notes = notes.trimmedValue {
            metadata["capture_notes"] = notes
        }
        if let sourceArchiveHint = sourceArchiveHint.trimmedValue {
            metadata["capture_source_archive_hint"] = sourceArchiveHint
        }

        return metadata
    }
}

enum MobileCaptureUploadState: String, Codable, Hashable {
    case queued
    case waitingForBackend
    case uploading
    case uploaded
    case failed
}

struct MobileCaptureQueueItem: Identifiable, Codable, Hashable {
    let id: String
    var imageFileName: String
    var createdAt: Date
    var updatedAt: Date
    var catalog: MobileCaptureCatalogFields
    var uploadState: MobileCaptureUploadState
    var uploadedDocumentId: String?
    var lastError: String?
    var requiresExplicitRetry: Bool
    var retryCount: Int
    var lastAttemptAt: Date?

    init(
        id: String,
        imageFileName: String,
        createdAt: Date,
        updatedAt: Date,
        catalog: MobileCaptureCatalogFields,
        uploadState: MobileCaptureUploadState,
        uploadedDocumentId: String?,
        lastError: String?,
        requiresExplicitRetry: Bool = false,
        retryCount: Int,
        lastAttemptAt: Date?
    ) {
        self.id = id
        self.imageFileName = imageFileName
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.catalog = catalog
        self.uploadState = uploadState
        self.uploadedDocumentId = uploadedDocumentId
        self.lastError = lastError
        self.requiresExplicitRetry = requiresExplicitRetry
        self.retryCount = retryCount
        self.lastAttemptAt = lastAttemptAt
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case imageFileName
        case createdAt
        case updatedAt
        case catalog
        case uploadState
        case uploadedDocumentId
        case lastError
        case requiresExplicitRetry
        case retryCount
        case lastAttemptAt
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        imageFileName = try container.decode(String.self, forKey: .imageFileName)
        createdAt = try container.decode(Date.self, forKey: .createdAt)
        updatedAt = try container.decode(Date.self, forKey: .updatedAt)
        catalog = try container.decode(MobileCaptureCatalogFields.self, forKey: .catalog)
        uploadState = try container.decode(MobileCaptureUploadState.self, forKey: .uploadState)
        uploadedDocumentId = try container.decodeIfPresent(String.self, forKey: .uploadedDocumentId)
        lastError = try container.decodeIfPresent(String.self, forKey: .lastError)
        requiresExplicitRetry = try container.decodeIfPresent(Bool.self, forKey: .requiresExplicitRetry) ?? false
        retryCount = try container.decode(Int.self, forKey: .retryCount)
        lastAttemptAt = try container.decodeIfPresent(Date.self, forKey: .lastAttemptAt)
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(id, forKey: .id)
        try container.encode(imageFileName, forKey: .imageFileName)
        try container.encode(createdAt, forKey: .createdAt)
        try container.encode(updatedAt, forKey: .updatedAt)
        try container.encode(catalog, forKey: .catalog)
        try container.encode(uploadState, forKey: .uploadState)
        try container.encodeIfPresent(uploadedDocumentId, forKey: .uploadedDocumentId)
        try container.encodeIfPresent(lastError, forKey: .lastError)
        try container.encode(requiresExplicitRetry, forKey: .requiresExplicitRetry)
        try container.encode(retryCount, forKey: .retryCount)
        try container.encodeIfPresent(lastAttemptAt, forKey: .lastAttemptAt)
    }
}

struct MobileCaptureUploadSummary: Equatable {
    var uploadedCount: Int = 0
    var failedCount: Int = 0
    var waitingCount: Int = 0
}

enum MobileCaptureQueueRouting {
    static func canResumeUploads(
        backendHost: URL?,
        hasPairedLibraryPath: Bool = RemoteAccessConfig.hasPairedLibraryPath
    ) -> Bool {
        guard let backendHost else { return false }
        guard hasPairedLibraryPath else { return false }
        return (try? validatedRemoteURL(
            from: backendHost.absoluteString,
            allowLocalhost: false,
            requireSecureTransportForRemote: false
        )) != nil
    }
}

@MainActor
protocol MobileCaptureQueueUploading {
    var backendHost: URL? { get }
    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String
}

struct MobileCaptureBackendUploadClient: MobileCaptureQueueUploading {
    let libraryManager: LibraryManager
    // ponytail: nil → global library fallback (startup/retry callers); set to active library id in connected-library context
    var targetLibraryId: UUID?

    var backendHost: URL? {
        EngineConfig.host
    }

    @MainActor
    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String {
        guard RemoteAccessConfig.hasPairedLibraryPath else {
            throw MobileCaptureQueueStoreError.noLibraryAvailable
        }
        let resolved = targetLibraryId.map { libraryManager.getLibrary(id: $0) }
            ?? libraryManager.globalLibrary
        guard let library = resolved else {
            throw MobileCaptureQueueStoreError.noLibraryAvailable
        }

        let imported = try await library.importService.importFiles([fileURL], mode: .copy, parentId: nil)
        guard let importedDocument = imported.first else {
            throw MobileCaptureQueueStoreError.importFailed
        }

        let metadata = catalog.documentMetadata()
        _ = try await library.documentServiceGenerated.updateDocument(
            importedDocument.id,
            name: catalog.documentName(fallback: fileURL.deletingPathExtension().lastPathComponent),
            metadata: metadata.isEmpty ? nil : metadata,
            pageContent: catalog.notes.trimmedValue
        )
        return importedDocument.id
    }
}

enum MobileCaptureQueueStoreError: Error, LocalizedError {
    case noLibraryAvailable
    case importFailed

    var errorDescription: String? {
        switch self {
        case .noLibraryAvailable:
            return "No paired library is available yet."
        case .importFailed:
            return "The paired engine did not return a document."
        }
    }
}

@MainActor
@Observable
final class MobileCaptureQueueStore {
    private(set) var items: [MobileCaptureQueueItem] = []

    private let storageDirectory: URL
    private let fileManager: FileManager
    private let manifestURL: URL
    private let assetsDirectoryURL: URL

    init(
        storageDirectory: URL? = nil,
        fileManager: FileManager = .default
    ) {
        self.fileManager = fileManager
        self.storageDirectory = storageDirectory ?? Self.defaultStorageDirectory(fileManager: fileManager)
        self.manifestURL = self.storageDirectory.appendingPathComponent("capture-queue.json")
        self.assetsDirectoryURL = self.storageDirectory.appendingPathComponent("assets", isDirectory: true)
        loadPersistedQueue()
    }

    var pendingCount: Int {
        items.filter {
            $0.uploadState == .queued || $0.uploadState == .failed || $0.uploadState == .waitingForBackend
        }.count
    }

    var uploadedCount: Int {
        items.filter { $0.uploadState == .uploaded }.count
    }

    func imageURL(for item: MobileCaptureQueueItem) -> URL {
        assetsDirectoryURL.appendingPathComponent(item.imageFileName)
    }

    @discardableResult
    func enqueueCapturedImage(
        _ imageData: Data,
        catalog: MobileCaptureCatalogFields = .init(),
        fileName: String? = nil,
        fileExtension: String = "jpg"
    ) throws -> MobileCaptureQueueItem {
        try prepareStorage()

        let id = UUID().uuidString
        let resolvedFileName = fileName ?? "\(id).\(fileExtension)"
        let imageURL = assetsDirectoryURL.appendingPathComponent(resolvedFileName)
        try imageData.write(to: imageURL, options: .atomic)

        let now = Date()
        let item = MobileCaptureQueueItem(
            id: id,
            imageFileName: resolvedFileName,
            createdAt: now,
            updatedAt: now,
            catalog: catalog,
            uploadState: .queued,
            uploadedDocumentId: nil,
            lastError: nil,
            requiresExplicitRetry: false,
            retryCount: 0,
            lastAttemptAt: nil
        )
        items.insert(item, at: 0)
        persistQueue()
        return item
    }

    func updateCatalog(
        id: String,
        mutate: (inout MobileCaptureCatalogFields) -> Void
    ) {
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        let wasInterruptedRetry =
            items[index].requiresExplicitRetry
            || items[index].lastError == mobileCaptureInterruptedUploadError
        mutate(&items[index].catalog)
        items[index].updatedAt = Date()
        if items[index].uploadState == .uploaded {
            items[index].uploadState = .queued
            items[index].uploadedDocumentId = nil
            items[index].requiresExplicitRetry = false
        } else if wasInterruptedRetry {
            items[index].uploadState = .failed
            items[index].requiresExplicitRetry = true
            items[index].lastError = mobileCaptureInterruptedUploadError
        } else if items[index].uploadState != .uploading {
            items[index].uploadState = .queued
        }
        if !wasInterruptedRetry {
            items[index].lastError = nil
        }
        persistQueue()
    }

    func removeItem(id: String) {
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        let item = items.remove(at: index)
        try? fileManager.removeItem(at: imageURL(for: item))
        persistQueue()
    }

    func markAllWaitingForBackend() {
        var changed = false
        for index in items.indices where items[index].uploadState == .queued || items[index].uploadState == .failed {
            items[index].uploadState = .waitingForBackend
            if items[index].lastError != mobileCaptureInterruptedUploadError {
                items[index].lastError = nil
            }
            changed = true
        }
        if changed { persistQueue() }
    }

    @discardableResult
    func resumePendingUploads(
        using uploader: some MobileCaptureQueueUploading,
        retryInterruptedUploads: Bool = false
    ) async -> MobileCaptureUploadSummary {
        guard MobileCaptureQueueRouting.canResumeUploads(backendHost: uploader.backendHost) else {
            markAllWaitingForBackend()
            return MobileCaptureUploadSummary(waitingCount: pendingCount)
        }

        var summary = MobileCaptureUploadSummary()
        let retryableIndices = items.indices.filter { index in
            switch items[index].uploadState {
            case .queued, .failed, .waitingForBackend:
                if items[index].requiresExplicitRetry && !retryInterruptedUploads {
                    return false
                }
                if !retryInterruptedUploads,
                   items[index].lastError == mobileCaptureInterruptedUploadError {
                    return false
                }
                return true
            case .uploading, .uploaded:
                return false
            }
        }

        for index in retryableIndices {
            items[index].uploadState = .uploading
            items[index].lastAttemptAt = Date()
            items[index].retryCount += 1
            items[index].lastError = nil
        }
        persistQueue()

        for index in retryableIndices {
            let item = items[index]
            do {
                let documentId = try await uploader.upload(
                    fileURL: imageURL(for: item),
                    catalog: item.catalog
                )
                items[index].uploadState = .uploaded
                items[index].uploadedDocumentId = documentId
                items[index].lastError = nil
                summary.uploadedCount += 1
            } catch {
                items[index].uploadState = .failed
                items[index].lastError = error.localizedDescription
                summary.failedCount += 1
                mobileCaptureQueueLogger.error("Capture upload failed: \(error.localizedDescription)")
            }
            persistQueue()
        }

        return summary
    }

    private func loadPersistedQueue() {
        guard fileManager.fileExists(atPath: manifestURL.path),
              let data = try? Data(contentsOf: manifestURL),
              let decoded = try? JSONDecoder().decode([MobileCaptureQueueItem].self, from: data)
        else {
            items = []
            return
        }

        items = decoded.compactMap { item in
            guard fileManager.fileExists(atPath: imageURL(for: item).path) else {
                return nil
            }

            var normalized = item
            if normalized.uploadState == .uploading {
                normalized.uploadState = .failed
                normalized.lastError = mobileCaptureInterruptedUploadError
                normalized.requiresExplicitRetry = true
                normalized.lastAttemptAt = nil
            }
            return normalized
        }
    }

    private func persistQueue() {
        do {
            try prepareStorage()
            let data = try JSONEncoder().encode(items)
            try data.write(to: manifestURL, options: .atomic)
        } catch {
            mobileCaptureQueueLogger.error("Failed to persist capture queue: \(error.localizedDescription)")
        }
    }

    private func prepareStorage() throws {
        if !fileManager.fileExists(atPath: storageDirectory.path) {
            try fileManager.createDirectory(at: storageDirectory, withIntermediateDirectories: true)
        }
        if !fileManager.fileExists(atPath: assetsDirectoryURL.path) {
            try fileManager.createDirectory(at: assetsDirectoryURL, withIntermediateDirectories: true)
        }
    }

    private static func defaultStorageDirectory(fileManager: FileManager) -> URL {
        let baseURL = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return baseURL.appendingPathComponent("Fichero/MobileCaptureQueue", isDirectory: true)
    }
}

private extension String {
    var trimmedValue: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
