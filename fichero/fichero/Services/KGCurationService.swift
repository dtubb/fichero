import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let kgCurationServiceLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "KGCurationService"
)

// Typed wrappers for `/api/kg/curation-rules/*`.

@MainActor
@Observable
final class KGCurationService {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    enum ServiceError: Error, LocalizedError {
        case validationError(String)
        case unexpectedResponse(Int)

        // Surface the real cause instead of the generic "The operation couldn't
        // be completed" Cocoa message (#2500). The claim/entity merge throws this,
        // so on iPhone the masked failure now shows its actual detail/status.
        var errorDescription: String? {
            switch self {
            case .validationError(let message): return message
            case .unexpectedResponse(let code): return "Unexpected response from the server (status \(code))."
            }
        }
    }

    enum PruneTrivialScope: Equatable {
        case document(documentId: String)
        case folder(folderId: String)
        case libraryWide
    }

    static func makePruneTrivialClaimsRequest(
        scope: PruneTrivialScope,
        reason: String = "Prune trivial is-a copula claims",
        createdBy: String = "human"
    ) -> Components.Schemas.PruneTrivialClaimsRequest {
        var request = Components.Schemas.PruneTrivialClaimsRequest()
        switch scope {
        case .document(let documentId):
            request.documentId = documentId
            request.folderId = nil
            request.libraryWide = false
        case .folder(let folderId):
            request.documentId = nil
            request.folderId = folderId
            request.libraryWide = false
        case .libraryWide:
            request.documentId = nil
            request.folderId = nil
            request.libraryWide = true
        }
        request.reason = reason
        request.createdBy = createdBy
        return request
    }

    func listEntityRules() async throws -> [Components.Schemas.EntityRuleReadResponse] {
        let response = try await client.api.listEntityRulesApiKgCurationRulesEntityRulesGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("listEntityRules unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func createEntityRule(
        _ request: Components.Schemas.EntityRuleCreateRequest
    ) async throws -> Components.Schemas.EntityRuleReadResponse {
        let response = try await client.api.createEntityRuleApiKgCurationRulesEntityRulesPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("createEntityRule unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func deleteEntityRule(ruleId: String) async throws -> Components.Schemas.EntityRuleDeleteResponse {
        let request = Components.Schemas.EntityRuleDeleteRequest(ruleId: ruleId)
        let response = try await client.api.deleteEntityRuleApiKgCurationRulesEntityRulesDelete(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("deleteEntityRule unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func batchCreateEntityRules(
        _ requests: [Components.Schemas.EntityRuleCreateRequest]
    ) async throws -> [Components.Schemas.EntityRuleReadResponse] {
        var body = Components.Schemas.EntityRuleBatchCreateRequest()
        body.items = requests
        let response = try await client.api.createEntityRulesBatchApiKgCurationRulesEntityRulesBatchPost(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("batchCreateEntityRules unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func batchSetEntityCurationState(
        entityIds: [String],
        curationState: Components.Schemas.EntityCurationState
    ) async throws -> Components.Schemas.BatchEntityCurationResponse {
        let body = Components.Schemas.BatchEntityCurationRequest(
            entityIds: entityIds,
            curationState: curationState
        )
        let response = try await client.api.batchSetEntityCurationStateApiKgEntitiesBatchCurationPatch(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("batchSetEntityCurationState unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - External authority curation (#3757)

    /// GET /api/kg/entity-curation/authority/settings — whether external
    /// authority linking (Wikidata / VIAF / LoC) is enabled for this library.
    /// The setting defaults off, so an absent flag reads as `false`.
    func externalAuthorityEnabled() async throws -> Bool {
        let response = try await client.api
            .getExternalAuthoritySettingsApiKgEntityCurationAuthoritySettingsGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.externalAuthorityEnabled ?? false
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("externalAuthorityEnabled unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// PUT /api/kg/entity-curation/authority/settings — enable/disable external
    /// authority linking. Returns the persisted value so the store reflects
    /// exactly what the backend stored.
    @discardableResult
    func setExternalAuthorityEnabled(_ enabled: Bool) async throws -> Bool {
        let body = Components.Schemas.ExternalAuthoritySettings(externalAuthorityEnabled: enabled)
        let response = try await client.api
            .putExternalAuthoritySettingsApiKgEntityCurationAuthoritySettingsPut(body: .json(body))

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.externalAuthorityEnabled ?? false
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("setExternalAuthorityEnabled unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

}

// MARK: - Claim curation rules

extension KGCurationService {
    func listClaimRules() async throws -> [Components.Schemas.ClaimRuleReadResponse] {
        let response = try await client.api.listClaimRulesApiKgCurationRulesClaimRulesGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("listClaimRules unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func createClaimRule(
        _ request: Components.Schemas.ClaimRuleCreateRequest
    ) async throws -> Components.Schemas.ClaimRuleReadResponse {
        let response = try await client.api.createClaimRuleApiKgCurationRulesClaimRulesPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("createClaimRule unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func deleteClaimRule(ruleId: String) async throws -> Components.Schemas.ClaimRuleDeleteResponse {
        let request = Components.Schemas.ClaimRuleDeleteRequest(ruleId: ruleId)
        let response = try await client.api.deleteClaimRuleApiKgCurationRulesClaimRulesDelete(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("deleteClaimRule unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func batchCreateClaimRules(
        _ requests: [Components.Schemas.ClaimRuleCreateRequest]
    ) async throws -> [Components.Schemas.ClaimRuleReadResponse] {
        var body = Components.Schemas.ClaimRuleBatchCreateRequest()
        body.items = requests
        let response = try await client.api.createClaimRulesBatchApiKgCurationRulesClaimRulesBatchPost(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("batchCreateClaimRules unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func batchSetClaimCurationState(
        claimIds: [String],
        curationState: Components.Schemas.ClaimCurationState
    ) async throws -> Components.Schemas.BatchClaimCurationResponse {
        let body = Components.Schemas.BatchClaimCurationRequest(
            claimIds: claimIds,
            curationState: curationState
        )
        let response = try await client.api.batchSetClaimCurationStateApiKgClaimsBatchCurationPatch(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("batchSetClaimCurationState unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func mergeClaims(
        survivorId: String,
        absorbedIds: [String]
    ) async throws -> Components.Schemas.ClaimAuditResponse {
        let body = Components.Schemas.ClaimMergeRequest(
            survivingClaimId: survivorId,
            absorbedClaimIds: absorbedIds
        )
        let response = try await client.api.mergeClaimsApiKgClaimsMergePost(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("mergeClaims unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func unmergeClaims(
        auditId: String
    ) async throws -> Components.Schemas.ClaimAuditResponse {
        let body = Components.Schemas.ClaimUnmergeRequest(auditId: auditId)
        let response = try await client.api.unmergeClaimsApiKgClaimsUnmergePost(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("unmergeClaims unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func pruneTrivialClaims(
        scope: PruneTrivialScope
    ) async throws -> Components.Schemas.PruneTrivialClaimsResponse {
        let body = Self.makePruneTrivialClaimsRequest(scope: scope)
        let response = try await client.api.pruneTrivialClaimsApiKgClaimsPruneTrivialPost(
            body: .json(body)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            kgCurationServiceLogger.error("pruneTrivialClaims unexpected response: \(code)")
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
