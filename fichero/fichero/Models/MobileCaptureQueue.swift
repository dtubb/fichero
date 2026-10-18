import Foundation
import Observation
import OSLog
import SwiftUI

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
    /// Where this capture was meant to go (#3281): never the ambient global host.
    /// nil only for items queued before this field existed.
    var targetLibraryId: String?
    var targetHost: String?

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
        lastAttemptAt: Date?,
        targetLibraryId: String? = nil,
        targetHost: String? = nil
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
        self.targetLibraryId = targetLibraryId
        self.targetHost = targetHost
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
        case targetLibraryId
        case targetHost
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
        targetLibraryId = try container.decodeIfPresent(String.self, forKey: .targetLibraryId)
        targetHost = try container.decodeIfPresent(String.self, forKey: .targetHost)
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
        try container.encodeIfPresent(targetLibraryId, forKey: .targetLibraryId)
        try container.encodeIfPresent(targetHost, forKey: .targetHost)
    }
}

struct MobileCaptureUploadSummary: Equatable {
    var uploadedCount: Int = 0
    var failedCount: Int = 0
    var waitingCount: Int = 0
}

enum MobileCaptureQueueRouting {
    /// Whether two engine host strings name the same host: scheme and host compare case-insensitively, a trailing
    /// dot on the host and trailing slashes on the path do not count (#3281). An exact string compare would hold
    /// an item for "https://Mac.local./" forever when the current host reads "https://mac.local".
    static func sameHost(_ lhs: String?, _ rhs: String?) -> Bool {
        guard let lhs, let rhs else { return lhs == nil && rhs == nil }
        return normalisedHost(lhs) == normalisedHost(rhs)
    }

    static func normalisedHost(_ raw: String) -> String {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        func stripped(_ value: String, _ mark: Character) -> String {
            var out = value
            while out.last == mark { out.removeLast() }
            return out
        }
        guard var parts = URLComponents(string: text), let host = parts.host else {
            return stripped(stripped(text.lowercased(), "/"), ".")
        }
        parts.scheme = parts.scheme?.lowercased()
        parts.host = stripped(host.lowercased(), ".")
        parts.path = stripped(parts.path, "/")
        return parts.string ?? text.lowercased()
    }

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
    /// The library this uploader writes into, as the string an item's `targetLibraryId` holds; nil = any.
    var targetLibraryKey: String? { get }
    func upload(fileURL: URL, catalog: MobileCaptureCatalogFields) async throws -> String
}

extension MobileCaptureQueueUploading {
    var targetLibraryKey: String? { nil }
}

struct MobileCaptureBackendUploadClient: MobileCaptureQueueUploading {
    let libraryManager: LibraryManager
    // ponytail: nil → global library fallback (startup/retry callers); set to active library id in connected-library context
    var targetLibraryId: UUID?

    var backendHost: URL? {
        EngineConfig.host
    }

    var targetLibraryKey: String? { targetLibraryId?.uuidString }

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

        let outcome = try await library.importService.importFiles([fileURL], mode: .copy, parentId: nil)
        guard let importedDocument = outcome.documents.first else {
            throw MobileCaptureQueueStoreError.importFailed
        }

        let metadata = catalog.documentMetadata()
        _ = try await library.documentService.updateDocument(
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
            return "No paired project is available yet."
        case .importFailed:
            return "The paired engine did not return a document."
        }
    }
}

@MainActor
@Observable
final class MobileCaptureQueueStore {
    static let logger = Logger(
        subsystem: "app.fichero.fichero",
        category: "MobileCaptureQueue"
    )

    static let interruptedUploadError =
        "This upload was interrupted before it completed. Tap Retry to upload it again."

    /// Outbox blobs and the manifest are file-protected on iOS (#3290): readable after the first unlock,
    /// so a background upload still runs, but not from a locked, freshly booted phone.
    static var writeOptions: Data.WritingOptions {
        #if os(iOS)
        [.atomic, .completeFileProtectionUntilFirstUserAuthentication]
        #else
        .atomic
        #endif
    }

    var items: [MobileCaptureQueueItem] = []

    let storageDirectory: URL
    let fileManager: FileManager
    let manifestURL: URL
    let assetsDirectoryURL: URL

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

}

private extension String {
    var trimmedValue: String? {
        let trimmed = trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
