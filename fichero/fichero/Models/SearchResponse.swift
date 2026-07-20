import FicheroAPIClient
import Foundation

struct SearchResponse: Codable {
    let results: [SearchResult]
    let entityHits: [Components.Schemas.SearchEntityHit]
    let claimHits: [Components.Schemas.SearchClaimHit]
    let count: Int
    let totalResults: Int
    let query: String
    let searchType: String
    let executionTimeMs: Double
    let hasMore: Bool
    let filtersApplied: [String: String]?
    let suggestions: [String]?

    enum CodingKeys: String, CodingKey {
        case results
        case entityHits = "entity_hits"
        case claimHits = "claim_hits"
        case count
        case totalResults = "total_results"
        case query
        case searchType = "search_type"
        case executionTimeMs = "execution_time_ms"
        case hasMore = "has_more"
        case filtersApplied = "filters_applied"
        case suggestions
    }

    init(
        results: [SearchResult],
        entityHits: [Components.Schemas.SearchEntityHit] = [],
        claimHits: [Components.Schemas.SearchClaimHit] = [],
        count: Int,
        totalResults: Int,
        query: String,
        searchType: String,
        executionTimeMs: Double,
        hasMore: Bool,
        filtersApplied: [String: String]?,
        suggestions: [String]?
    ) {
        self.results = results
        self.entityHits = entityHits
        self.claimHits = claimHits
        self.count = count
        self.totalResults = totalResults
        self.query = query
        self.searchType = searchType
        self.executionTimeMs = executionTimeMs
        self.hasMore = hasMore
        self.filtersApplied = filtersApplied
        self.suggestions = suggestions
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        results = try container.decode([SearchResult].self, forKey: .results)
        entityHits = try container.decodeIfPresent(
            [Components.Schemas.SearchEntityHit].self,
            forKey: .entityHits
        ) ?? []
        claimHits = try container.decodeIfPresent(
            [Components.Schemas.SearchClaimHit].self,
            forKey: .claimHits
        ) ?? []
        count = try container.decode(Int.self, forKey: .count)
        totalResults = try container.decode(Int.self, forKey: .totalResults)
        query = try container.decode(String.self, forKey: .query)
        searchType = try container.decode(String.self, forKey: .searchType)
        executionTimeMs = try container.decode(Double.self, forKey: .executionTimeMs)
        hasMore = try container.decode(Bool.self, forKey: .hasMore)
        filtersApplied = try container.decodeIfPresent([String: String].self, forKey: .filtersApplied)
        suggestions = try container.decodeIfPresent([String].self, forKey: .suggestions)
    }
}
