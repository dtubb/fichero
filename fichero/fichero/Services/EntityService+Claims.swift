import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - Claims, entities, registries, and multilingual wiring (#1424)

    func getClaimLink(_ linkId: String) async throws -> Data {
        try await endpointData(path: "/api/claim-links/\(linkId)")
    }

    func updateClaimLink(
        _ linkId: String,
        patch: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claim-links/\(linkId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClaimLink(_ linkId: String) async throws {
        _ = try await endpointData(path: "/api/claim-links/\(linkId)", method: "DELETE")
    }

    func assignClaimTimePeriod(
        claimId: String,
        timePeriodId: String
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claims/assign-time-period",
            method: "POST",
            jsonBody: ["claim_id": claimId, "time_period_id": timePeriodId]
        )
    }

    func batchTransitionClaims(
        claimIds: [String],
        state: String
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claims/batch/transition",
            method: "POST",
            jsonBody: ["claim_ids": claimIds, "state": state]
        )
    }

    func unreviewedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/unreviewed", limit: limit, offset: offset)
    }

    func shortlistedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/shortlisted", limit: limit, offset: offset)
    }

    func curatedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/curated", limit: limit, offset: offset)
    }

    func rejectedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/rejected", limit: limit, offset: offset)
    }

    func resolveClaimSource(claimId: String) async throws -> Data {
        try await endpointData(
            path: "/api/claims/resolve-source",
            method: "POST",
            jsonBody: ["claim_id": claimId]
        )
    }

    func relatedClaims(claimId: String, limit: Int = 10) async throws -> Data {
        try await endpointData(
            path: "/api/claims/\(claimId)/related",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func transitionClaim(_ claimId: String, state: String) async throws -> Data {
        try await endpointData(
            path: "/api/claims/\(claimId)/transition",
            method: "PATCH",
            jsonBody: ["state": state]
        )
    }

    func listClassifications(dimension: String? = nil) async throws -> Data {
        try await endpointData(
            path: "/api/classifications",
            queryItems: dimension.map { [URLQueryItem(name: "dimension", value: $0)] } ?? []
        )
    }

    func createClassification(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/classifications", method: "POST", jsonBody: body)
    }

    func patchClassification(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/classifications/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClassification(_ valueId: String) async throws {
        _ = try await endpointData(path: "/api/classifications/\(valueId)", method: "DELETE")
    }

    func entityAliasMap() async throws -> Data {
        try await endpointData(path: "/api/entities/alias-map")
    }

    func entityClaimCountsData() async throws -> Data {
        try await endpointData(path: "/api/entities/claim-counts")
    }

    func resolveEntityValue(_ value: String) async throws -> Data {
        let encoded = value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
        return try await endpointData(path: "/api/entities/resolve/\(encoded)")
    }

    func topEntities(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/entities/top",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func addEntityAliases(_ entityId: String, aliases: [String]) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/aliases",
            method: "POST",
            jsonBody: ["aliases": aliases]
        )
    }

    func entityBiography(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/entities/\(entityId)/biography")
    }

    func entityCoOccurrence(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/co-occurrence",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func entityDocuments(_ entityId: String, limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/documents",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func entityDrillDown(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/entities/\(entityId)/drill-down")
    }

    func multilingualClaims(language: String, limit: Int = 100) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/claims",
            queryItems: [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func detectLanguage(text: String) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/detect",
            method: "POST",
            jsonBody: ["text": text]
        )
    }

    func multilingualEntities(language: String, limit: Int = 100) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/entities",
            queryItems: [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func searchMultilingualEntities(query: String, languages: [String] = []) async throws -> Data {
        var body: [String: Any] = ["query": query]
        if !languages.isEmpty {
            body["languages"] = languages
        }
        return try await endpointData(
            path: "/api/multilingual/entities/search",
            method: "POST",
            jsonBody: body
        )
    }

    func normalizeMultilingualText(_ text: String, language: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let language {
            body["language"] = language
        }
        return try await endpointData(
            path: "/api/multilingual/normalize",
            method: "POST",
            jsonBody: body
        )
    }

    func transliterateMultilingualText(_ text: String, language: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let language {
            body["language"] = language
        }
        return try await endpointData(
            path: "/api/multilingual/transliterate",
            method: "POST",
            jsonBody: body
        )
    }

    func listClaimKinds() async throws -> Data {
        try await endpointData(path: "/api/registries/claim-kinds")
    }

    func createClaimKind(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/registries/claim-kinds", method: "POST", jsonBody: body)
    }

    func patchClaimKind(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/registries/claim-kinds/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClaimKind(_ valueId: String) async throws {
        _ = try await endpointData(path: "/api/registries/claim-kinds/\(valueId)", method: "DELETE")
    }

    func listEpistemicStatuses() async throws -> Data {
        try await endpointData(path: "/api/registries/epistemic-statuses")
    }

    func createEpistemicStatus(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/registries/epistemic-statuses", method: "POST", jsonBody: body)
    }

    func patchEpistemicStatus(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/registries/epistemic-statuses/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteEpistemicStatus(_ valueId: String) async throws {
        _ = try await endpointData(
            path: "/api/registries/epistemic-statuses/\(valueId)",
            method: "DELETE"
        )
    }

    private func claimsQueue(path: String, limit: Int, offset: Int) async throws -> Data {
        try await endpointData(
            path: path,
            queryItems: [
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "offset", value: "\(offset)")
            ]
        )
    }

    /// Generate cheap candidate links via embedding similarity. Requires
    /// claims to have been embedded first via the claim-search embed
    /// endpoint. Backed by `/api/kg/predictions/heuristic`.
    func generateHeuristicPredictions(
        topK: Int = 10,
        entityId: String? = nil
    ) async throws -> Components.Schemas.HeuristicPredictionsResponse {
        let body = Components.Schemas.HeuristicRequest(topK: topK, entityId: entityId)
        let response = try await client.api.generateHeuristicPredictionsApiKgPredictionsHeuristicPost(
            body: .json(body)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
