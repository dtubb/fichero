import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    /// PATCH a KnowledgeEntity — partial update of canonical name,
    /// entity type, aliases, description, language. Any nil field is
    /// left untouched on the server side. (#901)
    @discardableResult
    func patchEntity(
        _ entityId: String,
        canonicalName: String? = nil,
        entityType: String? = nil,
        aliases: [String]? = nil,
        description: String? = nil,
        metadata: [String: any Sendable]? = nil
    ) async throws -> Components.Schemas.KnowledgeEntity {
        var body = Components.Schemas.EntityPatchRequest()
        body.canonicalName = canonicalName
        body.entityType = entityType.flatMap {
            Components.Schemas.FicheroServerModelsKnowledgeEntityType(rawValue: $0)
        }
        body.aliases = aliases
        body.description = description
        if let metadata = metadata {
            let container = try OpenAPIObjectContainer(unvalidatedValue: metadata)
            body.metadata = .init(additionalProperties: container)
        }
        let response = try await client.api.patchEntityApiEntitiesEntityIdPatch(
            path: .init(entityId: entityId),
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

    /// Delete a single KnowledgeClaim. Entities referenced by the
    /// claim are NOT cascaded — the entity is the bigger concept, the
    /// claim is one piece of evidence about it (#901).
    /// Patch a claim's editable fields. All args are optional — only
    /// non-nil keys are sent to the server so untouched fields stay
    /// untouched. Returns the refreshed claim. (#901 — inline editing
    /// in the claim card.)
    @discardableResult
    func patchClaim(
        _ claimId: String,
        text: String? = nil,
        subjectCanonical: String? = nil,
        predicateVerb: String? = nil,
        objectPhrase: String? = nil,
        sourcePageLabel: String? = nil,
        curationState: Components.Schemas.ClaimCurationState? = nil,
        claimType: Components.Schemas.ClaimType? = nil,
        epistemicStatus: Components.Schemas.EpistemicStatus? = nil,
        confidence: Double? = nil,
        speakerName: String? = nil,
        speakerEntityId: String? = nil
    ) async throws -> Components.Schemas.KnowledgeClaim {
        var body = Components.Schemas.ClaimPatchRequest()
        body.text = text
        body.subjectCanonical = subjectCanonical
        body.predicateVerb = predicateVerb
        body.objectPhrase = objectPhrase
        body.sourcePageLabel = sourcePageLabel
        body.curationState = curationState
        body.claimType = claimType
        body.epistemicStatus = epistemicStatus
        body.confidence = confidence
        body.speakerName = speakerName
        body.speakerEntityId = speakerEntityId
        let response = try await client.api.patchClaimApiClaimsClaimIdPatch(
            path: .init(claimId: claimId),
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

    func getClaim(_ claimId: String) async throws -> Components.Schemas.KnowledgeClaim {
        let response = try await client.api.getClaimApiClaimsClaimIdGet(
            path: .init(claimId: claimId),
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

    func deleteClaim(_ claimId: String) async throws {
        let response = try await client.api.deleteClaimApiClaimsClaimIdDelete(
            path: .init(claimId: claimId),
        )
        switch response {
        case .noContent:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Full inspector payload for one entity: entity, claims with source
    /// metadata, associated documents, annotations, and notes in one call.
    /// Backed by GET /api/entities/{entity_id}/inspector (#1183).
    func getEntityInspector(
        _ entityId: String
    ) async throws -> Components.Schemas.EntityInspectorResponse {
        let response = try await client.api.inspectorApiEntitiesEntityIdInspectorGet(
            path: .init(entityId: entityId),
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

    /// Delete a KnowledgeEntity. The backend cascade-removes claims
    /// whose entity_ids reference it (per #901). Returns once the
    /// 204 response lands.
    func deleteEntity(_ entityId: String) async throws {
        let response = try await client.api.deleteEntityApiEntitiesEntityIdDelete(
            path: .init(entityId: entityId),
        )
        switch response {
        case .noContent:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Create or update a KnowledgeEntity manually (user-driven CRUD
    /// path for #916). Backed by `POST /api/entities`.
    @discardableResult
    func upsertEntity(
        name: String,
        entityType: String? = nil,
        aliases: [String] = []
    ) async throws -> Components.Schemas.KnowledgeEntity {
        let typeEnum = entityType.flatMap {
            Components.Schemas.FicheroServerModelsKnowledgeEntityType(rawValue: $0)
        }
        var body = Components.Schemas.EntityUpsertRequest(canonicalName: name)
        body.entityType = typeEnum
        body.aliases = aliases.isEmpty ? nil : aliases
        let response = try await client.api.upsertEntityApiEntitiesPost(
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

    /// Create a typed claim ↔ claim relationship (supports / refines /
    /// contradicts / related_to). Backed by `/api/claims/{id}/links`.
    @discardableResult
    func createClaimLink(
        claimId: String,
        relatedClaimId: String,
        relationType: Components.Schemas.ClaimRelationType,
        linkQuality: Double? = nil,
        evidence: String? = nil
    ) async throws -> Components.Schemas.KnowledgeClaimLink {
        let body = Components.Schemas.ClaimLinkCreateRequest(
            relatedClaimId: relatedClaimId,
            relationType: relationType,
            linkQuality: linkQuality,
            evidence: evidence
        )
        let response = try await client.api.createClaimLinkApiClaimsClaimIdLinksPost(
            path: .init(claimId: claimId),
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
