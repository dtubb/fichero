import Foundation
import Combine

/// Service for browsing and selecting LLM models via the backend API.
/// Supports Hugging Face model discovery with search and filtering.
@MainActor
class ModelService: ObservableObject {
    private let api = APIClient.shared

    // MARK: - Hugging Face Models

    /// List available task categories for filtering
    func listHuggingFaceTasks() async throws -> [HFTaskCategory] {
        try await api.get("/models/huggingface/tasks")
    }

    /// Search Hugging Face models
    func searchHuggingFaceModels(
        task: String? = nil,
        search: String? = nil,
        sort: HFSortOrder = .downloads,
        limit: Int = 20,
        offset: Int = 0,
        library: String? = nil
    ) async throws -> HFModelSearchResponse {
        var params: [String: String] = [
            "sort": sort.rawValue,
            "limit": String(limit),
            "offset": String(offset),
        ]
        if let task = task { params["task"] = task }
        if let search = search { params["search"] = search }
        if let library = library { params["library"] = library }

        let queryString = params.map { "\($0.key)=\($0.value)" }.joined(separator: "&")
        return try await api.get("/models/huggingface?\(queryString)")
    }

    /// Get details for a specific model
    func getHuggingFaceModel(_ modelId: String) async throws -> HFModelInfo {
        try await api.get("/models/huggingface/\(modelId)")
    }
}

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
    case downloads = "downloads"
    case likes = "likes"
    case trending = "trending"
    case lastModified = "lastModified"

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
        HFTaskCategory(id: "summarization", label: "Summarization"),
    ]
}
