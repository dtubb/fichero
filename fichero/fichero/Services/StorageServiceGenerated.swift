import AppKit
import FicheroAPIClient
import Foundation
import ImageIO
import OpenAPIRuntime
import OpenAPIURLSession
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageServiceGenerated")

/// StorageService using the generated OpenAPI client.
/// Handles storage operations (thumbnails, previews, source files).
/// Note: Image loading is done via direct URLSession for efficiency.
@MainActor
class StorageServiceGenerated: ObservableObject {
    // MARK: - Published State

    @Published var isLoading: Bool = false
    @Published var lastError: Error?

    private let client: FicheroClient
    private let session = URLSession.shared
    private let configuredBaseURL: URL?

    /// In-memory cache keyed by `docId`. Prevents the "Loading thumbnail
    /// for document: X" storms Daniel was seeing — `.task` re-fires on
    /// every grid view identity reset (e.g., when filteredDocuments
    /// re-computes or LazyVGrid re-lays out), each firing a fresh
    /// network request + byte decode. With the cache, re-fires return
    /// instantly. Scoped to this service instance (one per library), so
    /// switching libraries naturally resets.
    private var thumbnailCache: [String: Image] = [:]
    private var displayCache: [String: Image] = [:]
    private var displayNSImageCache: [String: NSImage] = [:]
    private var sourceDataCache: [String: Data] = [:]

    /// Upper bound on the thumbnail cache so opening a folder with thousands
    /// of images can't grow it without limit (#719). When exceeded, the
    /// oldest-inserted entries are evicted first (FIFO) — by the time the
    /// cache is this full the user has scrolled well past those rows.
    static let thumbnailCacheLimit = 1000
    /// Insertion order of thumbnail-cache keys, oldest first. Drives FIFO
    /// eviction in `cacheThumbnail`.
    private var thumbnailCacheOrder: [String] = []

    /// Number of cached thumbnails. Exposed for tests (#719 eviction).
    var thumbnailCacheCount: Int { thumbnailCache.count }

    /// Cached thumbnail for `docId`, if present. Exposed for tests (#719).
    func cachedThumbnail(for docId: String) -> Image? { thumbnailCache[docId] }

    private var baseURL: URL {
        configuredBaseURL ?? EngineConfig.apiBaseURL
    }

    init(ficheroClient: FicheroClient, baseURL: URL? = nil) {
        self.client = ficheroClient
        self.configuredBaseURL = baseURL
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Image Loading

    /// Get thumbnail image for a document. Memoised per-service-instance.
    func getThumbnail(_ docId: String) async throws -> Image {
        if let cached = thumbnailCache[docId] {
            return cached
        }
        logger.info("Loading thumbnail for document: \(docId)")
        let data = try await fetchImageData(from: thumbnailURL(for: docId))
        let image = try await Self.decodeImage(from: data)
        cacheThumbnail(image, for: docId)
        return image
    }

    /// Insert a thumbnail into the cache, evicting the oldest entries (FIFO)
    /// once the cache exceeds `thumbnailCacheLimit`. Internal so the eviction
    /// bound can be unit-tested without a live backend. (#719)
    func cacheThumbnail(_ image: Image, for docId: String) {
        if thumbnailCache[docId] == nil {
            thumbnailCacheOrder.append(docId)
        }
        thumbnailCache[docId] = image
        while thumbnailCacheOrder.count > Self.thumbnailCacheLimit {
            let oldest = thumbnailCacheOrder.removeFirst()
            thumbnailCache.removeValue(forKey: oldest)
        }
    }

    /// Raw thumbnail bytes for `docId`, bypassing the decoded-`Image` cache.
    /// RealityKit's `TextureResource(contentsOf:)` needs a file on disk, so the
    /// Mind Palace 3D scene fetches undecoded bytes through this authenticated
    /// storage path instead of hand-building a URL and calling `URLSession`
    /// directly (#1902).
    func thumbnailData(for docId: String) async throws -> Data {
        try await fetchImageData(from: thumbnailURL(for: docId))
    }

    /// Get display-quality image for a document. Memoised per-service-instance.
    func getDisplayImage(_ docId: String) async throws -> Image {
        if let cached = displayCache[docId] {
            return cached
        }
        logger.info("Loading display image for document: \(docId)")
        let data = try await fetchImageData(from: displayURL(for: docId))
        let image = try await Self.decodeImage(from: data)
        displayCache[docId] = image
        return image
    }

    /// Get display-quality image for zoomable AppKit-backed canvases.
    /// Uses the same generated storage endpoint as `getDisplayImage`, not the
    /// image-edit preview endpoint.
    func getDisplayNSImage(_ docId: String) async throws -> NSImage {
        if let cached = displayNSImageCache[docId] {
            return cached
        }
        logger.info("Loading display NSImage for document: \(docId)")
        let data = try await fetchImageData(from: displayURL(for: docId))
        guard let image = NSImage(data: data) else {
            throw StorageServiceError.invalidImageData
        }
        displayNSImageCache[docId] = image
        return image
    }

    /// Get original source-file bytes for a document. Memoised per-service
    /// instance so PDFKit surfaces can share one download.
    func getSourceData(_ docId: String) async throws -> Data {
        if let cached = sourceDataCache[docId] {
            return cached
        }
        logger.info("Loading source data for document: \(docId)")
        let data = try await fetchBinaryData(from: sourceURL(for: docId))
        sourceDataCache[docId] = data
        return data
    }

    /// Warm the thumbnail cache for a batch of documents (#719).
    /// Fires concurrent fetches (max 6 at a time) only for uncached ids.
    /// Errors are swallowed — this is best-effort prefetch, not critical load.
    func prefetchThumbnails(_ docIds: [String]) async {
        let uncached = docIds.filter { thumbnailCache[$0] == nil }
        guard !uncached.isEmpty else { return }
        await withTaskGroup(of: Void.self) { group in
            var inFlight = 0
            for docId in uncached {
                if inFlight >= 6 {
                    await group.next()
                    inFlight -= 1
                }
                group.addTask { [weak self] in
                    guard let self else { return }
                    _ = try? await self.getThumbnail(docId)
                }
                inFlight += 1
            }
        }
    }

    /// Evict a document's cached images — call when the user knows a
    /// thumbnail has changed (e.g., after a rebuild/reindex).
    func invalidateImageCache(for docId: String) {
        thumbnailCache.removeValue(forKey: docId)
        displayCache.removeValue(forKey: docId)
        displayNSImageCache.removeValue(forKey: docId)
        sourceDataCache.removeValue(forKey: docId)
        thumbnailCacheOrder.removeAll { $0 == docId }
    }

    /// Fetch raw image bytes from the backend. Suspends during the
    /// network call; doesn't block main thread.
    ///
    /// On non-200, surfaces the actual status code + content-type instead
    /// of a generic "invalid response" so #1018-style failures can be
    /// diagnosed from logs without re-instrumenting the backend.
    private func fetchImageData(from url: URL) async throws -> Data {
        try await fetchBinaryData(from: url)
    }

    private func fetchBinaryData(from url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: client.currentLibraryPath)
        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw StorageServiceError.invalidResponse
        }
        if httpResponse.statusCode == 200 {
            return data
        }
        let contentType = httpResponse.value(forHTTPHeaderField: "Content-Type") ?? "unknown"
        if httpResponse.statusCode == 404 {
            throw StorageServiceError.notFound(url: url, contentType: contentType)
        }
        let bodyPeek = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
        throw StorageServiceError.unexpectedStatus(
            status: httpResponse.statusCode,
            contentType: contentType,
            bodyPeek: bodyPeek
        )
    }

    /// Decode image bytes into a SwiftUI `Image` off the main thread.
    ///
    /// `NSImage(data:)` and the underlying CGImageSource decode path both
    /// parse the full bitmap synchronously — a 2MB JPG can take 10-50 ms
    /// per image. Done on the main actor (where `LibraryImageView.task`
    /// runs), 250+ thumbnails per folder click stack up and block clicks
    /// + gestures for seconds. #605.
    ///
    /// `Task.detached` runs the decode on a background executor, then
    /// hands back a `Sendable` `Image` value. `Image(decorative:scale:)`
    /// wraps a CGImage for SwiftUI display; it's safe to construct off
    /// the main actor and the resulting `Image` can cross actor boundaries.
    nonisolated private static func decodeImage(from data: Data) async throws -> Image {
        try await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw StorageServiceError.invalidImageData
            }
            return Image(decorative: cgImage, scale: 1.0)
        }.value
    }

    // MARK: - URL Providers

    /// Get thumbnail URL for AsyncImage
    func thumbnailURL(for docId: String) -> URL {
        baseURL.appendingPathComponent("storage/thumbnail/\(docId)")
    }

    /// Get display image URL for AsyncImage
    func displayURL(for docId: String) -> URL {
        baseURL.appendingPathComponent("storage/display/\(docId)")
    }

    /// Get source file URL
    func sourceURL(for docId: String) -> URL {
        baseURL.appendingPathComponent("storage/source/\(docId)")
    }

    // MARK: - File Access

    /// Download the original source file
    func downloadSourceFile(_ docId: String) async throws -> URL {
        isLoading = true
        defer { isLoading = false }

        logger.info("Downloading source file for document: \(docId)")

        let url = sourceURL(for: docId)
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: client.currentLibraryPath)

        let (localURL, response) = try await session.download(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageServiceError.invalidResponse
        }

        logger.info("Downloaded source file to: \(localURL.path)")
        return localURL
    }

    // MARK: - Storage Stats

    /// Get storage statistics
    func getStats() async throws -> StorageStats {
        logger.info("Fetching storage stats")

        let response = try await client.api.storageStatsApiStorageStatsGet()

        switch response {
        case .ok(let okResponse):
            let container = try okResponse.body.json
            // Extract values from OpenAPIValueContainer
            guard let dict = container.value as? [String: Any] else {
                throw StorageServiceError.unexpectedResponse
            }
            let totalSize = (dict["total_size"] as? Int) ?? 0
            let fileCount = (dict["file_count"] as? Int) ?? 0
            let collectionCount = (dict["collection_count"] as? Int) ?? 0
            let linkedCount = (dict["linked_count"] as? Int) ?? 0
            let copiedCount = (dict["copied_count"] as? Int) ?? 0

            logger.info("Storage stats: \(totalSize) bytes, \(fileCount) files")
            return StorageStats(
                totalSize: Int64(totalSize),
                fileCount: fileCount,
                collectionCount: collectionCount,
                linkedCount: linkedCount,
                copiedCount: copiedCount
            )
        default:
            throw StorageServiceError.unexpectedResponse
        }
    }

    // MARK: - Error Handling

    /// Clear last error
    func clearError() {
        lastError = nil
    }
}

// MARK: - Error Types

enum StorageServiceError: Error, LocalizedError {
    case invalidResponse
    case invalidImageData
    case downloadFailed
    case unexpectedResponse
    case notFound(url: URL, contentType: String)
    case unexpectedStatus(status: Int, contentType: String, bodyPeek: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from storage service"
        case .invalidImageData:
            return "Could not decode image data"
        case .downloadFailed:
            return "File download failed"
        case .unexpectedResponse:
            return "Unexpected response from storage service"
        case .notFound(let url, _):
            return "Storage 404 for \(url.lastPathComponent) (no thumbnail/display image generated yet)"
        case let .unexpectedStatus(status, contentType, bodyPeek):
            return "Storage HTTP \(status) (content-type=\(contentType)): \(bodyPeek)"
        }
    }
}
