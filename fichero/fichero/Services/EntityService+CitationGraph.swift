import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

extension EntityService {
    // MARK: - Citation graph (#974 hook-up)

    /// Associate an existing citation with a document through the audited
    /// `citation.patch` action.
    @discardableResult
    func patchCitation(
        _ citationId: String,
        targetDocumentId: String
    ) async throws -> Components.Schemas.DocumentCitation {
        var body = Components.Schemas.CitationPatchRequest()
        body.targetDocumentId = targetDocumentId
        let response = try await client.api.patchCitationApiCitationsGraphCitationIdPatch(
            path: .init(citationId: citationId),
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

    /// Get inbound citations for a document — i.e. other documents that
    /// cite this one. Backed by
    /// `/api/citations/graph/document/{document_id}/inbound`.
    func inboundCitations(
        forDocumentId documentId: String
    ) async throws -> [Components.Schemas.DocumentCitation] {
        let response = try await client.api.inboundApiCitationsGraphDocumentDocumentIdInboundGet(
            path: .init(documentId: documentId),
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

    /// Get outbound citations for a document — i.e. documents that this
    /// document cites. Backed by
    /// `/api/citations/graph/document/{document_id}/outbound`.
    func outboundCitations(
        forDocumentId documentId: String
    ) async throws -> [Components.Schemas.DocumentCitation] {
        let response = try await client.api.outboundApiCitationsGraphDocumentDocumentIdOutboundGet(
            path: .init(documentId: documentId),
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

    // MARK: - Document citations (extracted bibliography) (#1434)

    func listDocumentCitations(
        documentId: String
    ) async throws -> Components.Schemas.DocumentCitationsResponse {
        let response = try await client.api.getDocumentCitationsApiDocumentsDocumentIdCitationsGet(
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

    // MARK: - KG-RAG: focus-neighborhood graph (#976/#977/#983 Phase 5)

    /// Fetch the focus entity + k-hop neighbor entities + the SVO-labeled
    /// claim edges connecting them. Backs the focus-neighborhood viz —
    /// Tinderbox / Neo4j Explore style: pick one entity, see its
    /// immediate context with predicate-labeled arrows, click an edge to
    /// open the source. Bounded by `hops` (default 1, max 3) +
    /// `limit` (default 50, max 500); the backend ranks by edge weight
    /// before truncating so the most-connected neighbors survive.
    /// Backed by `/api/kg/graph/neighborhood/{entity_id}`.
    func fetchNeighborhood(
        entityId: String,
        hops: Int = 1,
        limit: Int = 50,
        rank: String = "edge_weight"
    ) async throws -> Components.Schemas.NeighborhoodResponse {
        let response = try await client.api.neighborhoodApiKgGraphNeighborhoodEntityIdGet(
            path: .init(entityId: entityId),
            query: .init(hops: hops, limit: limit, rank: rank),
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

    // MARK: - KG-RAG: similar-claim search (#959)

    /// Find claims semantically similar to `claimId`. Requires claims to
    /// have been embedded first (run "Embed claims" from the Ontology
    /// Browser Tools menu). Backed by
    /// `/api/kg/claim-search/{claim_id}/similar`.
    func findSimilarClaims(
        claimId: String,
        limit: Int = 5
    ) async throws -> [SimilarClaim] {
        let response = try await client.api.findSimilarClaimsApiKgClaimSearchClaimIdSimilarGet(
            path: .init(claimId: claimId),
            query: .init(limit: limit),
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.compactMap(Self.decodeSimilar(payload:))
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }
}
