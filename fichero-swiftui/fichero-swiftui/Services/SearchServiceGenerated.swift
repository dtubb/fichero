import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "SearchServiceGenerated")

/// Service for search operations using generated OpenAPI client
@MainActor
class SearchServiceGenerated: ObservableObject {
    private let client: FicheroClient

    /// Initialize with FicheroClient (preferred)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Current library path from the client
    private var libraryPath: String {
        client.currentLibraryPath ?? ""
    }

    // MARK: - Search Operations

    /// Perform enhanced search over documents
    func search(
        query: String,
        limit: Int = 10,
        minScore: Double = 0.0,
        searchType: String = "hybrid",
        filters: [String: any Sendable]? = nil,
        sortBy: String = "relevance",
        sortDirection: String = "desc",
        offset: Int = 0
    ) async throws -> Components.Schemas.SearchResponse {
        let filtersPayload: Components.Schemas.SearchRequest.FiltersPayload? = try filters.map { dict in
            let container = try OpenAPIObjectContainer(unvalidatedValue: dict)
            return Components.Schemas.SearchRequest.FiltersPayload(additionalProperties: container)
        }

        let searchRequest = Components.Schemas.SearchRequest(
            query: query,
            limit: limit,
            minScore: minScore,
            searchType: searchType,
            filters: filtersPayload,
            sortBy: sortBy,
            sortDirection: sortDirection,
            offset: offset
        )

        let response = try await client.api.enhancedSearchApiSearchPost(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath),
                body: .json(searchRequest)
            )
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Get search/embedding statistics
    func stats() async throws -> EmbeddingStatsResponse {
        let response = try await client.api.searchStatsApiSearchStatsGet(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok(let okResponse):
            let container = try okResponse.body.json
            return extractEmbeddingStats(from: container)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Reindex all documents (runs in background on server)
    func reindexAll() async throws -> ReindexStatus {
        let response = try await client.api.reindexAllApiSearchReindexPost(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok(let okResponse):
            let container = try okResponse.body.json
            return extractReindexStatus(from: container)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Embed a specific document
    func embedDocument(_ documentId: String) async throws -> EmbedStatus {
        let response = try await client.api.embedDocumentApiSearchEmbedDocIdPost(
            .init(
                path: .init(docId: documentId),
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok(let okResponse):
            let container = try okResponse.body.json
            return extractEmbedStatus(from: container, defaultDocId: documentId)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Saved Searches

    /// List all saved searches
    func listSavedSearches() async throws -> [Components.Schemas.SavedSearchResponse] {
        let response = try await client.api.listSavedSearchesApiSearchSavedGet(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Save a search
    func saveSearch(
        query: String,
        isSmartSearch: Bool = true,
        filters: [String: any Sendable]? = nil,
        searchType: String = "hybrid",
        sortBy: String = "relevance",
        sortDirection: String = "desc",
        folderPath: String = "/",
        sortOrder: Int = 0
    ) async throws -> Components.Schemas.SavedSearchResponse {
        let filtersPayload: Components.Schemas.SavedSearchCreate.FiltersPayload? = try filters.map { dict in
            let container = try OpenAPIObjectContainer(unvalidatedValue: dict)
            return Components.Schemas.SavedSearchCreate.FiltersPayload(additionalProperties: container)
        }

        let createRequest = Components.Schemas.SavedSearchCreate(
            query: query,
            isSmartSearch: isSmartSearch,
            filters: filtersPayload,
            searchType: searchType,
            sortBy: sortBy,
            sortDirection: sortDirection,
            folderPath: folderPath,
            sortOrder: sortOrder
        )

        let response = try await client.api.saveSearchApiSearchSavedPost(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath),
                body: .json(createRequest)
            )
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Update a saved search
    func updateSavedSearch(
        searchId: String,
        query: String? = nil,
        isSmartSearch: Bool? = nil,
        filters: [String: any Sendable]? = nil,
        searchType: String? = nil,
        sortBy: String? = nil,
        sortDirection: String? = nil,
        folderPath: String? = nil
    ) async throws -> Components.Schemas.SavedSearchResponse {
        let filtersPayload: Components.Schemas.SavedSearchUpdate.FiltersPayload? = try filters.map { dict in
            let container = try OpenAPIObjectContainer(unvalidatedValue: dict)
            return Components.Schemas.SavedSearchUpdate.FiltersPayload(additionalProperties: container)
        }

        let updateRequest = Components.Schemas.SavedSearchUpdate(
            query: query,
            isSmartSearch: isSmartSearch,
            filters: filtersPayload,
            searchType: searchType,
            sortBy: sortBy,
            sortDirection: sortDirection,
            folderPath: folderPath
        )

        let response = try await client.api.updateSavedSearchApiSearchSavedSearchIdPut(
            .init(
                path: .init(searchId: searchId),
                headers: .init(xFicheroLibraryPath: libraryPath),
                body: .json(updateRequest)
            )
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a saved search
    func deleteSavedSearch(searchId: String) async throws {
        let response = try await client.api.deleteSavedSearchApiSearchSavedSearchIdDelete(
            .init(
                path: .init(searchId: searchId),
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Duplicate a saved search
    func duplicateSavedSearch(searchId: String) async throws -> Components.Schemas.SavedSearchResponse {
        let response = try await client.api.duplicateSavedSearchApiSearchSavedSearchIdDuplicatePost(
            .init(
                path: .init(searchId: searchId),
                headers: .init(xFicheroLibraryPath: libraryPath)
            )
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Reorder saved searches
    /// Note: The backend returns an untyped object response, so we re-fetch the list after reordering
    func reorderSavedSearches(ids: [String]) async throws -> [Components.Schemas.SavedSearchResponse] {
        let response = try await client.api.reorderSavedSearchesApiSearchSavedReorderPost(
            .init(
                headers: .init(xFicheroLibraryPath: libraryPath),
                body: .json(ids)
            )
        )

        switch response {
        case .ok:
            // The response is an untyped object; re-fetch the saved searches to get typed response
            return try await listSavedSearches()
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Backward Compatibility Methods

    /// Search with backward-compatible interface returning manual types
    /// This matches the old SearchService.search() signature
    func searchCompatible(
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
        // Convert [String: String] to [String: any Sendable] for the generated API
        let filtersAsAny: [String: any Sendable]? = filters

        let response = try await search(
            query: query,
            limit: limit,
            minScore: minScore,
            searchType: searchType,
            filters: filtersAsAny,
            sortBy: sortBy,
            sortDirection: sortOrder,  // Map sortOrder -> sortDirection
            offset: offset
        )

        return convertToManualSearchResponse(response)
    }

    /// Convert generated SearchResponse to manual SearchResponse type
    private func convertToManualSearchResponse(_ generated: Components.Schemas.SearchResponse) -> SearchResponse {
        let results = generated.results.map { convertToManualSearchResult($0) }

        // Convert filters_applied from OpenAPIObjectContainer to [String: String]
        var filtersApplied: [String: String]?
        if let filtersPayload = generated.filtersApplied,
           let filtersDict = filtersPayload.additionalProperties.value as [String: any Sendable]? {
            var dict: [String: String] = [:]
            for (key, value) in filtersDict {
                if let stringValue = value as? String {
                    dict[key] = stringValue
                }
            }
            if !dict.isEmpty {
                filtersApplied = dict
            }
        }

        return SearchResponse(
            results: results,
            count: generated.count,
            totalResults: generated.totalResults,
            query: generated.query,
            searchType: generated.searchType,
            executionTimeMs: generated.executionTimeMs,
            hasMore: generated.hasMore ?? false,
            filtersApplied: filtersApplied,
            suggestions: generated.suggestions
        )
    }

    /// Convert generated SearchResult to manual SearchResult type
    private func convertToManualSearchResult(_ generated: Components.Schemas.SearchResult) -> SearchResult {
        // Convert metadata from OpenAPIObjectContainer to [String: AnyCodable]
        var metadata: [String: AnyCodable] = [:]
        if let metadataDict = generated.metadata.additionalProperties.value as [String: any Sendable]? {
            for (key, value) in metadataDict {
                metadata[key] = AnyCodable(value)
            }
        }

        return SearchResult(
            documentId: generated.documentId,
            score: generated.score,
            contentPreview: generated.contentPreview,
            metadata: metadata,
            highlights: generated.highlights
        )
    }

    // MARK: - Type Conversions

    /// Extract embedding stats from untyped response container
    private func extractEmbeddingStats(from container: OpenAPIRuntime.OpenAPIValueContainer) -> EmbeddingStatsResponse {
        var indexedCount = 0
        var tableExists = false

        if let dict = container.value as? [String: any Sendable] {
            if let count = dict["indexed_count"] as? Int {
                indexedCount = count
            }
            if let exists = dict["table_exists"] as? Bool {
                tableExists = exists
            }
        }

        return EmbeddingStatsResponse(indexedCount: indexedCount, tableExists: tableExists)
    }

    /// Extract reindex status from untyped response container
    private func extractReindexStatus(from container: OpenAPIRuntime.OpenAPIValueContainer) -> ReindexStatus {
        var status = "unknown"
        var message: String?

        if let dict = container.value as? [String: any Sendable] {
            if let statusValue = dict["status"] as? String {
                status = statusValue
            }
            if let messageValue = dict["message"] as? String {
                message = messageValue
            }
        }

        return ReindexStatus(status: status, message: message)
    }

    /// Extract embed status from untyped response container
    private func extractEmbedStatus(from container: OpenAPIRuntime.OpenAPIValueContainer, defaultDocId: String) -> EmbedStatus {
        var documentId = defaultDocId
        var embedded = false

        if let dict = container.value as? [String: any Sendable] {
            if let docId = dict["document_id"] as? String {
                documentId = docId
            }
            if let emb = dict["embedded"] as? Bool {
                embedded = emb
            }
        }

        return EmbedStatus(documentId: documentId, embedded: embedded)
    }
}

// MARK: - Response Types

/// Response for embedding statistics
struct EmbeddingStatsResponse {
    let indexedCount: Int
    let tableExists: Bool
}

/// Response for reindex status
struct ReindexStatus: Codable {
    let status: String
    let message: String?
}

/// Response for embed status
struct EmbedStatus: Codable {
    let documentId: String
    let embedded: Bool

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case embedded
    }

    init(documentId: String, embedded: Bool) {
        self.documentId = documentId
        self.embedded = embedded
    }
}

// MARK: - Error Types

enum SearchServiceGeneratedError: LocalizedError {
    case validationError(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
