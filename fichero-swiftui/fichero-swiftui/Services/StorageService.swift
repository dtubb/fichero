import Foundation
import SwiftUI
import OSLog

/// Service for storage operations (thumbnails, previews, source files)
/// Wraps the Python backend storage API
@MainActor
class StorageService: ObservableObject {
    // MARK: - Published State

    @Published var isLoading: Bool = false
    @Published var lastError: Error?

    private let api: APIClient
    private let session = URLSession.shared
    private let logger = Logger(subsystem: "com.tubb.Fichero", category: "StorageService")

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Image Loading

    /// Get thumbnail image for a document
    /// - Parameter docId: Document ID
    /// - Returns: SwiftUI Image
    func getThumbnail(_ docId: String) async throws -> Image {
        logger.info("Loading thumbnail for document: \(docId)")

        let url = api.thumbnailURL(for: docId)
        var request = URLRequest(url: url)

        // Add library path header for multi-library support
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageError.invalidResponse
        }

        #if canImport(AppKit)
        guard let nsImage = NSImage(data: data) else {
            throw StorageError.invalidImageData
        }
        return Image(nsImage: nsImage)
        #else
        guard let uiImage = UIImage(data: data) else {
            throw StorageError.invalidImageData
        }
        return Image(uiImage: uiImage)
        #endif
    }

    /// Get display-quality image for a document
    /// - Parameter docId: Document ID
    /// - Returns: SwiftUI Image
    func getDisplayImage(_ docId: String) async throws -> Image {
        logger.info("Loading display image for document: \(docId)")

        let url = api.displayURL(for: docId)
        var request = URLRequest(url: url)

        // Add library path header for multi-library support
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageError.invalidResponse
        }

        #if canImport(AppKit)
        guard let nsImage = NSImage(data: data) else {
            throw StorageError.invalidImageData
        }
        return Image(nsImage: nsImage)
        #else
        guard let uiImage = UIImage(data: data) else {
            throw StorageError.invalidImageData
        }
        return Image(uiImage: uiImage)
        #endif
    }

    // MARK: - URL Providers

    /// Get thumbnail URL for AsyncImage
    /// - Parameter docId: Document ID
    /// - Returns: URL for thumbnail
    func thumbnailURL(for docId: String) -> URL {
        api.thumbnailURL(for: docId)
    }

    /// Get display image URL for AsyncImage
    /// - Parameter docId: Document ID
    /// - Returns: URL for display image
    func displayURL(for docId: String) -> URL {
        api.displayURL(for: docId)
    }

    /// Get source file URL
    /// - Parameter docId: Document ID
    /// - Returns: URL for original source file
    func sourceURL(for docId: String) -> URL {
        api.sourceURL(for: docId)
    }

    // MARK: - File Access

    /// Download the original source file
    /// - Parameter docId: Document ID
    /// - Returns: Local file URL
    func downloadSourceFile(_ docId: String) async throws -> URL {
        isLoading = true
        defer { isLoading = false }

        logger.info("Downloading source file for document: \(docId)")

        let url = api.sourceURL(for: docId)
        var request = URLRequest(url: url)

        // Add library path header for multi-library support
        if let libraryPath = api.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (localURL, response) = try await session.download(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageError.invalidResponse
        }

        logger.info("Downloaded source file to: \(localURL.path)")
        return localURL
    }

    // MARK: - Storage Stats

    /// Get storage statistics
    /// - Returns: Storage stats (total size, file count, etc.)
    func getStats() async throws -> StorageStats {
        logger.info("Fetching storage stats")
        let stats: StorageStats = try await api.get("/storage/stats")
        logger.info("Storage stats: \(stats.totalSize) bytes, \(stats.fileCount) files")
        return stats
    }

    // MARK: - Error Handling

    /// Clear last error
    func clearError() {
        lastError = nil
    }
}

// MARK: - Supporting Types

/// Storage statistics
struct StorageStats: Codable {
    let totalSize: Int64
    let fileCount: Int
    let collectionCount: Int
    let linkedCount: Int
    let copiedCount: Int

    enum CodingKeys: String, CodingKey {
        case totalSize = "total_size"
        case fileCount = "file_count"
        case collectionCount = "collection_count"
        case linkedCount = "linked_count"
        case copiedCount = "copied_count"
    }

    /// Formatted total size (e.g., "1.5 GB")
    var formattedSize: String {
        ByteCountFormatter.string(fromByteCount: totalSize, countStyle: .file)
    }
}

/// Storage service errors
enum StorageError: Error, LocalizedError {
    case invalidResponse
    case invalidImageData
    case downloadFailed

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from storage service"
        case .invalidImageData:
            return "Could not decode image data"
        case .downloadFailed:
            return "File download failed"
        }
    }
}
