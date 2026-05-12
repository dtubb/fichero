import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ArtifactServiceGenerated")

/// ArtifactService using the generated OpenAPI client.
/// Manages document artifacts (transcripts, descriptions, etc.)
@MainActor
class ArtifactServiceGenerated: ObservableObject {
    private let client: FicheroClient

    /// Cached artifacts by document ID
    @Published private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    @Published private(set) var loadingDocuments: Set<String> = []

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Fetch Artifacts

    /// Fetch all artifacts for a document.
    ///
    /// `includeDescendants` controls whether the backend aggregates artifacts
    /// from children and parent (legacy V1 behavior, default true) or scopes
    /// strictly to the requested document (V2). The aggregation caused
    /// "delete pops back" confusion in V2 because deleting one artifact left
    /// a sibling in place that looked like the same one.
    func getArtifacts(
        forDocumentId documentId: String,
        type: String? = nil,
        forceRefresh: Bool = false,
        includeDescendants: Bool = true
    ) async throws -> [Artifact] {
        // Cache key needs the scope flag so V1 and V2 don't share entries.
        let cacheKey = includeDescendants ? documentId : "\(documentId)|own"
        if !forceRefresh, let cached = artifactsByDocument[cacheKey] {
            if let type = type {
                return cached.filter { $0.artifactType == type }
            }
            return cached
        }

        loadingDocuments.insert(documentId)
        defer { loadingDocuments.remove(documentId) }

        let response = try await client.api.listDocumentArtifactsApiArtifactsDocumentDocIdGet(
            path: .init(docId: documentId),
            query: .init(artifactType: type, includeDescendants: includeDescendants),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let okResponse):
            let artifactList = try okResponse.body.json
            let artifacts = artifactList.artifacts.map { convertToArtifact($0) }

            artifactsByDocument[cacheKey] = artifacts

            logger.info("Fetched \(artifacts.count) artifacts for document \(documentId)")
            return artifacts
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get a specific artifact by ID
    func getArtifact(id: String) async throws -> Artifact {
        let response = try await client.api.getArtifactApiArtifactsArtifactIdGet(
            path: .init(artifactId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let okResponse):
            let artifact = try okResponse.body.json
            return convertToArtifact(artifact)
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifact types in the library
    func getArtifactTypes() async throws -> [String] {
        let response = try await client.api.listArtifactTypesApiArtifactsTypesGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifacts in the library (uses direct HTTP call since generated client may not have this endpoint)
    func getAllArtifacts(type: String? = nil, limit: Int = 100, offset: Int = 0) async throws -> [Artifact] {
        var urlString = "http://localhost:8765/api/artifacts?limit=\(limit)&offset=\(offset)"
        if let type = type {
            urlString += "&artifact_type=\(type.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? type)"
        }

        guard let url = URL(string: urlString) else {
            throw ArtifactServiceError.serverError("Invalid URL")
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.addEngineAuth(libraryPath: client.currentLibraryPath)

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse else {
            throw ArtifactServiceError.unexpectedResponse(-1)
        }

        guard httpResponse.statusCode == 200 else {
            throw ArtifactServiceError.unexpectedResponse(httpResponse.statusCode)
        }

        let decoder = JSONDecoder()
        let artifactList = try decoder.decode(AllArtifactsResponse.self, from: data)

        logger.info("Fetched \(artifactList.artifacts.count) total artifacts")
        return artifactList.artifacts.map { convertToArtifactFromJSON($0) }
    }

    // MARK: - JSON Conversion for direct HTTP calls

    private func convertToArtifactFromJSON(_ json: ArtifactJSON) -> Artifact {
        // Use the multi-format parser (audit class F).
        let createdAt = parseEngineDate(json.createdAt) ?? Date()

        // Convert data dict
        var data: [String: AnyCodable]?
        if let jsonData = json.data, !jsonData.isEmpty {
            var dict: [String: AnyCodable] = [:]
            for (key, value) in jsonData {
                dict[key] = AnyCodable(value)
            }
            data = dict
        }

        return Artifact(
            id: json.id,
            documentId: json.documentId,
            version: json.version,
            artifactType: json.artifactType,
            content: json.content,
            data: data,
            provider: json.provider,
            model: json.model,
            reviewed: json.reviewed,
            createdAt: createdAt
        )
    }

    /// Update an artifact's editable fields (content, reviewed flag).
    /// Provenance fields (provider, model, version) stay set by the tool
    /// that produced the artifact.
    func updateArtifact(
        id: String,
        documentId: String,
        content: String? = nil,
        reviewed: Bool? = nil
    ) async throws -> Artifact {
        let request = Components.Schemas.ArtifactUpdate(
            content: content,
            reviewed: reviewed
        )
        let response = try await client.api.updateArtifactApiArtifactsArtifactIdPut(.init(
            path: .init(artifactId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
            body: .json(request)
        ))

        switch response {
        case .ok(let okResponse):
            let json = try okResponse.body.json
            let updated = convertToArtifact(json)

            for key in [documentId, "\(documentId)|own"] {
                if var cached = artifactsByDocument[key] {
                    if let index = cached.firstIndex(where: { $0.id == id }) {
                        cached[index] = updated
                    } else {
                        cached.append(updated)
                    }
                    artifactsByDocument[key] = cached
                }
            }
            return updated
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete an artifact
    func deleteArtifact(id: String, documentId: String) async throws {
        let response = try await client.api.deleteArtifactApiArtifactsArtifactIdDelete(
            path: .init(artifactId: id),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )

        switch response {
        case .noContent:
            // Update both cache scopes — V1 (aggregated) and V2 (own-only)
            // can both have entries for the doc keyed differently.
            for key in [documentId, "\(documentId)|own"] {
                if var artifacts = artifactsByDocument[key] {
                    artifacts.removeAll { $0.id == id }
                    artifactsByDocument[key] = artifacts
                }
            }
            logger.info("Deleted artifact \(id)")
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    // MARK: - Cache Management

    /// Clear cached artifacts for a document
    func clearCache(forDocumentId documentId: String) {
        artifactsByDocument.removeValue(forKey: documentId)
    }

    /// Clear all cached artifacts
    func clearAllCache() {
        artifactsByDocument.removeAll()
    }

    /// Check if we're loading artifacts for a document
    func isLoading(documentId: String) -> Bool {
        loadingDocuments.contains(documentId)
    }

    // MARK: - Type Conversions

    private func convertToArtifact(_ generated: Components.Schemas.ArtifactResponse) -> Artifact {
        // Convert data dict
        var data: [String: AnyCodable]?
        if let genData = generated.data {
            var dict: [String: AnyCodable] = [:]
            for (key, value) in genData.additionalProperties.value {
                if let unwrapped = value {
                    dict[key] = AnyCodable(unwrapped)
                }
            }
            data = dict.isEmpty ? nil : dict
        }

        // Parse date from string
        // Use the multi-format parser; falling back to Date() (today) silently
        // mis-dated artifacts whose timestamp didn't match the rigid format.
        // (Audit class F.)
        let createdAt = parseEngineDate(generated.createdAt) ?? Date()

        return Artifact(
            id: generated.id,
            documentId: generated.documentId,
            version: generated.version,
            artifactType: generated.artifactType,
            content: generated.content,
            data: data,
            provider: generated.provider,
            model: generated.model,
            reviewed: generated.reviewed,
            createdAt: createdAt
        )
    }
}

// MARK: - Error Types

enum ArtifactServiceError: Error, LocalizedError {
    case unexpectedResponse(Int)
    case serverError(String)

    var errorDescription: String? {
        switch self {
        case .unexpectedResponse(let code):
            return "Unexpected response from artifact service (status: \(code))"
        case .serverError(let message):
            return "Server error: \(message)"
        }
    }
}

// MARK: - JSON Types for Direct HTTP Calls

/// Response for list all artifacts endpoint
private struct AllArtifactsResponse: Codable {
    let artifacts: [ArtifactJSON]
    let total: Int
}

/// JSON artifact representation for direct HTTP decoding
private struct ArtifactJSON: Codable {
    let id: String
    let documentId: String
    let artifactType: String
    let content: String?
    let data: [String: AnyCodable]?
    let version: Int
    let provider: String?
    let model: String?
    let confidence: Double?
    let reviewed: Bool
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case documentId = "document_id"
        case artifactType = "artifact_type"
        case content
        case data
        case version
        case provider
        case model
        case confidence
        case reviewed
        case createdAt = "created_at"
    }
}
// EntityServiceGenerated lives in this file (instead of its own) because the
// Xcode project's main target uses traditional file references; new .swift
// files would need pbxproj edits. See MEMORY: feedback_swift_file_sync.md.

private let entityServiceLogger = Logger(
    subsystem: "com.fichero.fichero",
    category: "EntityServiceGenerated"
)

/// Service wrapper for the dedicated `/api/entities` and `/api/claims`
/// endpoints. The catalogue extractors write `KnowledgeEntity` +
/// `KnowledgeClaim` rows (#728); this service is the read path the
/// Inspector consumes.
///
/// Note: there is also a `KnowledgeGraphServiceGenerated` that wraps the
/// `/api/knowledge-graph/*` routes — those return the `EntityCoreference`
/// shape used by the merge/split UI. This service is for the simpler
/// per-document entity/claim views in the Inspector.
@MainActor
final class EntityServiceGenerated: ObservableObject {
    private let client: FicheroClient

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    enum ServiceError: Error {
        case validationError(String)
        case unexpectedResponse(Int)
    }

    /// List all knowledge entities, optionally filtered by type or query.
    ///
    /// - Parameters:
    ///   - entityType: filter to one EntityType (nil for all types)
    ///   - query: free-text query against canonical_name + aliases (nil for none)
    ///   - limit: page size
    func listEntities(
        entityType: Components.Schemas.FicheroKnowledgeModelsEntityType? = nil,
        query: String? = nil,
        limit: Int = 100
    ) async throws -> [Components.Schemas.KnowledgeEntity] {
        let response = try await client.api.listEntitiesApiEntitiesGet(
            query: .init(q: query, entityType: entityType, limit: limit),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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

    /// Get a single entity by ID.
    func getEntity(
        _ entityId: String
    ) async throws -> Components.Schemas.KnowledgeEntity {
        let response = try await client.api.getEntityApiEntitiesEntityIdGet(
            path: .init(entityId: entityId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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

    /// Traverse the evidence chain for a claim.
    /// Backed by `/api/kg/claim-analysis/{id}/evidence-chain`.
    func evidenceChain(
        claimId: String,
        maxDepth: Int = 2
    ) async throws -> Components.Schemas.EvidenceChain {
        let response = try await client.api.evidenceChainApiKgClaimAnalysisClaimIdEvidenceChainGet(
            path: .init(claimId: claimId),
            query: .init(maxDepth: maxDepth),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
        let response = try await client.api.embedClaimsApiKgClaimSearchEmbedPost(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )
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
        let response = try await client.api.embedEntitiesApiKgEntityCurationSemanticEmbedPost(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )
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

    /// Generate cheap candidate links via embedding similarity. Requires
    /// claims to have been embedded first via the claim-search embed
    /// endpoint. Backed by `/api/kg/predictions/heuristic`.
    func generateHeuristicPredictions(
        topK: Int = 10,
        entityId: String? = nil
    ) async throws -> Components.Schemas.HeuristicPredictionsResponse {
        let body = Components.Schemas.HeuristicRequest(topK: topK, entityId: entityId)
        let response = try await client.api.generateHeuristicPredictionsApiKgPredictionsHeuristicPost(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? ""),
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
