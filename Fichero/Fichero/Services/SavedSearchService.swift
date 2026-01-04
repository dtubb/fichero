import Foundation
import Combine

/// Service for managing saved searches via the backend API.
@MainActor
class SavedSearchService: ObservableObject {
    private let api: APIClient

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Published State

    /// All saved searches loaded from backend
    @Published var savedSearches: [SavedSearch] = []

    /// Save a search.
    func saveSearch(
        query: String,
        isSmartSearch: Bool = true,
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortOrder: String = "desc"
    ) async throws -> SavedSearchAPI {
        let request = SaveSearchRequest(
            query: query,
            isSmartSearch: isSmartSearch,
            searchType: searchType,
            sortBy: sortBy,
            sortOrder: sortOrder
        )
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

    /// Load saved searches from backend and update @Published property
    func loadSavedSearches() async throws {
        let apiSearches = try await listSavedSearches()
        savedSearches = apiSearches.map { api in
            SavedSearch(
                id: api.id,
                name: api.query,  // Use query as display name
                query: api.query,
                filters: SearchFilters(),  // Filters parsing not yet implemented
                isSmartSearch: api.isSmartSearch,
                folderPath: api.folderPath,
                sortOrder: api.sortOrderInt
            )
        }
    }

    /// Convert API responses to local SavedSearch models for sidebar.
    func getSavedSearchesForSidebar() async throws -> [SavedSearch] {
        let apiSearches = try await listSavedSearches()
        return apiSearches.map { api in
            SavedSearch(
                id: api.id,
                name: api.query,  // Use query as display name
                query: api.query,
                filters: SearchFilters(),  // Filters parsing not yet implemented
                isSmartSearch: api.isSmartSearch,
                folderPath: api.folderPath,
                sortOrder: api.sortOrderInt
            )
        }
    }

    /// Rename a saved search.
    func renameSavedSearch(_ id: String, newName: String) async throws -> SavedSearchAPI {
        let update = SavedSearchUpdate(query: newName)
        return try await api.put("/search/saved/\(id)", body: update)
    }

    /// Update a saved search.
    func updateSavedSearch(
        _ id: String,
        query: String? = nil,
        isSmartSearch: Bool? = nil,
        filters: [String: String]? = nil,
        searchType: String? = nil,
        sortBy: String? = nil,
        sortOrder: String? = nil,
        folderPath: String? = nil
    ) async throws -> SavedSearchAPI {
        let update = SavedSearchUpdate(
            query: query,
            isSmartSearch: isSmartSearch,
            filters: filters,
            searchType: searchType,
            sortBy: sortBy,
            sortOrder: sortOrder,
            folderPath: folderPath
        )
        return try await api.put("/search/saved/\(id)", body: update)
    }

    /// Move saved search to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> SavedSearchAPI {
        return try await updateSavedSearch(id, folderPath: folderPath)
    }

    /// Reorder saved searches.
    func reorderSavedSearches(_ searchIds: [String], folderPath: String = "/") async throws {
        let request: SavedSearchReorderRequest = SavedSearchReorderRequest(
            searchIds: searchIds,
            folderPath: folderPath
        )
        try await api.postVoid("/search/saved/reorder", body: request)
    }
}

// MARK: - Request Models

struct SaveSearchRequest: Encodable {
    let query: String
    let isSmartSearch: Bool
    let searchType: String
    let sortBy: String
    let sortOrder: String

    enum CodingKeys: String, CodingKey {
        case query
        case isSmartSearch = "is_smart_search"
        case searchType = "search_type"
        case sortBy = "sort_by"
        case sortOrder = "sort_order"
    }

    init(
        query: String,
        isSmartSearch: Bool = true,
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortOrder: String = "desc"
    ) {
        self.query = query
        self.isSmartSearch = isSmartSearch
        self.searchType = searchType
        self.sortBy = sortBy
        self.sortOrder = sortOrder
    }
}

struct SavedSearchUpdate: Encodable {
    let query: String?
    let isSmartSearch: Bool?
    let filters: [String: String]?
    let searchType: String?
    let sortBy: String?
    let sortOrder: String?
    let folderPath: String?

    enum CodingKeys: String, CodingKey {
        case query
        case isSmartSearch = "is_smart_search"
        case filters
        case searchType = "search_type"
        case sortBy = "sort_by"
        case sortOrder = "sort_order"
        case folderPath = "folder_path"
    }

    init(
        query: String? = nil,
        isSmartSearch: Bool? = nil,
        filters: [String: String]? = nil,
        searchType: String? = nil,
        sortBy: String? = nil,
        sortOrder: String? = nil,
        folderPath: String? = nil
    ) {
        self.query = query
        self.isSmartSearch = isSmartSearch
        self.filters = filters
        self.searchType = searchType
        self.sortBy = sortBy
        self.sortOrder = sortOrder
        self.folderPath = folderPath
    }
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
    let searchType: String
    let sortBy: String
    let sortOrder: String  // "asc" or "desc"
    let folderPath: String
    let sortOrderInt: Int  // Position within folder
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case query
        case isSmartSearch = "is_smart_search"
        case filters
        case searchType = "search_type"
        case sortBy = "sort_by"
        case sortOrder = "sort_order"
        case folderPath = "folder_path"
        case sortOrderInt = "sort_order_int"
        case createdAt = "created_at"
    }
}
