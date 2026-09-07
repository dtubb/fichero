import FicheroAPIClient
import Foundation

extension EntityService {
    // MARK: - Wikidata enrichment (builds on the #3757 authority-link seam)

    /// POST `/api/kg/entity-curation/enrich/preview` — fetch a linked entity's
    /// Wikidata statements for review. Returns the raw JSON envelope so the store
    /// parses the untyped `statements`; this uses the raw `endpointData` path (not
    /// a generated client method) so it needs no OpenAPI regen. Opt-in outbound
    /// network, gated server-side by the same external-authority switch as the
    /// authority refresh — a 403 surfaces when enrichment is disabled.
    func enrichPreview(entityId: String, qid: String? = nil) async throws -> Data {
        var body: [String: Any] = ["entity_id": entityId]
        if let qid, !qid.isEmpty { body["qid"] = qid }
        return try await endpointData(
            path: "/api/kg/entity-curation/enrich/preview",
            method: "POST",
            jsonBody: body
        )
    }

    /// POST `/api/kg/entity-curation/enrich/import` — import the selected Wikidata
    /// statements as WIKIDATA-SOURCED claims. Returns the raw `{ imported, claim_ids }`
    /// envelope; a non-throwing call is success.
    @discardableResult
    func enrichImport(
        entityId: String,
        qid: String,
        statements: [[String: Any]]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/kg/entity-curation/enrich/import",
            method: "POST",
            jsonBody: ["entity_id": entityId, "qid": qid, "statements": statements]
        )
    }
}
