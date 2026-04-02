import Foundation
import OSLog
import FicheroAPIClient
import OpenAPIRuntime
import OpenAPIURLSession

private let logger = Logger(subsystem: "com.tubb.Fichero", category: "KnowledgeGraphServiceGenerated")

/// Service for interacting with the Knowledge Graph API using generated OpenAPI client
@MainActor
class KnowledgeGraphServiceGenerated {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient)
    }

    // MARK: - Claims

    /// List all claims with optional filtering
    func listClaims(
        claimType: Components.Schemas.ClaimType? = nil,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.listClaimsApiKnowledgeGraphClaimsGet(
            query: .init(
                claimType: claimType,
                epistemicStatus: epistemicStatus,
                limit: limit,
                offset: offset
            ),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Get a single claim by ID
    func getClaim(claimId: String) async throws -> Components.Schemas.KnowledgeClaim {
        let response = try await client.api.getClaimApiKnowledgeGraphClaimsClaimIdGet(
            path: .init(claimId: claimId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Create a new claim
    func createClaim(
        text: String,
        sourceDocumentId: String? = nil,
        claimType: Components.Schemas.ClaimType? = nil,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        sourceIds: [String]? = nil
    ) async throws -> Components.Schemas.KnowledgeClaim {
        var body = Components.Schemas.CreateClaimRequest(text: text)
        body.sourceDocumentId = sourceDocumentId
        body.claimType = claimType
        body.epistemicStatus = epistemicStatus
        if let sourceIds = sourceIds {
            body.sourceIds = sourceIds
        }

        let response = try await client.api.createClaimApiKnowledgeGraphClaimsPost(
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Update a claim's epistemic status or curation state
    func patchClaim(
        claimId: String,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        curationState: Components.Schemas.ClaimCurationState? = nil,
        confidence: Double? = nil
    ) async throws -> Components.Schemas.KnowledgeClaim {
        var body = Components.Schemas.PatchClaimRequest()
        body.epistemicStatus = epistemicStatus
        body.curationState = curationState
        body.confidence = confidence

        let response = try await client.api.patchClaimApiKnowledgeGraphClaimsClaimIdPatch(
            path: .init(claimId: claimId),
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Filter claims with advanced filters
    func filterClaims(
        claimType: Components.Schemas.ClaimType? = nil,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        sourceLanguage: String? = nil,
        searchText: String? = nil,
        entityIds: [String]? = nil,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.listClaimsFilteredApiKnowledgeGraphClaimsFilteredGet(
            query: .init(
                claimType: claimType,
                epistemicStatus: epistemicStatus,
                sourceLanguage: sourceLanguage,
                searchText: searchText,
                entityIds: entityIds,
                limit: limit,
                offset: offset
            ),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Search claims semantically
    func searchClaimsSemantic(query: String, limit: Int = 20) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.searchClaimsSemanticApiKnowledgeGraphClaimsSemanticGet(
            query: .init(query: query, limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Find similar claims to a given claim
    func findSimilarClaims(claimId: String, limit: Int = 10) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.findSimilarClaimsApiKnowledgeGraphClaimsClaimIdSimilarGet(
            path: .init(claimId: claimId),
            query: .init(limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Claim Links

    /// List links to/from a claim
    func listClaimLinks(claimId: String) async throws -> [Components.Schemas.KnowledgeClaimLink] {
        let response = try await client.api.listClaimLinksApiKnowledgeGraphClaimsClaimIdLinksGet(
            path: .init(claimId: claimId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Create a link between two claims
    func createClaimLink(
        sourceClaimId: String,
        targetClaimId: String,
        linkType: String
    ) async throws -> Components.Schemas.KnowledgeClaimLink {
        var body = Components.Schemas.ClaimLinkCreateRequest(sourceClaimId: sourceClaimId, targetClaimId: targetClaimId, linkType: linkType)

        let response = try await client.api.createClaimLinkApiKnowledgeGraphClaimsClaimIdLinksPost(
            path: .init(claimId: sourceClaimId),
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Entities

    /// List all entities
    func listEntities(limit: Int = 100, offset: Int = 0) async throws -> [Components.Schemas.EntityCoreference] {
        let response = try await client.api.listEntitiesApiKnowledgeGraphEntitiesGet(
            query: .init(limit: limit, offset: offset),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Create or update an entity
    func upsertEntity(
        name: String,
        entityType: String? = nil,
        aliases: [String]? = nil
    ) async throws -> Components.Schemas.EntityCoreference {
        var body = Components.Schemas.UpsertEntityRequest(name: name)
        body.entityType = entityType
        if let aliases = aliases {
            body.aliases = aliases
        }

        let response = try await client.api.upsertEntityApiKnowledgeGraphEntitiesPost(
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Add aliases to an entity
    func addEntityAliases(entityId: String, aliases: [String]) async throws -> Components.Schemas.EntityCoreference {
        var body = Components.Schemas.AddAliasesRequest()
        body.aliases = aliases

        let response = try await client.api.addEntityAliasesApiKnowledgeGraphEntitiesEntityIdAliasesPost(
            path: .init(entityId: entityId),
            body: .json(body),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Resolve an entity by name or alias
    func resolveEntity(value: String) async throws -> Components.Schemas.EntityCoreference {
        let response = try await client.api.resolveEntityApiKnowledgeGraphEntitiesResolveValueGet(
            path: .init(value: value),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Predictions

    /// Generate heuristic-based predictions for unreviewed claims
    func generateHeuristicPredictions() async throws -> Components.Schemas.KnowledgePredictionRun {
        let response = try await client.api.generateHeuristicPredictionsApiKnowledgeGraphPredictionsGenerateHeuristicPost(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// List prediction runs
    func listPredictions(limit: Int = 20) async throws -> [Components.Schemas.KnowledgePredictionRun] {
        let response = try await client.api.listPredictionsApiKnowledgeGraphPredictionsGet(
            query: .init(limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    /// Apply predictions to update claim confidence scores
    func applyPredictions(runId: String) async throws {
        let response = try await client.api.applyPredictionApiKnowledgeGraphPredictionsRunIdApplyPost(
            path: .init(runId: runId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Overview

    /// Get knowledge graph overview statistics
    func getOverview() async throws -> Components.Schemas.KnowledgeGraphOverview {
        let response = try await client.api.overviewApiKnowledgeGraphOverviewGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let ok):
            return try ok.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw KnowledgeGraphServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw KnowledgeGraphServiceError.unexpectedResponse(code)
        }
    }
}

// MARK: - Error Types

enum KnowledgeGraphServiceError: LocalizedError {
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
