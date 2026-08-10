import FicheroAPIClient
import Foundation
import ImageIO
import Observation
import OpenAPIRuntime
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageService")

/// StorageService using the generated OpenAPI client.
/// Handles storage operations (thumbnails, previews, source files).
/// Note: Image and source bytes travel through the generated OpenAPI client
/// so auth, pinning, and library-path middleware stay central (#1710).
@MainActor
@Observable
class StorageService {
    // MARK: - Published State

    var isLoading: Bool = false
    var lastError: Error?

    private let client: FicheroClient
    private let configuredBaseURL: URL?

    /// In-memory cache keyed by `docId`. Prevents the "Loading thumbnail
    /// for document: X" storms the user was seeing — `.task` re-fires on
    /// every grid view identity reset (e.g., when filteredDocuments
    /// re-computes or LazyVGrid re-lays out), each firing a fresh
    /// network request + byte decode. With the cache, re-fires return
    /// instantly. Scoped to this service instance (one per library), so
    /// switching libraries naturally resets.
    private var thumbnailCache: [String: Image] = [:]
    // One in-flight task per image key (#4572): concurrent same-key loads
    // share the first task instead of each fetching. The engine log showed
    // EVERY thumbnail fetched exactly twice before this.
    private let thumbnailFlights = InFlightCoalescer<Image>()
    private let displayFlights = InFlightCoalescer<Image>()
    private let displayPlatformFlights = InFlightCoalescer<PlatformImage>()
    private var displayCache: [String: Image] = [:]
    private var displayPlatformImageCache: [String: PlatformImage] = [:]
    private var sourceDataCache: [String: Data] = [:]

    /// Upper bound on the thumbnail cache so opening a folder with thousands
    /// of images can't grow it without limit (#719). When exceeded, the
    /// oldest-inserted entries are evicted first (FIFO) — by the time the
    /// cache is this full the user has scrolled well past those rows.
    static let thumbnailCacheLimit = 1000
    /// Upper bound on the display-platform-image cache (#2469). 32, up from
    /// 12 (Daniel, 2026-08-10: page flips showed the OLD page then reloaded
    /// — cache misses on revisit): 12 entries meant a ±2 prefetch window
    /// plus a handful of displays evicted the page just left. ponytail:
    /// count-bounded FIFO stays; a byte budget is the upgrade if memory
    /// shows up in reviews.
    static let displayPlatformImageCacheLimit = 32
    static let maxImageBytes = 50 * 1024 * 1024
    static let maxSourceBytes = 500 * 1024 * 1024
    /// Insertion order of thumbnail-cache keys, oldest first. Drives FIFO
    /// eviction in `cacheThumbnail`.
    private var thumbnailCacheOrder: [String] = []
    /// Insertion order for `displayPlatformImageCache`. FIFO eviction.
    private var displayPlatformImageCacheOrder: [String] = []

    /// Number of cached thumbnails. Exposed for tests (#719 eviction).
    var thumbnailCacheCount: Int { thumbnailCache.count }

    /// Cached thumbnail for `docId`, if present. Exposed for tests (#719).
    func cachedThumbnail(for docId: String) -> Image? { thumbnailCache[docId] }

    /// Number of cached display platform images. Exposed for tests (#2469).
    var displayPlatformImageCacheCount: Int { displayPlatformImageCache.count }

    /// Cached display platform image for `docId`, if present. Exposed for tests (#2469).
    func cachedDisplayPlatformImage(for docId: String) -> PlatformImage? { displayPlatformImageCache[docId] }

    private var baseURL: URL {
        configuredBaseURL ?? EngineConfig.apiBaseURL
    }

    /// Shared per-document PDF cache (#3209): one download + one decode of a
    /// PDF's source bytes, reused by the Preview viewer, loupe, and thumbnails
    /// instead of each fetching + decoding its own copy. Lazily created so a
    /// library that never opens a PDF pays nothing; fetches route back through
    /// `getSourceData` (storage HTTP endpoint, never a local path).
    @ObservationIgnored lazy var pdfCache: PDFDocumentCache = PDFDocumentCache(
        fetch: { [weak self] documentId in
            guard let self else { throw StorageServiceError.unexpectedResponse }
            return try await self.getSourceData(documentId)
        }
    )

    /// The library this service is scoped to, for callers that cache across
    /// services (e.g. `SpaceTextureCache` keys textures per-library so the
    /// same sourceId in two libraries can't collide). Empty = global/unscoped.
    var libraryScopeKey: String { client.currentLibraryPath ?? "" }

    init(ficheroClient: FicheroClient, baseURL: URL? = nil) {
        self.client = ficheroClient
        self.configuredBaseURL = baseURL
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(
            baseURL: EngineConfig.host,
            libraryPath: libraryPath,
            transportMode: EngineConfig.transportMode
        )
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Image Loading

    /// Get thumbnail image for a document. Memoised per-service-instance.
    func getThumbnail(_ docId: String) async throws -> Image {
        if let cached = thumbnailCache[docId] {
            return cached
        }
        return try await thumbnailFlights.run(docId) { [weak self] in
            guard let self else { throw StorageServiceError.unexpectedResponse }
            if let cached = self.thumbnailCache[docId] { return cached }
            // .debug, not .info: fires per uncached thumbnail during hot scroll (#3870).
            logger.debug("Loading thumbnail for document: \(docId)")
            let data = try await self.thumbnailData(for: docId)
            let image = try await Self.decodeImage(from: data)
            self.cacheThumbnail(image, for: docId)
            return image
        }
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
    /// Spatial 3D scene fetches undecoded bytes through this authenticated
    /// storage path instead of hand-building a URL and calling `URLSession`
    /// directly (#1902).
    func thumbnailData(for docId: String) async throws -> Data {
        let response = try await client.api.getThumbnailApiStorageThumbnailDocIdGet(.init(
            path: .init(docId: docId)
        ))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.jpeg
            return try await Data(collecting: body, upTo: Self.maxImageBytes)
        case .notFound:
            throw StorageServiceError.notFound(url: thumbnailURL(for: docId), contentType: "application/json")
        default:
            throw StorageServiceError.unexpectedResponse
        }
    }

    /// Get display-quality image for a document. Memoised per-service-instance.
    func getDisplayImage(_ docId: String) async throws -> Image {
        if let cached = displayCache[docId] {
            return cached
        }
        return try await displayFlights.run(docId) { [weak self] in
            guard let self else { throw StorageServiceError.unexpectedResponse }
            if let cached = self.displayCache[docId] { return cached }
            logger.info("Loading display image for document: \(docId)")
            let data = try await self.displayData(for: docId)
            let image = try await Self.decodeImage(from: data)
            self.displayCache[docId] = image
            return image
        }
    }

    /// Get display-quality image for zoomable canvases.
    /// Uses the same generated storage endpoint as `getDisplayImage`, not the
    /// image-edit preview endpoint.
    func getDisplayPlatformImage(_ docId: String) async throws -> PlatformImage {
        if let cached = displayPlatformImageCache[docId] {
            return cached
        }
        return try await displayPlatformFlights.run(docId) { [weak self] in
            guard let self else { throw StorageServiceError.unexpectedResponse }
            if let cached = self.displayPlatformImageCache[docId] { return cached }
            logger.info("Loading display image for document: \(docId)")
            let data = try await self.displayData(for: docId)
            // Decode OFF the main actor — `PlatformImage(data:)` parses the
            // full bitmap synchronously, and doing it here on the MainActor
            // was the measured 959ms "Loading display image" stall
            // (2026-08-08 session; the exact #605 anti-pattern this file's
            // own decodeImage comment warns about). The bitmap is parsed in
            // the detached CGImage decode; wrapping it on main is cheap.
            let cgImage = try await Self.decodeCGImage(from: data)
            #if os(macOS)
            let image = PlatformImage(cgImage: cgImage, size: .zero)
            #else
            let image = PlatformImage(cgImage: cgImage)
            #endif
            self.cacheDisplayPlatformImage(image, for: docId)
            return image
        }
    }

    /// Insert a display platform image into the bounded cache, evicting the
    /// oldest entries (FIFO) once the cache exceeds `displayPlatformImageCacheLimit`.
    /// Internal so the eviction bound can be unit-tested without a live backend. (#2469)
    func cacheDisplayPlatformImage(_ image: PlatformImage, for docId: String) {
        if displayPlatformImageCache[docId] == nil {
            displayPlatformImageCacheOrder.append(docId)
        }
        displayPlatformImageCache[docId] = image
        while displayPlatformImageCacheOrder.count > Self.displayPlatformImageCacheLimit {
            let oldest = displayPlatformImageCacheOrder.removeFirst()
            displayPlatformImageCache.removeValue(forKey: oldest)
        }
    }

    /// Warm the display-image cache for a batch of document ids (#2469).
    /// Fires concurrent fetches (max 4 at a time) only for uncached ids.
    /// Errors are swallowed — this is best-effort prefetch, not critical load.
    func prefetchDisplayImages(_ docIds: [String]) async {
        let uncached = docIds.filter { displayPlatformImageCache[$0] == nil }
        guard !uncached.isEmpty else { return }
        await withTaskGroup(of: Void.self) { group in
            var inFlight = 0
            for docId in uncached {
                if inFlight >= 4 {
                    await group.next()
                    inFlight -= 1
                }
                group.addTask { [weak self] in
                    guard let self else { return }
                    _ = try? await self.getDisplayPlatformImage(docId)
                }
                inFlight += 1
            }
        }
    }

    /// Fetch display image bytes via the generated OpenAPI client.
    private func displayData(for docId: String) async throws -> Data {
        let response = try await client.api.getDisplayImageApiStorageDisplayDocIdGet(.init(
            path: .init(docId: docId)
        ))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.jpeg
            return try await Data(collecting: body, upTo: Self.maxImageBytes)
        case .notFound:
            throw StorageServiceError.notFound(url: displayURL(for: docId), contentType: "application/json")
        default:
            throw StorageServiceError.unexpectedResponse
        }
    }

    /// Get original source-file bytes for a document. Memoised per-service
    /// instance so PDFKit surfaces can share one download.
    func getSourceData(_ docId: String) async throws -> Data {
        if let cached = sourceDataCache[docId] {
            return cached
        }
        logger.info("Loading source data for document: \(docId)")
        let response = try await client.api.getSourceFileApiStorageSourceDocIdGet(.init(
            path: .init(docId: docId)
        ))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.any
            let data = try await Data(collecting: body, upTo: Self.maxSourceBytes)
            sourceDataCache[docId] = data
            return data
        case .notFound:
            throw StorageServiceError.notFound(url: sourceURL(for: docId), contentType: "application/json")
        default:
            throw StorageServiceError.unexpectedResponse
        }
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
        displayPlatformImageCache.removeValue(forKey: docId)
        sourceDataCache.removeValue(forKey: docId)
        thumbnailCacheOrder.removeAll { $0 == docId }
        displayPlatformImageCacheOrder.removeAll { $0 == docId }
    }

    /// Clear every in-memory byte/image cache, used when the app switches engine hosts.
    func clearAll() {
        thumbnailCache.removeAll()
        displayCache.removeAll()
        displayPlatformImageCache.removeAll()
        sourceDataCache.removeAll()
        thumbnailCacheOrder.removeAll()
        displayPlatformImageCacheOrder.removeAll()
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
    /// Decode to a CGImage off-main — the bitmap parse happens detached; the
    /// caller wraps the (immutable, Sendable) CGImage in its platform type.
    nonisolated private static func decodeCGImage(from data: Data) async throws -> CGImage {
        try await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw StorageServiceError.invalidImageData
            }
            return cgImage
        }.value
    }

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

    /// Transport-agnostic `fichero-res://` URLs (resolved through the generated
    /// client by the scheme adapters), so a URL handed to `AsyncImage`/WebKit/
    /// AVFoundation works over `.https`, `.uds`, and in-memory transports alike.
    /// These also back the human-readable `notFound` error strings below.

    func thumbnailURL(for docId: String) -> URL {
        StorageResourceRegistry.shared.url(for: client, kind: .thumbnail, documentId: docId)
    }

    func displayURL(for docId: String) -> URL {
        StorageResourceRegistry.shared.url(for: client, kind: .display, documentId: docId)
    }

    func sourceURL(for docId: String) -> URL {
        StorageResourceRegistry.shared.url(for: client, kind: .source, documentId: docId)
    }

    // MARK: - File Access

    /// Download the original source file
    func downloadSourceFile(_ docId: String) async throws -> URL {
        isLoading = true
        defer { isLoading = false }

        logger.info("Downloading source file for document: \(docId)")

        let response = try await client.api.getSourceFileApiStorageSourceDocIdGet(.init(
            path: .init(docId: docId)
        ))
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.any
            let tempURL = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString)
                .appendingPathExtension("fichero")
            FileManager.default.createFile(atPath: tempURL.path, contents: nil, attributes: nil)
            let handle = try FileHandle(forWritingTo: tempURL)
            defer { try? handle.close() }
            for try await chunk in body {
                handle.write(Data(chunk))
            }
            logger.info("Downloaded source file to: \(tempURL.path)")
            return tempURL
        case .notFound:
            throw StorageServiceError.notFound(url: sourceURL(for: docId), contentType: "application/json")
        default:
            throw StorageServiceError.unexpectedResponse
        }
    }

}

// MARK: - Error Types

// MARK: - Source file (#3726)

extension StorageService {
    /// The source file streamed to a temp path, plus the server's
    /// `Content-Disposition` (#3726). Same op as `downloadSourceFile`, but it
    /// surfaces the header — the preview cache names the file from it, and the
    /// extension is what selects the QuickLook renderer, so the caller cannot
    /// just invent a name.
    ///
    /// Non-2xx raises `SourceFileTransportError` carrying the status + raw body
    /// so the caller can surface the engine's JSON `detail` (#3206) rather than a
    /// bare status code. Bytes stream chunk-by-chunk — a scan or a large PDF is
    /// never held whole in memory.
    func fetchSourceFile(_ docId: String) async throws -> (fileURL: URL, contentDisposition: String?) {
        isLoading = true
        defer { isLoading = false }

        let response = try await client.api.getSourceFileApiStorageSourceDocIdGet(.init(
            path: .init(docId: docId)
        ))
        switch response {
        case .ok(let okResponse):
            let tempURL = FileManager.default.temporaryDirectory
                .appendingPathComponent(UUID().uuidString)
                .appendingPathExtension("fichero")
            FileManager.default.createFile(atPath: tempURL.path, contents: nil, attributes: nil)
            let handle = try FileHandle(forWritingTo: tempURL)
            defer { try? handle.close() }
            let body = try okResponse.body.any
            for try await chunk in body {
                handle.write(Data(chunk))
            }
            return (tempURL, okResponse.headers.contentDisposition)
        case .notFound(let notFound):
            // Re-encode the typed detail as the `{"detail": ...}` body the shared
            // message builder already parses, so 404 and every other status take
            // one path.
            let detail = (try? notFound.body.json.detail) ?? "Source file not available"
            let body = try? JSONSerialization.data(withJSONObject: ["detail": detail])
            throw SourceFileTransportError(statusCode: 404, body: body)
        case .unprocessableContent(let error):
            // A 422 means the request genuinely failed validation — it must surface
            // as a thrown, user-visible error, never a silent fallback. Same path as
            // 404 so the engine's detail reaches the error UI (#3206).
            let detail = (try? error.body.json)?.detail?.description ?? "Validation error"
            let body = try? JSONSerialization.data(withJSONObject: ["detail": detail])
            throw SourceFileTransportError(statusCode: 422, body: body)
        case .undocumented(let statusCode, let payload):
            var body: Data?
            if let payloadBody = payload.body {
                body = try? await Data(collecting: payloadBody, upTo: 64 * 1024)
            }
            throw SourceFileTransportError(statusCode: statusCode, body: body)
        }
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

/// A non-2xx from the source-file op, carrying the status and the raw body so the
/// caller can surface the engine's JSON `detail` (#3206/#3726) instead of a bare
/// status code.
struct SourceFileTransportError: Error {
    let statusCode: Int
    let body: Data?
}

enum StorageServiceError: Error, LocalizedError {
    case invalidImageData
    case unexpectedResponse
    case notFound(url: URL, contentType: String)

    var errorDescription: String? {
        switch self {
        case .invalidImageData:
            return "Could not decode image data"
        case .unexpectedResponse:
            return "Unexpected response from storage service"
        case .notFound(let url, _):
            return "Storage 404 for \(url.lastPathComponent) (no thumbnail/display image generated yet)"
        }
    }
}
