import Foundation

/// Service for search operations via the Fichero backend.
actor SearchService {
    private let api = APIClient.shared

    // MARK: - Semantic Search

    /// Perform semantic search over documents.
    func search(query: String, limit: Int = 10, minScore: Double = 0.0) async throws -> SearchResponse {
        let request = SearchRequest(query: query, limit: limit, minScore: minScore)
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

    enum CodingKeys: String, CodingKey {
        case query
        case limit
        case minScore = "min_score"
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
