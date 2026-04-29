import Foundation

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
