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

private struct EntityTypeListPayload: Decodable {
    let items: [LibraryEntityTypeItem]
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

private struct CitationUsageListPayload: Decodable {
    let items: [EntityCitationUsage]
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
    private let session: URLSession

    init(
        ficheroClient: FicheroClient,
        session: URLSession = RemoteCertificatePinning.configuredSession()
    ) {
        self.client = ficheroClient
        self.session = session
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

    func endpointData(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> Data {
        guard var components = URLComponents(
            url: client.baseURL.appending(path: path),
            resolvingAgainstBaseURL: false
        ) else {
            throw ServiceError.unexpectedResponse(0)
        }
        if !queryItems.isEmpty {
            components.queryItems = queryItems
        }
        guard let url = components.url else {
            throw ServiceError.unexpectedResponse(0)
        }
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.addEngineAuth(libraryPath: client.currentLibraryPath)
        if let jsonBody {
            request.addValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try JSONSerialization.data(withJSONObject: jsonBody)
        }
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse,
           !(200...299).contains(http.statusCode) {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
        return data
    }

    /// Body-pass citation usages for a document. These rows join an extracted
    /// citation marker to the KG claim it supports.
    func citationUsages(
        sourceDocumentId: String
    ) async throws -> [EntityCitationUsage] {
        guard var components = URLComponents(
            url: client.baseURL.appending(path: "/api/citation-usages"),
            resolvingAgainstBaseURL: false
        ) else {
            throw ServiceError.unexpectedResponse(0)
        }
        components.queryItems = [
            URLQueryItem(name: "source_document_id", value: sourceDocumentId)
        ]
        guard let url = components.url else {
            throw ServiceError.unexpectedResponse(0)
        }
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: client.currentLibraryPath)
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse, http.statusCode != 200 {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let raw = try container.decode(String.self)
            if let date = parseEngineDate(raw) {
                return date
            }
            throw DecodingError.dataCorruptedError(
                in: container,
                debugDescription: "Cannot decode date: \(raw)"
            )
        }
        return try decoder.decode(CitationUsageListPayload.self, from: data).items
    }

    // MARK: - Library entity-type registry (#874 / #1372)

    func listLibraryEntityTypes() async throws -> [LibraryEntityTypeItem] {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.validationError("No library selected")
        }
        let encoded = lib.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? lib
        guard let url = URL(string: "\(client.baseURL)/api/libraries/\(encoded)/entity-types") else {
            throw ServiceError.validationError("Invalid entity-types URL")
        }
        var req = URLRequest(url: url)
        req.addEngineAuth(libraryPath: lib)
        // Non-silent: surface non-2xx and decode failures instead of returning []
        // (which silently drops custom ontology types and changes extractor
        // behaviour without telling the user — #1672).
        let (data, response) = try await RemoteCertificatePinning.configuredSession().data(for: req)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
        return try JSONDecoder().decode(EntityTypeListPayload.self, from: data).items
    }

    @discardableResult
    func addLibraryEntityType(key: String) async throws -> LibraryEntityTypeItem {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.noLibrary
        }
        let encoded = lib.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? lib
        let keyEncoded = key.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? key
        let urlString = "\(client.baseURL)/api/libraries/\(encoded)/entity-types"
            + "?entity_type_key=\(keyEncoded)&enabled=true"
        guard let url = URL(string: urlString) else {
            throw ServiceError.noLibrary
        }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.addEngineAuth(libraryPath: lib)
        let (data, _) = try await RemoteCertificatePinning.configuredSession().data(for: req)
        return try JSONDecoder().decode(LibraryEntityTypeItem.self, from: data)
    }

    func removeLibraryEntityType(key: String) async throws {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else {
            throw ServiceError.validationError("No library selected")
        }
        let encoded = lib.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? lib
        let keyEncoded = key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key
        guard let url = URL(string: "\(client.baseURL)/api/libraries/\(encoded)/entity-types/\(keyEncoded)") else {
            throw ServiceError.validationError("Invalid entity-type URL")
        }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.addEngineAuth(libraryPath: lib)
        // Non-silent: a rejected delete must throw so the UI keeps the chip
        // instead of appearing to succeed (#1672).
        let (_, response) = try await RemoteCertificatePinning.configuredSession().data(for: req)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
    }

    // MARK: - Document prototype / class registry (#1377)

    /// Fetch all classification values for the document_prototype dimension.
    /// Uses a direct URLRequest because ClassificationListResponse.items is
    /// [OpenAPIValueContainer] — untyped — so we decode directly to [ClassificationValue].
    func listDocumentPrototypes() async throws -> [Components.Schemas.ClassificationValue] {
        guard let lib = client.currentLibraryPath else {
            throw ServiceError.validationError("No library selected")
        }
        guard let url = URL(string: "\(client.baseURL)/api/classifications?dimension=document_prototype") else {
            throw ServiceError.validationError("Invalid classifications URL")
        }
        var req = URLRequest(url: url)
        req.addEngineAuth(libraryPath: lib)
        // Non-silent: a failed load must surface a backend/API error, not render
        // as "No types defined" empty state (#1671).
        let (data, response) = try await RemoteCertificatePinning.configuredSession().data(for: req)
        if let http = response as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
        struct Envelope: Decodable {
            let items: [Components.Schemas.ClassificationValue]
        }
        return try JSONDecoder().decode(Envelope.self, from: data).items
    }

    /// Fetch all classification values for the node_class dimension —
    /// Tinderbox-style node classes for workspace curated items (#1570).
    /// Mirrors `listDocumentPrototypes()`; `dimension=node_class`.
    func listNodeClasses() async throws -> [Components.Schemas.ClassificationValue] {
        guard let lib = client.currentLibraryPath else { return [] }
        guard let url = URL(string: "\(client.baseURL)/api/classifications?dimension=node_class") else {
            return []
        }
        var req = URLRequest(url: url)
        req.addEngineAuth(libraryPath: lib)
        let (data, _) = try await RemoteCertificatePinning.configuredSession().data(for: req)
        struct Envelope: Decodable {
            let items: [Components.Schemas.ClassificationValue]
        }
        return (try? JSONDecoder().decode(Envelope.self, from: data))?.items ?? []
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
