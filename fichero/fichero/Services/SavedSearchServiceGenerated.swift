import Observation
import Foundation
import Combine
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SavedSearchService")

/// SavedSearchService using the generated OpenAPI client.
/// This replaces the manual APIClient with type-safe generated calls.
@MainActor
@Observable
class SavedSearchServiceGenerated {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Published State

    /// All saved searches loaded from backend
    var savedSearches: [SavedSearch] = []

    // MARK: - API Methods

    /// Save a search.
    func saveSearch(
        query: String,
        isSmartSearch: Bool = true,
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortDirection: String = "desc"
    ) async throws -> SavedSearchAPI {
        let request = Components.Schemas.SavedSearchCreate(
            query: query,
            isSmartSearch: isSmartSearch,
            searchType: searchType,
            sortBy: sortBy,
            sortDirection: sortDirection
        )

        let response = try await client.api.saveSearchApiSearchSavedPost(.init(
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            return convertToSavedSearchAPI(try okResponse.body.json)
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// List all saved searches.
    func listSavedSearches() async throws -> [SavedSearchAPI] {
        let response = try await client.api.listSavedSearchesApiSearchSavedGet(.init())

        switch response {
        case .ok(let okResponse):
            let searches = try okResponse.body.json
            return searches.items.map { convertToSavedSearchAPI($0) }
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// Delete a saved search.
    func deleteSavedSearch(_ id: String) async throws {
        let response = try await client.api.deleteSavedSearchApiSearchSavedSearchIdDelete(.init(
            path: .init(searchId: id),
        ))

        switch response {
        case .ok:
            // Update local array to trigger UI refresh
            savedSearches.removeAll { $0.id == id }
            return
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// Duplicate a saved search.
    func duplicateSavedSearch(_ id: String) async throws -> SavedSearchAPI {
        let response = try await client.api.duplicateSavedSearchApiSearchSavedSearchIdDuplicatePost(.init(
            path: .init(searchId: id),
        ))

        switch response {
        case .ok(let okResponse):
            return convertToSavedSearchAPI(try okResponse.body.json)
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// Rename a saved search.
    func renameSavedSearch(_ id: String, newName: String) async throws -> SavedSearchAPI {
        return try await updateSavedSearch(id, query: newName)
    }

    /// Update a saved search.
    func updateSavedSearch(
        _ id: String,
        query: String? = nil,
        isSmartSearch: Bool? = nil,
        filters: [String: String]? = nil,
        searchType: String? = nil,
        sortBy: String? = nil,
        sortDirection: String? = nil,
        folderPath: String? = nil
    ) async throws -> SavedSearchAPI {
        // Use typed fields on SavedSearchUpdate. See 31fc4141 for why dumping
        // everything into additionalProperties silently dropped writes.
        var filtersPayload: Components.Schemas.SavedSearchUpdate.FiltersPayload?
        if let filters = filters {
            let castFilters: [String: any Sendable] = filters.reduce(into: [:]) { acc, pair in
                acc[pair.key] = pair.value
            }
            let container = try OpenAPIObjectContainer(unvalidatedValue: castFilters)
            filtersPayload = .init(additionalProperties: container)
        }

        let request = Components.Schemas.SavedSearchUpdate(
            query: query,
            isSmartSearch: isSmartSearch,
            filters: filtersPayload,
            searchType: searchType,
            sortBy: sortBy,
            sortDirection: sortDirection,
            folderPath: folderPath
        )

        let response = try await client.api.updateSavedSearchApiSearchSavedSearchIdPut(.init(
            path: .init(searchId: id),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let result = convertToSavedSearchAPI(try okResponse.body.json)

            // Update local array to trigger UI refresh
            if let index = savedSearches.firstIndex(where: { $0.id == id }) {
                if let newQuery = query {
                    savedSearches[index].query = newQuery
                    savedSearches[index].name = newQuery  // name is usually same as query
                }
                if let newFolderPath = folderPath {
                    savedSearches[index].folderPath = newFolderPath
                }
            }

            return result
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// Move saved search to a different folder.
    func moveToFolder(_ id: String, folderPath: String) async throws -> SavedSearchAPI {
        return try await updateSavedSearch(id, folderPath: folderPath)
    }

    /// Reorder saved searches.
    func reorderSavedSearches(_ searchIds: [String], folderPath: String = "/") async throws {
        // Note: The generated API expects just an array of search IDs as the body
        let response = try await client.api.reorderSavedSearchesApiSearchSavedReorderPost(.init(
            query: .init(folderPath: folderPath),
            body: .json(searchIds)
        ))

        switch response {
        case .ok:
            return
        default:
            throw SavedSearchServiceError.unexpectedResponse
        }
    }

    /// Load saved searches from backend and update property
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
                sortOrder: api.sortOrder
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
                sortOrder: api.sortOrder
            )
        }
    }

    // MARK: - Type Conversion

    /// Convert generated type to app type
    private func convertToSavedSearchAPI(_ generated: Components.Schemas.SavedSearchResponse) -> SavedSearchAPI {
        SavedSearchAPI(
            id: generated.id,
            query: generated.query,
            isSmartSearch: generated.isSmartSearch,
            filters: nil,  // TODO: Parse filters from generated type
            searchType: generated.searchType,
            sortBy: generated.sortBy,
            sortDirection: generated.sortDirection,
            folderPath: generated.folderPath,
            sortOrder: generated.sortOrder,
            createdAt: generated.createdAt
        )
    }
}

// MARK: - Error Types

enum SavedSearchServiceError: Error, LocalizedError {
    case unexpectedResponse
    case invalidData
    case notFound

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse:
            return "Unexpected response from server"
        case .invalidData:
            return "Invalid data received"
        case .notFound:
            return "Saved search not found"
        }
    }
}
