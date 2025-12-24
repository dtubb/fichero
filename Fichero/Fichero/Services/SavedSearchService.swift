import Foundation

/// Service for managing saved searches via the backend API.
actor SavedSearchService {
    private let api = APIClient.shared

    /// Save a search.
    func saveSearch(query: String, isSmartSearch: Bool = true) async throws -> SavedSearchAPI {
        let request = SaveSearchRequest(query: query, isSmartSearch: isSmartSearch)
        return try await api.post("/search/saved", body: request)
    }

    /// List all saved searches.
    func listSavedSearches() async throws -> [SavedSearchAPI] {
        try await api.get("/search/saved")
    }

    /// Delete a saved search.
    func deleteSavedSearch(_ id: String) async throws {
        try await api.delete("/search/saved/\(id)")
    }

    /// Convert API responses to local SavedSearch models for sidebar.
    func getSavedSearchesForSidebar() async throws -> [SavedSearch] {
        let apiSearches = try await listSavedSearches()
        return apiSearches.map { api in
            SavedSearch(
                id: api.id,
                name: api.query,  // Use query as display name
                query: api.query,
                filters: SearchFilters(),  // TODO: Parse filters from API
                isSmartSearch: api.isSmartSearch
            )
        }
    }
}

// MARK: - Request Models

struct SaveSearchRequest: Encodable {
    let query: String
    let isSmartSearch: Bool

    enum CodingKeys: String, CodingKey {
        case query
        case isSmartSearch = "is_smart_search"
    }
}

// MARK: - Response Models

struct SavedSearchAPI: Codable, Identifiable {
    let id: String
    let query: String
    let isSmartSearch: Bool
    let filters: [String: String]?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case query
        case isSmartSearch = "is_smart_search"
        case filters
        case createdAt = "created_at"
    }
}
