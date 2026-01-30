import Foundation
import SwiftUI
import OSLog
import FicheroAPIClient
import OpenAPIRuntime
import OpenAPIURLSession

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "StorageServiceGenerated")

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
    private let baseURL: URL

    init(ficheroClient: FicheroClient, baseURL: URL = URL(string: "http://127.0.0.1:8765/api")!) {
        self.client = ficheroClient
        self.baseURL = baseURL
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient, baseURL: apiClient.baseURL)
    }

    // MARK: - Image Loading

    /// Get thumbnail image for a document
    func getThumbnail(_ docId: String) async throws -> Image {
        logger.info("Loading thumbnail for document: \(docId)")

        let url = thumbnailURL(for: docId)
        var request = URLRequest(url: url)

        // Add library path header
        if let libraryPath = client.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageServiceError.invalidResponse
        }

        #if canImport(AppKit)
        guard let nsImage = NSImage(data: data) else {
            throw StorageServiceError.invalidImageData
        }
        return Image(nsImage: nsImage)
        #else
        guard let uiImage = UIImage(data: data) else {
            throw StorageServiceError.invalidImageData
        }
        return Image(uiImage: uiImage)
        #endif
    }

    /// Get display-quality image for a document
    func getDisplayImage(_ docId: String) async throws -> Image {
        logger.info("Loading display image for document: \(docId)")

        let url = displayURL(for: docId)
        var request = URLRequest(url: url)

        // Add library path header
        if let libraryPath = client.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

        let (data, response) = try await session.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw StorageServiceError.invalidResponse
        }

        #if canImport(AppKit)
        guard let nsImage = NSImage(data: data) else {
            throw StorageServiceError.invalidImageData
        }
        return Image(nsImage: nsImage)
        #else
        guard let uiImage = UIImage(data: data) else {
            throw StorageServiceError.invalidImageData
        }
        return Image(uiImage: uiImage)
        #endif
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

        // Add library path header
        if let libraryPath = client.currentLibraryPath {
            request.setValue(libraryPath, forHTTPHeaderField: "X-Fichero-Library-Path")
        }

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

        let response = try await client.api.storageStatsApiStorageStatsGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

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
        }
    }
}
