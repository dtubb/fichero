import Foundation
import Combine

/// Service for search operations via the Fichero backend.
@MainActor
class SearchService: ObservableObject {
    private let api = APIClient.shared

    // MARK: - Semantic Search

    /// Perform enhanced search over documents.
    func search(
        query: String,
        limit: Int = 10,
        minScore: Double = 0.0,
        searchType: String = "hybrid",
        filters: [String: String]? = nil,
        sortBy: String = "relevance",
        sortOrder: String = "desc",
        offset: Int = 0,
        useFuzzyMatch: Bool = false,
        highlightResults: Bool = true
    ) async throws -> SearchResponse {
        let request = SearchRequest(
            query: query,
            limit: limit,
            minScore: minScore,
            searchType: searchType,
            filters: filters,
            sortBy: sortBy,
            sortOrder: sortOrder,
            offset: offset,
            useFuzzyMatch: useFuzzyMatch,
            highlightResults: highlightResults
        )
        return try await api.post("/search", body: request)
    }

    // MARK: - Stats

    /// Get embedding/search statistics.
    func stats() async throws -> StatsResponse {
        try await api.get("/search/stats")
    }

    // MARK: - Indexing

    /// Reindex all documents (runs in background on server).
    func reindexAll() async throws -> ReindexStatus {
        try await api.post("/search/reindex", body: EmptyBody())
    }

    /// Embed a specific document.
    func embedDocument(_ documentId: String) async throws -> EmbedStatus {
        try await api.post("/search/embed/\(documentId)", body: EmptyBody())
    }
}

// MARK: - Request Models

struct SearchRequest: Codable {
    let query: String
    let limit: Int
    let minScore: Double
    let searchType: String
    let filters: [String: String]?
    let sortBy: String
    let sortOrder: String
    let offset: Int
    let useFuzzyMatch: Bool
    let highlightResults: Bool

    enum CodingKeys: String, CodingKey {
        case query
        case limit
        case minScore = "min_score"
        case searchType = "search_type"
        case filters
        case sortBy = "sort_by"
        case sortOrder = "sort_order"
        case offset
        case useFuzzyMatch = "use_fuzzy_match"
        case highlightResults = "highlight_results"
    }

    init(query: String, limit: Int = 10, minScore: Double = 0.0, searchType: String = "hybrid", filters: [String: String]? = nil, sortBy: String = "relevance", sortOrder: String = "desc", offset: Int = 0, useFuzzyMatch: Bool = false, highlightResults: Bool = true) {
        self.query = query
        self.limit = limit
        self.minScore = minScore
        self.searchType = searchType
        self.filters = filters
        self.sortBy = sortBy
        self.sortOrder = sortOrder
        self.offset = offset
        self.useFuzzyMatch = useFuzzyMatch
        self.highlightResults = highlightResults
    }
}

struct EmptyBody: Codable {}

// MARK: - Additional Response Models

struct ReindexStatus: Codable {
    let status: String
    let message: String?
}

struct EmbedStatus: Codable {
    let documentId: String
    let embedded: Bool

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case embedded
    }
}
