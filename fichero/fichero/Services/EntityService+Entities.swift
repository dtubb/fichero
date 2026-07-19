import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    /// List all knowledge entities, optionally filtered by type or query.
    ///
    /// - Parameters:
    ///   - entityType: filter to one EntityType (nil for all types)
    ///   - query: free-text query against canonical_name + aliases (nil for none)
    ///   - limit: page size
    func listEntities(
        entityType: Components.Schemas.FicheroKnowledgeKnowledgeModelsEntityType? = nil,
        query: String? = nil,
        limit: Int = 100
    ) async throws -> [Components.Schemas.KnowledgeEntity] {
        let response = try await client.api.listEntitiesApiEntitiesGet(
            query: .init(q: query, entityType: entityType, limit: limit),
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

    /// List entities filtered to a specific source document.
    func listEntitiesForDocument(
        documentId: String,
        limit: Int = 200
    ) async throws -> [Components.Schemas.KnowledgeEntity] {
        let response = try await client.api.listEntitiesApiEntitiesGet(
            query: .init(documentId: documentId, limit: limit),
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

    /// Inspector source-of-truth entity payload for one document/page.
    ///
    /// Backed by `GET /api/documents/{document_id}/inspector`, which is the
    /// same route the CLI `docs inspector <page>` verifies in #1653.
    func listInspectorEntitiesForDocument(
        documentId: String
    ) async throws -> [Components.Schemas.KnowledgeEntity] {
        let response = try await client.api.inspectorApiDocumentsDocumentIdInspectorGet(
            path: .init(documentId: documentId),
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.entities
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Fetch per-entity claim counts for badge display in the entity browser.
    func fetchClaimCounts() async throws -> [String: Int] {
        let response = try await client.api.entityClaimCountsApiEntitiesClaimCountsGet()
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.counts.additionalProperties
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Get a single entity by ID.
    func getEntity(
        _ entityId: String
    ) async throws -> Components.Schemas.KnowledgeEntity {
        let response = try await client.api.getEntityApiEntitiesEntityIdGet(
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

    /// List claims, optionally filtered by source document. The
    /// document-scoped form is the primary path the Inspector uses to
    /// answer "what KG claims exist for this document?"
    func listClaims(
        sourceDocumentId: String? = nil,
        entityId: String? = nil,
        includeDescendants: Bool = false,
        limit: Int = 100,
        offset: Int = 0
    ) async throws -> [Components.Schemas.KnowledgeClaim] {
        let response = try await client.api.listClaimsApiClaimsGet(
            query: .init(
                entityId: entityId,
                sourceDocumentId: sourceDocumentId,
                includeDescendants: includeDescendants,
                limit: limit,
                offset: offset
            ),
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

    /// Canonical document knowledge-graph endpoint.
    ///
    /// Single source of truth for grouped/deduped per-document KG reads:
    /// GET /api/documents/{id}/knowledge-graph
    func documentKnowledgeGraph(
        documentId: String,
        includeChildren: Bool = true
    ) async throws -> Components.Schemas.DocumentKnowledgeGraphResponse {
        let response = try await client.api.knowledgeGraphApiDocumentsDocumentIdKnowledgeGraphGet(
            path: .init(documentId: documentId),
            query: .init(includeChildren: includeChildren),
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

    /// Cheap per-type child counts for a document (#2258).
    ///
    /// Backs a *collapsed* library outline row — returns artifact /
    /// entity / note / claim / page counts rolled up over the document
    /// and its descendant pages, without assembling the heavier child
    /// payloads. The expandable Table shows these on a collapsed row and
    /// only loads the per-type children when the disclosure is expanded.
    /// GET /api/documents/{id}/rollup
    func documentRollup(
        documentId: String
    ) async throws -> Components.Schemas.DocumentRollupResponse {
        let response = try await client.api.documentRollupApiDocumentsDocumentIdRollupGet(
            path: .init(documentId: documentId),
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
