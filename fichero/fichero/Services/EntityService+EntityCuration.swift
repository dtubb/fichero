import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - KG analytics (post 1587a1b6 namespace consolidation)

    /// Get contradiction evidence for a claim.
    /// Backed by `/api/kg/claim-analysis/{id}/contradictions`.
    func contradictions(
        claimId: String,
        minLinkQuality: Double = 0
    ) async throws -> [Components.Schemas.ContradictionEvidence] {
        let response = try await client.api.contradictionsApiKgClaimAnalysisClaimIdContradictionsGet(
            path: .init(claimId: claimId),
            query: .init(minLinkQuality: minLinkQuality),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Traverse the evidence chain for a claim.
    /// Backed by `/api/kg/claim-analysis/{id}/evidence-chain`.
    func evidenceChain(
        claimId: String,
        maxDepth: Int = 2
    ) async throws -> Components.Schemas.EvidenceChain {
        let response = try await client.api.evidenceChainApiKgClaimAnalysisClaimIdEvidenceChainGet(
            path: .init(claimId: claimId),
            query: .init(maxDepth: maxDepth),
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

    /// Graph-context merge candidate pairs (Jaccard over co-occurrence
    /// neighborhoods) for the chosen scope. Backed by
    /// `/api/kg/entity-curation/candidates` (#3318). Returns the raw JSON so the
    /// store parses the freeform `items` (the OpenAPI envelope is untyped).
    func reconciliationCandidates(scope: String, folderId: String?) async throws -> Data {
        var items = [URLQueryItem(name: "scope", value: scope)]
        if let folderId, !folderId.isEmpty {
            items.append(URLQueryItem(name: "folder_id", value: folderId))
        }
        return try await endpointData(
            path: "/api/kg/entity-curation/candidates",
            queryItems: items
        )
    }

    /// POST /api/kg/entity-curation/authority/refresh (#3757) — fetch and cache
    /// external-authority snapshots (Wikidata / VIAF / LoC) matching `query`.
    /// Returns the raw `{ items, count }` envelope; the store parses it. This is
    /// the only opt-in outbound-network call — refresh is always explicit.
    func refreshAuthoritySnapshots(query: String, limit: Int = 10) async throws -> Data {
        try await endpointData(
            path: "/api/kg/entity-curation/authority/refresh",
            method: "POST",
            jsonBody: ["query": query, "limit": limit]
        )
    }

    /// POST /api/kg/entity-curation/authority/link (#3757) — persist an
    /// entity→authority link from a previously refreshed snapshot. Returns the
    /// raw audit envelope; the store treats a non-throwing call as success.
    @discardableResult
    func linkAuthority(entityId: String, authority: String, authorityId: String) async throws -> Data {
        try await endpointData(
            path: "/api/kg/entity-curation/authority/link",
            method: "POST",
            jsonBody: ["entity_id": entityId, "authority": authority, "authority_id": authorityId]
        )
    }

    /// Merge multiple entities into a single absorbing entity with audit.
    /// Backed by `/api/kg/entity-curation/merge`.
    func mergeEntities(
        absorbingEntityId: String,
        absorbedEntityIds: [String],
        mergedAliases: [String] = [],
        mergedDescription: String? = nil
    ) async throws -> Components.Schemas.EntityAuditResponse {
        let body = Components.Schemas.EntityMergeRequest(
            absorbingEntityId: absorbingEntityId,
            absorbedEntityIds: absorbedEntityIds,
            mergedAliases: mergedAliases,
            mergedDescription: mergedDescription
        )
        let response = try await client.api.mergeEntitiesApiKgEntityCurationMergePost(
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

    /// Split off one or more entities from a primary entity, with audit.
    /// Backed by `/api/kg/entity-curation/split`.
    func splitEntity(
        primaryEntityId: String,
        splitOffEntityIds: [String],
        aliasesToMove: [String] = []
    ) async throws -> Components.Schemas.EntityAuditResponse {
        let body = Components.Schemas.EntitySplitRequest(
            primaryEntityId: primaryEntityId,
            splitOffEntityIds: splitOffEntityIds,
            aliasesToMove: aliasesToMove
        )
        let response = try await client.api.splitEntityApiKgEntityCurationSplitPost(
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

    /// List entity merge/split audit records, optionally filtered.
    /// Backed by `/api/kg/entity-curation/audit`.
    func listEntityAudits(
        entityId: String? = nil,
        limit: Int = 50
    ) async throws -> [Components.Schemas.EntityAuditResponse] {
        let response = try await client.api.listEntityAuditsApiKgEntityCurationAuditGet(
            query: .init(entityId: entityId, limit: limit),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Undo a merge/split audit operation.
    /// Backed by `/api/kg/entity-curation/audit/{audit_id}/undo`.
    @discardableResult
    func undoEntityAudit(_ auditId: String) async throws -> Components.Schemas.EntityAuditResponse {
        let response = try await client.api.undoEntityOperationApiKgEntityCurationAuditAuditIdUndoPost(
            path: .init(auditId: auditId),
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

    /// Index all claims in LanceDB for semantic search + heuristic
    /// predictions. Returns the number of vectors written.
    /// Backed by `/api/kg/claim-search/embed`.
    @discardableResult
    func embedClaims() async throws -> Int {
        let response = try await client.api.embedClaimsApiKgClaimSearchEmbedPost()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.embedded
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Index all entities (canonical names + aliases) for semantic
    /// search. Returns the number of vectors written.
    /// Backed by `/api/kg/entity-curation/semantic/embed`.
    @discardableResult
    func embedEntities() async throws -> Int {
        let response = try await client.api.embedEntitiesApiKgEntityCurationSemanticEmbedPost()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.embedded
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
