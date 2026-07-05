// swiftlint:disable file_length
import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SearchServiceGenerated")

/// Service for search operations using generated OpenAPI client
/// Lightweight DTO matching `KeywordCloudEntry` on the backend.
struct KeywordCloudEntryDTO: Decodable, Identifiable {
    let name: String
    let count: Int
    var id: String { name }
}

@MainActor
@Observable
// swiftlint:disable:next type_body_length
class SearchServiceGenerated {
    struct SearchRequestOptions {
        let query: String
        let limit: Int
        let include: [Components.Schemas.SearchInclude]?
        let minScore: Double
        let searchType: String
        let sortBy: String
        let sortDirection: String
        let offset: Int
    }

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
        include: [Components.Schemas.SearchInclude]? = nil,
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

        let options = SearchRequestOptions(
            query: query,
            limit: limit,
            include: include,
            minScore: minScore,
            searchType: searchType,
            sortBy: sortBy,
            sortDirection: sortDirection,
            offset: offset
        )

        let searchRequest = Self.makeSearchRequest(
            options,
            filtersPayload: filtersPayload
        )

        let response = try await client.api.enhancedSearchApiSearchPost(
            .init(
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
            .init()
        )

        switch response {
        case .ok(let okResponse):
            let payload = try okResponse.body.json
            return EmbeddingStatsResponse(
                indexedCount: payload.indexedCount,
                tableExists: payload.tableExists
            )
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Reindex all documents.  POST /api/search/reindex
    func reindexAll() async throws -> ReindexStatus {
        let response = try await client.api.reindexAllApiSearchReindexPost(
            .init()
        )

        switch response {
        case .ok(let okResponse):
            let result = try okResponse.body.json
            return ReindexStatus(status: result.status, message: result.message)
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Embed a specific document.  POST /api/search/embed/{doc_id}
    func embedDocument(_ documentId: String) async throws -> EmbedStatus {
        let response = try await client.api.embedDocumentApiSearchEmbedDocIdPost(
            .init(
                path: .init(docId: documentId),
            )
        )

        switch response {
        case .ok(let okResponse):
            let result = try okResponse.body.json
            return EmbedStatus(documentId: result.documentId, embedded: result.embedded)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Saved Searches

    /// List all saved searches.  GET /api/search/saved
    func listSavedSearches() async throws -> [Components.Schemas.SavedSearchResponse] {
        let response = try await client.api.listSavedSearchesApiSearchSavedGet(
            .init()
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw SearchServiceGeneratedError.unexpectedResponse(statusCode)
        }
    }

    /// Save a search.  POST /api/search/saved
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

    /// Update a saved search.  PUT /api/search/saved/{search_id}
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

    /// Delete a saved search.  DELETE /api/search/saved/{search_id}
    func deleteSavedSearch(searchId: String) async throws {
        let response = try await client.api.deleteSavedSearchApiSearchSavedSearchIdDelete(
            .init(
                path: .init(searchId: searchId),
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

    /// Duplicate a saved search.  POST /api/search/saved/{search_id}/duplicate
    func duplicateSavedSearch(searchId: String) async throws -> Components.Schemas.SavedSearchResponse {
        let response = try await client.api.duplicateSavedSearchApiSearchSavedSearchIdDuplicatePost(
            .init(
                path: .init(searchId: searchId),
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

    /// Reorder saved searches.  POST /api/search/saved/reorder
    /// Note: The backend returns an untyped object response, so we re-fetch the list after reordering
    func reorderSavedSearches(ids: [String]) async throws -> [Components.Schemas.SavedSearchResponse] {
        let response = try await client.api.reorderSavedSearchesApiSearchSavedReorderPost(
            .init(
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

    /// Top-N keyword cloud — name + per-doc count, sorted by frequency.
    /// Empty array when the workflow hasn't extracted any keywords yet.
    func keywordCloud(limit: Int = 50) async throws -> [KeywordCloudEntryDTO] {
        let response = try await client.api.keywordCloudApiSearchKeywordsGet(
            .init(
                query: .init(limit: limit),
            )
        )

        switch response {
        case .ok(let okResponse):
            let payload = try okResponse.body.json
            return payload.items.map { KeywordCloudEntryDTO(name: $0.name, count: $0.count) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw SearchServiceGeneratedError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented:
            return []
        }
    }

    /// Search with backward-compatible interface returning manual types
    /// This matches the old SearchService.search() signature
    func searchCompatible(
        query: String,
        limit: Int = 10,
        include: [Components.Schemas.SearchInclude]? = nil,
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
            include: include,
            minScore: minScore,
            searchType: searchType,
            filters: filtersAsAny,
            sortBy: sortBy,
            sortDirection: sortOrder,  // Map sortOrder -> sortDirection
            offset: offset
        )

        return convertToManualSearchResponse(response)
    }

    static func makeSearchRequest(
        _ options: SearchRequestOptions,
        filtersPayload: Components.Schemas.SearchRequest.FiltersPayload?
    ) -> Components.Schemas.SearchRequest {
        Components.Schemas.SearchRequest(
            query: options.query,
            limit: options.limit,
            include: options.include,
            minScore: options.minScore,
            searchType: options.searchType,
            filters: filtersPayload,
            sortBy: options.sortBy,
            sortDirection: options.sortDirection,
            offset: options.offset
        )
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
            entityHits: generated.entityHits ?? [],
            claimHits: generated.claimHits ?? [],
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
            highlights: generated.highlights,
            transcriptExcerpts: generated.transcriptExcerpts ?? []
        )
    }

    // MARK: - Type Conversions

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
