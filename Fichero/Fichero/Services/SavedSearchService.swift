import Foundation
import Combine

/// Service for managing saved searches via the backend API.
@MainActor
class SavedSearchService: ObservableObject {
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

    /// Duplicate a saved search.
    func duplicateSavedSearch(_ id: String) async throws -> SavedSearchAPI {
        return try await api.post("/search/saved/\(id)/duplicate")
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

    /// Rename a saved search.
    func renameSavedSearch(_ id: String, newName: String) async throws -> SavedSearchAPI {
        let update = SavedSearchUpdate(name: newName)
        return try await api.patch("/search/saved/\(id)", body: update)
    }

    /// Reorder saved searches.
    func reorderSavedSearches(_ searchIds: [String], folderPath: String = "/") async throws {
        let request: SavedSearchReorderRequest = SavedSearchReorderRequest(searchIds: searchIds, folderPath: folderPath)
        try await api.postVoid("/search/saved/reorder", body: request)
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

struct SavedSearchUpdate: Encodable {
    let name: String
}

struct SavedSearchReorderRequest: Encodable {
    let searchIds: [String]
    let folderPath: String

    enum CodingKeys: String, CodingKey {
        case searchIds = "search_ids"
        case folderPath = "folder_path"
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
