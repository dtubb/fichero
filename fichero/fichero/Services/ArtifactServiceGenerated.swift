// swiftlint:disable file_length
// This file hosts both ArtifactServiceGenerated AND EntityServiceGenerated
// because Services is a non-synchronized PBXGroup (per MEMORY note
// [[feedback_swift_file_sync]]). Splitting would require pbxproj
// surgery; suppressing here is the lower-risk path until we decide
// to move the entity service into its own file.
import Observation
import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ArtifactServiceGenerated")

/// ArtifactService using the generated OpenAPI client.
/// Manages document artifacts (transcripts, descriptions, etc.)
@MainActor
@Observable
class ArtifactServiceGenerated {
    private let client: FicheroClient

    /// Cached artifacts by document ID
    private(set) var artifactsByDocument: [String: [Artifact]] = [:]

    /// Loading state per document
    private(set) var loadingDocuments: Set<String> = []

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
        let response = try await client.api.listArtifactTypesApiArtifactsTypesGet()

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get all artifacts in the library.
    func getAllArtifacts(type: String? = nil, limit: Int = 100, offset: Int = 0) async throws -> [Artifact] {
        let response = try await client.api.listAllArtifactsApiArtifactsGet(
            query: .init(artifactType: type, limit: limit, offset: offset),
        )

        switch response {
        case .ok(let okResponse):
            let artifactList = try okResponse.body.json
            logger.info("Fetched \(artifactList.items.count) total artifacts")
            return artifactList.items.map { convertToArtifact($0) }
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw ArtifactServiceError.serverError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw ArtifactServiceError.unexpectedResponse(statusCode)
        }
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

// EntityServiceGenerated lives in this file (instead of its own) because the
// Xcode project's main target uses traditional file references; new .swift
// files would need pbxproj edits. See MEMORY: feedback_swift_file_sync.md.

private let entityServiceLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "EntityServiceGenerated"
)

private let kgCurationServiceLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "KGCurationServiceGenerated"
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
@Observable
// swiftlint:disable:next type_body_length
final class EntityServiceGenerated {
    private let client: FicheroClient

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
            Components.Schemas.FicheroKnowledgeKnowledgeModelsEntityType(rawValue: $0)
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
            Components.Schemas.FicheroKnowledgeKnowledgeModelsEntityType(rawValue: $0)
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

    // MARK: - Claims, entities, registries, and multilingual wiring (#1424)

    func getClaimLink(_ linkId: String) async throws -> Data {
        try await endpointData(path: "/api/claim-links/\(linkId)")
    }

    func updateClaimLink(
        _ linkId: String,
        patch: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claim-links/\(linkId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClaimLink(_ linkId: String) async throws {
        _ = try await endpointData(path: "/api/claim-links/\(linkId)", method: "DELETE")
    }

    func assignClaimTimePeriod(
        claimId: String,
        timePeriodId: String
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claims/assign-time-period",
            method: "POST",
            jsonBody: ["claim_id": claimId, "time_period_id": timePeriodId]
        )
    }

    func batchTransitionClaims(
        claimIds: [String],
        state: String
    ) async throws -> Data {
        try await endpointData(
            path: "/api/claims/batch/transition",
            method: "POST",
            jsonBody: ["claim_ids": claimIds, "state": state]
        )
    }

    func unreviewedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/unreviewed", limit: limit, offset: offset)
    }

    func shortlistedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/shortlisted", limit: limit, offset: offset)
    }

    func curatedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/curated", limit: limit, offset: offset)
    }

    func rejectedClaimsQueue(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await claimsQueue(path: "/api/claims/queues/rejected", limit: limit, offset: offset)
    }

    func resolveClaimSource(claimId: String) async throws -> Data {
        try await endpointData(
            path: "/api/claims/resolve-source",
            method: "POST",
            jsonBody: ["claim_id": claimId]
        )
    }

    func relatedClaims(claimId: String, limit: Int = 10) async throws -> Data {
        try await endpointData(
            path: "/api/claims/\(claimId)/related",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func transitionClaim(_ claimId: String, state: String) async throws -> Data {
        try await endpointData(
            path: "/api/claims/\(claimId)/transition",
            method: "PATCH",
            jsonBody: ["state": state]
        )
    }

    func listClassifications(dimension: String? = nil) async throws -> Data {
        try await endpointData(
            path: "/api/classifications",
            queryItems: dimension.map { [URLQueryItem(name: "dimension", value: $0)] } ?? []
        )
    }

    func createClassification(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/classifications", method: "POST", jsonBody: body)
    }

    func patchClassification(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/classifications/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClassification(_ valueId: String) async throws {
        _ = try await endpointData(path: "/api/classifications/\(valueId)", method: "DELETE")
    }

    func entityAliasMap() async throws -> Data {
        try await endpointData(path: "/api/entities/alias-map")
    }

    func entityClaimCountsData() async throws -> Data {
        try await endpointData(path: "/api/entities/claim-counts")
    }

    func entityDigest(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/entities/digest",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func resolveEntityValue(_ value: String) async throws -> Data {
        let encoded = value.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? value
        return try await endpointData(path: "/api/entities/resolve/\(encoded)")
    }

    func topEntities(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/entities/top",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func addEntityAliases(_ entityId: String, aliases: [String]) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/aliases",
            method: "POST",
            jsonBody: ["aliases": aliases]
        )
    }

    func entityBiography(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/entities/\(entityId)/biography")
    }

    func entityCoOccurrence(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/co-occurrence",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func entityDocuments(_ entityId: String, limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/entities/\(entityId)/documents",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func entityDrillDown(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/entities/\(entityId)/drill-down")
    }

    func multilingualClaims(language: String, limit: Int = 100) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/claims",
            queryItems: [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func detectLanguage(text: String) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/detect",
            method: "POST",
            jsonBody: ["text": text]
        )
    }

    func multilingualEntities(language: String, limit: Int = 100) async throws -> Data {
        try await endpointData(
            path: "/api/multilingual/entities",
            queryItems: [
                URLQueryItem(name: "language", value: language),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func searchMultilingualEntities(query: String, languages: [String] = []) async throws -> Data {
        var body: [String: Any] = ["query": query]
        if !languages.isEmpty {
            body["languages"] = languages
        }
        return try await endpointData(
            path: "/api/multilingual/entities/search",
            method: "POST",
            jsonBody: body
        )
    }

    func normalizeMultilingualText(_ text: String, language: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let language {
            body["language"] = language
        }
        return try await endpointData(
            path: "/api/multilingual/normalize",
            method: "POST",
            jsonBody: body
        )
    }

    func transliterateMultilingualText(_ text: String, language: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let language {
            body["language"] = language
        }
        return try await endpointData(
            path: "/api/multilingual/transliterate",
            method: "POST",
            jsonBody: body
        )
    }

    func listClaimKinds() async throws -> Data {
        try await endpointData(path: "/api/registries/claim-kinds")
    }

    func createClaimKind(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/registries/claim-kinds", method: "POST", jsonBody: body)
    }

    func patchClaimKind(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/registries/claim-kinds/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteClaimKind(_ valueId: String) async throws {
        _ = try await endpointData(path: "/api/registries/claim-kinds/\(valueId)", method: "DELETE")
    }

    func listEpistemicStatuses() async throws -> Data {
        try await endpointData(path: "/api/registries/epistemic-statuses")
    }

    func createEpistemicStatus(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/registries/epistemic-statuses", method: "POST", jsonBody: body)
    }

    func patchEpistemicStatus(_ valueId: String, patch: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/registries/epistemic-statuses/\(valueId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteEpistemicStatus(_ valueId: String) async throws {
        _ = try await endpointData(
            path: "/api/registries/epistemic-statuses/\(valueId)",
            method: "DELETE"
        )
    }

    private func claimsQueue(path: String, limit: Int, offset: Int) async throws -> Data {
        try await endpointData(
            path: path,
            queryItems: [
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "offset", value: "\(offset)")
            ]
        )
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
        let session = RemoteCertificatePinning.configuredSession()
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

    /// Set bibliographic metadata for a document. ⚠️ The backend **replaces**
    /// `source_metadata` wholesale — unspecified keys (including extractor-
    /// emitted fields like canonical BibTeX / identifiers) are DROPPED, not
    /// merged. To preserve them, GET the current metadata and merge client-side
    /// before calling. (#3253: this documents today's behavior so a metadata
    /// editor built on this wrapper doesn't silently destroy fields; the
    /// eventual merge-vs-replace semantics are a pending product decision.)
    /// Pass the full key/value set the bibliography editor supports — title,
    /// authors, year, container_title, etc.
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

    // MARK: - Document workflow provenance (#1434)

    func listDocumentWorkflowRuns(
        documentId: String
    ) async throws -> [Components.Schemas.WorkflowRunProvenanceResponse] {
        let response = try await client.api.getDocumentWorkflowRunsApiDocumentsDocIdWorkflowRunsGet(
            path: .init(docId: documentId),
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

    private func endpointData(
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
        let session = RemoteCertificatePinning.configuredSession()
        let (data, response) = try await session.data(for: request)
        if let http = response as? HTTPURLResponse,
           !(200...299).contains(http.statusCode) {
            throw ServiceError.unexpectedResponse(http.statusCode)
        }
        return data
    }

    private func bibliographyData(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> Data {
        try await endpointData(
            path: path,
            method: method,
            queryItems: queryItems,
            jsonBody: jsonBody
        )
    }

    private func bibliographyText(
        path: String,
        method: String = "GET",
        queryItems: [URLQueryItem] = [],
        jsonBody: [String: Any]? = nil
    ) async throws -> String {
        let data = try await bibliographyData(
            path: path,
            method: method,
            queryItems: queryItems,
            jsonBody: jsonBody
        )
        return String(data: data, encoding: .utf8) ?? ""
    }

    func exportBibliographyBib(documentIds: [String]) async throws -> String {
        try await bibliographyText(
            path: "/api/bibliography/export.bib",
            method: "POST",
            jsonBody: ["document_ids": documentIds]
        )
    }

    func importBibliography(text: String, format: String? = nil) async throws -> Data {
        var body: [String: Any] = ["text": text]
        if let format {
            body["format"] = format
        }
        return try await bibliographyData(
            path: "/api/bibliography/import",
            method: "POST",
            jsonBody: body
        )
    }

    func resolveBibliography(
        doi: String? = nil,
        isbn: String? = nil,
        documentId: String? = nil
    ) async throws -> Data {
        var body: [String: Any] = [:]
        if let doi {
            body["doi"] = doi
        }
        if let isbn {
            body["isbn"] = isbn
        }
        let queryItems = documentId.map {
            [URLQueryItem(name: "document_id", value: $0)]
        } ?? []
        return try await bibliographyData(
            path: "/api/bibliography/resolve",
            method: "POST",
            queryItems: queryItems,
            jsonBody: body
        )
    }

    func renderDocumentCitation(
        documentId: String,
        style: String = "bibtex"
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/citations/document/\(documentId)",
            queryItems: [URLQueryItem(name: "style", value: style)]
        )
    }

    func documentBibtexCitation(documentId: String) async throws -> String {
        try await bibliographyText(path: "/api/citations/document/\(documentId).bib")
    }

    func exportCitationsBibtex(documentIds: [String]) async throws -> String {
        try await bibliographyText(
            path: "/api/citations/export",
            queryItems: documentIds.map {
                URLQueryItem(name: "document_ids", value: $0)
            }
        )
    }

    func listReferences(limit: Int = 100, offset: Int = 0) async throws -> Data {
        try await bibliographyData(
            path: "/api/references",
            queryItems: [
                URLQueryItem(name: "limit", value: "\(limit)"),
                URLQueryItem(name: "offset", value: "\(offset)")
            ]
        )
    }

    func getReference(_ referenceId: String) async throws -> Data {
        try await bibliographyData(path: "/api/references/\(referenceId)")
    }

    func patchReference(
        _ referenceId: String,
        patch: [String: Any]
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/references/\(referenceId)",
            method: "PATCH",
            jsonBody: patch
        )
    }

    func deleteReference(_ referenceId: String) async throws {
        _ = try await bibliographyData(
            path: "/api/references/\(referenceId)",
            method: "DELETE"
        )
    }

    func listSources() async throws -> Data {
        try await bibliographyData(path: "/api/sources")
    }

    func upsertSource(
        title: String,
        filePath: String,
        id: String? = nil,
        metadata: [String: Any] = [:]
    ) async throws -> Data {
        var body: [String: Any] = [
            "title": title,
            "file_path": filePath,
            "document_type": "source",
            "metadata": metadata
        ]
        if let id {
            body["id"] = id
        }
        return try await bibliographyData(
            path: "/api/sources",
            method: "POST",
            jsonBody: body
        )
    }

    func getSource(_ sourceId: String) async throws -> Data {
        try await bibliographyData(path: "/api/sources/\(sourceId)")
    }

    func updateSource(
        _ sourceId: String,
        title: String,
        filePath: String,
        metadata: [String: Any] = [:]
    ) async throws -> Data {
        try await bibliographyData(
            path: "/api/sources/\(sourceId)",
            method: "PUT",
            jsonBody: [
                "title": title,
                "file_path": filePath,
                "document_type": "source",
                "metadata": metadata
            ]
        )
    }

    func deleteSource(_ sourceId: String) async throws {
        _ = try await bibliographyData(
            path: "/api/sources/\(sourceId)",
            method: "DELETE"
        )
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

    @discardableResult
    func assignDocumentPrototype(
        documentId: String,
        prototypeKey: String
    ) async throws -> Components.Schemas.PrototypeAssignResponse {
        let response = try await client.api.assignDocumentPrototypeApiDocumentsDocIdPrototypePut(
            path: .init(docId: documentId),
            body: .json(.init(prototypeKey: prototypeKey))
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

    // MARK: - Hermeneutics interpretations per document

    /// Fetch interpretations for a document through the generated OpenAPI client.
    func listDocumentInterpretations(
        documentId: String
    ) async throws -> [Components.Schemas.Interpretation] {
        let response = try await client.api.listInterpretationsApiHermeneuticsInterpretationsGet(
            query: .init(documentId: documentId)
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

    /// GET /api/hermeneutics/frameworks through the generated OpenAPI client.
    func listFrameworks() async throws -> [Components.Schemas.InterpretiveFramework] {
        let response = try await client.api.listFrameworksApiHermeneuticsFrameworksGet(query: .init())
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

    /// PATCH /api/hermeneutics/interpretations/{id} — update text and/or confidence.
    @discardableResult
    func updateInterpretation(
        interpretationId: String,
        interpretationText: String,
        confidence: Double
    ) async throws -> Components.Schemas.Interpretation {
        let response = try await client.api.updateInterpretationApiHermeneuticsInterpretationsInterpretationIdPatch(
            path: .init(interpretationId: interpretationId),
            body: .json(.init(interpretationText: interpretationText, confidence: confidence))
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

    /// POST /api/hermeneutics/interpretations — create a human interpretation on a document.
    @discardableResult
    func createInterpretation(
        frameworkId: String,
        documentId: String,
        act: Components.Schemas.InterpretiveActType,
        interpretationText: String,
        confidence: Double = 0.8
    ) async throws -> Components.Schemas.Interpretation {
        let response = try await client.api.createInterpretationApiHermeneuticsInterpretationsPost(
            body: .json(.init(
                frameworkId: frameworkId,
                documentId: documentId,
                interpretationText: interpretationText,
                act: act,
                confidence: confidence,
                createdBy: "human"
            ))
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

    // MARK: - Knowledge Graph endpoint wiring (#1422)

    func generateKGEntityBiography(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/entities/\(entityId)/bio", method: "POST")
    }

    func kgEntityCurationCandidates(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/entity-curation/candidates",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    /// Semantic (embedding) entity search — returns entities similar to `q`
    /// with a `similarity_score`, catching name variants + cross-script
    /// duplicates that structural co-occurrence misses (#3317). `entityType`
    /// constrains to the same kind.
    func searchEntitiesSemantic(
        query: String,
        entityType: String? = nil,
        limit: Int = 20
    ) async throws -> Data {
        var items = [
            URLQueryItem(name: "q", value: query),
            URLQueryItem(name: "limit", value: "\(limit)")
        ]
        if let entityType {
            items.append(URLQueryItem(name: "entity_type", value: entityType))
        }
        return try await endpointData(
            path: "/api/kg/entity-curation/semantic",
            queryItems: items
        )
    }

    func kgGraphCentrality(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/centrality",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphClustering() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/clustering")
    }

    func kgGraphCommunities() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/communities")
    }

    func kgGraphComponents() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/components")
    }

    func kgGraphCooccurrence(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/cooccurrence/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphMetrics() async throws -> Data {
        try await endpointData(path: "/api/kg/graph/metrics")
    }

    func kgGraphPagerank(limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/pagerank",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphPath(from sourceEntityId: String, to targetEntityId: String) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/path",
            queryItems: [
                URLQueryItem(name: "source_entity_id", value: sourceEntityId),
                URLQueryItem(name: "target_entity_id", value: targetEntityId)
            ]
        )
    }

    func kgGraphSimilar(_ entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/similar/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgGraphTraverse(_ entityId: String, depth: Int = 2) async throws -> Data {
        try await endpointData(
            path: "/api/kg/graph/traverse/\(entityId)",
            queryItems: [URLQueryItem(name: "depth", value: "\(depth)")]
        )
    }

    func kgGraphTriangles(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/graph/triangles/\(entityId)")
    }

    func upsertKGInclusion(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/inclusion", method: "POST", jsonBody: body)
    }

    func listKGInclusions() async throws -> Data {
        try await endpointData(path: "/api/kg/inclusion")
    }

    func kgMutations(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/mutations",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func undoKGMutation(_ mutationId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/mutations/\(mutationId)/undo", method: "POST")
    }

    func applyKGPredictionRun(_ runId: String, body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/predictions/\(runId)/apply", method: "POST", jsonBody: body)
    }

    func deletePyKEENModel(_ modelId: String) async throws {
        _ = try await endpointData(path: "/api/kg/pykeen/models/\(modelId)", method: "DELETE")
    }

    func pyKEENPredictions(entityId: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/pykeen/predict/\(entityId)",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func storedPyKEENPredictions() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/stored")
    }

    func storedPyKEENPrediction(_ predictionId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/stored/\(predictionId)")
    }

    func verifyStoredPyKEENPrediction(_ predictionId: String, body: [String: Any]) async throws -> Data {
        try await endpointData(
            path: "/api/kg/pykeen/stored/\(predictionId)/verify",
            method: "PATCH",
            jsonBody: body
        )
    }

    func trainPyKEEN(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/train", method: "POST", jsonBody: body)
    }

    func pyKEENTrainingJobs() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/training-jobs")
    }

    func pyKEENTrainingJob(_ modelId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/training-jobs/\(modelId)")
    }

    // PyKEEN prediction review queue (#3677 store-layer coverage). Routes the
    // `/api/kg/pykeen/reviews` endpoints through the service layer like the rest
    // of the PyKEEN surface, so views read them via the store, not the raw client.
    func pyKEENReviews() async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews")
    }

    func createPyKEENReview(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews", method: "POST", jsonBody: body)
    }

    func updatePyKEENReview(_ reviewId: String, body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/pykeen/reviews/\(reviewId)", method: "PATCH", jsonBody: body)
    }

    // Content-representations Reader surface (#3677 store-layer coverage). The
    // Reader's derived-content/knowledge layer reads a document's representations
    // and their revision history through the service layer, not the raw client —
    // same endpointData path the rest of the knowledge surface uses.
    func contentRepresentations(documentId: String) async throws -> Data {
        try await endpointData(path: "/api/content-representations/document/\(documentId)")
    }

    func contentRepresentationRevisions(_ representationId: String) async throws -> Data {
        try await endpointData(path: "/api/content-representations/\(representationId)/revisions")
    }

    func createContentRepresentationRevision(
        _ representationId: String,
        body: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/content-representations/\(representationId)/revisions",
            method: "POST",
            jsonBody: body
        )
    }

    // Multi-user workspace-membership admin (#3561 / #3677 store-layer coverage).
    // PATCHes a chat workspace's member set through the service layer so the
    // multi-user admin surface reaches it via the store, not the raw client.
    func updateChatWorkspaceMembers(
        _ workspaceId: String,
        body: [String: Any]
    ) async throws -> Data {
        try await endpointData(
            path: "/api/chat/workspaces/\(workspaceId)/members",
            method: "PATCH",
            jsonBody: body
        )
    }

    func rebuildKnowledgeGraph(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/rebuild", method: "POST", jsonBody: body)
    }

    func renderKGParagraph(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/render/paragraph", method: "POST", jsonBody: body)
    }

    func resetKnowledgeGraph(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/reset", method: "POST", jsonBody: body)
    }

    func kgReviewGraphCandidates(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/review/graph-candidates",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgReviewLabels() async throws -> Data {
        try await endpointData(path: "/api/kg/review/labels")
    }

    func kgReviewPairs(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/review/pairs",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func queueKGReviewPair(_ body: [String: Any]) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs", method: "POST", jsonBody: body)
    }

    func acceptKGReviewPair(_ pairId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs/\(pairId)/accept", method: "POST")
    }

    func rejectKGReviewPair(_ pairId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/review/pairs/\(pairId)/reject", method: "POST")
    }

    func searchKnowledgeGraph(_ query: String, limit: Int = 25) async throws -> Data {
        try await endpointData(
            path: "/api/kg/search",
            queryItems: [
                URLQueryItem(name: "q", value: query),
                URLQueryItem(name: "limit", value: "\(limit)")
            ]
        )
    }

    func runKnowledgeGraphSPARQL(_ query: String) async throws -> Data {
        try await endpointData(
            path: "/api/kg/sparql",
            method: "POST",
            jsonBody: ["query": query]
        )
    }

    func kgTriangulation(limit: Int = 50) async throws -> Data {
        try await endpointData(
            path: "/api/kg/triangulation",
            queryItems: [URLQueryItem(name: "limit", value: "\(limit)")]
        )
    }

    func kgEntityTriangulation(_ entityId: String) async throws -> Data {
        try await endpointData(path: "/api/kg/triangulation/entity/\(entityId)")
    }

    func recomputeKGTriangulation(_ body: [String: Any] = [:]) async throws -> Data {
        try await endpointData(path: "/api/kg/triangulation/recompute", method: "POST", jsonBody: body)
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

// Typed wrappers for `/api/kg/curation-rules/*`.

// swiftlint:disable type_body_length
@MainActor
@Observable
final class KGCurationServiceGenerated {
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
// swiftlint:enable type_body_length
