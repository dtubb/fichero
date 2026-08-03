import FicheroAPIClient
import Foundation

struct SearchResponse: Codable {
    let results: [SearchResult]
    let entityHits: [Components.Schemas.SearchEntityHit]
    let claimHits: [Components.Schemas.SearchClaimHit]
    /// Workflow outputs that matched (#4118) — typed, opt-in leg.
    let artifactHits: [Components.Schemas.SearchArtifactHit]
    let count: Int
    let totalResults: Int
    let query: String
    let searchType: String
    let executionTimeMs: Double
    let hasMore: Bool
    let filtersApplied: [String: String]?
    let suggestions: [String]?
    // Query compilation (#4116): what the LLM turned a natural-language
    // request into (always shown — AI = instrument), and any failure.
    let compiledQuery: Components.Schemas.CompiledQuery?
    let compilationError: String?
    /// The engine's own count of every leg it returned (#4505). `nil` when the
    /// field is absent — an older engine. DELIBERATELY not used for the header,
    /// which stays derived from the arrays actually rendered (#4403); this
    /// exists only so a disagreement can be noticed instead of silently
    /// shrinking the results.
    let renderedTotal: Int?

    enum CodingKeys: String, CodingKey {
        case results
        case entityHits = "entity_hits"
        case claimHits = "claim_hits"
        case artifactHits = "artifact_hits"
        case count
        case totalResults = "total_results"
        case query
        case searchType = "search_type"
        case executionTimeMs = "execution_time_ms"
        case hasMore = "has_more"
        case filtersApplied = "filters_applied"
        case suggestions
        case compiledQuery = "compiled_query"
        case compilationError = "compilation_error"
        case renderedTotal = "rendered_total"
    }

    init(
        results: [SearchResult],
        entityHits: [Components.Schemas.SearchEntityHit] = [],
        claimHits: [Components.Schemas.SearchClaimHit] = [],
        artifactHits: [Components.Schemas.SearchArtifactHit] = [],
        count: Int,
        totalResults: Int,
        query: String,
        searchType: String,
        executionTimeMs: Double,
        hasMore: Bool,
        filtersApplied: [String: String]?,
        suggestions: [String]?,
        compiledQuery: Components.Schemas.CompiledQuery? = nil,
        compilationError: String? = nil,
        renderedTotal: Int? = nil
    ) {
        self.results = results
        self.entityHits = entityHits
        self.claimHits = claimHits
        self.artifactHits = artifactHits
        self.count = count
        self.totalResults = totalResults
        self.query = query
        self.searchType = searchType
        self.executionTimeMs = executionTimeMs
        self.hasMore = hasMore
        self.filtersApplied = filtersApplied
        self.suggestions = suggestions
        self.compiledQuery = compiledQuery
        self.compilationError = compilationError
        self.renderedTotal = renderedTotal
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
        artifactHits = try container.decodeIfPresent(
            [Components.Schemas.SearchArtifactHit].self,
            forKey: .artifactHits
        ) ?? []
        count = try container.decode(Int.self, forKey: .count)
        totalResults = try container.decode(Int.self, forKey: .totalResults)
        query = try container.decode(String.self, forKey: .query)
        searchType = try container.decode(String.self, forKey: .searchType)
        executionTimeMs = try container.decode(Double.self, forKey: .executionTimeMs)
        hasMore = try container.decode(Bool.self, forKey: .hasMore)
        filtersApplied = try container.decodeIfPresent([String: String].self, forKey: .filtersApplied)
        suggestions = try container.decodeIfPresent([String].self, forKey: .suggestions)
        compiledQuery = try container.decodeIfPresent(
            Components.Schemas.CompiledQuery.self, forKey: .compiledQuery
        )
        compilationError = try container.decodeIfPresent(String.self, forKey: .compilationError)
        // decodeIfPresent, so an absent field stays nil rather than becoming a
        // zero the agreement check would read as a claim (#4505/#4394).
        renderedTotal = try container.decodeIfPresent(Int.self, forKey: .renderedTotal)
    }
}
