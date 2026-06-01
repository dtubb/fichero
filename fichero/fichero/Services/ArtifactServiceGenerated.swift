// swiftlint:disable file_length type_body_length
// This file hosts both ArtifactServiceGenerated AND EntityServiceGenerated
// because Services is a non-synchronized PBXGroup (per MEMORY note
// [[feedback_swift_file_sync]]). Splitting would require pbxproj
// surgery; suppressing here is the lower-risk path until we decide
// to move the entity service into its own file.
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ArtifactServiceGenerated")

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
            let artifacts = artifactList.items.map { convertToArtifact($0) }

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
            return try okResponse.body.json.items
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

        logger.info("Fetched \(artifactList.items.count) total artifacts")
        return artifactList.items.map { convertToArtifactFromJSON($0) }
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
    let items: [ArtifactJSON]
    let count: Int
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

// EntityServiceGenerated lives in this file (instead of its own) because the
// Xcode project's main target uses traditional file references; new .swift
// files would need pbxproj edits. See MEMORY: feedback_swift_file_sync.md.

private let entityServiceLogger = Logger(
    subsystem: "app.fichero.fichero",
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
        case noLibrary
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
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let code, _):
            throw ServiceError.unexpectedResponse(code)
        }
    }

    /// Fetch per-entity claim counts for badge display in the entity browser.
    func fetchClaimCounts() async throws -> [String: Int] {
        let response = try await client.api.entityClaimCountsApiEntitiesClaimCountsGet(
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.counts.additionalProperties
        case .unprocessableContent:
            return [:]
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
            Components.Schemas.FicheroKnowledgeModelsEntityType(rawValue: $0)
        }
        body.aliases = aliases
        body.description = description
        if let metadata = metadata {
            let container = try OpenAPIObjectContainer(unvalidatedValue: metadata)
            body.metadata = .init(additionalProperties: container)
        }
        let response = try await client.api.patchEntityApiEntitiesEntityIdPatch(
            path: .init(entityId: entityId),
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
        confidence: Double? = nil
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
        let response = try await client.api.patchClaimApiClaimsClaimIdPatch(
            path: .init(claimId: claimId),
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

    func getClaim(_ claimId: String) async throws -> Components.Schemas.KnowledgeClaim {
        let response = try await client.api.getClaimApiClaimsClaimIdGet(
            path: .init(claimId: claimId),
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

    func deleteClaim(_ claimId: String) async throws {
        let response = try await client.api.deleteClaimApiClaimsClaimIdDelete(
            path: .init(claimId: claimId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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

    /// Delete a KnowledgeEntity. The backend cascade-removes claims
    /// whose entity_ids reference it (per #901). Returns once the
    /// 204 response lands.
    func deleteEntity(_ entityId: String) async throws {
        let response = try await client.api.deleteEntityApiEntitiesEntityIdDelete(
            path: .init(entityId: entityId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            Components.Schemas.FicheroKnowledgeModelsEntityType(rawValue: $0)
        }
        var body = Components.Schemas.EntityUpsertRequest(canonicalName: name)
        body.entityType = typeEnum
        body.aliases = aliases.isEmpty ? nil : aliases
        let response = try await client.api.upsertEntityApiEntitiesPost(
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

    // MARK: - Citation graph (#974 hook-up)

    /// Get inbound citations for a document — i.e. other documents that
    /// cite this one. Backed by
    /// `/api/citations/graph/document/{document_id}/inbound`.
    func inboundCitations(
        forDocumentId documentId: String
    ) async throws -> [Components.Schemas.DocumentCitation] {
        let response = try await client.api.inboundApiCitationsGraphDocumentDocumentIdInboundGet(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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

    // MARK: - Bibliography (per-document metadata)

    /// Fetch bibliographic metadata for a document — title, authors,
    /// year, container, identifiers, etc. The backend stores
    /// extractor-emitted bib data alongside user edits and merges them.
    /// Backed by `/api/bibliography/document/{document_id}`.
    func bibliographyMetadata(
        forDocumentId documentId: String
    ) async throws -> Components.Schemas.MetadataResponse {
        let response = try await client.api.getMetadataApiBibliographyDocumentDocumentIdGet(
            path: .init(documentId: documentId),
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

    /// Patch bibliographic metadata for a document. The backend merges
    /// the patch into existing metadata (so unspecified keys are
    /// preserved). Pass any key/value pairs the bibliography editor
    /// supports — title, authors, year, container_title, etc.
    /// Backed by `PATCH /api/bibliography/document/{document_id}`.
    func patchBibliographyMetadata(
        forDocumentId documentId: String,
        metadata: [String: any Sendable]
    ) async throws -> Components.Schemas.MetadataResponse {
        let payload = Components.Schemas.MetadataPatchRequest.MetadataPayload(
            additionalProperties: try .init(unvalidatedValue: metadata)
        )
        let body = Components.Schemas.MetadataPatchRequest(metadata: payload)
        let response = try await client.api.patchMetadataApiBibliographyDocumentDocumentIdPatch(
            path: .init(documentId: documentId),
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

    /// Trigger the bibliography extractor on a document — re-runs the
    /// LLM-backed metadata extraction and replaces extractor-emitted
    /// fields (user-edited fields are preserved per the backend's merge
    /// rule). Backed by
    /// `POST /api/bibliography/document/{document_id}/extract`.
    func runBibliographyExtractor(
        forDocumentId documentId: String
    ) async throws -> Components.Schemas.MetadataResponse {
        let response = try await client.api.runExtractorApiBibliographyDocumentDocumentIdExtractPost(
            path: .init(documentId: documentId),
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

    // MARK: - Library entity-type registry (#874 / #1372)

    func listLibraryEntityTypes() async throws -> [LibraryEntityTypeItem] {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else { return [] }
        let encoded = lib.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? lib
        guard let url = URL(string: "\(client.baseURL)/api/libraries/\(encoded)/entity-types") else {
            return []
        }
        var req = URLRequest(url: url)
        req.addEngineAuth(libraryPath: lib)
        let (data, _) = try await URLSession.shared.data(for: req)
        return (try? JSONDecoder().decode(EntityTypeListPayload.self, from: data))?.items ?? []
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
        let (data, _) = try await URLSession.shared.data(for: req)
        return try JSONDecoder().decode(LibraryEntityTypeItem.self, from: data)
    }

    func removeLibraryEntityType(key: String) async throws {
        guard let lib = client.currentLibraryPath, !lib.isEmpty else { return }
        let encoded = lib.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? lib
        let keyEncoded = key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? key
        guard let url = URL(string: "\(client.baseURL)/api/libraries/\(encoded)/entity-types/\(keyEncoded)") else {
            return
        }
        var req = URLRequest(url: url)
        req.httpMethod = "DELETE"
        req.addEngineAuth(libraryPath: lib)
        _ = try? await URLSession.shared.data(for: req)
    }

    // MARK: - Document workflow provenance (#1434)

    func listDocumentWorkflowRuns(
        documentId: String
    ) async throws -> [Components.Schemas.WorkflowRunProvenanceResponse] {
        let response = try await client.api.getDocumentWorkflowRunsApiDocumentsDocIdWorkflowRunsGet(
            path: .init(docId: documentId),
            headers: .init(xFicheroLibraryPath: client.currentLibraryPath ?? "")
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

    private static func decodeSimilar(
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
