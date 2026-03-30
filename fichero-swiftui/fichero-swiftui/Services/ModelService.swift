import Foundation

// MARK: - Models

struct HFTaskCategory: Codable, Identifiable, Hashable {
    let id: String       // e.g., "text-generation"
    let label: String    // e.g., "Text Generation"
}

struct HFModelInfo: Codable, Identifiable {
    let id: String                  // e.g., "meta-llama/Llama-3.1-8B-Instruct"
    let downloads: Int
    let likes: Int
    let pipelineTag: String?        // Task type
    let libraryName: String?        // Primary library
    let createdAt: String?
    let tags: [String]

    enum CodingKeys: String, CodingKey {
        case id
        case downloads
        case likes
        case pipelineTag = "pipeline_tag"
        case libraryName = "library_name"
        case createdAt = "created_at"
        case tags
    }

    /// Human-readable download count
    var formattedDownloads: String {
        if downloads >= 1_000_000 {
            return String(format: "%.1fM", Double(downloads) / 1_000_000)
        } else if downloads >= 1_000 {
            return String(format: "%.1fK", Double(downloads) / 1_000)
        }
        return "\(downloads)"
    }

    /// Model name without author prefix
    var shortName: String {
        if let slash = id.lastIndex(of: "/") {
            return String(id[id.index(after: slash)...])
        }
        return id
    }

    /// Author/organization name
    var author: String {
        if let slash = id.firstIndex(of: "/") {
            return String(id[..<slash])
        }
        return ""
    }
}

struct HFModelSearchResponse: Codable {
    let models: [HFModelInfo]
    let total: Int
    let hasMore: Bool

    enum CodingKeys: String, CodingKey {
        case models
        case total
        case hasMore = "has_more"
    }
}

enum HFSortOrder: String, CaseIterable, Identifiable {
    case downloads
    case likes
    case trending
    case lastModified

    var id: String { rawValue }

    var label: String {
        switch self {
        case .downloads: return "Most Downloads"
        case .likes: return "Most Likes"
        case .trending: return "Trending"
        case .lastModified: return "Recently Updated"
        }
    }
}

// MARK: - Popular Task Categories (for UI)

extension HFTaskCategory {
    /// Most commonly used tasks for our use case
    static let popularTasks: [HFTaskCategory] = [
        HFTaskCategory(id: "text-generation", label: "Text Generation"),
        HFTaskCategory(id: "image-to-text", label: "Image to Text"),
        HFTaskCategory(id: "feature-extraction", label: "Embeddings"),
        HFTaskCategory(id: "automatic-speech-recognition", label: "Speech Recognition"),
        HFTaskCategory(id: "text-to-image", label: "Image Generation"),
        HFTaskCategory(id: "translation", label: "Translation"),
        HFTaskCategory(id: "summarization", label: "Summarization")
    ]
}
