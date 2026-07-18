import Foundation
import UniformTypeIdentifiers

// MARK: - Supporting Types

/// Ingest mode - LINK creates bookmark reference, COPY imports file into library
enum IngestMode: String, Codable {
    case link = "LINK"  // Create bookmark reference (zero disk usage)
    case copy = "COPY"  // Copy file into library (uses APFS cloning)
    case move = "MOVE"  // Move file into library (original deleted)

    var displayName: String {
        switch self {
        case .link: return "Link Files"
        case .copy: return "Copy Files"
        case .move: return "Move Files"
        }
    }

    var description: String {
        switch self {
        case .link: return "Reference files in place (no disk usage)"
        case .copy: return "Duplicate files into library"
        case .move: return "Move files into library (original deleted)"
        }
    }

    var icon: String {
        switch self {
        case .link: return "link"
        case .copy: return "doc.on.doc"
        case .move: return "arrow.right.doc"
        }
    }
}

/// Request body for file import
struct IngestFileRequest: Codable {
    let path: String
    let mode: String
    let parentId: String?
    let extractText: Bool
    let autoEmbed: Bool
    let save: Bool

    enum CodingKeys: String, CodingKey {
        case path
        case mode
        case parentId = "parent_id"
        case extractText = "extract_text"
        case autoEmbed = "auto_embed"
        case save
    }
}

/// Request body for folder import
struct IngestFolderRequest: Codable {
    let path: String
    let copyMode: Bool
    let parentId: String?
    let recursive: Bool
    let extractText: Bool
    let autoEmbed: Bool

    enum CodingKeys: String, CodingKey {
        case path
        case copyMode = "copy_mode"
        case parentId = "parent_id"
        case recursive
        case extractText = "extract_text"
        case autoEmbed = "auto_embed"
    }
}

/// Import progress information
struct ImportProgress {
    let current: Int
    let total: Int
    let currentFile: String

    var percentage: Double {
        // Guard against total==0 (empty import) — an unguarded divide yields
        // NaN and corrupts the progress bar.
        guard total > 0 else { return 0 }
        return Double(current) / Double(total) * 100
    }

    var description: String {
        "Importing \(current)/\(total): \(currentFile)"
    }
}

/// Import error wrapper
struct ImportError: Error, LocalizedError, Identifiable {
    let id = UUID()
    let url: URL
    let error: Error

    var errorDescription: String? {
        "Failed to import \(url.lastPathComponent): \(error.localizedDescription)"
    }
}
