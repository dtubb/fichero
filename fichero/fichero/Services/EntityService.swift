import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

// MARK: - Library entity-type registry models (#874 / #1372)

struct LibraryEntityTypeItem: Decodable {
    let id: String?
    let entityTypeKey: String
    let enabled: Bool?
    enum CodingKeys: String, CodingKey {
        case id
        case entityTypeKey = "entity_type_key"
        case enabled
    }
}

struct EntityCitationUsage: Decodable, Identifiable {
    let citation: Components.Schemas.DocumentCitation
    let claim: Components.Schemas.KnowledgeClaim?
    let referenceId: String?
    let stance: String?

    var id: String {
        citation.id ?? [
            citation.sourceDocumentId,
            citation.targetCitationText,
            citation.pageLabel ?? ""
        ].joined(separator: "|")
    }

    enum CodingKeys: String, CodingKey {
        case citation
        case claim
        case referenceId = "reference_id"
        case stance
    }
}

private let entityServiceLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "EntityService"
)

/// Service wrapper for the dedicated `/api/entities` and `/api/claims`
/// endpoints. The catalogue extractors write `KnowledgeEntity` +
/// `KnowledgeClaim` rows (#728); this service is the read path the
/// Inspector consumes.
///
/// Note: there is also a `KnowledgeGraphService` that wraps the
/// `/api/knowledge-graph/*` routes — those return the `EntityCoreference`
/// shape used by the merge/split UI. This service is for the simpler
/// per-document entity/claim views in the Inspector.
@MainActor
@Observable
final class EntityService {
    // internal (not private) so the EntityService+*.swift concern extensions can
    // reach the generated client directly, same as endpointData/decodeSimilar (#1943).
    let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    enum ServiceError: Error, LocalizedError {
        case validationError(String)
        case unexpectedResponse(Int)
        case noLibrary

        // Surface the real cause instead of the generic "The operation couldn't
        // be completed" Cocoa message (#2500) — a non-LocalizedError Swift error
        // stringifies to that generic text.
        var errorDescription: String? {
            switch self {
            case .validationError(let message): return message
            case .unexpectedResponse(let code): return "Unexpected response from the server (status \(code))."
            case .noLibrary: return "No library is selected."
            }
        }
    }

    /// Generic buffered request helper for the ~90 concern-extension callers.
    ///
    /// Routes through `FicheroClient.requestData` — the SAME `ClientTransport` +
    /// auth/library middleware stack the generated `client.api` calls use — so it
    /// reaches the engine over `.https`, `.uds`, or the in-process `.inMemory`
    /// transport. A raw `URLSession` to `client.baseURL` could dial only `.https`
    /// and silently failed over UDS / in-process (the "Loaded 0 entities" symptom).
    /// Auth (`AuthTokenMiddleware`) and library scoping (`LibraryPathMiddleware`)
    /// are injected by the middleware stack, so no headers are hand-rolled here.
    func endpointData(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> Data {
        let bodyData: Data? = try jsonBody.map {
            try JSONSerialization.data(withJSONObject: $0)
        }
        let (status, data) = try await client.requestData(
            path: path,
            method: method,
            queryItems: queryItems,
            jsonBody: bodyData
        )
        if !(200...299).contains(status) {
            throw ServiceError.unexpectedResponse(status)
        }
        return data
    }

    /// Body-pass citation usages for a document. These rows join an extracted
    /// citation marker to the KG claim it supports.
    func citationUsages(
        sourceDocumentId: String
    ) async throws -> [EntityCitationUsage] {
        // Through the generated op (centralized transport) — dates decode via the
        // client's `LenientISO8601DateTranscoder`, the same one every other
        // generated call already uses for `DocumentCitation` / `KnowledgeClaim`.
        let response = try await client.api.listCitationUsagesApiCitationUsagesGet(
            query: .init(sourceDocumentId: sourceDocumentId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items.map {
                EntityCitationUsage(
                    citation: $0.citation,
                    claim: $0.claim,
                    referenceId: $0.referenceId,
                    stance: $0.stance
                )
            }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    // MARK: - Library entity-type registry (#874 / #1372)

    func listLibraryEntityTypes() async throws -> [LibraryEntityTypeItem] {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.validationError("No library selected")
        }
        // Non-silent: surface non-2xx and decode failures instead of returning []
        // (which silently drops custom ontology types and changes extractor
        // behaviour without telling the user — #1672).
        let response = try await client.api.listLibraryEntityTypesApiLibrariesLibEntityTypesGet(
            path: .init(lib: lib)
        )
        switch response {
        case .ok(let okResponse):
            // `items` is an open-ended `[OpenAPIValueContainer]`; re-encode and
            // decode into our typed rows, preserving the throw-on-malformed
            // behaviour the raw path had.
            let data = try JSONEncoder().encode(try okResponse.body.json.items)
            return try JSONDecoder().decode([LibraryEntityTypeItem].self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    @discardableResult
    func addLibraryEntityType(key: String) async throws -> LibraryEntityTypeItem {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.noLibrary
        }
        let response = try await client.api.addLibraryEntityTypeApiLibrariesLibEntityTypesPost(
            path: .init(lib: lib),
            query: .init(entityTypeKey: key, enabled: true)
        )
        switch response {
        case .ok(let okResponse):
            let created = try okResponse.body.json
            return LibraryEntityTypeItem(
                id: created.id,
                entityTypeKey: created.entityTypeKey,
                enabled: created.enabled
            )
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    func removeLibraryEntityType(key: String) async throws {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.validationError("No library selected")
        }
        // Non-silent: a rejected delete must throw so the UI keeps the chip
        // instead of appearing to succeed (#1672).
        let response = try await client.api
            .removeLibraryEntityTypeApiLibrariesLibEntityTypesEntityTypeKeyDelete(
                path: .init(lib: lib, entityTypeKey: key)
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

    // MARK: - Document prototype / class registry (#1377)

    /// Fetch all classification values for the document_prototype dimension via
    /// the generated op (centralized transport). `ClassificationListResponse.items`
    /// is untyped `[OpenAPIValueContainer]`, so `classificationValues` re-encodes
    /// and decodes into `[ClassificationValue]`.
    func listDocumentPrototypes() async throws -> [Components.Schemas.ClassificationValue] {
        guard client.currentLibraryPath != nil else {
            throw ServiceError.validationError("No library selected")
        }
        // Non-silent: a failed load must surface a backend/API error, not render
        // as "No types defined" empty state (#1671).
        return try await classificationValues(dimension: .documentPrototype)
    }

    /// Fetch classification values for a dimension through the generated op.
    /// `ClassificationListResponse.items` is an open-ended
    /// `[OpenAPIValueContainer]`, so we re-encode and decode into the typed
    /// `ClassificationValue` rows (same decode the raw path used).
    private func classificationValues(
        dimension: Components.Schemas.ClassificationDimension
    ) async throws -> [Components.Schemas.ClassificationValue] {
        let response = try await client.api.listValuesApiClassificationsGet(
            query: .init(dimension: dimension)
        )
        switch response {
        case .ok(let okResponse):
            let data = try JSONEncoder().encode(try okResponse.body.json.items)
            return try JSONDecoder().decode([Components.Schemas.ClassificationValue].self, from: data)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Fetch all classification values for the node_class dimension —
    /// Tinderbox-style node classes for workspace curated items (#1570).
    /// Mirrors `listDocumentPrototypes()`; `dimension=node_class`.
    func listNodeClasses() async throws -> [Components.Schemas.ClassificationValue] {
        guard client.currentLibraryPath != nil else { return [] }
        // Lenient by design (unlike the prototypes/entity-type loaders): node
        // classes are optional decoration, so any failure degrades to [] rather
        // than surfacing an error.
        return (try? await classificationValues(dimension: .nodeClass)) ?? []
    }

    // MARK: - KG-RAG: similar-claim search (#959)

    /// A single similar-claim result decoded from the open-ended
    /// `additionalProperties` payload that
    /// `/api/kg/claim-search/{claim_id}/similar` returns. The endpoint's
    /// generated response type is a `[JsonPayloadPayload]` with a free-form
    /// `OpenAPIObjectContainer`, so we decode the well-known keys ourselves
    /// (id, text, source_document_id, source_excerpt, similarity_score)
    /// and ignore anything else the backend adds.
    struct SimilarClaim: Identifiable, Hashable {
        let id: String
        let text: String
        let sourceDocumentId: String?
        let sourceExcerpt: String?
        let similarityScore: Double
    }

    static func decodeSimilar(
        payload: OpenAPIRuntime.OpenAPIValueContainer
    ) -> SimilarClaim? {
        guard let dict = payload.value as? [String: Any],
              let id = dict["id"] as? String,
              let text = dict["text"] as? String
        else { return nil }
        let score: Double
        if let asDouble = dict["similarity_score"] as? Double {
            score = asDouble
        } else if let asInt = dict["similarity_score"] as? Int {
            score = Double(asInt)
        } else {
            score = 0.0
        }
        return SimilarClaim(
            id: id,
            text: text,
            sourceDocumentId: dict["source_document_id"] as? String,
            sourceExcerpt: dict["source_excerpt"] as? String,
            similarityScore: score
        )
    }
}
